import sys
import os

# This set of lines are needed to import the gRPC stubs.
# The path of the stubs is relative to the current file, or absolute inside the container.
# Change these lines only if strictly needed.
FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
fraud_detection_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/fraud_detection'))
sys.path.insert(0, fraud_detection_grpc_path)
import fraud_detection_pb2 as fraud_detection
import fraud_detection_pb2_grpc as fraud_detection_grpc

import grpc

def call_fraud_detection(request):

    proto_request = fraud_detection.FraudRequest(
        credit_card=fraud_detection.CreditCard(
            number=request["creditCard"].get("number", ""),
            expiration_date=request["creditCard"].get("expirationDate", ""),
            cvv=request["creditCard"].get("cvv", ""),
        ),
        items=[
            fraud_detection.Item(name=item["name"], quantity=item["quantity"])
            for item in request.get("items", [])
        ],
        billing_address=fraud_detection.Address(
            country=request.get("billingAddress", {}).get("country", ""),
            city=request.get("billingAddress", {}).get("city", "")
        ),
        device=fraud_detection.Device(
            type=request.get("device", {}).get("type", ""),
            os=request.get("device", {}).get("os", "")
        ),
        browser=fraud_detection.Browser(
            name=request.get("browser", {}).get("name", "")
        ),
        terms_accepted=request.get("termsAccepted", False)
    )

    with grpc.insecure_channel('fraud_detection:50051') as channel:
        stub = fraud_detection_grpc.FraudDetectionServiceStub(channel)
        response = stub.CheckFraud(proto_request)

    return response.is_fraud

# Import Flask.
# Flask is a web framework for Python.
# It allows you to build a web application quickly.
# For more information, see https://flask.palletsprojects.com/en/latest/
from flask import Flask, request
from flask_cors import CORS
import json

# Create a simple Flask app.
app = Flask(__name__)
# Enable CORS for the app.
CORS(app, resources={r'/*': {'origins': '*'}})

@app.route('/checkout', methods=['POST'])
def checkout():
    """
    Responds with a JSON object containing the order ID, status, and suggested books.
    """
    # Get request object data to json
    request_data = json.loads(request.data)
    # Print request object data
    # TODO: incoming request do not correspond to the yaml specification
    print("Request Data:", request_data)

    is_fraud = call_fraud_detection(request_data)

    # Dummy response following the provided YAML specification for the bookstore
    order_status_response = {
        'orderId': '12345',
        'status': 'Order Approved',
        'suggestedBooks': [
            {'bookId': '123', 'title': 'The Best Book', 'author': 'Author 1'},
            {'bookId': '456', 'title': 'The Second Best Book', 'author': 'Author 2'}
        ]
    }

    return order_status_response


if __name__ == '__main__':
    # Run the app in debug mode to enable hot reloading.
    # This is useful for development.
    # The default port is 5000.
    app.run(host='0.0.0.0')
