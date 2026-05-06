import os
import json
import sys
import time
import random
from concurrent import futures

import grpc
import logging

from utils.logging import setup_logging, set_request_id_from_context

# This set of lines are needed to import the gRPC stubs.
# The path of the stubs is relative to the current file, or absolute inside the container.
# Change these lines only if strictly needed.
FILE = __file__ if "__file__" in globals() else os.getenv("PYTHONFILE", "")
payment_grpc_path = os.path.abspath(
    os.path.join(FILE, "../../../utils/pb/payment")
)
sys.path.insert(0, payment_grpc_path)

import payment_pb2 as payment
import payment_pb2_grpc as payment_grpc

setup_logging()
logger = logging.getLogger(__name__)


class PaymentService(
    payment_grpc.PaymentServiceServicer
):
    def __init__(self):
        self.prepared_log_path = os.getenv("PAYMENT_PREPARED_LOG_PATH", "/tmp/payment_prepared.json")
        self._prepared_orders = set()
        #bonus failure test
        self.commit_sleep_seconds = float(os.getenv("PAYMENT_COMMIT_SLEEP_SECONDS", "10.0"))
        self.commit_sleep_probability = float(os.getenv("PAYMENT_COMMIT_SLEEP_PROBABILITY", "0.5"))
        self._load_prepared_from_disk()

    def Prepare(self, request, context):
        set_request_id_from_context(context)
        if not request.order_id:
            return payment.PrepareResponse(is_ok=False, errors=["missing_order_id"])

        #prepare always returns prepareOK.
        self._prepared_orders.add(request.order_id)
        self._persist_prepared_to_disk()

        return payment.PrepareResponse(is_ok=True)

    def Commit(self, request, context):
        set_request_id_from_context(context)
        if not request.order_id:
            return payment.CommitResponse(is_ok=False, errors=["missing_order_id"])

        # bonus point: artificial failure: payment falls asleep and not able to commit sometimes
        if random.random() < self.commit_sleep_probability:
            logger.warning(
                "Injected Commit sleep for order %s: sleeping %ss.",
                request.order_id,
                self.commit_sleep_seconds,
            )
            time.sleep(self.commit_sleep_seconds)

        # Missing prepare is treated as idempotent success.
        self._prepared_orders.discard(request.order_id)
        self._persist_prepared_to_disk()
        logger.info("Payment committed for order %s. This is idempotent so second commit does nothing.", request.order_id)
        return payment.CommitResponse(is_ok=True)
    
    def Abort(self, request, context):
        set_request_id_from_context(context)
        if not request.order_id:
            return payment.AbortResponse(is_ok=False, errors=["missing_order_id"])

        self._prepared_orders.discard(request.order_id)
        self._persist_prepared_to_disk()
        logger.info("Payment aborted for order %s.", request.order_id)
        return payment.AbortResponse(is_ok=True)

    def _load_prepared_from_disk(self):
        try:
            with open(self.prepared_log_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, list):
                self._prepared_orders = set(map(str, raw))
                logger.info("Recovered %s prepared payment(s) from disk.", len(self._prepared_orders))
        except FileNotFoundError:
            return
        except Exception:
            logger.exception("Failed to load payment prepared log %s.", self.prepared_log_path)

    def _persist_prepared_to_disk(self):
        tmp_path = f"{self.prepared_log_path}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(sorted(self._prepared_orders), f)
            os.replace(tmp_path, self.prepared_log_path)
        except Exception:
            logger.exception("Failed to persist payment prepared log %s.", self.prepared_log_path)
    

def serve():
    server = grpc.server(futures.ThreadPoolExecutor())
    payment_grpc.add_PaymentServiceServicer_to_server(
        PaymentService(),
        server,
    )
    port = os.getenv("PAYMENT_PORT", "50060")
    server.add_insecure_port("[::]:" + port)
    server.start()
    logger.info("Payment server started on port %s.", port)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
