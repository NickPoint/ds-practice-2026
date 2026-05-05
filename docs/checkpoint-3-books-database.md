# Checkpoint 3 Books Database

## Overview

This checkpoint adds a replicated key-value books database. The key is the book
title and the value is the available stock count. The public database operations
are `Read` and `Write`, with an extra `ReserveStock` operation used by order
executors to handle concurrent purchases atomically.

## Services

- `books_database_1`: head replica
- `books_database_2`: middle replica
- `books_database_3`: tail replica
- `order_executor_1` and `order_executor_2`: replicated executors with Bully
  leader election
- `order_queue`: stores approved orders including item titles and quantities

## Consistency Protocol

The database uses chain replication:

1. Clients may call any replica, but writes are routed to the head.
2. The head applies a write locally and forwards it to the middle replica.
3. The middle replica applies the write and forwards it to the tail.
4. The write is acknowledged only after the downstream chain accepts it.
5. Reads are routed to the tail replica.

Because reads come from the tail and successful writes are acknowledged only
after propagation through the chain, clients observe a single serialized order of
committed writes. This provides sequential consistency for successful operations.

## Concurrent Orders

Concurrent stock decrements are handled by `ReserveStock`.

`ReserveStock(title, quantity)` is routed to the head replica. The head keeps a
write lock, checks the current stock, calculates the new value, and commits that
new value through the chain as one serialized operation. This prevents lost
updates when two orders try to buy the same book at the same time.

The executor still performs a `Read` before reservation for logging and to match
the assignment flow, but correctness does not depend on the read result.

## Trade-offs

- Reads are consistent but concentrated on the tail replica.
- Writes are serialized at the head, so write throughput is limited by the head
  and by propagation through the chain.
- If a middle or tail replica is unavailable, new writes fail instead of being
  acknowledged on only part of the chain.
- This implementation does not perform automatic chain reconfiguration after a
  database replica failure. It favors consistency over availability.

## Order Flow

1. The orchestrator validates the checkout request.
2. Approved orders are enqueued with item titles and quantities.
3. The elected order executor dequeues the next order.
4. For each item, the executor reads the current stock and calls
   `ReserveStock`.
5. The database commits the reservation through the chain.
