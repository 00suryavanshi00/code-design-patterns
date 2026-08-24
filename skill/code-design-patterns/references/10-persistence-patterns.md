# Persistence & Data Patterns

Most designs that "handle concurrency" handle it in the wrong process. The moment state lives in a
database and more than one instance of the service is running, a mutex protects nothing: two
processes each hold their own lock and both write. The correctness mechanism has to live where the
state lives.

This file is the database-side answer to the questions the rest of the skill asks in memory — two
members reserving the last copy, two orders for the last item, a seat booked twice. If a design
says "take a lock" about rows in Postgres, it has not answered the question.

## Contents

- [Where the invariant lives](#where-the-invariant-lives) ·
  [Optimistic locking](#optimistic-locking-version-column) ·
  [Pessimistic locking](#pessimistic-locking-select--for-update) ·
  [Unique constraint as the mechanism](#unique-constraint-as-the-mechanism) ·
  [Conditional writes](#conditional-writes-compare-and-set-at-the-store)
- [Isolation levels](#isolation-levels-and-what-they-actually-permit) ·
  [Write skew](#write-skew-the-anomaly-that-survives-repeatable-read)
- [Aggregates and transaction boundaries](#aggregates-as-transaction-boundaries) ·
  [Idempotent writes](#idempotent-writes-and-natural-keys) ·
  [Soft delete](#soft-delete) · [Multi-tenant isolation](#multi-tenant-data-isolation)
- [Read models](#read-models-and-derived-state) · [Schema change](#schema-change)

---

## Where the invariant lives

Before choosing a mechanism, answer one question: **what is the invariant, and what is the smallest
thing that can enforce it atomically?**

| Invariant | Enforce it with |
|---|---|
| "This value must be unique" | A unique constraint. Not a `SELECT` then `INSERT`. |
| "This row must not change under me" | Optimistic version column, or `SELECT … FOR UPDATE` |
| "This counter must not go below zero" | A conditional `UPDATE … WHERE qty > 0`, checked by rows-affected |
| "These two rows must agree" | One transaction, at `SERIALIZABLE` — or model them as one row |
| "This must happen exactly once" | Idempotency key with a unique index (see `04-…`) |
| "These two systems must agree" | You cannot have this. Outbox + eventual consistency (see `04-…`) |

The design smell this table exists to catch: a check-then-act written in application code
(`if (!exists) insert`, `if (seat.free) book()`), which is a race whether or not a mutex is
mentioned, because the gap between the read and the write is where the second process lives.

## Optimistic locking (version column)

**Force:** conflicting concurrent updates are possible but rare, and holding a lock for the whole
user think-time — a form open in a browser for four minutes — is unacceptable.

Every row carries a `version`. Writers read it, then commit conditionally:

```sql
UPDATE listings SET price = ?, version = version + 1
 WHERE id = ? AND version = ?;     -- rows affected 0 → somebody else won
```

Zero rows affected is not an error to swallow: it means a concurrent write landed. The design must
say what happens next — refetch and retry, or surface a conflict to the user. `OptimisticLockException`
that reaches the user as a 500 is an unfinished design.

**Not this when:** conflicts are the normal case rather than the exception. A hot counter under
contention will livelock on retries; use an atomic increment or a conditional update instead.

**In the wild:** JPA `@Version`, ActiveRecord's `lock_version`, ETag + `If-Match` at the HTTP edge,
which is the same pattern spelled in headers.

## Pessimistic locking (`SELECT … FOR UPDATE`)

**Force:** the conflict window is short but the operation must not be retried — decrement stock,
allocate a seat, move money.

```sql
BEGIN;
SELECT qty FROM inventory WHERE sku = ? FOR UPDATE;   -- other writers block here
UPDATE inventory SET qty = qty - 1 WHERE sku = ?;
COMMIT;
```

Three things the design must state: the **lock order** (always the same, or two transactions
deadlock), the **lock timeout** (`NOWAIT` / `SKIP LOCKED` / `lock_timeout`), and what happens on
deadlock — the database will pick a victim, and somebody has to retry it.

`FOR UPDATE SKIP LOCKED` is the idiomatic way to build a work queue on a table: each worker claims
rows nobody else holds, no queue broker required, up to moderate throughput.

**Not this when:** the lock would be held across a network call. A row lock held while calling a
payment gateway ties database connections to a third party's latency — that is how a slow dependency
takes down a database.

**Simpler than both:** often the whole thing collapses into one statement.
`UPDATE inventory SET qty = qty - 1 WHERE sku = ? AND qty > 0` is atomic on its own; check
rows-affected, and "sold out" is the zero case. Reach for this before either lock.

## Unique constraint as the mechanism

**Force:** "there can only be one" — one active reservation per seat, one signup per email, one
charge per idempotency key — and the check-then-insert version has a race in the middle.

Make the database enforce it and treat the constraint violation as a normal control-flow outcome,
not an exception to log:

```sql
CREATE UNIQUE INDEX one_active_booking_per_seat
    ON bookings (seat_id) WHERE status = 'active';   -- partial index
```

This is the highest-leverage line in most booking designs: the invariant is enforced by the one
component that sees all writers, with no lock, no coordination and no retry storm.

**Not this when:** the invariant spans rows or tables ("no more than five active per user") — a
unique index cannot express it. Use a conditional update against a counter row, or a transaction at
`SERIALIZABLE`, and see write skew below.

## Conditional writes (compare-and-set at the store)

**Force:** the same problem in a store with no transactions.

CAS is not a relational idea; it is the general one. DynamoDB's `ConditionExpression`, Redis
`SET key val NX`, MongoDB's `findOneAndUpdate` with a filter on the current value, `etcd` compare-
and-swap, S3 conditional writes, an HTTP `If-Match` — all the same shape: *write only if the state
you read is still the state that is there.*

Design rule: if the store offers a conditional write, the invariant belongs in the condition. A
read-modify-write in application code is a race with extra steps, and "we use Redis for the lock" is
a distributed lock (`04-distributed-resilience-patterns.md`) with all of that pattern's caveats —
clock skew, lost leases, and the need for a fencing token.

## Isolation levels and what they actually permit

Designs say "in a transaction" as if that settled it. What a transaction guarantees depends entirely
on the isolation level, and almost every database's default is weaker than people assume.

| Level | Prevents | Still permits |
|---|---|---|
| Read committed *(Postgres, SQL Server, Oracle default)* | Dirty reads | Non-repeatable reads, phantoms, **lost updates**, write skew |
| Repeatable read / snapshot *(MySQL InnoDB default)* | Non-repeatable reads | Phantoms (not in InnoDB), **write skew** |
| Serializable | Everything above | Nothing — but transactions abort and must be retried |

**The one to internalise:** at read committed, two transactions reading the same row and writing
back a derived value silently lose one of the writes. `SELECT balance` → compute → `UPDATE balance`
is broken at the default isolation level of most production databases. `UPDATE … SET balance =
balance - 10` is not, because the read and the write are the same statement.

Postgres's `SERIALIZABLE` (SSI) is genuinely serializable and genuinely usable — the cost is that
transactions can fail with a serialization error, so **every** caller needs a retry loop. A design
that chooses `SERIALIZABLE` without mentioning that retry loop has not chosen it.

## Write skew: the anomaly that survives repeatable read

Two transactions read an overlapping set, each verifies a condition still holds, and each writes a
*different* row. No conflict is detected, yet the invariant across the rows is now violated.

The canonical case: "at least one doctor must be on call." Two doctors check the count (two on
call), each sees it is safe to leave, each updates their own row. Zero doctors on call, no error
raised, every transaction committed. Repeatable read does not stop this; neither does a per-row
lock, because the rows written were never in conflict.

Fixes, in order of preference: materialise the invariant into a single row that both transactions
must write (a counter, a schedule row); take an explicit lock on that shared row; or run at
`SERIALIZABLE` and retry. The general lesson — **an invariant over a set needs a lock on the set, or
a row that represents the set** — is the one reviewers probe for.

## Aggregates as transaction boundaries

**Force:** which objects must be consistent *right now*, and which can be consistent in a second?

An aggregate is the unit that is loaded, checked and saved atomically: one transaction, one
aggregate. Its boundary is a design decision with a direct performance consequence — a large
aggregate (Order with 10,000 line items) means contention and long transactions; a small one means
cross-aggregate rules become eventual.

Rule of thumb: reference other aggregates **by id**, not by object. A design that navigates
`order.customer.address.country` from inside a transaction has drawn no boundary at all, and will
load half the database to check one field.

**Not this when:** the domain is genuinely CRUD. Aggregate design is a cost; charge it where
invariants exist.

## Idempotent writes and natural keys

A retried request must not create a second row. Two mechanisms, in preference order:

1. **A natural key** — the write is keyed on something the client already owns
   (`payment_id`, `(order_id, line_no)`), so a retry is an upsert on the same key.
2. **An idempotency key** — a client-supplied UUID with a unique index, storing the *response* so a
   retry returns the original result rather than replaying the effect. See `04-…` for the TTL and
   concurrent-duplicate handling.

`INSERT … ON CONFLICT DO NOTHING` / `MERGE` is how both are spelled. The design should say which
column carries the uniqueness — "we'll deduplicate" without naming a key is not a mechanism.

## Soft delete

**Force:** rows must disappear from the product but survive for audit, undo, or referential sanity.

`deleted_at TIMESTAMP NULL`, and every query filters it. That last clause is the whole cost, and
it is larger than it looks:

- Every query, view, join, and report must remember the filter. The one that forgets is a data leak,
  and it is usually a report.
- Unique constraints stop working as intended — a "deleted" row still occupies the email address
  unless the index is partial (`WHERE deleted_at IS NULL`).
- Foreign keys still point at rows the product considers gone.
- Right-to-erasure requests are not satisfied by a flag.

**Preferable when it fits:** move the row to an archive/history table on delete. The live table stays
honest, the filter cannot be forgotten, and the audit trail is explicit rather than implied.

**In the wild:** most ORMs offer soft delete as a default-on scope precisely because forgetting the
filter is so common — and that default is itself a leaky abstraction the moment you write raw SQL.

## Multi-tenant data isolation

Three shapes, and the choice is mostly about blast radius and compliance, not about code:

| Shape | Isolation | Cost |
|---|---|---|
| Shared tables + `tenant_id` | Weakest — one missing `WHERE` is a cross-tenant leak | Cheapest to run; noisy-neighbour effects |
| Schema per tenant | Strong-ish; migrations run N times | Middling; connection/pooling pressure at high N |
| Database per tenant | Strongest; per-tenant restore and residency | Most expensive; hardest to operate at N in the thousands |

If the answer is shared tables — it usually is — the `tenant_id` filter must be **structurally
impossible to forget**: Postgres row-level security, or a repository layer that takes the tenant from
an ambient request context and no query path that bypasses it. "Developers will remember" is not an
isolation strategy; it is the design flaw that produces the incident.

**Always state:** where the tenant id enters (token claim, not a request body field the client can
set), and how a cross-tenant read would be detected — a test that queries as tenant A for tenant B's
row and expects zero results is the cheapest guard in this file.

## Read models and derived state

When reads and writes want different shapes, stop forcing one schema to serve both: a denormalised
read model, a materialised view, or a search index fed from the write side. That is CQRS
(`02-modern-application-patterns.md`) at the data layer.

The design must answer two things it usually skips: **how the read model is rebuilt from scratch**
(if it cannot be, it is not derived state, it is a second source of truth), and **what staleness the
product tolerates** — stated in seconds, and visible in the UI if it matters.

Feeding it: change data capture (Debezium reading the WAL) is preferable to dual writes, because
dual writes lose data on partial failure — see the anti-pattern in `06-…` and the outbox in `04-…`.

## Schema change

Migrations are the expand–contract pattern (`04-distributed-resilience-patterns.md`) with a database
attached: add nullable column → backfill in batches → switch readers → enforce the constraint → drop
the old. Two operational notes a design should include when it changes a live table:

- **Never a blocking rewrite on a hot table** — adding a `NOT NULL` column with a default, or an
  index without `CONCURRENTLY`, takes a lock that queues every writer behind it.
- **Backfills are batched and resumable** — a single `UPDATE` over ten million rows is one long
  transaction, one enormous WAL segment, and one very bad afternoon.
