# Modern Application & Architectural Patterns

The patterns that carry more weight in a production codebase than most of the GoF catalogue, and
which the 1994 book predates or barely touches.

## Contents

- [Dependency Injection](#dependency-injection) · [Repository](#repository) ·
  [Unit of Work](#unit-of-work) · [Data Mapper, DAO, DTO](#data-mapper-dao-and-dto) ·
  [Specification](#specification) · [Domain model patterns](#domain-model-patterns)
- [Ports & Adapters](#ports--adapters-hexagonal) · [Layered / Clean](#layered--clean-architecture) ·
  [MVC, MVP, MVVM](#mvc-mvp-mvvm)
- [CQRS](#cqrs) · [Event Sourcing](#event-sourcing)
- [Result types](#result-and-error-types) · [Functional Options](#functional-options) ·
  [Plugin / Extension point](#plugin--extension-point) · [Feature flags](#feature-flags) ·
  [Middleware](#middleware--interceptor-chain) · [Where security lives](#where-security-lives)

---

## Dependency Injection

**Force:** a class needs a collaborator, but constructing it inside the class welds the two
together and makes the class untestable.

Inject dependencies through the constructor. That is the whole pattern; frameworks are optional.

```typescript
class OrderService {
  constructor(
    private readonly orders: OrderRepository,
    private readonly payments: PaymentGateway,
    private readonly clock: Clock,          // inject time — never call now() inline
  ) {}
}
```

**Rules that matter more than the framework choice:**

- Constructor injection over setter or field injection — a half-constructed object is a bug source.
- Depend on interfaces you own, not on vendor types. `PaymentGateway`, not `StripeClient`.
- Wire everything at one **composition root** (`main`, `App`, the module bootstrap). Nothing else
  constructs its own dependencies.
- Inject non-determinism: clock, random, UUID generator, filesystem. Untestable code is almost
  always code that reached for one of these directly.
- More than ~6 constructor parameters means the class has too many responsibilities. The
  parameter count is a design smell detector, not an inconvenience to work around.

**Service Locator is not DI.** `locator.get(Foo)` inside a method hides the dependency instead of
declaring it. It is Tier 3.

**In the wild:** Spring's entire container; Go's Wire and Dig; Angular's injector; `dependency-injector`
in Python. In small Go and Rust codebases, plain constructor wiring in `main` is the norm and is
correct — do not recommend a container for 15 types.

## Repository

**Force:** domain logic should not know whether data lives in Postgres, Redis, or a test fixture.

```java
interface OrderRepository {
    Optional<Order> findById(OrderId id);
    List<Order> findPendingOlderThan(Instant t);
    void save(Order order);
}
```

The domain depends on this interface; a `PostgresOrderRepository` implements it in the
infrastructure layer. Tests use an in-memory implementation and run in milliseconds.

**Not this when:** you are writing a CRUD app whose "domain logic" is field validation. Wrapping
an ORM that is already a repository in another repository is a common source of pointless layers.
Spring Data is itself the Repository pattern — do not wrap it again.

**Leak to watch for:** a repository returning ORM entities with lazy relations, or accepting a
`Specification` built from SQL fragments, has leaked the database into the domain anyway.

## Unit of Work

**Force:** several repository operations must commit or roll back together.

Tracks changed objects across a business transaction and flushes them in one commit. Hibernate's
`Session` and EF's `DbContext` are Units of Work you already use.

**Not this when:** your framework gives you transactional boundaries declaratively
(`@Transactional`). Reimplementing change tracking by hand is rarely worth it.

## Data Mapper, DAO, and DTO

Three things people conflate:

| | Job | Lives in |
|---|---|---|
| **DAO** | Encapsulates access to one table/collection. Thinks in rows. | Infrastructure |
| **Repository** | Encapsulates access to an aggregate. Thinks in domain objects. | Domain boundary |
| **Data Mapper** | Translates between the persistence shape and the domain shape. | Infrastructure |
| **DTO** | Carries data across a boundary (API request/response). No behaviour. | API edge |

**Why DTOs are not optional at an API edge:** returning domain entities directly leaks internal
fields (password hashes, internal IDs, soft-delete flags) and welds your public contract to your
schema. A separate DTO lets the domain evolve without breaking clients.

## Specification

**Force:** business rules for "which objects qualify" are duplicated across query code, validation,
and in-memory filtering.

```csharp
var eligible = new IsActive().And(new HasBalanceOver(100)).And(new NotSuspended());
repository.Find(eligible);   // translated to SQL
eligible.IsSatisfiedBy(user); // evaluated in memory
```

**Not this when:** the rule is used once. This is Tier 2 — it pays off when the same predicate
must run in two places (database and memory) or when non-engineers compose rules.

## Domain model patterns

- **Value Object** — immutable, equality by value, no identity. `Money`, `EmailAddress`,
  `DateRange`. Replacing primitives with value objects kills a whole class of bug (currency
  mismatch, invalid email reaching the database). This is the highest-value, lowest-cost pattern
  in the entire list.
- **Entity** — identity that persists across state changes. Equality by ID.
- **Aggregate** — a cluster of entities with one root that guards invariants. External code holds
  a reference only to the root. Transaction boundaries follow aggregate boundaries.
- **Domain Service** — logic that belongs to no single entity (e.g. transferring between two
  accounts).
- **Null Object** — a do-nothing implementation (`NoOpMetrics`, `SilentLogger`) instead of null
  checks scattered through the code. Tier 2, but cheap and effective.

**Anemic domain model:** entities that are bags of getters and setters with all logic in
`*Service` classes. Common, and worth flagging in review — the invariants have nowhere to live,
so they get re-checked (or forgotten) at every call site.

## Ports & Adapters (Hexagonal)

**Force:** business rules should outlive the framework, the database, and the transport.

- The **core** holds domain logic and defines **ports** (interfaces) for everything it needs.
- **Driving adapters** (HTTP handler, CLI, message consumer) call *into* ports.
- **Driven adapters** (Postgres repo, S3 client, email sender) *implement* ports.
- Dependencies point inward. The core imports nothing from infrastructure.

**The failure mode to check for:** a driving adapter calling a driven adapter directly, bypassing
the core. The layering is then decorative — the HTTP handler is talking to the database.

**Not this when:** the app is a thin CRUD wrapper. Hexagonal costs indirection; it pays when
domain logic is substantial or when transport/storage will genuinely be swapped.

## Layered / Clean Architecture

`Presentation → Application → Domain → (Infrastructure implements Domain interfaces)`

Same dependency-inversion idea as Hexagonal with more prescribed layers. The one rule that
actually matters: **Domain depends on nothing.** If `Order.java` imports a JPA annotation, you
have a layered folder structure, not layered architecture.

## MVC, MVP, MVVM

| | Who holds view state | Typical home |
|---|---|---|
| **MVC** | Controller mediates; View reads Model | Server-rendered web, Rails, Spring MVC |
| **MVP** | Presenter holds it, View is passive and dumb | Legacy Android, testable desktop UI |
| **MVVM** | ViewModel exposes observable state, View binds | WPF, SwiftUI, Vue, Android Jetpack |

**Front Controller** (one entry point routing all requests) is the pattern behind every web
framework's dispatcher.

## CQRS

**Force:** reads and writes have genuinely different shapes, consistency needs, or scaling curves
— an e-commerce product page read 100× more often than it is written, needing joins that slow
the write path.

Split the model: commands mutate through the domain model; queries read from a shape optimised
for reading (a denormalised table, a search index, a cache).

**The honest cost:** two models to keep in sync, and eventual consistency the UI must handle
("your order is processing"). Most systems that adopt CQRS did not need it.

**Not this when:** read and write models would be identical. That is just a repository with
two method groups.

## Event Sourcing

**Force:** the *history* of changes is itself business-critical — audit, ledgers, "how did this
account reach this balance", replay for debugging or new read models.

Store the append-only sequence of events as the source of truth; current state is a fold over
them. Snapshots keep replay cheap.

**The costs people underestimate:** schema evolution of old events, GDPR deletion against an
append-only log, and the fact that querying requires projections. Frequently paired with CQRS.

**Not this when:** you want an audit table. Add an audit table.

## Result and Error Types

**Force:** exceptions for expected failures make control flow invisible and turn "this can fail"
into something the type system does not say.

```rust
fn find_user(id: UserId) -> Result<User, UserError>
```

Model *expected* failures (validation failed, not found, insufficient funds) as return values;
reserve exceptions/panics for programmer error and truly exceptional conditions. Go's explicit
`error` return, Rust's `Result`, and functional `Either` are the same idea. In Java/TypeScript,
a sealed `Result` type or a discriminated union does it.

**Related:** wrap errors with context as they cross layers (`fmt.Errorf("charging order %s: %w", id, err)`)
rather than logging at every level and rethrowing — that produces the same failure printed nine times.

## Functional Options

Go's answer to Builder and optional parameters. Extensible without breaking callers, and the
zero value stays useful. See the Builder entry in `01-gof-catalog.md` for the shape.

## Plugin / Extension Point

**Force:** third parties (or other teams) must extend behaviour without forking the core.

Define an interface plus a registration mechanism; discover implementations at startup.

**In the wild:** Kubernetes' interface-and-plugin design is the reason it is extensible at all —
CSI for storage, CNI for networking, CRI for runtimes, scheduler plugins, admission webhooks.
Prometheus exporters, Grafana datasources, and every editor's extension API work the same way.

**Design requirements people forget:** version the interface, sandbox failures so one plugin
cannot take the host down, and define ordering when multiple plugins apply.

## Feature Flags

**Force:** deploy and release must be decoupled; risky changes need a kill switch.

Treat the flag check as a Strategy selection, keep flag logic out of the domain, and — the part
teams skip — schedule flag removal. Stale flags are combinatorial debt: 10 flags is 1024
theoretical code paths, none of them tested.

## Where security lives

Not a security course — a placement question, and placement is a design decision the rest of this
file's patterns already answer for everything else.

**Authorization belongs in one layer, and it is not the UI.** Hiding a button is a usability
feature; the endpoint behind it is still open. Copy-pasting `if (user.role != ADMIN)` into forty
handlers is the same failure as a `switch` on vehicle type — the rule is smeared across every place
that must remember it, and the one that forgets is the breach. Put the decision in a policy object
the domain calls (`can(user, :approve, invoice)`) and enforce it in one middleware/interceptor chain
or one authorization service. Then "who can approve an invoice" has exactly one answer, and it is
testable in isolation.

**Object-level checks are the ones that get skipped.** Role checks are easy and mostly present;
"this invoice belongs to this tenant" is the check that is missing, and it is the most common serious
API vulnerability there is. Where multi-tenancy is involved, make it structural rather than
remembered — see the tenancy section of `10-persistence-patterns.md`.

**Validate at the trust boundary, then stop.** Parse untrusted input into domain types once, at the
edge, and let the type system carry the guarantee inward — `EmailAddress`, not `String` checked in
four places. Make illegal states unrepresentable applies precisely here.

**Secrets are infrastructure, not domain state.** A domain object holding an API key or a raw
password serialises it into logs, caches, test fixtures and error reports the moment anything prints
it. Keep credentials behind the adapter that uses them, and give sensitive value objects a
`toString`/serializer that redacts.

**In the wild:** Rails' Pundit/CanCanCan policies, Casbin, OPA/Rego, and Postgres row-level
security are all the same idea — the authorization rule as a first-class object, one place, testable.

## Middleware / Interceptor Chain

**Force:** cross-cutting concerns (auth, logging, tracing, compression, rate limiting) apply to
many handlers and must not be copy-pasted into each.

Structurally a Decorator chain. Order is semantic: authentication before authorisation, tracing
outermost so it observes everything, compression innermost. Say the order explicitly in a design
— getting it wrong is a security bug, not a style issue.

**In the wild:** Express, Gin, Django, ASP.NET Core, gRPC interceptors, Spring AOP (implemented
with Proxy rather than an explicit chain).
