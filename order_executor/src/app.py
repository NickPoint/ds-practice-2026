import os
import sys
import threading
import time
from concurrent import futures

import grpc
import logging

from utils.logging import grpc_client_metadata_for_request_id, setup_logging

FILE = __file__ if "__file__" in globals() else os.getenv("PYTHONFILE", "")
order_executor_grpc_path = os.path.abspath(os.path.join(FILE, "../../../utils/pb/order_executor"))
order_queue_grpc_path = os.path.abspath(os.path.join(FILE, "../../../utils/pb/order_queue"))
books_database_grpc_path = os.path.abspath(os.path.join(FILE, "../../../utils/pb/books_database"))
sys.path.insert(0, order_executor_grpc_path)
sys.path.insert(0, order_queue_grpc_path)
sys.path.insert(0, books_database_grpc_path)

import order_executor_pb2 as order_executor
import order_executor_pb2_grpc as order_executor_grpc
import order_queue_pb2 as order_queue
import order_queue_pb2_grpc as order_queue_grpc
import books_database_pb2 as books_database
import books_database_pb2_grpc as books_database_grpc

setup_logging()
logger = logging.getLogger(__name__)

ELECTION_TIMEOUT_SECONDS = 3
LEADER_HEARTBEAT_SECONDS = 1


class OrderExecutorService(order_executor_grpc.OrderExecutorServiceServicer):
    def __init__(self):
        self.executor_id = int(os.getenv("EXECUTOR_ID", "1"))
        self.executor_name = os.getenv("EXECUTOR_NAME", f"order-executor-{self.executor_id}")
        self.listen_port = os.getenv("EXECUTOR_PORT", "50055")
        self.queue_address = os.getenv("ORDER_QUEUE_ADDRESS", "order_queue:50054")
        self.database_address = os.getenv("BOOKS_DATABASE_ADDRESS", "books_database_1:50057")
        self.peers = self._load_peers(os.getenv("EXECUTOR_PEERS", ""))

        self.state_lock = threading.Lock()
        self.current_leader_id = None
        self.last_leader_signal = 0.0
        self.election_in_progress = False

    def Election(self, request, context):
        with self.state_lock:
            self.last_leader_signal = time.time()

        logger.info(
            "Executor %s received an election request from candidate %s.",
            self.executor_id,
            request.candidate_id,
        )
        self._start_election_async()
        return order_executor.ElectionResponse(ok=True)

    def Coordinator(self, request, context):
        with self.state_lock:
            self.current_leader_id = request.leader_id
            self.last_leader_signal = time.time()
            self.election_in_progress = False

        logger.info(
            "Executor %s accepted executor %s as the current leader.",
            self.executor_id,
            request.leader_id,
        )
        return order_executor.CoordinatorResponse(ok=True)

    def Ping(self, request, context):
        return order_executor.PingResponse(ok=True)

    def run_background_loops(self):
        threading.Thread(target=self._leader_monitor_loop, name="leader-monitor", daemon=True).start()
        threading.Thread(target=self._execution_loop, name="execution-loop", daemon=True).start()

    def _leader_monitor_loop(self):
        self._start_election_async()
        while True:
            if self._leader_timed_out():
                self._start_election_async()
            # The leader keeps broadcasting coordinator messages as a heartbeat.
            if self._is_leader():
                self._announce_leadership()
            time.sleep(LEADER_HEARTBEAT_SECONDS)

    def _execution_loop(self):
        while True:
            if not self._is_leader():
                time.sleep(0.5)
                continue

            try:
                # Only the elected leader is allowed to pull the next order from the queue.
                with grpc.insecure_channel(self.queue_address) as channel:
                    stub = order_queue_grpc.OrderQueueServiceStub(channel)
                    response = stub.Dequeue(
                        order_queue.DequeueRequest(executor_id=str(self.executor_id)),
                        metadata=grpc_client_metadata_for_request_id(),
                    )
                if response.is_ok and response.order_id:
                    logger.info(
                        "Leader executor %s dequeued order %s and is executing it.",
                        self.executor_id,
                        response.order_id,
                    )
                    self._execute_order(response)
            except Exception:
                logger.exception("Leader executor %s failed to dequeue an order.", self.executor_id)
                time.sleep(1)

    def _execute_order(self, dequeued_order):
        if not dequeued_order.items:
            logger.info("Order %s has no items to reserve.", dequeued_order.order_id)
            return

        with grpc.insecure_channel(self.database_address) as channel:
            stub = books_database_grpc.BooksDatabaseStub(channel)
            for item in dequeued_order.items:
                read_response = stub.Read(
                    books_database.ReadRequest(title=item.title),
                    metadata=grpc_client_metadata_for_request_id(),
                    timeout=3,
                )
                logger.info(
                    "Order %s read current stock for %s: %s.",
                    dequeued_order.order_id,
                    item.title,
                    read_response.stock,
                )

                reserve_response = stub.ReserveStock(
                    books_database.ReserveStockRequest(
                        title=item.title,
                        quantity=item.quantity,
                    ),
                    metadata=grpc_client_metadata_for_request_id(),
                    timeout=5,
                )
                if not reserve_response.success:
                    logger.warning(
                        "Order %s failed to reserve %s x %s. Remaining stock=%s error=%s.",
                        dequeued_order.order_id,
                        item.quantity,
                        item.title,
                        reserve_response.remaining_stock,
                        reserve_response.error,
                    )
                    return

                logger.info(
                    "Order %s reserved %s x %s. Remaining stock=%s.",
                    dequeued_order.order_id,
                    item.quantity,
                    item.title,
                    reserve_response.remaining_stock,
                )

        logger.info("Order %s completed stock reservation.", dequeued_order.order_id)

    def _load_peers(self, peers_value):
        peers = []
        for peer in peers_value.split(","):
            peer = peer.strip()
            if not peer:
                continue
            peer_id_text, peer_address = peer.split("@", 1)
            peers.append((int(peer_id_text), peer_address))
        return peers

    def _leader_timed_out(self):
        with self.state_lock:
            no_leader = self.current_leader_id is None
            timed_out = (time.time() - self.last_leader_signal) > ELECTION_TIMEOUT_SECONDS
        return no_leader or timed_out

    def _is_leader(self):
        with self.state_lock:
            return self.current_leader_id == self.executor_id

    def _start_election_async(self):
        with self.state_lock:
            if self.election_in_progress:
                return
            self.election_in_progress = True
        threading.Thread(target=self._run_bully_election, name="bully-election", daemon=True).start()

    def _run_bully_election(self):
        logger.info("Executor %s started a Bully election round.", self.executor_id)
        higher_peer_replied = False

        # In the Bully algorithm, the highest live replica id wins the election.
        for peer_id, peer_address in self.peers:
            if peer_id <= self.executor_id:
                continue
            try:
                with grpc.insecure_channel(peer_address) as channel:
                    stub = order_executor_grpc.OrderExecutorServiceStub(channel)
                    response = stub.Election(
                        order_executor.ElectionRequest(candidate_id=self.executor_id),
                        timeout=1,
                    )
                if response.ok:
                    higher_peer_replied = True
            except Exception:
                logger.info(
                    "Executor %s could not reach higher-priority peer %s during election.",
                    self.executor_id,
                    peer_id,
                )

        if higher_peer_replied:
            with self.state_lock:
                self.election_in_progress = False
            return

        with self.state_lock:
            self.current_leader_id = self.executor_id
            self.last_leader_signal = time.time()
            self.election_in_progress = False

        logger.info("Executor %s became the leader.", self.executor_id)
        self._announce_leadership()

    def _announce_leadership(self):
        with self.state_lock:
            self.current_leader_id = self.executor_id
            self.last_leader_signal = time.time()

        for peer_id, peer_address in self.peers:
            if peer_id == self.executor_id:
                continue
            try:
                with grpc.insecure_channel(peer_address) as channel:
                    stub = order_executor_grpc.OrderExecutorServiceStub(channel)
                    stub.Coordinator(
                        order_executor.CoordinatorRequest(leader_id=self.executor_id),
                        timeout=1,
                    )
            except Exception:
                logger.info(
                    "Executor %s could not notify peer %s about the current leader.",
                    self.executor_id,
                    peer_id,
                )


def serve():
    service = OrderExecutorService()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    order_executor_grpc.add_OrderExecutorServiceServicer_to_server(service, server)
    server.add_insecure_port(f"[::]:{service.listen_port}")
    server.start()
    logger.info(
        "OrderExecutor %s started on port %s with peers %s.",
        service.executor_id,
        service.listen_port,
        [peer_id for peer_id, _ in service.peers],
    )
    service.run_background_loops()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
