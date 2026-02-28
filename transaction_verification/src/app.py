import sys
import os
from datetime import datetime
import re

# This set of lines are needed to import the gRPC stubs.
# The path of the stubs is relative to the current file, or absolute inside the container.
# Change these lines only if strictly needed.
FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
transaction_verification_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/transaction_verification'))
sys.path.insert(0, transaction_verification_grpc_path)
import transaction_verification_pb2 as transaction_verification
import transaction_verification_pb2_grpc as transaction_verification_grpc

import grpc
from concurrent import futures

class TransactionVerificationService(transaction_verification_grpc.TransactionVerificationServiceServicer):
    def VerifyTransaction(self, request, context):
        errors = []

        self.validate_user(request.user, errors)
        self.validate_items(request.items, errors)
        self.validate_card(request.credit_card, errors)
        self.validate_address(request.billing_address, errors)
        self.validate_shipping_method(request.shipping_method, errors)
        self.validate_terms(request.terms_accepted, errors)

        is_valid = len(errors) == 0

        print(
            f"Transaction verification completed. "
            f"Result: {'VALID' if is_valid else 'INVALID'}. "
            f"Errors: {', '.join(errors) if errors else 'none'}"
        )

        return transaction_verification.TransactionResponse(
            is_valid=is_valid,
            errors=errors
        )

    def validate_user(self, user, errors):
        if not user.name.strip():
            errors.append("missing_user_name")

        if not user.contact.strip():
            errors.append("missing_user_contact")
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", user.contact.strip()):
            errors.append("invalid_user_contact")

    def validate_items(self, items, errors):
        if len(items) == 0:
            errors.append("empty_items")
            return

        for item in items:
            if not item.name.strip():
                errors.append("missing_item_name")
            if item.quantity <= 0:
                errors.append("invalid_item_quantity")

    def validate_card(self, card, errors):
        number = card.number.replace(" ", "").replace("-", "")
        exp = card.expiration_date.strip()
        cvv = card.cvv.strip()

        if not number:
            errors.append("missing_card_number")
        elif not number.isdigit() or len(number) < 13 or len(number) > 19:
            errors.append("invalid_card_number")

        if not exp:
            errors.append("missing_expiration_date")
        elif not re.fullmatch(r"(0[1-9]|1[0-2])/\d{2}", exp):
            errors.append("invalid_expiration_date")
        elif self.is_expired(exp):
            errors.append("card_expired")

        if not cvv:
            errors.append("missing_cvv")
        elif not re.fullmatch(r"\d{3,4}", cvv):
            errors.append("invalid_cvv")

    def validate_address(self, address, errors):
        if not address.street.strip():
            errors.append("missing_billing_street")
        if not address.city.strip():
            errors.append("missing_billing_city")
        if not address.state.strip():
            errors.append("missing_billing_state")
        if not address.zip.strip():
            errors.append("missing_billing_zip")
        if not address.country.strip():
            errors.append("missing_billing_country")

    def validate_shipping_method(self, shipping_method, errors):
        allowed = {"Standard", "Express"}

        if not shipping_method.strip():
            errors.append("missing_shipping_method")
        elif shipping_method not in allowed:
            errors.append("invalid_shipping_method")

    def validate_terms(self, terms_accepted, errors):
        if not terms_accepted:
            errors.append("terms_not_accepted")

    def is_expired(self, expiration_date):
        month_str, year_str = expiration_date.split("/")
        month = int(month_str)
        year = 2000 + int(year_str)

        now = datetime.utcnow()
        return year < now.year or (year == now.year and month < now.month)

def serve():
    # Create a gRPC server
    server = grpc.server(futures.ThreadPoolExecutor())
    # Add HelloService
    transaction_verification_grpc.add_TransactionVerificationServiceServicer_to_server(TransactionVerificationService(), server)
    # Listen on port 50052
    port = "50052"
    server.add_insecure_port("[::]:" + port)
    # Start the server
    server.start()
    print("Server started. Listening on port 50052.")
    # Keep thread alive
    server.wait_for_termination()

if __name__ == '__main__':
    serve()