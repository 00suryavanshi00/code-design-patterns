# Operating a Pattern: Test, Observe, Cost

A pattern is not done when it compiles. Every pattern in this catalogue adds a thing that can
break at 3am, and most of them add a *new* failure mode that did not exist before. A circuit
breaker you cannot observe is a mystery-outage generator: the system starts refusing traffic and
nobody can tell whether the dependency is down or the breaker latched open on a bad threshold.

Use this file when a design includes any Tier 1 or Tier 2 pattern from `03` or `04`, and when
answering "how would you test this?" — which is the most common follow-up in a design review.

## The three questions

Attach these to every pattern you introduce:

1. **How is it tested?** Specifically: what can be tested without a network, and what genuinely
   requires an integration test.
2. **How is it observed?** What metric, log, or span tells an operator this pattern is working,
   and what tells them it has failed. If you cannot name the signal, you cannot run it.
3. **What does it cost?** Latency, memory, operational surface, and — most often forgotten —
   the cognitive cost to the next engineer.

## Two standard signal frameworks

**RED** — for request-driven services (the thing handling traffic):

| | Signal | Typical alert |
|---|---|---|
| **R**ate | Requests per second | Sudden drop = upstream broken or breaker open |
| **E**rrors | Failed requests per second, as a *rate* not a count | Error ratio over a rolling window |
| **D**uration | Latency distribution — p50, p95, p99 | p99 breach, never the mean |

**USE** — for resources (pools, queues, caches, threads):

| | Signal | Typical alert |
|---|---|---|
| **U**tilisation | Fraction of time the resource is busy | Sustained near 100% |
| **S**aturation | Queue depth / wait time for the resource | Queue depth trending up = the real early warning |
| **E**rrors | Rejections, timeouts acquiring the resource | Any pool-exhaustion event |

**Never alert on averages.** A mean latency of 40ms is compatible with 1% of users waiting 8
seconds. Percentiles or nothing.

**Rate, not count.** "500 errors" is meaningless without a denominator. 500 out of 50,000 is a
Tuesday; 500 out of 600 is an outage.

## Per-family operability

### Behavioural patterns (Strategy, State, Command, Observer)

| | |
|---|---|
| **Test** | Pure unit tests — this is the main reason to use them. Each Strategy tested in isolation; State transitions as a table-driven test over (state, event) → state; Command tested by asserting on the recorded action, not by executing it. For State, assert that *invalid* transitions are rejected, not just that valid ones work. |
| **Observe** | State machines: a counter per transition, labelled `from`/`to`. This one metric answers "how many orders got stuck in PENDING" without a database query. Observer: gauge on subscriber count (catches lapsed-listener leaks), and duration of the slowest listener. Strategy: counter labelled by which strategy was selected — you will want to know that the "fallback" pricing rule fired 40% of the time. |
| **Cost** | Indirection. Stack traces get deeper and jumping to the implementation requires knowing which one is wired in. Real, and the reason Tier 3 exists. |

### Worker pools, queues, pipelines (`03`)

| | |
|---|---|
| **Test** | Determinism is the whole problem. Inject the clock. Make concurrency a parameter so tests can run with 1 worker. Use a race detector (`go test -race`, TSAN, Java's jcstress) in CI — it catches what review does not. Test the *shutdown* path, which is where leaks live. |
| **Observe** | USE, on the queue: **queue depth is the single most valuable metric in the system** — it rises before latency does, giving you warning rather than a postmortem. Also: enqueue-to-dequeue wait time, active worker count, tasks dropped or rejected. |
| **Cost** | Bounded queues mean you must decide what happens when full, and that decision is a product decision (block, shed, or drop), not a technical one. |

### Circuit breaker, retry, bulkhead (`04`)

| | |
|---|---|
| **Test** | Breaker: drive the state machine directly with a fake clock — Closed→Open on threshold, Open→Half-Open after cooldown, Half-Open→Closed on success, Half-Open→Open on failure. Do not test it with `sleep`. Retry: assert the *number* of attempts and that backoff grew; assert non-idempotent operations are not retried. Then fault injection at integration level: latency, errors, and — the one people skip — a dependency that is slow rather than down, which is the harder failure. |
| **Observe** | Breaker: a state gauge (0/1/2) plus a counter on every transition. **A breaker with no metric on state transitions is the classic unobservable component** — the alert should fire on the transition to Open, not on the resulting error rate, because the transition is minutes earlier. Retry: attempts-per-call histogram; a p99 of 3 means you are systematically retrying and something upstream is wrong. Bulkhead: USE on each pool, alerting on rejections. |
| **Cost** | Breakers add modal behaviour — the system now has a mode that is rare, hard to test, and can lengthen recovery, because a breaker that latches open keeps refusing traffic after the dependency is healthy. Half-open probes exist to bound that; verify yours actually close. |

### Caches (`04`)

| | |
|---|---|
| **Test** | Hit, miss, expiry (fake clock), and concurrent-miss-on-the-same-key (stampede). Test that a cache failure degrades to the origin rather than failing the request — a cache that can take the system down is worse than no cache. |
| **Observe** | Hit ratio (the number everyone quotes), but also: origin load, eviction rate, and key cardinality. A hit ratio of 95% with a rising eviction rate means the working set outgrew the cache and you are about to fall off a cliff. |
| **Cost** | Every cache is a second source of truth and therefore a staleness bug waiting to be reported as "the data is wrong". |

### Idempotency, outbox, saga (`04`)

| | |
|---|---|
| **Test** | Send the same request twice and assert one effect — this should be a standing test, not a one-off. Kill the process between the local transaction and the publish, and assert the relay still delivers. For sagas, test each compensation *in isolation*, and test compensating something that never happened. |
| **Observe** | Duplicate-key hit rate (tells you how often clients are retrying — a leading indicator of upstream trouble). Outbox: unpublished row count and oldest-unpublished age; if that age grows, the relay is dead and events are silently not happening. Saga: count of sagas per state, and an alert on any saga stuck mid-flight beyond a deadline. DLQ depth, always alerted. |
| **Cost** | Idempotency keys need storage and a TTL policy. Sagas make every intermediate state user-visible, which is a UX cost, not just an engineering one. |

## Adding this to a design

The design template in `SKILL.md` includes an operability step. Keep it to a few lines — one
metric per pattern introduced, plus what would page someone:

> **Operability.** Breaker state transitions counter (alert on → Open). Queue depth gauge
> (alert at 80% of bound). Idempotency-key hit rate. Spot fee calculation is unit-testable
> because `Clock` is injected; the allocation race is covered by a concurrent test with the
> race detector on.

If a design introduces a breaker, a queue, or a cache and says nothing about how anyone would
know it is working, that is a real gap — rubric dimension 8 covers it.
