import os
import sys
import threading
from concurrent import futures

import grpc
import logging

from utils.logging import setup_logging, set_request_id_from_context
from utils.vector_clock import VectorClock, vector_clock_from_metadata

# Import the generated gRPC code
FILE = __file__ if "__file__" in globals() else os.getenv("PYTHONFILE", "")
sys.path.insert(0, os.path.join(os.path.dirname(FILE), "../../utils/pb/suggestions"))

import suggestions_pb2
import suggestions_pb2_grpc

setup_logging()
logger = logging.getLogger(__name__)

# Static book catalog
BOOK_CATALOG = [
    {"book_id": "1", "title": "The Great Gatsby", "author": "F. Scott Fitzgerald"},
    {"book_id": "2", "title": "To Kill a Mockingbird", "author": "Harper Lee"},
    {"book_id": "3", "title": "The Alchemist", "author": "Paulo Coelho"},
    {"book_id": "4", "title": "Sapiens", "author": "Yuval Noah Harari"},
    {"book_id": "5", "title": "The Road", "author": "Cormac McCarthy"},
    {"book_id": "6", "title": "Brave New World", "author": "Aldous Huxley"},
    {"book_id": "7", "title": "The Subtle Art of Not Giving a F*ck", "author": "Mark Manson"},
    {"book_id": "8", "title": "Atomic Habits", "author": "James Clear"},
    {"book_id": "9", "title": "The Power of Now", "author": "Eckhart Tolle"},
    {"book_id": "10", "title": "Thinking, Fast and Slow", "author": "Daniel Kahneman"},
]


class SuggestionsServicer(suggestions_pb2_grpc.SuggestionsServiceServicer):
    def __init__(self):
        self.node_id = "suggestions"
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
            "Cached order %s during suggestions init. Clock: %s",
            request.order_id,
            init_clock,
        )
        return suggestions_pb2.InitOrderResponse(is_ok=True, errors=[])

    def GetSuggestions(self, request, context):
        set_request_id_from_context(context)
        entry = self._get_order(request.order_id)
        if entry is None:
            logger.info(
                "Skipped suggestions for order %s because the order was not initialized. Clock: %s",
                request.order_id,
                {},
            )
            return suggestions_pb2.SuggestionResponse(suggestions=[], vector_clock={})

        base_snapshot = entry["clock"].receive_event(dict(request.vector_clock))
        data = entry["data"]
        logger.info(
            "Received pipeline clock for order %s and merged incoming history. Clock: %s",
            request.order_id,
            base_snapshot,
        )

        ordered_titles = {item.lower() for item in data.ordered_items}
        available = [
            book for book in BOOK_CATALOG if book["title"].lower() not in ordered_titles
        ]
        selected = available[:3]

        event_f_clock = VectorClock(self.node_id, base_snapshot)
        event_f_snapshot = event_f_clock.local_event()
        logger.info(
            "Completed event f for order %s: generated suggestions %s. Clock: %s",
            request.order_id,
            [book["title"] for book in selected],
            event_f_snapshot,
        )

        final_snapshot = VectorClock.merge_clocks(base_snapshot, event_f_snapshot)
        with self.orders_lock:
            entry["clock"] = VectorClock(self.node_id, final_snapshot)
        logger.info(
            "Suggestions finished for order %s. Suggested titles: %s. Clock: %s",
            request.order_id,
            [book["title"] for book in selected],
            final_snapshot,
        )

        return suggestions_pb2.SuggestionResponse(
            suggestions=[
                suggestions_pb2.Book(
                    book_id=book["book_id"],
                    title=book["title"],
                    author=book["author"],
                )
                for book in selected
            ],
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


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    suggestions_pb2_grpc.add_SuggestionsServiceServicer_to_server(
        SuggestionsServicer(), server
    )
    port = "50053"
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info("Suggestions server started on port %s.", port)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
