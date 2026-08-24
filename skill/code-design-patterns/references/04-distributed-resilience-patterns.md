# Distributed & Resilience Patterns

Patterns that apply the moment a call crosses a process boundary. The governing assumption: the
network is unreliable, dependencies fail, and every remote call has three outcomes — success,
failure, and *unknown*. The third one is why idempotency matters.

## Contents

- [Circuit Breaker](#circuit-breaker) · [Retry with backoff](#retry-with-backoff-and-jitter) ·
  [Timeout budgets](#timeouts-and-deadline-budgets) · [Bulkhead](#bulkhead) ·
  [Fallback / graceful degradation](#fallback-and-graceful-degradation)
- [Rate limiting](#rate-limiting) · [Load shedding](#load-shedding)
- [Idempotency key](#idempotency-key) · [Saga](#saga) · [Outbox](#transactional-outbox) ·
  [Dead letter queue](#dead-letter-queue)
- [Caching](#caching-patterns) · [API Gateway / BFF](#api-gateway--bff) ·
  [Sidecar & Ambassador](#sidecar-and-ambassador) · [Service discovery](#service-discovery) ·
  [Leader election](#leader-election)

---

## Circuit Breaker

**Force:** a failing dependency should not consume your threads and cascade the outage upward.
Waiting 30 seconds to fail 10,000 times is worse than failing instantly.

A three-state machine — the canonical real-world **State pattern**:

- **Closed** — calls pass through; failures counted.
- **Open** — calls fail immediately without touching the dependency. After a cooldown → Half-Open.
- **Half-Open** — a limited number of trial calls. Success → Closed; failure → Open.

**Design details people omit:** what counts as a failure (timeouts yes, HTTP 400 no — a client
error is not the dependency being unhealthy); the threshold as a *rate over a window* rather than
a raw count; per-dependency breakers, never one global one; and what callers get when the circuit
is open (that is the Fallback decision).

**In the wild:** Resilience4j, Polly, gobreaker, Envoy outlier detection, Hystrix (deprecated but
the reference implementation).

## Retry with Backoff and Jitter

**Force:** transient failures resolve themselves; immediate retries turn a blip into a stampede.

Three rules, all mandatory:

1. **Retry only idempotent or idempotency-keyed operations.** Retrying a non-idempotent charge
   double-charges someone.
2. **Exponential backoff with jitter.** Without jitter, every client retries at the same instant
   and the recovering service falls over again — a retry storm. Full jitter:
   `sleep = random(0, min(cap, base * 2^attempt))`.
3. **Cap attempts and respect the deadline budget.** Retries at three stacked layers multiply:
   3 × 3 × 3 = 27 requests from one user action. Retry at *one* layer.

Do not retry: 4xx client errors, validation failures, or anything that failed deterministically.

## Timeouts and Deadline Budgets

Every remote call needs a timeout; the default of "none" is the most common production outage.

Better than per-call timeouts: a **deadline propagated down the call chain** (gRPC deadlines,
Go `context.WithTimeout`). Each hop gets the remaining budget, so a downstream service does not
spend 10 seconds on work the caller stopped waiting for 8 seconds ago.

Timeouts must shrink as you go deeper — a downstream timeout longer than its caller's is
meaningless work.

## Bulkhead

**Force:** one misbehaving dependency or tenant should not consume every thread and connection.

Isolate resources into compartments: separate connection pools or thread pools per downstream
dependency, or per tenant class. Named after ship compartments — a hull breach floods one section,
not the vessel.

**In the wild:** separate thread pools per integration in Resilience4j; separate node pools per
workload class in Kubernetes; per-tenant queues in multi-tenant SaaS.

## Fallback and Graceful Degradation

Decide explicitly what happens when a dependency is unavailable: cached/stale data, a default
value, a reduced-feature response, or an honest error. "Show the product page without the
personalised recommendations" is a better outcome than a 500.

**The rule:** a fallback must not itself be able to fail in the same way. A fallback that calls
another service has not removed the dependency.

## Rate Limiting

| Algorithm | Behaviour | Use for |
|---|---|---|
| **Token bucket** | Refills at rate R, capacity B — allows bursts up to B | Most API limits; the default choice |
| **Leaky bucket** | Drains at a constant rate — smooths bursts entirely | Traffic shaping, protecting a fixed-throughput backend |
| **Fixed window** | Count per calendar window | Simple, but allows 2× burst at the boundary |
| **Sliding window log** | Exact, per-request timestamps | Precision needed, memory available |
| **Sliding window counter** | Weighted blend of two windows | Good accuracy/memory trade-off; common in production |

**Distributed rate limiting** needs shared state (Redis with a Lua script for atomicity) or
per-node quotas that sum to the global limit. Say which in a design; per-node limits with N
nodes silently allow N× traffic during scaling.

Always return `Retry-After` and `429`, not a silent drop.

## Load Shedding

Under overload, reject work *early and cheaply* rather than accepting everything and timing out
on all of it. Prioritise: shed health-check-adjacent and batch traffic before user-facing traffic.
Related: **admission control**, and queue-time-based shedding (drop requests already older than
their deadline — the client has given up, so processing them is pure waste).

## Idempotency Key

**Force:** the client got a timeout. It does not know whether the payment went through. It must
be able to retry safely.

The client generates a unique key per logical operation and sends it with every retry; the server
stores key → result, and on a repeat returns the stored result instead of re-executing.

**Details that make it actually work:** store the key in the same transaction as the effect (or
use the outbox); define a TTL; handle the concurrent-duplicate case (unique constraint on the key,
second request waits or gets a conflict); and scope the key per endpoint and per customer.

**In the wild:** Stripe's `Idempotency-Key` header is the reference design.

## Saga

**Force:** a business transaction spans services; two-phase commit's distributed locks are too
slow and too fragile.

Decompose into local transactions, each publishing an event that triggers the next. On failure,
run **compensating transactions** backwards.

- **Choreography** — each service reacts to events. No central coordinator; simple for 2–3 steps,
  becomes impossible to trace beyond that.
- **Orchestration** — a coordinator (often a state machine) drives each step and compensation.
  Preferred past a few steps; the workflow is explicit and debuggable.

**What people get wrong:** compensation is not rollback. You cannot un-send an email; you send an
apology. Compensations must be idempotent and must handle "the thing I'm compensating never
actually happened". And every intermediate state is visible to users — the design must say what
they see.

**In the wild:** order → reserve inventory → charge payment → schedule shipping, with
release-inventory and refund as compensations. Temporal, AWS Step Functions, and Camunda are
orchestrators.

## Transactional Outbox

**Force:** "write to the database *and* publish to Kafka" cannot be atomic across two systems.
Doing them separately means either a lost event or an event for a write that rolled back.

Write the event into an `outbox` table in the *same* database transaction as the state change. A
separate relay polls or tails the CDC log and publishes to the broker, marking rows sent.

Gives at-least-once delivery — so consumers must be idempotent (see idempotency key). The
**Inbox** pattern is the consumer-side mirror: record processed message IDs to deduplicate.

## Dead Letter Queue

Messages that fail repeatedly get quarantined rather than blocking the queue or retrying forever.
The design must say: how many attempts before DLQ, who is alerted, and how messages are inspected
and replayed. A DLQ nobody monitors is a silent data-loss mechanism.

## Caching Patterns

| Pattern | Read path | Write path | Watch for |
|---|---|---|---|
| **Cache-aside** | Miss → load → populate | Write DB, invalidate cache | Most common; brief inconsistency window |
| **Read-through** | Cache loads on miss itself | — | Cleaner API, needs cache-side loader |
| **Write-through** | — | Write cache and DB synchronously | Consistent, slower writes |
| **Write-behind** | — | Write cache, flush to DB async | Fast; can lose data on crash |
| **Refresh-ahead** | Proactively refresh hot keys before expiry | — | Wasted work on cold keys |

**Failure modes to design against:** *stampede* (many concurrent misses on the same hot key —
solve with a per-key lock or single-flight); *penetration* (repeated misses for keys that do not
exist — cache the negative result); *avalanche* (many keys expiring together — add jitter to TTLs).

## API Gateway / BFF

**Gateway:** one entry point handling auth, rate limiting, routing, and TLS termination so every
service does not reimplement them. Risk: it becomes a monolith of business logic.

**Backend-for-Frontend:** a gateway per client type, because a mobile app wants fewer, smaller,
aggregated payloads than a web app. Avoids one API compromising for all clients.

## Sidecar and Ambassador

**Sidecar:** a helper process deployed alongside the service, sharing its lifecycle, handling
cross-cutting infrastructure (mTLS, retries, telemetry) — Envoy in a service mesh, a log shipper.
The application stays language-agnostic and free of that logic.

**Ambassador:** a sidecar specifically proxying *outbound* calls, applying retries, circuit
breaking, and discovery on the service's behalf.

## Service Discovery

Client-side (client queries a registry and load-balances itself — Consul, etcd, Eureka) versus
server-side (a load balancer or DNS name fronts instances — Kubernetes Services). Health checks
and how fast an unhealthy instance leaves rotation matter more than the mechanism.

## Leader Election

**Force:** exactly one instance should run a scheduled job or own a partition, but instances are
interchangeable and can die.

Use a lease with a TTL in a consensus store (etcd, ZooKeeper, Consul) or a database row with a
`heartbeat_at`. The leader renews; if it stops, the lease expires and another instance takes over.

**The correctness trap:** a leader that pauses (GC, network partition) may still believe it is
leader after its lease expires — two leaders briefly. Guard downstream writes with a monotonically
increasing **fencing token** so stale-leader writes are rejected.

---

## Composition

These are combined, not chosen between. A typical resilient outbound call, from outside in:

`deadline budget → bulkhead (isolated pool) → circuit breaker → retry with jitter → timeout → call`
with a fallback if the breaker is open, and an idempotency key if the call mutates anything.

A typical event-driven write: `local transaction + outbox row → relay → broker → idempotent
consumer with inbox dedupe → DLQ after N failures`.
