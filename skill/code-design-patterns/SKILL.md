---
name: code-design-patterns
description: Choose, apply, and critique software design patterns — GoF (Strategy, Factory, Observer, State, Decorator, Adapter, Command), architectural (dependency injection, repository, hexagonal/ports-and-adapters, CQRS, event sourcing), concurrency (worker pool, pipeline, fan-out/fan-in, actor), distributed resilience (circuit breaker, retry/backoff, bulkhead, saga, outbox, idempotency key, rate limiter), and frontend component patterns (compound components, hooks, providers). Use whenever the work involves object-oriented or component design, class modelling, low-level design (LLD) or machine-coding problems, "design a parking lot / elevator / rate limiter"-style tasks, refactoring toward SOLID, reviewing a class design, structuring a new module or service, or any question touching design patterns, code architecture, extensibility, coupling, or code smells — even when the user never says "design pattern". Also use it to grade a design against a rubric before presenting it.
license: MIT
---

# Code Design Patterns

Patterns are a vocabulary for trade-offs, not a checklist to satisfy. The failure mode this
skill exists to prevent is pattern-stuffing: producing a design with a Factory, a Singleton,
and an Observer bolted on because those are the famous names, when the problem called for one
interface and a function.

The bar to clear: **every pattern in the output must be traceable to a specific, stated force
in the requirements.** If you cannot name the force, remove the pattern.

## Workflow

Work in this order. Do not skip to step 4 — designs that start from a pattern name almost
always end up contorted around it.

### 1. Pin the requirements and the axis of change

Restate what is being built in two or three sentences, then list:

- **Functional requirements** — what it must do. Number them; you will trace the design back to them.
- **Scale and concurrency** — single-threaded? Many threads sharing state? Distributed across
  processes? This single question decides more of the design than any pattern choice.
- **The axis of change** — the one thing most likely to be different in six months. New payment
  provider? New pricing rule? New notification channel? Patterns exist to make one axis cheap
  to extend; picking the wrong axis is worse than picking no pattern.
- **Explicit non-goals** — what you are choosing not to support. This is what keeps a design
  from sprawling.

If the requirements are genuinely ambiguous on something load-bearing (concurrency, persistence,
multi-tenancy), state the assumption you are making and move on. Do not stall the design on it.

### 2. Model the domain before the mechanism

Extract the nouns into entities, value objects, and services. Draw the relationships. At this
stage there are no patterns, only responsibilities:

- One class, one reason to change. If a class name contains "and", or the class both computes
  fees and writes to a database, split it.
- Prefer composition over inheritance. Inheritance is for genuine substitutability (an
  `ElectricCar` really is a `Vehicle` everywhere a `Vehicle` is used), not for code reuse.
- Make illegal states unrepresentable. A `Ticket` with a null `exitTime` and a `status` field
  that must agree with it is two bugs waiting; model `ActiveTicket` and `ClosedTicket` instead.
- Push I/O to the edges. Domain logic that reaches for a database or a clock cannot be tested.

### 3. Name the forces

For each place the design feels tense, write the force as a sentence with a "but":

> "Pricing varies by vehicle type and time of day, **but** I don't want a switch statement that
> every new rule has to edit."

Forces map to pattern families:

| Force | Family | See |
|---|---|---|
| An algorithm or policy must vary at runtime | Strategy, Policy object | `references/01-gof-catalog.md` |
| Object behaviour changes with its lifecycle stage | State, State machine | `references/01-gof-catalog.md` |
| Construction is complex, conditional, or has many optional parts | Builder, Factory Method, Abstract Factory, Functional Options | `references/01-gof-catalog.md` |
| Callers must react to something without the source knowing them | Observer, Pub/Sub, Event bus | `references/01-gof-catalog.md` |
| An existing interface is the wrong shape | Adapter, Facade, Anti-Corruption Layer | `references/01-gof-catalog.md` |
| Behaviour must be added per-instance, stackably | Decorator, Middleware chain | `references/01-gof-catalog.md` |
| Access must be controlled, deferred, or remoted | Proxy | `references/01-gof-catalog.md` |
| An action must be queued, logged, undone, or retried | Command | `references/01-gof-catalog.md` |
| Domain logic must not depend on the database or framework | Repository, Ports & Adapters, DI | `references/02-modern-application-patterns.md` |
| Reads and writes have divergent shapes or scaling needs | CQRS, Materialized view | `references/02-modern-application-patterns.md` |
| Bounded parallelism over a stream of work | Worker pool, Pipeline, Fan-out/fan-in | `references/03-concurrency-patterns.md` |
| A dependency may be slow or down | Circuit breaker, Timeout, Retry+jitter, Bulkhead | `references/04-distributed-resilience-patterns.md` |
| A transaction spans services that cannot share a lock | Saga, Outbox, Idempotency key | `references/04-distributed-resilience-patterns.md` |
| Two writers may update the same stored row | Optimistic version column, `SELECT … FOR UPDATE`, single-statement conditional update | `references/10-persistence-patterns.md` |
| "There can only be one" — one booking, one signup, one charge | Unique constraint, idempotency key, conditional write | `references/10-persistence-patterns.md` |
| The contended state lives in a database, not in this process | Persistence-layer concurrency — a mutex protects nothing across instances | `references/10-persistence-patterns.md` |
| UI state and presentation are tangled | Container/presentational, Custom hook, Compound components | `references/05-frontend-patterns.md` |
| A pattern is in the design but nobody could tell if it were broken | RED/USE signals, test seams | `references/09-operability.md` |

Read only the reference file(s) the forces point to. Reading all of them wastes context.

### 4. Choose, and justify the ones you rejected

State the chosen pattern, the force it resolves, and **one credible alternative you rejected and
why**. The rejection is the part that demonstrates judgement. A design that lists only what it
chose reads like a lookup; a design that says "Strategy over a `switch` because pricing rules
are added by a different team than the one that owns `ParkingLot`" reads like engineering.

Default to the simplest thing that resolves the force:

- A function or a lambda beats a Strategy class hierarchy when there is no per-strategy state.
- A `dict`/`map` from key to handler beats a Factory when construction is a one-liner.
- Passing a dependency into a constructor beats a DI container in anything under ~20 types.
- An enum with behaviour beats a State class hierarchy when there are three states and no
  per-state data.

### 5. Write the design

Produce, in this order:

1. **Requirements and assumptions** — numbered, including the axis of change and non-goals.
2. **Class model** — a diagram (ASCII, Mermaid, or UML-style text) showing entities, interfaces,
   and relationships. Mark interfaces clearly.
3. **Key interfaces as code** — signatures for the abstractions that carry the design. Do not
   write every getter; write the seams.
4. **Core flows** — the two or three main operations, as code or numbered sequence steps,
   showing how the objects collaborate.
5. **Pattern ledger** — a short table: pattern | force it resolves | alternative rejected.
6. **Concurrency and failure** — what is shared, what lock or channel guards it, what happens
   when a dependency fails, what is idempotent. If the shared state is *stored* rather than
   in-process, name the database-level mechanism — version column, `FOR UPDATE`, unique constraint,
   conditional write — because a mutex in one instance does not constrain another
   (`references/10-persistence-patterns.md`).
7. **Operability** — a few lines: one metric per breaker, queue, or cache introduced, and what
   would page someone. If a pattern cannot be observed, it cannot be run. See
   `references/09-operability.md`.
8. **Extension walkthrough** — take the axis of change from step 1 and show concretely what a
   developer edits to extend it. If the answer touches more than two files, the design is not
   as extensible as claimed.
9. **Trade-offs** — what this design is bad at.

Use the user's language and stack. If none is given, prefer a typed language (Java, TypeScript,
Go, Python with type hints) — untyped pseudocode hides exactly the interface decisions that
matter here.

### 6. Grade before presenting

Before showing the design, score it against `references/07-evaluation-rubric.md`. Fix anything
scoring 0 or 1. If asked to *review* someone else's design rather than produce one, that rubric
is the review structure — use it directly, and lead with the two highest-leverage problems
rather than an exhaustive list.

## Pattern tiers

Not all patterns earn their place equally. When choosing, weight by how often the pattern is
genuinely the right answer in production code:

**Tier 1 — reach for these freely.** Strategy, Factory Method, Builder, Adapter, Decorator,
Observer, State, Template Method, Command, Iterator, Facade, Composite, Proxy, Dependency
Injection, Repository, Middleware/Interceptor chain, Worker pool, Circuit breaker, Retry with
backoff and budget, Cache-aside, Idempotency key, Optimistic locking, Unique-constraint invariants,
Expand-contract migration.

**Tier 2 — correct in specific situations, suspicious otherwise.** Abstract Factory, Chain of
Responsibility, Visitor, Mediator, Bridge, Memento, Flyweight, Object Pool, Specification, Null
Object, Unit of Work, CQRS, Event sourcing, Saga, Actor, Bulkhead, Pessimistic row locking, Soft
delete.

**Tier 3 — usually a smell.** Singleton (a global with extra steps; it destroys testability and
hides coupling — prefer one instance injected at composition root), Prototype (most languages
have a copy idiom), Interpreter (reach for a parser generator or an existing expression library),
Service Locator (hides dependencies where DI would expose them), Anemic Domain Model.

A design that names a Tier 3 pattern positively needs an unusually good justification.

## Reference files

Read on demand, not upfront.

| File | Contents | Read when |
|---|---|---|
| `references/01-gof-catalog.md` | All 23 GoF patterns: intent, force, real-codebase sighting, minimal example, when *not* to use | Object-level design, LLD problems |
| `references/02-modern-application-patterns.md` | DI, Repository, Unit of Work, DTO/Data Mapper, Hexagonal, Layered/Clean, MVC/MVP/MVVM, CQRS, Event Sourcing, Specification, Result types, Functional Options, Plugin/Extension point, Feature flags | Structuring a service, module, or app |
| `references/03-concurrency-patterns.md` | Worker pool, Producer-consumer, Pipeline, Fan-out/fan-in, Actor, Reactor, Futures/Promises, Structured concurrency, Immutability/CoW, Read-write lock, Double-checked locking, Backpressure, Thread confinement | Anything with shared mutable state or parallelism |
| `references/04-distributed-resilience-patterns.md` | Circuit breaker, Retry+jitter, Timeout budgets, Bulkhead, Rate limiting (token/leaky bucket), Saga, Outbox, Idempotency, Cache-aside/read-through/write-behind, API Gateway/BFF, Sidecar, Leader election, Dead letter queue | Service boundaries, network calls |
| `references/05-frontend-patterns.md` | Container/presentational, Custom hooks, Compound components, Provider, Render props, HOC, State reducer, Error boundary, Feature-sliced structure | React/Vue/UI component design |
| `references/06-antipatterns-and-smells.md` | God object, Anemic domain model, Pattern-stuffing, Premature abstraction, Leaky abstraction, Primitive obsession, Shotgun surgery, Circular dependency, Singleton abuse, Callback hell, Distributed monolith | Reviewing or refactoring existing code |
| `references/07-evaluation-rubric.md` | 10-dimension scoring rubric with 0–3 anchors, plus red flags and a worked scored example | Before presenting any design; all review tasks |
| `references/08-lld-question-bank.md` | 30 canonical LLD problems with required abstractions, legitimate pattern fits, trap answers, and follow-up probes | LLD/machine-coding practice, generating or grading design problems |
| `references/09-operability.md` | How to test and observe each pattern family; RED and USE; what each pattern costs to run | Any design using a breaker, queue, pool or cache; "how would you test this?" |
| `references/10-persistence-patterns.md` | Optimistic vs. pessimistic locking, unique constraints and conditional writes, isolation levels and write skew, aggregates as transaction boundaries, idempotent writes, soft delete, multi-tenant isolation, read models, schema change | Any design where the contended state is in a database; "two users book the last seat" |

## Calibration examples

**Input:** "Design a parking lot."
**Good response shape:** entities (`ParkingLot` → `Floor` → `Spot`, `Vehicle`, `Ticket`); a
`SpotAllocationStrategy` interface because allocation policy is the stated axis of change; a
`PricingStrategy` separate from allocation because they change for different reasons; explicit
statement that `Spot` reservation needs a lock or compare-and-swap because two entrances can
race; a `Ticket` state machine. Notably absent: a Singleton `ParkingLotManager`, an Abstract
Factory for vehicles, an Observer no one subscribes to.

**Input:** "Should I use the Visitor pattern here?" (with a small class hierarchy that changes often)
**Good response shape:** No, and say why — Visitor makes adding *operations* cheap at the cost of
making adding *types* expensive, so it is backwards for a hierarchy where types churn. Offer the
alternative that fits the actual axis of change.

**Input:** "Review my order service" (pasted code with a 400-line `OrderService`)
**Good response shape:** rubric-structured review, leading with the two problems that matter
most — probably that the class has four reasons to change and that business rules are entangled
with SQL — with a concrete seam to introduce first, not a list of eleven nitpicks.
