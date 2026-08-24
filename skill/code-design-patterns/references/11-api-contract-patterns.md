# API & Contract Patterns

An interface inside a process can be changed by whoever compiles it. An interface across a process
boundary cannot: somebody else's deploy schedule now owns it. Every pattern here exists because of
that one asymmetry.

The design question is not "what endpoints do we need" — it is **what have we promised, and how do
we change it without a coordinated release**.

## Contents

- [The contract is the promise, not the code](#the-contract-is-the-promise-not-the-code) ·
  [Resource shape and DTOs](#resource-shape-and-dtos-at-the-edge) ·
  [Errors are part of the contract](#errors-are-part-of-the-contract)
- [Idempotent HTTP semantics](#idempotent-http-semantics) ·
  [Long-running operations](#long-running-operations) ·
  [Batch endpoints and partial failure](#batch-endpoints-and-partial-failure)
- [Pagination](#pagination) · [Filtering and field selection](#filtering-and-field-selection)
- [Compatible evolution](#compatible-evolution) · [Versioning](#versioning) ·
  [Deprecation](#deprecation-and-sunset)
- [Webhooks as an outbound contract](#webhooks-as-an-outbound-contract) ·
  [Contract tests](#contract-tests)

---

## The contract is the promise, not the code

Three things are promised the moment a client integrates, whether or not they were written down:
the **shape** (fields and types), the **semantics** (what an operation does, and what it does twice),
and the **failure modes** (which errors are retryable). Generated OpenAPI covers the first and
almost never the other two, which is why "we have a spec" and "we have a contract" are different
claims.

Write the contract before the handler. If you cannot state what a repeated call does, the endpoint
is not designed yet.

## Resource shape and DTOs at the edge

Serialising domain entities directly is the most common contract mistake: it leaks internal fields
(`passwordHash`, `internalScore`, `deletedAt`), welds the public shape to the database schema, and
turns every refactor into a client-visible change. A DTO at the edge is not ceremony — it is the
seam that lets the domain move (see `02-modern-application-patterns.md`).

**Rules that pay for themselves:**

- **Nulls are a decision, not an accident.** `"discount": null` and an absent `discount` must not
  mean different things to different clients.
- **Money is an object, never a float.** `{"amount": "10.50", "currency": "USD"}` — minor units or a
  decimal string, never IEEE 754.
- **Timestamps are RFC 3339 with an offset.** A bare local time is a bug waiting for a client in
  another zone.
- **Ids are opaque strings** to the client, even when they are integers in your database. This keeps
  a future migration from being a breaking change.
- **Enums are the hardest field to evolve** — see compatible evolution below.

## Errors are part of the contract

Most designs specify success and hand-wave failure, so clients end up parsing English error strings.
An error response needs a **stable machine-readable code**, a human message, and enough structure to
act on:

```json
{ "type": "https://api.example.com/errors/insufficient-funds",
  "title": "Insufficient funds",
  "status": 402,
  "code": "insufficient_funds",
  "detail": "Balance 12.00 USD is below the 30.00 USD charge",
  "instance": "/charges/ch_9f2",
  "request_id": "req_01HZ…" }
```

That is RFC 9457 (*problem+json*), and using it means clients get one parser rather than one per
endpoint. The `code` is the part clients branch on, so it is as much a public contract as the field
names — do not rename codes.

**The taxonomy the design must state:** which errors are the client's fault (4xx, never retry, fix
the request), which are ours and transient (429/503, retry with backoff — say whether `Retry-After`
is sent), and which are ours and permanent (500, retrying makes it worse). A client cannot implement
`04-distributed-resilience-patterns.md`'s retry policy against an API that does not answer this.

Always return a **request id** on errors and log it. It converts "the API is broken" into one grep.

## Idempotent HTTP semantics

| Method | Safe | Idempotent | Use for |
|---|---|---|---|
| `GET`, `HEAD` | yes | yes | Reads. Never mutate in a `GET` — crawlers and prefetchers exist. |
| `PUT` | no | **yes** | Client-chosen id, full replacement: `PUT /reservations/{client-uuid}` |
| `DELETE` | no | **yes** | Second delete returns 204/404, not an error |
| `POST` | no | **no** | Creation with a server-chosen id, and non-CRUD actions |
| `PATCH` | no | not inherently | Partial update; make it idempotent with a version precondition |

**The decision that matters:** a create that a client may retry after a timeout is either a `PUT`
with a client-generated id, or a `POST` carrying an **`Idempotency-Key`** header whose stored
response is replayed on retry (`04-…`). There is no third option — "the client shouldn't retry" is
not a design, because the network will retry for it.

Preconditions are the read-modify-write version of the same idea: return an `ETag`, require
`If-Match` on update, and answer `412 Precondition Failed` when the resource moved. It is optimistic
locking (`10-persistence-patterns.md`) expressed in headers.

## Long-running operations

If the work outlives a sane HTTP timeout, do not hold the connection. Accept and hand back a handle:

```
POST /exports          → 202 Accepted, Location: /exports/e_42
GET  /exports/e_42     → { "status": "running" | "succeeded" | "failed", "result": …, "error": … }
```

The design must state polling guidance (or a webhook), how long the status resource lives, and
whether re-submitting the same request creates a second job — which is the idempotency question
again.

## Batch endpoints and partial failure

A batch endpoint's real design question is what happens when item 37 of 100 fails. There are exactly
two honest answers, and the contract must pick one: **all-or-nothing** (one transaction, one error,
nothing applied) or **per-item results**, where the response carries a status per element and the
overall status is 200 even though some items failed. What breaks clients is a batch that fails
halfway and reports a single top-level error, leaving them unable to tell which half landed.

## Pagination

**Offset/limit** is simple and wrong at scale in two ways: `OFFSET 100000` makes the database walk
100,000 rows, and rows inserted during paging shift the window, so clients silently skip or repeat
items.

**Keyset (cursor) pagination** pages on a stable sort key instead:

```sql
SELECT … FROM events WHERE (created_at, id) < (?, ?) ORDER BY created_at DESC, id DESC LIMIT 50;
```

Return the cursor as an **opaque string** — clients must not construct it, or its encoding becomes
part of the contract. Always include a tiebreaker column: a sort on a non-unique field has no stable
order, and pages will overlap.

**State in the contract:** the default and maximum page size (an unbounded `limit` is a denial of
service you shipped yourself), whether the total count is available (on large tables it usually
should not be), and that the cursor may expire.

## Filtering and field selection

Ad-hoc query languages in URL parameters (`?filter=price>10 AND tag in (a,b)`) become a contract you
must parse, validate, index, and support forever. Prefer a small, closed set of named filters that
map to indexed columns, and add filters deliberately. Sparse fieldsets (`?fields=id,name`) are worth
it only when payloads are genuinely large; otherwise they multiply the shapes you must test.

If clients truly need arbitrary shapes, that is the argument for GraphQL — with its own cost, since
now every client query is a query planner input you cannot see in advance.

## Compatible evolution

The rules, in the order they get broken:

1. **Add, never repurpose.** A new optional field is compatible. Changing what an existing field
   means is invisible to type checkers and breaks clients silently — the worst failure mode there is.
2. **Widen inputs, narrow outputs.** Accept more than you emit. Never make a request field required
   after launch; never remove a response field clients may read.
3. **Be a tolerant reader.** Ignore unknown fields on the way in. A client that rejects a response
   because it grew a field prevents you from ever adding one.
4. **Enums are the trap.** Adding a value breaks any client that switches exhaustively, so document
   from day one that unknown values must map to a default, and never send a new enum value to an
   existing version without a migration window.
5. **Optional means optional forever.** Loosening is compatible; tightening is not.
6. **In gRPC/protobuf:** never reuse a field number, `reserved` the retired ones, and treat
   `required` as a mistake the language already learned from.

The mechanism for a change that cannot be additive is expand–contract
(`04-distributed-resilience-patterns.md`): emit both shapes, migrate readers, verify with a metric
that the old one is unread, then remove it.

## Versioning

Version when compatible evolution genuinely cannot express the change — a resource that split in
two, a semantic reversal. Versioning is not free: every live version is a code path, a test matrix
row, and a support burden, so the number of live versions is a design constraint to state.

| Where | Trade-off |
|---|---|
| URL path (`/v2/orders`) | Most visible, easiest to route and cache, ugliest to migrate piecemeal |
| Header (`Accept: application/vnd.api+json;version=2`) | Clean URLs, invisible in logs and curl, easy to get wrong in caches |
| Per-resource or per-field | Finest grained, highest bookkeeping; used by APIs with very large surfaces |

Pick one, apply it uniformly, and never version an endpoint in two ways at once. Whatever the
scheme, **an unversioned request must keep meaning what it meant on the day the client integrated** —
defaulting old clients to "latest" is how you break people who did nothing.

## Deprecation and sunset

A deprecation with no date is a wish. State the removal date, announce it in the response
(`Deprecation` and `Sunset` headers, RFC 8594), and — the step everyone skips — **instrument usage
per client of the deprecated path**, because that counter, flat at zero, is the only evidence that
removal is safe. Same discipline as the contract phase of expand–contract; same failure if skipped.

## Webhooks as an outbound contract

An outbound callback is an API you cannot version by asking nicely, and it inverts every
responsibility. State all six:

- **Delivery is at-least-once** — receivers must dedupe on a stable event id, so send one.
- **Order is not guaranteed** — include a sequence number or a resource version so a receiver can
  discard stale events; never make a receiver infer state from arrival order.
- **Signing** — HMAC over the raw body with a timestamp, and a documented tolerance window so replay
  is bounded. Receivers verify before parsing.
- **Retry policy** — how many attempts, what backoff, and what a 4xx from the receiver means
  (usually: stop, it will never succeed).
- **Timeout** — what counts as a failed delivery, in seconds.
- **The escape hatch** — a "list events since X" endpoint, so a receiver that was down for an hour
  recovers by polling instead of by emailing you.

Producing them reliably is the outbox pattern (`04-…`); dropping them into a DLQ nobody watches is
the anti-pattern in `06-…`.

## Contract tests

Two implementations of one interface, or two services either side of one contract, need a test that
belongs to neither. **Consumer-driven contract tests** (Pact and friends) let each consumer record
the subset it depends on and run those expectations against the provider's build — so the provider
learns it broke someone at CI time rather than at deploy time.

The cheaper version, which is often enough: keep the request/response examples from the spec in the
repository and assert both sides against them — the provider serialises to them, the consumer's test
double is built from them. When they drift, the build fails. See `09-operability.md` for where these
sit relative to the rest of the test pyramid.
