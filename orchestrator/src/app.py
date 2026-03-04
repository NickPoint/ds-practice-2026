import sys
import os
import threading

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")

# Fraud detection
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

import grpc
from flask import Flask, request
from flask_cors import CORS
import json

app = Flask(__name__)
CORS(app, resources={r'/*': {'origins': '*'}})


def call_fraud_detection(request_data, results):
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
            response = stub.CheckFraud(proto_request)
            results["is_fraud"] = response.is_fraud
    except Exception as e:
        print(f"Fraud detection error: {e}")


def call_transaction_verification(request_data, results):
    try:
        proto_request = transaction_verification.TransactionRequest(
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
        with grpc.insecure_channel("transaction_verification:50052") as channel:
            stub = transaction_verification_grpc.TransactionVerificationServiceStub(channel)
            response = stub.VerifyTransaction(proto_request)
            results["is_valid"] = response.is_valid
    except Exception as e:
        print(f"Transaction verification error: {e}")


def call_suggestions(request_data, results):
    try:
        items = request_data.get("items", [])
        with grpc.insecure_channel('suggestions:50053') as channel:
            stub = suggestions_grpc.SuggestionsServiceStub(channel)
            response = stub.GetSuggestions(suggestions.SuggestionRequest(
                user_id=request_data.get("user", {}).get("name", "anonymous"),
                ordered_items=[item.get("name", "") for item in items]
            ))
            results["suggestions"] = [
                {"bookId": b.book_id, "title": b.title, "author": b.author}
                for b in response.suggestions
            ]
    except Exception as e:
        print(f"Suggestions error: {e}")


@app.route('/checkout', methods=['POST'])
def checkout():
    request_data = json.loads(request.data)
    print("Request Data:", request_data)

    results = {
        "is_fraud": False,
        "is_valid": True,
        "suggestions": []
    }

    # Run all three services in parallel
    t1 = threading.Thread(target=call_fraud_detection, args=(request_data, results))
    t2 = threading.Thread(target=call_transaction_verification, args=(request_data, results))
    t3 = threading.Thread(target=call_suggestions, args=(request_data, results))

    t1.start()
    t2.start()
    t3.start()
    t1.join()
    t2.join()
    t3.join()

    if results["is_fraud"]:
        return {"status": "Order Rejected", "error": {"message": "Fraud detected!"}}, 400

    if not results["is_valid"]:
        return {"status": "Order Rejected", "error": {"message": "Transaction could not be verified."}}, 400

    return {
        "orderId": "12345",
        "status": "Order Approved",
        "suggestedBooks": results["suggestions"]
    }


if __name__ == '__main__':
    app.run(host='0.0.0.0')