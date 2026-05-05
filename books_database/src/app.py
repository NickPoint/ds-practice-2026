import json
import os
import sys
import threading
from concurrent import futures

import grpc
import logging

from utils.logging import setup_logging, set_request_id_from_context

FILE = __file__ if "__file__" in globals() else os.getenv("PYTHONFILE", "")
books_database_grpc_path = os.path.abspath(
    os.path.join(FILE, "../../../utils/pb/books_database")
)
sys.path.insert(0, books_database_grpc_path)

import books_database_pb2 as books_database
import books_database_pb2_grpc as books_database_grpc

setup_logging()
logger = logging.getLogger(__name__)

DEFAULT_STOCKS = {
    "Book A": 10,
    "Book B": 10,
}


class BooksDatabaseService(books_database_grpc.BooksDatabaseServicer):
    def __init__(self):
        self.role = os.getenv("ROLE", "head")
        self.listen_port = os.getenv("DATABASE_PORT", "50057")
        self.listen_address = os.getenv("DATABASE_LISTEN_ADDRESS", "0.0.0.0")
        self.head_address = os.getenv("HEAD_ADDRESS", "books_database_1:50057")
        self.tail_address = os.getenv("TAIL_ADDRESS", "books_database_3:50057")
        self.next_address = self._address_from_host(os.getenv("NEXT_HOST", ""))

        self.store = self._load_initial_store()
        self.store_lock = threading.Lock()
        self.write_lock = threading.Lock()

    def Read(self, request, context):
        set_request_id_from_context(context)
        if self.role != "tail":
            return self._read_from_tail(request)

        with self.store_lock:
            stock = self.store.get(request.title, 0)

        logger.info("Read stock for %s from tail: %s.", request.title, stock)
        return books_database.ReadResponse(stock=stock)

    def Write(self, request, context):
        set_request_id_from_context(context)
        if request.new_stock < 0:
            return books_database.WriteResponse(
                success=False,
                error="stock_cannot_be_negative",
            )

        if self.role != "head":
            return self._write_to_head(request.title, request.new_stock)

        with self.write_lock:
            return self._commit_write(request.title, request.new_stock)

    def ReserveStock(self, request, context):
        set_request_id_from_context(context)
        if request.quantity <= 0:
            return books_database.ReserveStockResponse(
                success=False,
                remaining_stock=0,
                error="quantity_must_be_positive",
            )

        if self.role != "head":
            return self._reserve_at_head(request.title, request.quantity)

        with self.write_lock:
            with self.store_lock:
                current_stock = self.store.get(request.title, 0)

            if current_stock < request.quantity:
                logger.info(
                    "Rejected reservation for %s: requested %s, available %s.",
                    request.title,
                    request.quantity,
                    current_stock,
                )
                return books_database.ReserveStockResponse(
                    success=False,
                    remaining_stock=current_stock,
                    error="insufficient_stock",
                )

            new_stock = current_stock - request.quantity
            write_response = self._commit_write(request.title, new_stock)
            return books_database.ReserveStockResponse(
                success=write_response.success,
                remaining_stock=new_stock if write_response.success else current_stock,
                error=write_response.error,
            )

    def PropagateWrite(self, request, context):
        set_request_id_from_context(context)
        if self.role == "head":
            return books_database.WriteResponse(
                success=False,
                error="head_does_not_accept_propagated_writes",
            )

        with self.write_lock:
            return self._commit_write(request.title, request.new_stock)

    def _commit_write(self, title, new_stock):
        with self.store_lock:
            previous_stock = self.store.get(title)
            had_previous_stock = title in self.store
            self.store[title] = new_stock

        logger.info(
            "Replica role=%s applied stock write: %s=%s.",
            self.role,
            title,
            new_stock,
        )

        if self.next_address:
            try:
                with grpc.insecure_channel(self.next_address) as channel:
                    stub = books_database_grpc.BooksDatabaseStub(channel)
                    response = stub.PropagateWrite(
                        books_database.PropagateWriteRequest(
                            title=title,
                            new_stock=new_stock,
                        ),
                        timeout=3,
                )
                if not response.success:
                    self._rollback_write(title, previous_stock, had_previous_stock)
                    return response
            except Exception as exc:
                logger.exception(
                    "Failed to propagate write for %s to %s.",
                    title,
                    self.next_address,
                )
                self._rollback_write(title, previous_stock, had_previous_stock)
                return books_database.WriteResponse(
                    success=False,
                    error=f"replication_failed: {exc}",
                )

        return books_database.WriteResponse(success=True)

    def _rollback_write(self, title, previous_stock, had_previous_stock):
        with self.store_lock:
            if had_previous_stock:
                self.store[title] = previous_stock
            else:
                self.store.pop(title, None)

        logger.info("Rolled back local write for %s on role=%s.", title, self.role)

    def _read_from_tail(self, request):
        try:
            with grpc.insecure_channel(self.tail_address) as channel:
                stub = books_database_grpc.BooksDatabaseStub(channel)
                return stub.Read(request, timeout=3)
        except Exception:
            logger.exception("Failed to proxy read for %s to tail.", request.title)
            raise

    def _write_to_head(self, title, new_stock):
        try:
            with grpc.insecure_channel(self.head_address) as channel:
                stub = books_database_grpc.BooksDatabaseStub(channel)
                return stub.Write(
                    books_database.WriteRequest(title=title, new_stock=new_stock),
                    timeout=5,
                )
        except Exception as exc:
            logger.exception("Failed to proxy write for %s to head.", title)
            return books_database.WriteResponse(
                success=False,
                error=f"head_unavailable: {exc}",
            )

    def _reserve_at_head(self, title, quantity):
        try:
            with grpc.insecure_channel(self.head_address) as channel:
                stub = books_database_grpc.BooksDatabaseStub(channel)
                return stub.ReserveStock(
                    books_database.ReserveStockRequest(
                        title=title,
                        quantity=quantity,
                    ),
                    timeout=5,
                )
        except Exception as exc:
            logger.exception("Failed to proxy reservation for %s to head.", title)
            return books_database.ReserveStockResponse(
                success=False,
                remaining_stock=0,
                error=f"head_unavailable: {exc}",
            )

    def _load_initial_store(self):
        raw_value = os.getenv("INITIAL_STOCKS", "")
        if not raw_value:
            return dict(DEFAULT_STOCKS)

        try:
            parsed = json.loads(raw_value)
            return {
                str(title): int(stock)
                for title, stock in parsed.items()
            }
        except Exception:
            logger.exception("Invalid INITIAL_STOCKS value. Falling back to defaults.")
            return dict(DEFAULT_STOCKS)

    def _address_from_host(self, host):
        if not host:
            return ""
        if ":" in host:
            return host
        return f"{host}:{self.listen_port}"


def serve():
    service = BooksDatabaseService()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    books_database_grpc.add_BooksDatabaseServicer_to_server(service, server)
    server.add_insecure_port(f"{service.listen_address}:{service.listen_port}")
    server.start()
    logger.info(
        "BooksDatabase replica started as %s on %s:%s. Next=%s head=%s tail=%s.",
        service.role,
        service.listen_address,
        service.listen_port,
        service.next_address or "none",
        service.head_address,
        service.tail_address,
    )
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
