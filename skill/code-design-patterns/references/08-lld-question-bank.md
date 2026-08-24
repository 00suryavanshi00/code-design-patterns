# LLD Question Bank

Thirty canonical low-level-design problems, selected by how often they actually appear in
machine-coding and object-oriented-design rounds (Amazon, Google, Microsoft, Uber, Atlassian,
Flipkart, Swiggy, Razorpay, PhonePe, Salesforce, Goldman Sachs and similar).

Each entry gives:
- **Axis of change** — the thing the interviewer will ask you to extend.
- **Core abstractions** — what a good answer models.
- **Patterns that legitimately fit** — not a shopping list; the ones with a real force behind them.
- **Trap** — the plausible-sounding wrong answer.
- **Probe** — the follow-up that separates a memorised answer from a designed one.

Use these to practise, to generate a problem, or as ground truth when grading a design against
`07-evaluation-rubric.md`.

> The four patterns that carry most of this list are **Strategy, State, Observer, and Factory**.
> If a design uses none of them, check whether it missed a variation point; if it uses all four
> on a small problem, check for pattern-stuffing.

---

## Tier A — near-certain to appear

### 1. Parking Lot
**Axis:** allocation policy and pricing rules.
**Core:** `ParkingLot → Floor → Spot`, `Vehicle`, `Ticket` (state machine), `Money`.
**Patterns:** Strategy (allocation, pricing — two separate strategies, they change for different
reasons), State (ticket lifecycle), Repository if persistence is in scope.
**Trap:** a `VehicleFactory` producing `Car`/`Bike`/`Truck` subclasses that differ only by an enum;
a singleton `ParkingLotManager`.
**Probe:** two entrances race for the last spot — show me the atomic operation. Then: add EV
charging bays that only some vehicles can use.

### 2. Elevator System
**Axis:** the scheduling algorithm.
**Core:** `ElevatorCar` (state: idle/moving-up/moving-down/doors-open), `Request` (internal vs.
external), `Dispatcher`, `Building`.
**Patterns:** State (car), Strategy (dispatch: FCFS, SCAN/LOOK, nearest-car), Command (queued
requests), Observer (floor displays).
**Trap:** modelling direction as a boolean; one queue for all cars; ignoring that an external
request has a direction and an internal one does not.
**Probe:** four cars, sixteen floors — how does a request get assigned, and what happens when a
car goes out of service mid-journey?

### 3. Vending Machine
**Axis:** payment methods and product catalogue.
**Core:** `VendingMachine` with explicit states (Idle → ItemSelected → PaymentPending →
Dispensing), `Inventory`, `Coin`/`Payment`.
**Patterns:** State (the canonical teaching case), Strategy (payment), Command (dispense).
**Trap:** `if (status == ...)` in every method instead of a state object; forgetting change-making
and the "insufficient change" path.
**Probe:** power fails mid-dispense — what state does it resume in?

### 4. Rate Limiter
**Axis:** the algorithm, and single-node vs. distributed.
**Core:** `RateLimiter` interface, per-key buckets, a clock abstraction.
**Patterns:** Strategy (token bucket / leaky bucket / sliding window), Decorator (wrap a client),
Factory (per-key limiter creation).
**Trap:** fixed-window counters presented without acknowledging the 2× boundary burst; calling
`System.currentTimeMillis()` inline so it cannot be tested.
**Probe:** now it runs on 10 nodes. Does each node get limit/10, or do you need shared state?
What does the Redis version do about atomicity?

### 5. LRU / LFU Cache
**Axis:** eviction policy; then thread safety.
**Core:** hash map + doubly-linked list for O(1) LRU; frequency buckets for LFU.
**Patterns:** Strategy (eviction policy), Decorator (add metrics/TTL layers), Template Method
(shared cache skeleton).
**Trap:** claiming O(1) with a structure that is O(n); losing the map/list invariant on eviction.
**Probe:** make it thread-safe without a single global lock — what do you shard on?

### 6. Notification / Alerting System
**Axis:** channels (email, SMS, push, webhook) and routing rules.
**Core:** `Notification`, `Channel` interface, `Template`, `UserPreferences`, retry policy.
**Patterns:** Strategy or Plugin (channels), Observer/Pub-Sub (events → notifications), Decorator
(retry, rate limit, dedupe wrappers), Chain of Responsibility (fallback channel ladder).
**Trap:** synchronous sending in the request path; no deduplication, so a retry storm spams users.
**Probe:** the SMS provider is down for 20 minutes. What happens to those notifications, and does
the user get four of them when it recovers?

### 7. Library Management System
**Axis:** loan rules and fine policy.
**Core:** `Book` (title/metadata) vs. `BookCopy` (physical item with its own state) — modelling
these as one class is the main mistake, `Member`, `Loan`, `Reservation`.
**Patterns:** State (copy: available/loaned/reserved/lost), Strategy (fine calculation), Observer
(reservation-available notification).
**Probe:** two members reserve the last copy — who gets it, and how is the queue modelled?

### 8. Splitwise / Expense Sharing
**Axis:** split types.
**Core:** `Group`, `Expense`, `Split` (equal/exact/percentage/shares), `BalanceSheet`, `Money`.
**Patterns:** Strategy (split calculation), Factory (split construction with validation),
Command (an expense as a reversible transaction).
**Trap:** floating-point money; splits that do not sum to the total; simplifying debts without
being asked (and without saying it changes who owes whom).
**Probe:** three people, circular debts — implement debt simplification and tell me what it costs.

### 9. Movie Ticket Booking (BookMyShow)
**Axis:** pricing and seat-selection rules.
**Core:** `Theatre → Screen → Seat`, `Show`, `Booking` (state machine with a hold/timeout),
`SeatLock`.
**Patterns:** State (booking), Strategy (pricing by seat class/time), Observer (seat-map updates).
**Trap:** no seat-hold mechanism — two users book the same seat. This problem is *about* the lock.
**Probe:** a user holds seats and abandons the checkout. How and when are they released, and what
happens if the release job and the payment callback race?

### 10. Chess / Tic-Tac-Toe / Snakes and Ladders
**Axis:** new piece types, new rules, board size.
**Core:** `Board`, `Piece` hierarchy with `validMoves()`, `Player`, `Move`, `GameState`.
**Patterns:** Strategy (per-piece movement), Command (move, for undo and history), State (game
status), Factory (piece creation), Memento (undo).
**Trap:** movement logic in a giant `switch` in `Board`; forgetting that check/checkmate makes
move validity depend on global board state, not just the piece.
**Probe:** implement undo, then castling — castling is the rule that breaks naive per-piece
movement design.

---

## Tier B — very common

### 11. Logging Framework (log4j-like)
**Axis:** appenders (console/file/network), formats, levels.
**Patterns:** Chain of Responsibility (level-based handler chain), Strategy (formatter),
Observer (multiple appenders), Singleton (a *defensible* use: one logger registry — but injected).
**Probe:** make it non-blocking — what happens when the disk is slow?

### 12. ATM
**Axis:** transaction types and note-dispensing algorithm.
**Patterns:** State (card inserted → PIN → transaction → dispense), Strategy (note denomination
selection), Command (transaction, for audit and rollback).
**Probe:** the cash dispenses but the network drops before the account is debited.

### 13. Ride-Hailing Dispatch (Uber/Ola)
**Axis:** driver-matching algorithm and pricing.
**Core:** `Rider`, `Driver` (state), `Trip` (state machine), `Location`, `MatchingService`.
**Patterns:** Strategy (matching, surge pricing), State (trip and driver), Observer (location
updates).
**Probe:** two riders are matched to the same driver simultaneously.

### 14. Food Delivery (Swiggy/Zomato)
**Axis:** restaurant search/ranking, delivery-partner assignment, offers.
**Patterns:** Strategy (ranking, offer application), State (order lifecycle), Observer (order
tracking), Saga (order → payment → restaurant accept → assign partner, with compensations).
**Probe:** the restaurant rejects after payment succeeded.

### 15. Online Shopping / Amazon Cart & Checkout
**Axis:** discounts and payment methods.
**Patterns:** Strategy (discount, payment, shipping), Decorator (stacking discounts — and the
order-of-application question this exposes), State (order), Saga (checkout across services).
**Probe:** two coupons, one percentage and one flat — which applies first, and where does that
rule live?

### 16. Digital Wallet (Paytm/PhonePe)
**Axis:** transaction types and funding sources.
**Core:** `Account`, `Ledger` (append-only — this is the right model, not a mutable balance),
`Transaction` (state machine).
**Patterns:** Command (transactions), Event Sourcing (ledger), Saga (transfer between wallets),
Idempotency key (retry safety).
**Trap:** a mutable `balance` field as the source of truth; non-idempotent transfers.
**Probe:** the same transfer request arrives twice due to a client retry.

### 17. Message Queue / Pub-Sub
**Axis:** delivery semantics, multiple topics, consumer groups.
**Core:** `Topic`, `Partition`/`Queue`, `Producer`, `Consumer` with offsets.
**Patterns:** Observer (subscription), Producer-consumer, Worker pool, Strategy (retention,
partitioning), Dead letter queue.
**Probe:** at-least-once vs. exactly-once — which are you giving me, and what must the consumer do?

### 18. URL Shortener
**Axis:** ID generation and storage.
**Patterns:** Strategy (encoding: counter+base62 / hash+collision / pre-generated key range),
Repository, Cache-aside.
**Trap:** MD5-truncation without a collision story.
**Probe:** two servers generating IDs concurrently without coordination.

### 19. Task Scheduler / Cron
**Axis:** trigger types (interval, cron expression, one-shot) and execution guarantees.
**Patterns:** Command (jobs), Strategy (trigger), Worker pool, Leader election (only one node runs
a scheduled job), Priority queue / timing wheel.
**Probe:** the node running a job dies mid-execution.

### 20. In-Memory Key-Value Store with TTL
**Axis:** eviction and expiry strategy, persistence.
**Patterns:** Strategy (eviction), Observer (expiry callbacks), Command (write-ahead log).
**Probe:** lazy expiry vs. active sweeping — which, and what does each cost?

---

## Tier C — appears regularly, good differentiators

### 21. Custom HashMap
Collision handling (chaining vs. open addressing), resize/rehash, load factor. **Probe:** make it
concurrent — segment locking vs. CAS on buckets.

### 22. Text Editor with Undo/Redo
**Patterns:** Command (each edit), Memento (snapshots), Composite (document tree). **Probe:**
compound operations — typing 40 characters should be one undo, not forty.

### 23. Snake and Ladder / Board Game Engine
Generic engine + specific rules. **Patterns:** Strategy (dice, rules), State, Observer.

### 24. Inventory / Warehouse Management
**Patterns:** Repository, Specification (stock queries), Observer (reorder threshold), Optimistic
concurrency (stock decrements — the interesting part).
**Probe:** two orders for the last item.

### 25. Hotel / Car Rental Booking
Overlapping-interval availability is the core problem. **Patterns:** Strategy (pricing), State
(reservation), Specification (search filters).
**Probe:** prevent double-booking without locking the entire inventory.

### 26. Social Media Feed
**Patterns:** Strategy (ranking), Observer (follow graph updates), Fan-out on write vs. read,
Cache-aside. **Probe:** a celebrity with 30M followers posts — which fan-out, and why the hybrid?

### 27. Chat Application (1:1 and group)
**Core:** `User`, `Conversation`, `Message`, delivery receipts as a state machine.
**Patterns:** Observer/Pub-Sub, Mediator (chat room), Command (message with retry), Idempotency
(client-generated message IDs).
**Probe:** ordering guarantees in a group chat with clients on flaky networks.

### 28. File System Metadata (inodes, directories)
**Patterns:** Composite (the canonical case), Visitor (traversal: `du`, `find`, permissions
check), Iterator. **Probe:** hard links and symlinks break the pure tree — how does your Composite
handle a cycle?

### 29. Payment Gateway Integration Layer
**Axis:** providers.
**Patterns:** Adapter / Anti-Corruption Layer (per provider), Strategy (routing), Circuit breaker
+ retry + idempotency key, Outbox (webhook processing).
**Probe:** a webhook arrives twice, and out of order relative to your API response.

### 30. Feature Flag / Experimentation Service
**Patterns:** Strategy (targeting rules), Specification (rule composition), Cache-aside (flag
evaluation must be sub-millisecond and cannot fail), Null Object (default when the service is
unreachable).
**Probe:** the flag service is down — what does the SDK return, and how does it fail safe?

---

## Grading a design against this bank

1. Identify the problem's **axis of change** from the entry above.
2. Check whether the design put an interface on *that* axis (rubric dimension 3), and did **not**
   put interfaces on axes that do not vary (dimension 5).
3. Check whether the design addressed the **probe** — the probes are exactly the places where a
   memorised answer breaks. A design that handles the probe unprompted is a strong signal.
4. Check for the entry's **trap**.
5. Score with `07-evaluation-rubric.md`.

## Generating a new problem in this style

State the domain, three or four functional requirements, one scale/concurrency constraint, and one
explicit non-goal. Then hold back a follow-up that stresses the axis of change. A problem without
a concurrency constraint and without a stated axis of change will produce a design you cannot
grade meaningfully — those two elements are what make the answer discriminating.
