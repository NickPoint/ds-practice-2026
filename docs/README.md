# Documentation

## Services Overview

This system consists of four main services: three backend microservices (fraud_detection, transaction_verification, suggestions) and an orchestrator that coordinates them. All services communicate via gRPC, with protocol buffers defined in the `utils/pb` folder.

### Fraud Detection Service

Located in `fraud_detection/`, this service implements a heuristic-based fraud detection system. It evaluates transaction requests for potential fraud by calculating a risk score based on multiple factors:

- **Credit Card Validation**: Checks for missing card number, CVV, or invalid card length.
- **Items Analysis**: Flags high quantities (>10 items) or empty carts.
- **Address Verification**: Ensures billing country is provided.
- **Terms Acceptance**: Requires terms to be accepted.

The service assigns points to each risk factor (e.g., missing CVV: +30 points, terms not accepted: +50 points). If the total score reaches 70 or more, the transaction is flagged as fraudulent. The response includes the fraud decision, risk score, and specific reasons for the score.

### Transaction Verification Service

Located in `transaction_verification/`, this service validates the completeness and correctness of transaction data. It performs comprehensive checks on:

- **User Information**: Validates name and email format.
- **Items**: Ensures items have names and positive quantities, and the cart is not empty.
- **Credit Card**: Verifies card number length/format, expiration date (MM/YY format, not expired), and CVV (3-4 digits).
- **Billing Address**: Requires all address fields (street, city, state, zip, country).
- **Shipping Method**: Accepts only "Standard" or "Express".
- **Terms Acceptance**: Must be true.

If any validation fails, the service returns a list of error codes. A transaction is valid only if no errors are found.

### Suggestions Service

Located in `suggestions/`, this service provides personalized book recommendations. It maintains a static catalog of 10 books and suggests up to 3 books that the user hasn't already ordered. The suggestions are based on filtering out books with titles matching the ordered items (case-insensitive).

The service uses a simple exclusion-based approach: remove ordered books from the catalog and return the first 3 remaining books.

### Orchestrator

Located in `orchestrator/`, this service acts as the main API gateway, exposing a REST endpoint (`/checkout`) that coordinates the three backend services. It uses threading to call all three services in parallel for improved performance:

- **Parallel Execution**: Launches three threads simultaneously to call fraud_detection, transaction_verification, and suggestions services.
- **Result Aggregation**: Collects results from all services into a shared dictionary.
- **Decision Logic**: Rejects orders if fraud is detected or transaction is invalid. Otherwise, approves the order and includes suggestions.

The orchestrator handles errors gracefully by logging exceptions and proceeding with default values (e.g., assuming no fraud if the service fails). It uses Flask with CORS enabled for the REST API and communicates with backend services via gRPC channels.

## Architecture

```mermaid
flowchart LR
  %% External clients
  User[User Browser] -->|HTTP<br/>http://localhost:8080| FE
  FE -->|HTTP REST<br/>POST /checkout<br/>http://orchestrator:5000| ORCH

  %% Docker network boundary
  subgraph NET[Docker Compose Network]
    FE[frontend<br/>Nginx<br/>Container port: 80<br/>Host: 8080→80]
    ORCH[orchestrator<br/>Flask REST API<br/>Container port: 5000<br/>Host: 8081→5000]

    FD[fraud_detection<br/>gRPC<br/>Container port: 50051<br/>Host: 50051→50051]
    TV[transaction_verification<br/>gRPC<br/>Container port: 50052<br/>Host: 50052→50052]
    SG[suggestions<br/>gRPC<br/>Container port: 50053<br/>Host: 50053→50053]

    ORCH -->|gRPC<br/>orchestrator → fraud_detection:50051| FD
    ORCH -->|gRPC<br/>orchestrator → transaction_verification:50052| TV
    ORCH -->|gRPC<br/>orchestrator → suggestions:50053| SG
  end

  %% Shared protobufs
  PB[(Protocol Buffers<br/>./utils/pb)] -.-> ORCH
  PB -.-> FD
  PB -.-> TV
  PB -.-> SG
```

## System Flow

```mermaid
sequenceDiagram
  autonumber
  actor User as User (Browser)
  participant FE as Frontend (Nginx)
  participant ORCH as Orchestrator (Flask /checkout)
  participant FD as Fraud Detection (gRPC :50051)
  participant TV as Transaction Verification (gRPC :50052)
  participant SG as Suggestions (gRPC :50053)

  User->>FE: Open UI / Submit checkout
  FE->>ORCH: POST http://orchestrator:5000/checkout<br/>(JSON)

  Note over ORCH: Parse JSON<br/>Start parallel calls

  par Fraud Check
    ORCH->>FD: CheckFraud(request)
    FD-->>ORCH: is_fraud, risk_score, reasons[]
  and Verification
    ORCH->>TV: VerifyTransaction(request)
    TV-->>ORCH: is_valid, error_codes[]
  and Suggestions
    ORCH->>SG: GetSuggestions(request)
    SG-->>ORCH: suggested_books[]
  end

  alt Fraud detected
    ORCH-->>FE: 400 Order Rejected\nFraud detected
    FE-->>User: Show rejection
  else Transaction invalid
    ORCH-->>FE: 400 Order Rejected\nValidation errors
    FE-->>User: Show rejection
  else OK
    ORCH-->>FE: 200 Order Approved\n+ suggestedBooks[]
    FE-->>User: Show success + suggestions
  end
```