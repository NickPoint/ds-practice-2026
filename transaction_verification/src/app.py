import os
import re
import sys
import threading
from concurrent import futures
from datetime import datetime

import grpc
import logging

from utils.logging import setup_logging, set_request_id_from_context
from utils.vector_clock import VectorClock, vector_clock_from_metadata

# This set of lines are needed to import the gRPC stubs.
# The path of the stubs is relative to the current file, or absolute inside the container.
# Change these lines only if strictly needed.
FILE = __file__ if "__file__" in globals() else os.getenv("PYTHONFILE", "")
transaction_verification_grpc_path = os.path.abspath(
    os.path.join(FILE, "../../../utils/pb/transaction_verification")
)
sys.path.insert(0, transaction_verification_grpc_path)

import transaction_verification_pb2 as transaction_verification
import transaction_verification_pb2_grpc as transaction_verification_grpc

setup_logging()
logger = logging.getLogger(__name__)


class TransactionVerificationService(
    transaction_verification_grpc.TransactionVerificationServiceServicer
):
    def __init__(self):
        self.node_id = "txn"
        self.orders = {}
        self.orders_lock = threading.Lock()

    def InitOrder(self, request, context):
        set_request_id_from_context(context)
        incoming_clock = self._metadata_vector_clock(context)

        with self.orders_lock:
            order_clock = VectorClock(self.node_id)
            init_clock = order_clock.receive_event(incoming_clock)
            self.orders[request.order_id] = {
                "data": request.order_data,
                "clock": order_clock,
            }

        logger.info(
            "Cached order %s during transaction verification init. Clock: %s",
            request.order_id,
            init_clock,
        )
        return transaction_verification.InitOrderResponse(is_ok=True, errors=[])

    def ExecuteTransaction(self, request, context):
        set_request_id_from_context(context)
        entry = self._get_order(request.order_id)
        if entry is None:
            errors = ["requested_order_is_not_initialized"]
            logger.info(
                "Rejected transaction verification for order %s because the order was not initialized. Errors: %s. Clock: %s",
                request.order_id,
                errors,
                {},
            )
            return transaction_verification.TransactionRunResponse(
                is_valid=False,
                errors=errors,
                vector_clock={},
            )

        base_snapshot = entry["clock"].receive_event(dict(request.vector_clock))
        logger.info(
            "Received pipeline clock for order %s and merged incoming history. Clock: %s",
            request.order_id,
            base_snapshot,
        )

        data = entry["data"]
        branch_results = {}
        branch_errors = {}

        def validate_items_branch():
            items_validation_clock = VectorClock(self.node_id, base_snapshot)
            errors = []
            self.validate_items(data.items, errors)
            snapshot = items_validation_clock.local_event()
            branch_results["a"] = snapshot
            branch_errors["a"] = errors
            logger.info(
                "Completed event a for order %s: item validation is %s. Errors: %s. Clock: %s",
                request.order_id,
                "VALID" if not errors else "INVALID",
                errors or ["none"],
                snapshot,
            )

        def validate_user_data_branch():
            user_data_validation_clock = VectorClock(self.node_id, base_snapshot)
            errors = []
            self.validate_user(data.user, errors)
            self.validate_address(data.billing_address, errors)
            self.validate_shipping_method(data.shipping_method, errors)
            self.validate_terms(data.terms_accepted, errors)
            snapshot = user_data_validation_clock.local_event()
            branch_results["b"] = snapshot
            branch_errors["b"] = errors
            logger.info(
                "Completed event b for order %s: user data validation is %s. Errors: %s. Clock: %s",
                request.order_id,
                "VALID" if not errors else "INVALID",
                errors or ["none"],
                snapshot,
            )

        items_validation_thread = threading.Thread(
            target=validate_items_branch,
            name="txn-items",
        )
        user_data_validation_thread = threading.Thread(
            target=validate_user_data_branch,
            name="txn-user-data",
        )
        items_validation_thread.start()
        user_data_validation_thread.start()
        items_validation_thread.join()

        merged_items_dependency_clock = VectorClock.merge_clocks(base_snapshot, branch_results["a"])
        card_validation_clock = VectorClock(self.node_id, merged_items_dependency_clock)
        card_validation_errors = []
        self.validate_card(data.credit_card, card_validation_errors)
        card_validation_snapshot = card_validation_clock.local_event()
        branch_results["c"] = card_validation_snapshot
        branch_errors["c"] = card_validation_errors
        logger.info(
            "Completed event c for order %s: card format validation is %s after merging event a clock %s. Clock: %s",
            request.order_id,
            "VALID" if not card_validation_errors else "INVALID",
            merged_items_dependency_clock,
            card_validation_snapshot,
        )

        user_data_validation_thread.join()

        final_snapshot = VectorClock.merge_clocks(
            base_snapshot,
            branch_results["a"],
            branch_results["b"],
            branch_results["c"],
        )
        with self.orders_lock:
            entry["clock"] = VectorClock(self.node_id, final_snapshot)
        all_errors = branch_errors["a"] + branch_errors["b"] + branch_errors["c"]
        is_valid = not all_errors

        logger.info(
            "Transaction verification finished for order %s with result %s. Errors: %s. Clock: %s",
            request.order_id,
            "VALID" if is_valid else "INVALID",
            all_errors or ["none"],
            final_snapshot,
        )
        return transaction_verification.TransactionRunResponse(
            is_valid=is_valid,
            errors=all_errors,
            vector_clock=final_snapshot,
        )

    def _get_order(self, order_id):
        with self.orders_lock:
            return self.orders.get(order_id)

    def _metadata_vector_clock(self, context):
        metadata = {}
        for key, value in context.invocation_metadata():
            text_key = key.decode("utf-8") if isinstance(key, bytes) else key
            text_value = value.decode("utf-8") if isinstance(value, bytes) else value
            metadata[text_key.lower()] = text_value
        return vector_clock_from_metadata(metadata)

    def validate_user(self, user, errors):
        if not user.name.strip():
            errors.append("missing_user_name")

        if not user.contact.strip():
            errors.append("missing_user_contact")
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", user.contact.strip()):
            errors.append("invalid_user_contact")

    def validate_items(self, items, errors):
        if len(items) == 0:
            errors.append("empty_items")
            return

        for item in items:
            if not item.name.strip():
                errors.append("missing_item_name")
            if item.quantity <= 0:
                errors.append("invalid_item_quantity")

    def validate_card(self, card, errors):
        number = card.number.replace(" ", "").replace("-", "")
        exp = card.expiration_date.strip()
        cvv = card.cvv.strip()

        if not number:
            errors.append("missing_card_number")
        elif not number.isdigit() or len(number) < 13 or len(number) > 19:
            errors.append("invalid_card_number")

        if not exp:
            errors.append("missing_expiration_date")
        elif not re.fullmatch(r"(0[1-9]|1[0-2])/\d{2}", exp):
            errors.append("invalid_expiration_date")
        elif self.is_expired(exp):
            errors.append("card_expired")

        if not cvv:
            errors.append("missing_cvv")
        elif not re.fullmatch(r"\d{3,4}", cvv):
            errors.append("invalid_cvv")

    def validate_address(self, address, errors):
        if not address.street.strip():
            errors.append("missing_billing_street")
        if not address.city.strip():
            errors.append("missing_billing_city")
        if not address.state.strip():
            errors.append("missing_billing_state")
        if not address.zip.strip():
            errors.append("missing_billing_zip")
        if not address.country.strip():
            errors.append("missing_billing_country")

    def validate_shipping_method(self, shipping_method, errors):
        allowed = {"Standard", "Express"}

        if not shipping_method.strip():
            errors.append("missing_shipping_method")
        elif shipping_method not in allowed:
            errors.append("invalid_shipping_method")

    def validate_terms(self, terms_accepted, errors):
        if not terms_accepted:
            errors.append("terms_not_accepted")

    def is_expired(self, expiration_date):
        month_str, year_str = expiration_date.split("/")
        month = int(month_str)
        year = 2000 + int(year_str)

        now = datetime.utcnow()
        return year < now.year or (year == now.year and month < now.month)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor())
    transaction_verification_grpc.add_TransactionVerificationServiceServicer_to_server(
        TransactionVerificationService(),
        server,
    )
    port = "50052"
    server.add_insecure_port("[::]:" + port)
    server.start()
    logger.debug("TransactionVerification server started on port 50052.")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
