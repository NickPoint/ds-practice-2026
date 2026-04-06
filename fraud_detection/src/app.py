import os
import sys
import threading
from concurrent import futures

import grpc
import logging

from utils.logging import setup_logging, set_request_id_from_context
from utils.vector_clock import VectorClock, vector_clock_from_metadata

# This set of lines are needed to import the gRPC stubs.
# The path of the stubs is relative to the current file, or absolute inside the container.
# Change these lines only if strictly needed.
FILE = __file__ if "__file__" in globals() else os.getenv("PYTHONFILE", "")
fraud_detection_grpc_path = os.path.abspath(os.path.join(FILE, "../../../utils/pb/fraud_detection"))
sys.path.insert(0, fraud_detection_grpc_path)
import fraud_detection_pb2 as fraud_detection
import fraud_detection_pb2_grpc as fraud_detection_grpc

setup_logging()
logger = logging.getLogger(__name__)


class FraudDetectionService(fraud_detection_grpc.FraudDetectionServiceServicer):
    def __init__(self):
        self.node_id = "fraud"
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
            "fraud:init order_id=%s result=CACHED vc=%s",
            request.order_id,
            init_clock,
        )
        return fraud_detection.InitOrderResponse(is_ok=True, errors=[])

    def CheckFraud(self, request, context):
        set_request_id_from_context(context)
        entry = self._get_order(request.order_id)
        if entry is None:
            errors = ["requested_order_is_not_initialized"]
            logger.info(
                "fraud:run order_id=%s result=INVALID reasons=%s vc=%s",
                request.order_id,
                errors,
                {},
            )
            return fraud_detection.FraudResponse(
                is_fraud=True,
                risk_score=100,
                reasons=errors,
                vector_clock={},
            )

        base_snapshot = entry["clock"].receive_event(dict(request.vector_clock))
        logger.info(
            "fraud:run order_id=%s event=receive result=MERGED vc=%s",
            request.order_id,
            base_snapshot,
        )

        data = entry["data"]
        score = 0
        reasons = []

        event_d_clock = VectorClock(self.node_id, base_snapshot)
        score, reasons = self.check_items(data, score, reasons)
        score, reasons = self.check_address(data, score, reasons)
        score, reasons = self.check_terms(data, score, reasons)
        event_d_snapshot = event_d_clock.local_event()
        logger.info(
            "fraud:event=d order_id=%s result=score=%s reasons=%s vc=%s",
            request.order_id,
            score,
            reasons or ["none"],
            event_d_snapshot,
        )

        merge_d_snapshot = VectorClock.merge_clocks(base_snapshot, event_d_snapshot)
        event_e_clock = VectorClock(self.node_id, merge_d_snapshot)
        score, reasons = self.check_card(data, score, reasons)
        event_e_snapshot = event_e_clock.local_event()
        logger.info(
            "fraud:event=e order_id=%s result=score=%s reasons=%s merged_from_d=%s vc=%s",
            request.order_id,
            score,
            reasons or ["none"],
            merge_d_snapshot,
            event_e_snapshot,
        )

        final_snapshot = VectorClock.merge_clocks(base_snapshot, event_d_snapshot, event_e_snapshot)
        with self.orders_lock:
            entry["clock"] = VectorClock(self.node_id, final_snapshot)
        decision = score >= 70

        logger.info(
            "fraud:run order_id=%s result=%s score=%s reasons=%s vc=%s",
            request.order_id,
            "FRAUD" if decision else "LEGIT",
            score,
            reasons or ["none"],
            final_snapshot,
        )

        return fraud_detection.FraudResponse(
            is_fraud=decision,
            risk_score=score,
            reasons=reasons,
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

    def check_card(self, data, score, reasons):
        card = data.credit_card

        if not card.number:
            score += 40
            reasons.append("missing_card_number")

        if not card.cvv:
            score += 30
            reasons.append("missing_cvv")

        if card.number and len(card.number) < 12:
            score += 20
            reasons.append("invalid_card_length")

        return score, reasons

    def check_items(self, data, score, reasons):
        total_qty = sum(item.quantity for item in data.items)

        if total_qty > 10:
            score += 20
            reasons.append("high_quantity")

        if total_qty == 0:
            score += 30
            reasons.append("empty_cart")

        return score, reasons

    def check_device(self, data, score, reasons):
        known_os = ["iOS", "Android", "Windows", "MacOS", "Linux"]

        if data.device.os and data.device.os not in known_os:
            score += 15
            reasons.append("unknown_os")

        if not data.browser.name:
            score += 10
            reasons.append("missing_browser")

        return score, reasons

    def check_address(self, data, score, reasons):
        if not data.billing_address.country:
            score += 10
            reasons.append("missing_country")

        return score, reasons

    def check_terms(self, data, score, reasons):
        if not data.terms_accepted:
            score += 50
            reasons.append("terms_not_accepted")

        return score, reasons


def serve():
    server = grpc.server(futures.ThreadPoolExecutor())
    fraud_detection_grpc.add_FraudDetectionServiceServicer_to_server(
        FraudDetectionService(), server
    )
    port = "50051"
    server.add_insecure_port("[::]:" + port)
    server.start()
    logger.debug("Server started. Listening on port 50051.")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
