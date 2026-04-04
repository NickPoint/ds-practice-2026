import sys
import os
import threading
import uuid
import grpc
import logging
from flask import Flask, request
from flask_cors import CORS
import json

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")

fraud_detection_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/fraud_detection'))
transaction_verification_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/transaction_verification'))
suggestions_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/suggestions'))

sys.path.insert(0, fraud_detection_grpc_path)
sys.path.insert(0, transaction_verification_grpc_path)
sys.path.insert(0, suggestions_grpc_path)

import fraud_detection_pb2 as fraud_detection
import fraud_detection_pb2_grpc as fraud_detection_grpc
import transaction_verification_pb2 as transaction_verification
import transaction_verification_pb2_grpc as transaction_verification_grpc
import suggestions_pb2 as suggestions
import suggestions_pb2_grpc as suggestions_grpc

from utils.logging import (
    setup_logging,
    request_id_var,
    grpc_client_metadata_for_request_id,
)

app = Flask(__name__)
CORS(app, resources={r'/*': {'origins': '*'}})

# configure global logging for this microservice
setup_logging()
logger = logging.getLogger(__name__)

results_lock = threading.Lock()
BASE_VC = [1, 0, 0]

#--------------------------
# Helper funcs
#--------------------------
def fail(results, stop_event, message):
    with results_lock:
        if not stop_event.is_set():
            results["errors"].append(message)
            stop_event.set()

def wait_for(dep_event, stop_event, poll_interval=0.05):
    while not dep_event.wait(poll_interval):
        if stop_event.is_set():
            return False
    return not stop_event.is_set()

def merge_vc(*vectors):
    non_empty = [v for v in vectors if v]
    if not non_empty:
        return BASE_VC[:]
    size = max(len(v) for v in non_empty)
    merged = [0] * size
    for v in non_empty:
        for i, value in enumerate(v):
            merged[i] = max(merged[i], value)
    return merged

#--------------------------
# Request builders
#--------------------------
def build_transaction_request(request_data):
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
                quantity=item.get("quantity", 0)
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

#--------------------------
# Phase 1: init order
#--------------------------
def init_transaction_order(order_id, request_data, request_id, results):
    request_id_var.set(request_id)
    try:
        with grpc.insecure_channel("transaction_verification:50052") as channel:
            stub = transaction_verification_grpc.TransactionVerificationServiceStub(channel)

            response = stub.InitOrder(
                transaction_verification.InitOrderRequest(
                    order_id=order_id,
                    order_data=build_transaction_request(request_data)
                ),
                metadata=grpc_client_metadata_for_request_id(),
                timeout=5
            )

            logger.info("Transaction service initialized order %s", order_id)
            if not response.is_ok:
                with results_lock:
                    results["errors"].extend(response.errors or ["transaction_init_failed"])
    except Exception as e:
        logger.exception("Transaction init error")
        with results_lock:
            results["errors"].append(f"Transaction init failed: {str(e)}")

#--------------------------
# Phase 2: execute events
#--------------------------
def call_fraud_detection(request_data, results, request_id):
    request_id_var.set(request_id)
    logger.debug(
        "Started fraud detection in thread=%s",
        threading.current_thread().name)
    try:
        proto_request = fraud_detection.FraudRequest(
            credit_card=fraud_detection.CreditCard(
                number=request_data["creditCard"].get("number", ""),
                expiration_date=request_data["creditCard"].get("expirationDate", ""),
                cvv=request_data["creditCard"].get("cvv", ""),
            ),
            items=[
                fraud_detection.Item(name=item["name"], quantity=item["quantity"])
                for item in request_data.get("items", [])
            ],
            billing_address=fraud_detection.Address(
                country=request_data.get("billingAddress", {}).get("country", ""),
                city=request_data.get("billingAddress", {}).get("city", "")
            ),
            device=fraud_detection.Device(
                type=request_data.get("device", {}).get("type", ""),
                os=request_data.get("device", {}).get("os", "")
            ),
            browser=fraud_detection.Browser(
                name=request_data.get("browser", {}).get("name", "")
            ),
            terms_accepted=request_data.get("termsAccepted", False)
        )
        with grpc.insecure_channel('fraud_detection:50051') as channel:
            stub = fraud_detection_grpc.FraudDetectionServiceStub(channel)
            response = stub.CheckFraud(
                proto_request,
                metadata=grpc_client_metadata_for_request_id(),
            )
            results["is_fraud"] = response.is_fraud
    except Exception as e:
        logger.error(f"Fraud detection error: {e}")


def call_verify_items(order_id, request_id):
    request_id_var.set(request_id)

    logger.info(
        "Started item verification in thread=%s",
        threading.current_thread().name)
    
    with grpc.insecure_channel("transaction_verification:50052") as channel:
        stub = transaction_verification_grpc.TransactionVerificationServiceStub(channel)
        response = stub.VerifyItems(
            transaction_verification.StepRequest(
                order_id=order_id,
                vc=BASE_VC
            ),
            metadata=grpc_client_metadata_for_request_id(),
            timeout=5
        )
        return response

def call_verify_user_data(order_id, request_id):
    request_id_var.set(request_id)

    logger.info(
        "Started user data verification in thread=%s",
        threading.current_thread().name)
    
    with grpc.insecure_channel("transaction_verification:50052") as channel:
        stub = transaction_verification_grpc.TransactionVerificationServiceStub(channel)
        response = stub.VerifyUserData(
            transaction_verification.StepRequest(
                order_id=order_id,
                vc=BASE_VC
            ),
            metadata=grpc_client_metadata_for_request_id(),
            timeout=5
        )
        return response

def call_verify_card_format(order_id, vc, request_id):
    request_id_var.set(request_id)

    logger.info(
        "Started user data verification in thread=%s",
        threading.current_thread().name)
    
    with grpc.insecure_channel("transaction_verification:50052") as channel:
        stub = transaction_verification_grpc.TransactionVerificationServiceStub(channel)
        response = stub.VerifyCardFormat(
            transaction_verification.StepRequest(
                order_id=order_id,
                vc=vc
            ),
            metadata=grpc_client_metadata_for_request_id(),
            timeout=5
        )
        return response

def call_suggestions(request_data, results, request_id):
    request_id_var.set(request_id)
    logger.info(
        "Started suggestions in thread=%s",
        threading.current_thread().name)
    try:
        items = request_data.get("items", [])
        with grpc.insecure_channel('suggestions:50053') as channel:
            stub = suggestions_grpc.SuggestionsServiceStub(channel)
            response = stub.GetSuggestions(
                suggestions.SuggestionRequest(
                    user_id=request_data.get("user", {}).get("name", "anonymous"),
                    ordered_items=[item.get("name", "") for item in items]
                ),
                metadata=grpc_client_metadata_for_request_id(),
            )
            results["suggestions"] = [
                {"bookId": b.book_id, "title": b.title, "author": b.author}
                for b in response.suggestions
            ]
    except Exception as e:
        logger.error(f"Suggestions error: {e}")


@app.route('/checkout', methods=['POST'])
def checkout():
    request_id = uuid.uuid4().hex[:8]  # tracing
    order_id = uuid.uuid4().hex        # real business order id

    request_id_var.set(request_id)
    request_data = request.get_json(force=True)
    logger.info("request_id=%s order_id=%s request_data=%s", request_id, order_id, request_data)

    results = {
        "is_fraud": False, # ideally shouldn't be used, controlled by execution flow
        "errors": [],
        "suggestions": [],
        "vc": {}
    }

    #--------------------------
    # Initialize events
    #--------------------------
    a_done = threading.Event()
    b_done = threading.Event()
    c_done = threading.Event()
    d_done = threading.Event()
    e_done = threading.Event()
    stop_event = threading.Event()

    #--------------------------
    # Phase 1: initialize order in all services
    #--------------------------
    init_threads = [
        #init_fraud
        threading.Thread(target=init_transaction_order, args=(order_id, request_data, request_id, results)),
        #init suggestions
    ]

    for t in init_threads:
        t.start()
    for t in init_threads:
        t.join()

    if results["errors"]:
        return {
            "orderId": order_id,
            "status": "Order Rejected",
            "error": {"message": results["errors"][0]}
        }, 500
    

    # -------------------------
    # Phase 2: Logic execution steps
    # -------------------------
    def run_a():
        response = call_verify_items(order_id, request_id)
        if not response.is_valid:
            fail(results, stop_event, f"a failed: {', '.join(response.errors)}")
            return
        with results_lock:
            results["vc"]["a"] = list(response.vc)
        a_done.set()

    def run_b():
        response = call_verify_user_data(order_id, request_id)
        if not response.is_valid:
            fail(results, stop_event, f"b failed: {', '.join(response.errors)}")
            return
        with results_lock:
            results["vc"]["b"] = list(response.vc)
        b_done.set()

    def run_c():
        if not wait_for(a_done, stop_event):
            return
        
        with results_lock:
            vc_a = results["vc"].get("a", BASE_VC)
        response = call_verify_card_format(order_id, vc_a, request_id)
        if not response.is_valid:
            fail(results, stop_event, f"c failed: {', '.join(response.errors)}")
            return
        with results_lock:
            results["vc"]["c"] = list(response.vc)
        c_done.set()

    #next two are to be done
    def run_d():
        if not wait_for(b_done, stop_event):
            return

        if not wait_for(c_done, stop_event):
            return

        # should confirm b and c vector clocks:
        # vc_b = results["vc"].get("b", BASE_VC)
        # vc_c = results["vc"].get("b", BASE_VC)
        # and pass that to call funcs
        call_fraud_detection(request_data, results, request_id)

        #also don't forget to merge orchestrator's clock that call is done
        if results["is_fraud"]:
            fail(results, stop_event, "Fraud detected!")
            return
        
        d_done.set()

    def run_e():
        if not wait_for(d_done, stop_event):
            return

        # should confirm d vector clocks:
        # vc_d = results["vc"].get("b", BASE_VC)
        # and pass that to call funcs
        try:
            call_suggestions(request_data, results, request_id)
        except Exception as e:
            fail(results, stop_event, f"Fraud detection excepted with {e}!")
            return

        e_done.set()

    threads = [
        threading.Thread(target=run_a, name="step-a"),
        threading.Thread(target=run_b, name="step-b"),
        threading.Thread(target=run_c, name="step-c"),
        threading.Thread(target=run_d, name="step-d"), #TBD
        threading.Thread(target=run_e, name="sted-e")  #TBD
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if stop_event.is_set():
        return {
            "orderId": order_id,
            "status": "Order Rejected",
            "error": {"message": results["errors"][0]}
        }, 400

    #Legacy, should be handled within stop_event above as well
    if results["is_fraud"]:
        return {"status": "Order Rejected", "error": {"message": "Fraud detected!"}}, 400
    
    return {
        "orderId": order_id,
        "status": "Order Approved",
        "suggestedBooks": results["suggestions"],
    }, 200

if __name__ == '__main__':
    app.run(host='0.0.0.0')