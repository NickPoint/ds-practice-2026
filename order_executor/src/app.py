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
payment_grpc_path = os.path.abspath(os.path.join(FILE, "../../../utils/pb/payment"))
sys.path.insert(0, order_executor_grpc_path)
sys.path.insert(0, order_queue_grpc_path)
sys.path.insert(0, books_database_grpc_path)
sys.path.insert(0, payment_grpc_path)

import order_executor_pb2 as order_executor
import order_executor_pb2_grpc as order_executor_grpc
import order_queue_pb2 as order_queue
import order_queue_pb2_grpc as order_queue_grpc
import books_database_pb2 as books_database
import books_database_pb2_grpc as books_database_grpc

#import db
#import db_grpc
import payment_pb2 as payment
import payment_pb2_grpc as payment_grpc


setup_logging()
logger = logging.getLogger(__name__)

ELECTION_TIMEOUT_SECONDS = 3
LEADER_HEARTBEAT_SECONDS = 1

results_lock = threading.Lock()

def fail(results, message):
    with results_lock:
        results["errors"].append(message)

class OrderExecutorService(order_executor_grpc.OrderExecutorServiceServicer):
    def __init__(self):
        self.executor_id = int(os.getenv("EXECUTOR_ID", "1"))
        self.executor_name = os.getenv("EXECUTOR_NAME", f"order-executor-{self.executor_id}")
        self.listen_port = os.getenv("EXECUTOR_PORT", "50055")
        self.queue_address = os.getenv("ORDER_QUEUE_ADDRESS", "order_queue:50054")
        self.database_address = os.getenv("BOOKS_DATABASE_ADDRESS", "books_database_1:50057")
        self.payment_address = os.getenv("PAYMENT_ADDRESS", "payment:50060")
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

        #this shi is spamming logs
        #logger.info(
        #    "Executor %s accepted executor %s as the current leader.",
        #    self.executor_id,
        #    request.leader_id,
        #)
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

    def _commit_until_done(self, order_id, participant_name, address, stub_cls, method_name, request):
        while True:
            try:
                logger.info(
                        "Trying to commit %s for order %s.",
                        participant_name,
                        order_id,
                    )

                with grpc.insecure_channel(address) as channel:
                    stub = stub_cls(channel)
                    commit_method = getattr(stub, method_name)

                    response = commit_method(
                        request,
                        metadata=grpc_client_metadata_for_request_id(),
                        timeout=3,
                    )

                if response.is_ok:
                    logger.info(
                        "%s commit completed for order %s.",
                        participant_name,
                        order_id,
                    )
                    return

                logger.warning(
                    "%s commit returned not-ok for order %s: %s. Retrying.",
                    participant_name,
                    order_id,
                    list(response.errors),
                )

            except Exception as exc:
                logger.warning(
                    "%s commit timed out/failed for order %s: %s. Retrying.",
                    participant_name,
                    order_id,
                    exc,
                )

            time.sleep(1)

    def _commit_database_until_done(self, order_id: str):
        self._commit_until_done(
            order_id=order_id,
            participant_name="Database",
            address=self.database_address,
            stub_cls=books_database_grpc.BooksDatabaseStub,
            method_name="CommitOrder",
            request=books_database.CommitOrderRequest(order_id=order_id),
        )


    def _commit_payment_until_done(self, order_id: str):
        self._commit_until_done(
            order_id=order_id,
            participant_name="Payment",
            address=self.payment_address,
            stub_cls=payment_grpc.PaymentServiceStub,
            method_name="Commit",
            request=payment.CommitRequest(order_id=order_id),
        )

    def _abort_all(self, order_id, prepared_services, results):
        if "database" in prepared_services:
            try:
                with grpc.insecure_channel(self.database_address) as channel:
                    stub = books_database_grpc.BooksDatabaseStub(channel)
                    response = stub.AbortOrder(
                        books_database.AbortOrderRequest(order_id=order_id),
                        metadata=grpc_client_metadata_for_request_id(),
                        timeout=5,
                    )
                if not response.is_ok:
                    fail(results, response.errors[0] if response.errors else "Database abort failed")
            except Exception as exc:
                logger.exception("Failed to abort database for order %s.", order_id)
                fail(results, f"database_abort_failed: {exc}")

        if "payment" in prepared_services:
            try:
                with grpc.insecure_channel(self.payment_address) as channel:
                    stub = payment_grpc.PaymentServiceStub(channel)
                    response = stub.Abort(
                        payment.AbortRequest(order_id=order_id),
                        metadata=grpc_client_metadata_for_request_id(),
                        timeout=5,
                    )
                if not response.is_ok:
                    fail(results, response.errors[0] if response.errors else "Payment abort failed")
            except Exception as exc:
                logger.exception("Failed to abort payment for order %s.", order_id)
                fail(results, f"payment_abort_failed: {exc}")

    def execute_order_2pc(self, dequeued_order):
        results = {"errors": [], "suggestions": []}
        expected_services = ["database", "payment"]
        prepared_services = []

        order_id = dequeued_order.order_id

        # Prepare order in database.
        try:
            with grpc.insecure_channel(self.database_address) as channel:
                stub = books_database_grpc.BooksDatabaseStub(channel)
                response = stub.PrepareOrder(
                    books_database.PrepareOrderRequest(
                        order_id=order_id,
                        items=[
                            books_database.ReserveStockRequest(title=item.title, quantity=item.quantity)
                            for item in dequeued_order.items
                        ],
                    ),
                    metadata=grpc_client_metadata_for_request_id(),
                    timeout=5,
                )
            if not response.is_ok:
                self._abort_all(order_id, prepared_services, results)
                fail(results, response.errors[0] if response.errors else "Database prepare failed")
        except Exception as exc:
            logger.exception("Failed to Prepare database for order %s.", order_id)
            self._abort_all(order_id, prepared_services, results)
            fail(results, f"database_prepare_failed: {exc}")

        if not results["errors"]:
            prepared_services.append("database")
            logger.info(
                    "Leader executor %s prepared database for order %s.",
                    self.executor_id,
                    order_id,
                )

        #Prepare payments
        try:
            with grpc.insecure_channel(self.payment_address) as channel:
                stub = payment_grpc.PaymentServiceStub(channel)
                response = stub.Prepare(
                    payment.PrepareRequest(
                        order_id=order_id,
                    ),
                    metadata=grpc_client_metadata_for_request_id(),
                    timeout=5,
                )
            if not response.is_ok:
                self._abort_all(order_id, prepared_services, results)
                fail(results, response.errors[0] if response.errors else "Payment Prepare failed")
        except Exception as exc:
            logger.exception("Failed to Prepare payment for order %s.", order_id)
            self._abort_all(order_id, prepared_services, results)
            fail(results, f"payment_prepare_failed: {exc}")  

        if not results["errors"] and response.is_ok:
            prepared_services.append("payment")
            logger.info(
                    "Leader executor %s prepared payment for order %s.",
                    self.executor_id,
                    order_id,
                )

        #some are not prepared
        if not all(map(lambda v: v in expected_services, prepared_services)):
            self._abort_all(order_id, prepared_services, results)
            return
        
        # decision -> commiting
        #not sure if this counts as 2nd bonus point but issue here is that:
        #if executor fails between prepare and commit, it will loose the prepared order.
        #TO fix this, I should do the same as I did in payment with json persistence file where I track prepared orders.
        #So, if I write down prepared orders to a file with __append_prepared, then
        #A separate thread is responsible for calling commits based on file that tracks which order is prepared but not commited
        #then executor also becomes fully PC2 compliant
        self._commit_database_until_done(order_id)
        self._commit_payment_until_done(order_id)

        if results["errors"]:
            logger.warning("Order %s failed 2PC: %s", order_id, results["errors"][0])
            return

        logger.info("Order %s completed 2PC successfully.", order_id)

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
                    self.execute_order_2pc(response)
            except Exception:
                logger.exception("Leader executor %s failed to dequeue an order.", self.executor_id)
                time.sleep(1)

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
