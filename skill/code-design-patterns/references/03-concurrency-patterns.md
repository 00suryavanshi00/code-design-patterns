# Concurrency Patterns

Most LLD designs that fail in review fail here, not on class structure. Machine-coding rounds at
Amazon, Uber, Atlassian and similar routinely ask for a thread-safe implementation, and "I'd add
a lock" is not an answer — *which* lock, around *what*, and what does it cost.

## Contents

- [The three questions](#the-three-questions-to-answer-first)
- [Worker Pool](#worker-pool) · [Producer-Consumer](#producer-consumer) · [Pipeline](#pipeline) ·
  [Fan-out / Fan-in](#fan-out--fan-in)
- [Actor](#actor-model) · [Reactor / event loop](#reactor--event-loop) ·
  [Futures & Promises](#futures--promises) · [Structured concurrency](#structured-concurrency)
- [Immutability & CoW](#immutability-and-copy-on-write) · [Thread confinement & single writer](#thread-confinement-and-the-single-writer-principle) ·
  [Read-write lock](#readwrite-lock) · [Double-checked locking](#double-checked-locking) ·
  [Optimistic concurrency](#optimistic-concurrency-and-cas)
- [Backpressure](#backpressure) · [Graceful shutdown](#graceful-shutdown) ·
  [Common bugs](#the-bugs-reviewers-look-for)

---

## The three questions to answer first

Before naming any pattern, answer these in the design. A design that answers them plainly beats
one that name-drops five patterns.

1. **What is shared and mutable?** Anything neither shared nor mutable needs no protection. Most
   designs can shrink this set dramatically before adding a single lock.
2. **What is the unit of atomicity?** "Find a free spot and mark it taken" must be one atomic
   step; two separately-safe operations do not compose into a safe sequence. This is the single
   most common concurrency bug in LLD answers.
3. **What is the contention profile?** Read-heavy, write-heavy, or bursty? It decides between a
   mutex, a read-write lock, a concurrent collection, sharding, and CAS.

## Worker Pool

**Force:** thousands of tasks, but unbounded goroutines/threads exhaust memory, file descriptors,
or the database connection pool.

A fixed number of long-lived workers pull from a shared queue. The bounded queue *is* your
backpressure mechanism — that is a feature, not a limitation.

```go
jobs := make(chan Job, 100)          // bounded: producers block when full
results := make(chan Result, 100)

var wg sync.WaitGroup
for w := 0; w < numWorkers; w++ {
    wg.Add(1)
    go func() {
        defer wg.Done()
        for j := range jobs {         // exits when jobs is closed
            select {
            case results <- process(j):
            case <-ctx.Done():
                return
            }
        }
    }()
}
go func() { wg.Wait(); close(results) }()
```

**Sizing:** CPU-bound work → roughly `NumCPU`. I/O-bound → higher, but the real bound is usually
downstream (connection pool size, rate limit), so size to that, not to a guess.

**Not this when:** the tasks are few, or the work is trivially short — pool overhead dominates.

## Producer-Consumer

The same shape stated generally: producers append to a bounded buffer, consumers drain it. The
buffer decouples their rates and absorbs bursts. Classically implemented with a monitor
(`wait`/`notify`, condition variables); in Go a buffered channel is the buffer.

**The interview trap:** using `if (queue.isEmpty()) wait();` instead of `while (queue.isEmpty()) wait();`.
Spurious wakeups and multi-consumer races make `if` wrong. Always `while`.

## Pipeline

**Force:** multi-stage processing where stages have different throughputs and should run
concurrently.

Each stage is a function taking an input channel and returning an output channel. Stages run
concurrently; the slowest sets the rate. Cancellation must propagate through every stage —
in Go, thread `ctx` through all of them or you leak goroutines when a consumer stops early.

## Fan-out / Fan-in

**Fan-out:** distribute one input stream across N workers. **Fan-in:** merge N result channels
into one. Together they are the parallel middle of a pipeline.

Rules that prevent the usual bugs: the sender closes the channel, never the receiver; close
exactly once (double close panics); use a `WaitGroup` to know when all producers are done before
closing the merged channel.

## Actor Model

**Force:** shared mutable state is the problem — so remove sharing. Each actor owns its state
exclusively and communicates only by asynchronous messages, processed one at a time.

No locks, no data races by construction. Costs: message-ordering reasoning, mailbox overflow,
and debugging across asynchronous hops.

**In the wild:** Erlang/Elixir (with supervision trees for failure), Akka, Orleans virtual actors.
A single-threaded event loop owning a data structure is the same idea in one process.

## Reactor / Event Loop

**Force:** tens of thousands of mostly-idle connections; a thread per connection does not fit
in memory.

One loop demultiplexes readiness events (`epoll`/`kqueue`/IOCP) and dispatches handlers.
Nginx, Node.js, Redis, and Netty are all reactors.

**The rule that defines the pattern:** never block in a handler. One synchronous database call
or CPU-heavy loop stalls every connection. Offload blocking work to a pool.

**Proactor** is the completion-based variant (the OS signals "done" rather than "ready") — IOCP,
io_uring.

## Futures & Promises

Represent a value that will exist later; compose with `then`/`await`. `async/await` is syntactic
sugar over this.

**What to get right in a design:** every await point is a place another task can interleave —
invariants must hold there. And unhandled promise rejections must be caught somewhere, or
failures vanish silently.

## Structured Concurrency

**Force:** spawned tasks outliving their caller, leaking, and failing where nobody is listening.

The rule: a task's lifetime is bounded by a lexical scope, and that scope does not exit until all
children finish or are cancelled. Errors propagate to the parent.

**In the wild:** Go's `errgroup` with a `context`; Java 21's `StructuredTaskScope`; Kotlin's
`coroutineScope`; Trio/asyncio task groups. Any design that spawns background work should say
who owns it and how it is cancelled.

## Immutability and Copy-on-Write

The cheapest concurrency strategy: if a value never changes, it needs no synchronisation.

Copy-on-write suits read-heavy, rarely-written shared state (routing tables, configuration
snapshots, feature-flag sets): readers see a consistent immutable snapshot with no locking;
writers build a new version and swap an atomic reference.

**Not this when:** writes are frequent or the structure is large — copying dominates.

## Thread Confinement and the Single-Writer Principle

Confine mutable state to one thread and it needs no lock. Stack-local variables, thread-locals,
and "this struct is only touched by the event loop" are all confinement. Say so explicitly in a
design — an unstated confinement assumption is the thing the next engineer breaks.

The **single-writer principle** is the sharpened version: allow any number of readers, but let
exactly *one* thread write a given piece of state. Contention disappears by construction, because
contention requires two writers. Reads may then need only a memory barrier rather than a lock.

This is why an actor owning its state, a Redis-style single-threaded event loop, and a Kafka
partition with one consumer per group all outperform their lock-based equivalents at high
concurrency — they are the same principle applied at different scales. Scaling happens by
*sharding* the state so each shard has its own writer, not by adding writers to one shard.

**Mechanical sympathy:** at the hardware level, two cores writing to the same cache line contend
even when the variables are logically unrelated — **false sharing**. The LMAX Disruptor gets its
throughput from taking this seriously: a pre-allocated ring buffer, cache-line padding around
each cursor, single-writer discipline, and batching that falls out naturally under load. Worth
knowing exists; worth reaching for only when a bounded queue has been measured as the bottleneck.

## Read/Write Lock

Many concurrent readers, exclusive writers. Worth it only when reads dominate heavily and the
critical section is long enough to amortise the extra bookkeeping — `RWMutex` is *slower* than a
plain mutex for short critical sections. Beware writer starvation under sustained read load.

## Double-Checked Locking

Lazy initialisation without paying the lock on every read. Notoriously easy to get wrong: the
field must be `volatile` in Java (pre-JMM-fix versions were broken outright), and in C++ you need
proper memory ordering.

**Use the language's answer instead:** `sync.Once` in Go, a static holder class or enum in Java,
`std::call_once` in C++, `lazy` in Kotlin/Swift. Hand-rolling this in 2026 is a red flag.

## Optimistic Concurrency and CAS

**Force:** contention is rare, and locking every access costs more than occasionally retrying.

Read a value with its version, compute, then compare-and-swap; retry on conflict. Version columns
in databases and `AtomicReference.compareAndSet` are the same pattern at different layers.

**ABA hazard:** a value can change A→B→A between read and swap. Use a versioned/stamped reference
when identity alone is not enough.

**Where this belongs in LLD answers:** "two entrances race for the last spot" is better solved
with a CAS on spot status than by locking the whole floor.

## Backpressure

**Force:** a fast producer overwhelms a slow consumer; unbounded queues turn a throughput problem
into an out-of-memory crash.

Options, in rough order of preference: block the producer (bounded queue), shed load (reject with
429), sample or drop, or buffer to disk. **Unbounded is not an option** — it only moves the
failure to a worse place. Reactive Streams' request-N protocol is the formalised version.

## Graceful Shutdown

Stop accepting new work → signal cancellation → drain in-flight work with a deadline → force-stop
what remains → flush metrics and logs → close connections. Designs that omit shutdown lose
in-flight requests on every deploy.

## The bugs reviewers look for

| Bug | Signature |
|---|---|
| Check-then-act | `if (spot.isFree()) spot.assign()` — two atomic ops, not one atomic sequence |
| Lock ordering deadlock | Two locks acquired in different orders on different paths. Fix: a global lock order, or one lock |
| Leaked goroutine/thread | Nothing closes the channel or cancels the context; the worker blocks forever |
| `if` instead of `while` around a condition wait | Spurious wakeup proceeds with a false precondition |
| Unbounded queue | "We'll buffer it" with no limit |
| Lock held across I/O | A network call inside a critical section serialises the whole system |
| Non-atomic compound update | `map.get` then `map.put` on a concurrent map — use `compute`/`merge` |
| Shared mutable default/singleton | Global state mutated by request handlers |
| Missing memory-visibility guarantee | A flag read without `volatile`/atomic; the loop may never see the write |
