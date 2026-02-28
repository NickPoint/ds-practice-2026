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
from concurrent import futures

class FraudDetectionService(fraud_detection_grpc.FraudDetectionServiceServicer):

    def CheckFraud(self, request, context):
        score = 0
        reasons = []

        score, reasons = self.check_card(request, score, reasons)
        score, reasons = self.check_items(request, score, reasons)
        # score, reasons = self.check_device(request, score, reasons)
        score, reasons = self.check_address(request, score, reasons)
        score, reasons = self.check_terms(request, score, reasons)

        decision = True if score >=70 else False

        print(f"Fraud check completed. Score: {score}, Decision: {'FRAUD' if decision else 'LEGIT'}, Reasons: {', '.join(reasons)}")

        return fraud_detection.FraudResponse(
            is_fraud=decision,
            risk_score=score,
            reasons=reasons
        )

    def check_card(self, request, score, reasons):
        card = request.credit_card

        if not card.number:
            score += 40
            reasons.append("missing_card_number")

        if not card.cvv:
            score += 30
            reasons.append("missing_cvv")

        if card.number and len(card.number) < 12:
            score += 20
            reasons.append("invalid_card_length")

        return score, reasons

    def check_items(self, request, score, reasons):
        total_qty = sum(item.quantity for item in request.items)

        if total_qty > 10:
            score += 20
            reasons.append("high_quantity")

        if total_qty == 0:
            score += 30
            reasons.append("empty_cart")

        return score, reasons

    def check_device(self, request, score, reasons):
        known_os = ["iOS", "Android", "Windows", "MacOS", "Linux"]

        if request.device.os and request.device.os not in known_os:
            score += 15
            reasons.append("unknown_os")

        if not request.browser.name:
            score += 10
            reasons.append("missing_browser")

        return score, reasons

    def check_address(self, request, score, reasons):
        if not request.billing_address.country:
            score += 10
            reasons.append("missing_country")

        return score, reasons

    def check_terms(self, request, score, reasons):
        if not request.terms_accepted:
            score += 50
            reasons.append("terms_not_accepted")

        return score, reasons

def serve():
    # Create a gRPC server
    server = grpc.server(futures.ThreadPoolExecutor())
    # Add HelloService
    fraud_detection_grpc.add_FraudDetectionServiceServicer_to_server(FraudDetectionService(), server)
    # Listen on port 50051
    port = "50051"
    server.add_insecure_port("[::]:" + port)
    # Start the server
    server.start()
    print("Server started. Listening on port 50051.")
    # Keep thread alive
    server.wait_for_termination()

if __name__ == '__main__':
    serve()