# code-design-patterns

A Claude Skill that teaches Claude to **pick the right software design pattern, refuse the wrong
one, and grade its own design before you ever see it.**

**104 patterns · 21 anti-patterns · 30 canonical LLD problems · a 10-dimension design rubric.**

🔗 **Website:** https://code-design-patterns-sanskars-projects-e7b2c5c4.vercel.app

---

## Why this exists

The common failure mode when an LLM designs software is not ignorance of patterns — it is
**pattern-stuffing**: a Singleton, a Factory over `new`, and an Observer with no subscribers,
bolted onto a design because those are the famous names. Meanwhile the actual race condition in
the resource-allocation path goes unmentioned.

This skill inverts that. The bar it enforces:

> Every pattern in the output must be traceable to a specific, stated force in the requirements.
> If you cannot name the force, remove the pattern.

## What it changes

Asked to *"design a parking lot"*:

| Without | With the skill |
|---|---|
| Singleton `ParkingLotManager`, unexplained | Axis of change named before a class is written |
| `VehicleFactory` over classes differing by one enum | Allocation and pricing split — they change for different reasons |
| Fees as `double`, clock called inline | `Money` value object, `Clock` injected |
| "Add a lock" | Claiming a spot is one atomic op — CAS, not check-then-act |
| Patterns listed, never justified | Pattern ledger: force resolved, alternative rejected |
| No trade-offs stated | Self-scored against the rubric before presenting |

## What's inside

```
skill/code-design-patterns/
├── SKILL.md                              6-step workflow, pattern tiers, force→pattern routing
└── references/
    ├── 01-gof-catalog.md                 All 23 GoF patterns, tiered, with real-codebase sightings
    ├── 02-modern-application-patterns.md DI, Repository, Hexagonal, CQRS, Event Sourcing, plugins
    ├── 03-concurrency-patterns.md        Worker pools, pipelines, actors, CAS, backpressure
    ├── 04-distributed-resilience-…md     Circuit breakers, sagas, outbox, idempotency, caching
    ├── 05-frontend-patterns.md           Compound components, hooks, providers, error boundaries
    ├── 06-antipatterns-and-smells.md     20 smells with signature + smallest first move
    ├── 07-evaluation-rubric.md           10 dimensions scored /30, red flags, worked example
    ├── 08-lld-question-bank.md           30 problems: axis, patterns, trap, follow-up probe
    ├── 09-operability.md                 test/observe/cost per family; RED and USE
    ├── 10-persistence-patterns.md        Locking, isolation levels, constraints, tenancy, soft delete
    └── 11-api-contract-patterns.md       Idempotent HTTP, pagination, evolution, versioning, webhooks
```

Progressive disclosure: Claude loads `SKILL.md` when the task involves design, then reads **only**
the reference file the problem's forces point to.

### Pattern tiers

Patterns are weighted by how often they are genuinely the right answer in production code, not by
how famous they are.

- **Tier 1 — reach for freely.** Strategy, Factory Method, Builder, Adapter, Decorator, Observer,
  State, Template Method, Command, Iterator, Facade, Composite, Proxy, DI, Repository, Middleware
  chain, Worker Pool, Circuit Breaker, Retry+jitter+budget, Cache-aside, Idempotency Key,
  Value Object, Expand-contract migration.
- **Tier 2 — right in specific situations.** Abstract Factory, Chain of Responsibility, Visitor,
  Mediator, Bridge, Memento, Flyweight, Object Pool, Specification, Null Object, Unit of Work,
  CQRS, Event Sourcing, Saga, Actor, Bulkhead, Outbox, Leader Election, Hedged Requests,
  Single-writer/sharding.
- **Tier 3 — usually a smell.** Singleton, Prototype, Interpreter, Service Locator, Anemic Domain
  Model, hand-rolled double-checked locking.

### The rubric

Ten dimensions scored 0–3, total 30. Below 20 → revise before presenting. Any single 0 is a
blocker. Dimension 5 (pattern selection) **caps at 1** if any pattern cannot be traced to a
requirement.

Requirements fidelity · Responsibility allocation · Extensibility on the stated axis · Interface
quality · Pattern selection · Concurrency correctness · Failure handling · Testability · Data
modelling · Trade-off communication.

Plus automatic red flags that cap the total at 20 — unjustified Singleton, single-implementation
Strategy, check-then-act on a contended resource, unbounded queues, domain classes importing ORM
types, remote calls without timeouts, retry without idempotency, dual writes, and any breaker,
queue or cache with no stated metric.

## Install

**Claude Code**

```bash
git clone https://github.com/00suryavanshi00/code-design-patterns.git

# project scope
mkdir -p .claude/skills
cp -r code-design-patterns/skill/code-design-patterns .claude/skills/

# or personal scope
mkdir -p ~/.claude/skills
cp -r code-design-patterns/skill/code-design-patterns ~/.claude/skills/
```

**Claude.ai / Cowork** — download [`dist/code-design-patterns.skill`](https://github.com/00suryavanshi00/code-design-patterns/raw/main/dist/code-design-patterns.skill) and upload it from Settings →
Capabilities → Skills.

Nothing to build. No dependencies. It's Markdown.

## Try it

The skill triggers on design work even when you never say "design pattern":

```
Design a rate limiter that works across 10 nodes.
Review this OrderService — it's 400 lines and everything is static.
Should I use Visitor for my plugin node types?
Our Modal component has 11 boolean props. Restructure it.
Grade my vending machine design out of 30.
```

## Testing the skill

`evals/evals.json` holds 8 test prompts with checkable assertions. Two of them (cases 4 and 5) are
**negative tests** — the correct behaviour is restraint and refusal, not more patterns. Run them
with `skill-creator`, or by hand against a Claude with and without the skill loaded.

## Sources

The tiering and real-codebase sightings draw on published analyses of patterns in Kubernetes and
other Go infrastructure projects, the Spring Framework's proxy- and template-based internals,
`java.io`'s decorator chains, and the LLD/machine-coding problem sets that recur across public
interview reports. Resilience patterns follow the now-standard Resilience4j / Polly / Envoy
formulations; the idempotency-key design follows Stripe's.

## Contributing

Useful additions, roughly in order of value:

1. Real-codebase sightings with a file path — concrete beats abstract.
2. Language-specific notes where a language absorbed a pattern (Go's `sync.Once`, Rust's `Result`).
3. Additional LLD problems, but **only** with an axis of change, a trap, and a probe. A problem
   without those three cannot be graded meaningfully.
4. Rubric anchors that are more objectively checkable.

## Website

The landing page lives in a separate private repo — this one is the skill and nothing else, so a
clone contains only what you actually install.

## License

MIT.
