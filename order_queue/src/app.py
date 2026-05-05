import os
import sys
import threading
from collections import deque
from concurrent import futures

import grpc
import logging

from utils.logging import setup_logging, set_request_id_from_context

FILE = __file__ if "__file__" in globals() else os.getenv("PYTHONFILE", "")
order_queue_grpc_path = os.path.abspath(os.path.join(FILE, "../../../utils/pb/order_queue"))
sys.path.insert(0, order_queue_grpc_path)

import order_queue_pb2 as order_queue
import order_queue_pb2_grpc as order_queue_grpc

setup_logging()
logger = logging.getLogger(__name__)


class OrderQueueService(order_queue_grpc.OrderQueueServiceServicer):
    def __init__(self):
        self.queue = deque()
        self.condition = threading.Condition()

    def Enqueue(self, request, context):
        set_request_id_from_context(context)
        order_items = [
            order_queue.OrderItem(title=item.title, quantity=item.quantity)
            for item in request.items
        ]
        with self.condition:
            self.queue.append((request.order_id, order_items))
            queue_size = len(self.queue)
            self.condition.notify()

        logger.info(
            "Enqueued order %s with %s item(s). Queue size is now %s.",
            request.order_id,
            len(order_items),
            queue_size,
        )
        return order_queue.EnqueueResponse(is_ok=True)

    def Dequeue(self, request, context):
        set_request_id_from_context(context)
        with self.condition:
            while not self.queue:
                self.condition.wait(timeout=1)
                if not self.queue:
                    return order_queue.DequeueResponse(is_ok=False, order_id="")
            order_id, order_items = self.queue.popleft()
            queue_size = len(self.queue)

        logger.info(
            "Executor %s dequeued order %s. Queue size is now %s.",
            request.executor_id,
            order_id,
            queue_size,
        )
        return order_queue.DequeueResponse(
            is_ok=True,
            order_id=order_id,
            items=order_items,
        )


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    order_queue_grpc.add_OrderQueueServiceServicer_to_server(OrderQueueService(), server)
    port = "50054"
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info("OrderQueue server started on port %s.", port)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
