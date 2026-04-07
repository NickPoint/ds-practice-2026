import json
import logging
import os
import sys
import threading
import uuid

import grpc
from flask import Flask, request
from flask_cors import CORS

from utils.logging import (
    grpc_client_metadata_for_request_id,
    request_id_var,
    setup_logging,
)
from utils.vector_clock import VectorClock, vector_clock_to_metadata

FILE = __file__ if "__file__" in globals() else os.getenv("PYTHONFILE", "")

fraud_detection_grpc_path = os.path.abspath(os.path.join(FILE, "../../../utils/pb/fraud_detection"))
transaction_verification_grpc_path = os.path.abspath(
    os.path.join(FILE, "../../../utils/pb/transaction_verification")
)
suggestions_grpc_path = os.path.abspath(os.path.join(FILE, "../../../utils/pb/suggestions"))

sys.path.insert(0, fraud_detection_grpc_path)
sys.path.insert(0, transaction_verification_grpc_path)
sys.path.insert(0, suggestions_grpc_path)

import fraud_detection_pb2 as fraud_detection
import fraud_detection_pb2_grpc as fraud_detection_grpc
import suggestions_pb2 as suggestions
import suggestions_pb2_grpc as suggestions_grpc
import transaction_verification_pb2 as transaction_verification
import transaction_verification_pb2_grpc as transaction_verification_grpc

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

setup_logging()
logger = logging.getLogger(__name__)

results_lock = threading.Lock()


def fail(results, message):
    with results_lock:
        results["errors"].append(message)


def metadata_with_vector_clock(clock_snapshot):
    metadata = list(grpc_client_metadata_for_request_id())
    metadata.append(("x-vector-clock", vector_clock_to_metadata(clock_snapshot)))
    return metadata


def build_transaction_order_data(request_data):
    return transaction_verification.OrderData(
        user=transaction_verification.User(
            name=request_data.get("user", {}).get("name", ""),
            contact=request_data.get("user", {}).get("contact", ""),
        ),
        credit_card=transaction_verification.CreditCard(
            number=request_data.get("creditCard", {}).get("number", ""),
            expiration_date=request_data.get("creditCard", {}).get("expirationDate", ""),
            cvv=request_data.get("creditCard", {}).get("cvv", ""),
        ),
        user_comment=request_data.get("userComment", ""),
        items=[
            transaction_verification.Item(
                name=item.get("name", ""),
                quantity=item.get("quantity", 0),
            )
            for item in request_data.get("items", [])
        ],
        billing_address=transaction_verification.Address(
            street=request_data.get("billingAddress", {}).get("street", ""),
            city=request_data.get("billingAddress", {}).get("city", ""),
            state=request_data.get("billingAddress", {}).get("state", ""),
            zip=request_data.get("billingAddress", {}).get("zip", ""),
            country=request_data.get("billingAddress", {}).get("country", ""),
        ),
        shipping_method=request_data.get("shippingMethod", ""),
        gift_wrapping=request_data.get("giftWrapping", False),
        terms_accepted=request_data.get("termsAccepted", False),
    )


def build_fraud_order_data(request_data):
    return fraud_detection.FraudOrderData(
        credit_card=fraud_detection.CreditCard(
            number=request_data.get("creditCard", {}).get("number", ""),
            expiration_date=request_data.get("creditCard", {}).get("expirationDate", ""),
            cvv=request_data.get("creditCard", {}).get("cvv", ""),
        ),
        items=[
            fraud_detection.Item(
                name=item.get("name", ""),
                quantity=item.get("quantity", 0),
            )
            for item in request_data.get("items", [])
        ],
        billing_address=fraud_detection.Address(
            country=request_data.get("billingAddress", {}).get("country", ""),
            city=request_data.get("billingAddress", {}).get("city", ""),
        ),
        device=fraud_detection.Device(
            type=request_data.get("device", {}).get("type", ""),
            os=request_data.get("device", {}).get("os", ""),
        ),
        browser=fraud_detection.Browser(
            name=request_data.get("browser", {}).get("name", ""),
        ),
        terms_accepted=request_data.get("termsAccepted", False),
    )


def build_suggestions_order_data(request_data):
    return suggestions.SuggestionOrderData(
        user_id=request_data.get("user", {}).get("name", "anonymous"),
        ordered_items=[item.get("name", "") for item in request_data.get("items", [])],
    )


def init_transaction_order(order_id, request_data, request_id, orchestrator_clock, results):
    request_id_var.set(request_id)
    send_clock = orchestrator_clock.send_event()
    logger.info(
        "Sending init request to TransactionVerification for order %s. Clock: %s",
        order_id,
        send_clock,
    )
    try:
        with grpc.insecure_channel("transaction_verification:50052") as channel:
            stub = transaction_verification_grpc.TransactionVerificationServiceStub(channel)
            response = stub.InitOrder(
                transaction_verification.InitOrderRequest(
                    order_id=order_id,
                    order_data=build_transaction_order_data(request_data),
                ),
                metadata=metadata_with_vector_clock(send_clock),
                timeout=5,
            )
        if not response.is_ok:
            fail(results, response.errors[0] if response.errors else "transaction_init_failed")
    except Exception as exc:
        logger.exception("Failed to initialize TransactionVerification for order %s.", order_id)
        fail(results, f"transaction_init_failed: {exc}")


def init_fraud_order(order_id, request_data, request_id, orchestrator_clock, results):
    request_id_var.set(request_id)
    send_clock = orchestrator_clock.send_event()
    logger.info(
        "Sending init request to FraudDetection for order %s. Clock: %s",
        order_id,
        send_clock,
    )
    try:
        with grpc.insecure_channel("fraud_detection:50051") as channel:
            stub = fraud_detection_grpc.FraudDetectionServiceStub(channel)
            response = stub.InitOrder(
                fraud_detection.InitOrderRequest(
                    order_id=order_id,
                    order_data=build_fraud_order_data(request_data),
                ),
                metadata=metadata_with_vector_clock(send_clock),
                timeout=5,
            )
        if not response.is_ok:
            fail(results, response.errors[0] if response.errors else "fraud_init_failed")
    except Exception as exc:
        logger.exception("Failed to initialize FraudDetection for order %s.", order_id)
        fail(results, f"fraud_init_failed: {exc}")


def init_suggestions_order(order_id, request_data, request_id, orchestrator_clock, results):
    request_id_var.set(request_id)
    send_clock = orchestrator_clock.send_event()
    logger.info(
        "Sending init request to Suggestions for order %s. Clock: %s",
        order_id,
        send_clock,
    )
    try:
        with grpc.insecure_channel("suggestions:50053") as channel:
            stub = suggestions_grpc.SuggestionsServiceStub(channel)
            response = stub.InitOrder(
                suggestions.InitOrderRequest(
                    order_id=order_id,
                    order_data=build_suggestions_order_data(request_data),
                ),
                metadata=metadata_with_vector_clock(send_clock),
                timeout=5,
            )
        if not response.is_ok:
            fail(results, response.errors[0] if response.errors else "suggestions_init_failed")
    except Exception as exc:
        logger.exception("Failed to initialize Suggestions for order %s.", order_id)
        fail(results, f"suggestions_init_failed: {exc}")


def execute_transaction(order_id, request_id, orchestrator_clock):
    request_id_var.set(request_id)
    send_clock = orchestrator_clock.send_event()
    logger.info(
        "Sending transaction execution request for order %s. Clock: %s",
        order_id,
        send_clock,
    )
    with grpc.insecure_channel("transaction_verification:50052") as channel:
        stub = transaction_verification_grpc.TransactionVerificationServiceStub(channel)
        response = stub.ExecuteTransaction(
            transaction_verification.TransactionRunRequest(
                order_id=order_id,
                vector_clock=send_clock,
            ),
            metadata=grpc_client_metadata_for_request_id(),
            timeout=5,
        )
    merged_clock = orchestrator_clock.receive_event(dict(response.vector_clock))
    logger.info(
        "Merged TransactionVerification response clock for order %s. Clock: %s",
        order_id,
        merged_clock,
    )
    return response


def execute_fraud(order_id, request_id, orchestrator_clock):
    request_id_var.set(request_id)
    send_clock = orchestrator_clock.send_event()
    logger.info(
        "Sending fraud execution request for order %s. Clock: %s",
        order_id,
        send_clock,
    )
    with grpc.insecure_channel("fraud_detection:50051") as channel:
        stub = fraud_detection_grpc.FraudDetectionServiceStub(channel)
        response = stub.CheckFraud(
            fraud_detection.FraudRequest(
                order_id=order_id,
                vector_clock=send_clock,
            ),
            metadata=grpc_client_metadata_for_request_id(),
            timeout=5,
        )
    merged_clock = orchestrator_clock.receive_event(dict(response.vector_clock))
    logger.info(
        "Merged FraudDetection response clock for order %s. Clock: %s",
        order_id,
        merged_clock,
    )
    return response


def execute_suggestions(order_id, request_id, orchestrator_clock):
    request_id_var.set(request_id)
    send_clock = orchestrator_clock.send_event()
    logger.info(
        "Sending suggestions request for order %s. Clock: %s",
        order_id,
        send_clock,
    )
    with grpc.insecure_channel("suggestions:50053") as channel:
        stub = suggestions_grpc.SuggestionsServiceStub(channel)
        response = stub.GetSuggestions(
            suggestions.SuggestionRequest(
                order_id=order_id,
                vector_clock=send_clock,
            ),
            metadata=grpc_client_metadata_for_request_id(),
            timeout=5,
        )
    merged_clock = orchestrator_clock.receive_event(dict(response.vector_clock))
    logger.info(
        "Merged Suggestions response clock for order %s. Clock: %s",
        order_id,
        merged_clock,
    )
    return response


@app.route("/checkout", methods=["POST"])
def checkout():
    request_id = uuid.uuid4().hex[:8]
    order_id = str(uuid.uuid4())

    request_id_var.set(request_id)
    request_data = request.get_json(force=True)
    logger.info(
        "Received checkout request for order %s. Payload: %s",
        order_id,
        json.dumps(request_data, sort_keys=True),
    )

    orchestrator_clock = VectorClock("orchestrator")
    results = {"errors": [], "suggestions": []}

    init_threads = [
        threading.Thread(
            target=init_transaction_order,
            args=(order_id, request_data, request_id, orchestrator_clock, results),
            name="init-txn",
        ),
        threading.Thread(
            target=init_fraud_order,
            args=(order_id, request_data, request_id, orchestrator_clock, results),
            name="init-fraud",
        ),
        threading.Thread(
            target=init_suggestions_order,
            args=(order_id, request_data, request_id, orchestrator_clock, results),
            name="init-suggestions",
        ),
    ]

    for thread in init_threads:
        thread.start()
    for thread in init_threads:
        thread.join()

    if results["errors"]:
        return {
            "orderId": order_id,
            "status": "Order Rejected",
            "error": {"message": results["errors"][0]},
        }, 500

    try:
        txn_response = execute_transaction(order_id, request_id, orchestrator_clock)
    except Exception as exc:
        logger.exception("Transaction execution failed for order %s.", order_id)
        return {
            "orderId": order_id,
            "status": "Order Rejected",
            "error": {"message": f"transaction_execution_failed: {exc}"},
        }, 500

    if not txn_response.is_valid:
        return {
            "orderId": order_id,
            "status": "Order Rejected",
            "error": {"message": ", ".join(txn_response.errors)},
        }, 400

    try:
        fraud_response = execute_fraud(order_id, request_id, orchestrator_clock)
    except Exception as exc:
        logger.exception("Fraud execution failed for order %s.", order_id)
        return {
            "orderId": order_id,
            "status": "Order Rejected",
            "error": {"message": f"fraud_execution_failed: {exc}"},
        }, 500

    if fraud_response.is_fraud:
        reason = ", ".join(fraud_response.reasons) if fraud_response.reasons else "Fraud detected!"
        return {
            "orderId": order_id,
            "status": "Order Rejected",
            "error": {"message": reason},
        }, 400

    try:
        suggestions_response = execute_suggestions(order_id, request_id, orchestrator_clock)
    except Exception as exc:
        logger.exception("Suggestions execution failed for order %s.", order_id)
        return {
            "orderId": order_id,
            "status": "Order Approved",
            "suggestedBooks": [],
            "warning": f"suggestions_execution_failed: {exc}",
        }, 200

    results["suggestions"] = [
        {"bookId": book.book_id, "title": book.title, "author": book.author}
        for book in suggestions_response.suggestions
    ]

    logger.info(
        "Checkout finished for order %s. Final orchestrator clock: %s",
        order_id,
        orchestrator_clock.snapshot(),
    )
    return {
        "orderId": order_id,
        "status": "Order Approved",
        "suggestedBooks": results["suggestions"],
    }, 200


if __name__ == "__main__":
    app.run(host="0.0.0.0")
