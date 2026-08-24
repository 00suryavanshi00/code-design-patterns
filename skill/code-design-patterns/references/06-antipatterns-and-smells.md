# Anti-Patterns and Code Smells

Use this when reviewing existing code or critiquing a design. Each entry gives the detectable
signature, why it hurts, and the smallest first move — not a rewrite.

Review discipline: **lead with the two highest-leverage problems.** A review listing fourteen
issues gets none of them fixed. Rank by (blast radius × likelihood of causing a real bug), and
give one concrete first step.

## Structural smells

### God Object / God Class
**Signature:** 500+ lines, a name ending in `Manager`/`Helper`/`Utils`/`Processor`, more than
~7 dependencies, and a diff history where every feature touches it.
**Cost:** every change risks unrelated behaviour; it cannot be tested in isolation; it becomes a
merge-conflict magnet.
**First move:** find one cohesive cluster of methods sharing the same fields and extract it. Do
not attempt the whole split at once.

### Anemic Domain Model
**Signature:** entities are getters and setters only; all behaviour lives in `*Service` classes.
**Cost:** invariants have nowhere to live, so they get re-checked at every call site — or missed
at one. An `Order` that anyone can set to `status = SHIPPED` without payment has no invariants.
**First move:** move one invariant into the entity and make the corresponding setter private.

### Primitive Obsession
**Signature:** `String email`, `double amount`, `long userId`, `Map<String, Object> config`
threaded through signatures.
**Cost:** nothing prevents passing a customer ID where an order ID is expected, or adding USD to
EUR. Validation is repeated or forgotten.
**First move:** introduce one value object where the bug risk is highest — usually `Money` or an
identifier type.

### Shotgun Surgery
**Signature:** adding one field means editing eleven files.
**Cost:** the change is expensive and something always gets missed.
**Diagnosis:** the concept is smeared across layers instead of owned by one module. Often a
symptom of technical-kind folder structure (`controllers/`, `services/`, `dtos/`) rather than
feature structure.

### Circular Dependency
**Signature:** module A imports B imports C imports A. Build tools may allow it; comprehension
does not.
**Cost:** nothing can be understood, tested, or extracted independently.
**First move:** invert one edge — extract the shared interface into a lower layer that both depend
on (this is the Dependency Inversion Principle doing its actual job).

### Leaky Abstraction
**Signature:** a `Repository` returning ORM entities with lazy relations; a `Cache` interface with
a `redisPipeline()` method; a "database-agnostic" layer whose method names are SQL.
**Cost:** you pay the cost of the abstraction and get none of the benefit — swapping the
implementation is still impossible.
**Test:** could a second implementation satisfy this interface without absurdity? If no, it is not
an abstraction.

### Feature Envy
**Signature:** a method that mostly calls getters on another object and computes from them.
**First move:** move the method to the class whose data it uses.

## Abstraction smells

### Pattern-Stuffing
**Signature:** an `AbstractSingletonProxyFactoryBean`. A Strategy interface with one
implementation. An Observer with no subscribers. A Factory that wraps `new`.
**Cost:** every reader pays comprehension tax for flexibility nobody uses. It is the most common
failure in AI-generated and interview designs specifically.
**Test:** for each pattern, name the requirement that forces it. No requirement → delete it.

### Premature Abstraction / Speculative Generality
**Signature:** interfaces with one implementation "for future flexibility"; configuration for
things nobody configures; a plugin system with one plugin.
**Cost:** the abstraction is invariably wrong, because it was designed against imagined
requirements. Then it is load-bearing and hard to remove.
**Rule of thumb:** abstract on the second real instance, not the first imagined one. Duplication is
cheaper to fix than the wrong abstraction.

### Singleton Abuse
**Signature:** `getInstance()` called from inside business logic.
**Cost:** hidden dependency, untestable, test-order-dependent, unsafe under concurrency.
**First move:** keep one instance, but create it at the composition root and pass it in.

### Service Locator
**Signature:** `container.resolve(Foo.class)` inside a method body.
**Cost:** dependencies are invisible in the signature; failures move from compile time to run time.
**First move:** promote the resolved dependencies to constructor parameters.

### Utils Junk Drawer
**Signature:** `StringUtils`, `Helpers`, `Common`, `Misc` — files that only grow.
**Cost:** no cohesion, no ownership, and functions that belong on domain types instead.
**First move:** move each function to the type it operates on, or into a named, focused module.

## Process and system smells

### Distributed Monolith
**Signature:** services that must be deployed together; a schema change requiring coordinated
releases; synchronous call chains five services deep; shared database tables.
**Cost:** all the operational complexity of microservices, none of the independence.
**Diagnosis question:** can any one service be deployed on a Friday alone? If not, the boundaries
are wrong — they were drawn along technical layers rather than along business capabilities.

### Chatty Interface / N+1
**Signature:** a loop containing a network or database call.
**First move:** batch it — one call taking a list. In ORMs, an explicit join or eager fetch.

### Callback Hell / Promise Pyramid
**Signature:** nesting deeper than three levels of asynchronous continuations.
**First move:** `async/await`, and extract each level into a named function.

### Big Ball of Mud
**Signature:** no discernible architecture; everything reachable from everything.
**First move:** do not rewrite. Draw a boundary around one well-understood capability, put an
interface in front of it, and grow the island. (Strangler Fig: route new functionality through the
new module and migrate incrementally.)

### Golden Hammer
**Signature:** every problem solved with the team's favourite tool — Kafka for a cron job, a
microservice for a form, Kubernetes for a static site.

### Copy-Paste Programming
**Signature:** the same block in six places, diverging slightly.
**Nuance:** do not deduplicate reflexively. Two pieces of code that look identical but change for
different reasons should stay separate — that is coincidental duplication, and merging them
creates coupling that will hurt later.

### Boolean Trap
**Signature:** `render(true, false, true)`.
**First move:** named parameters, an options object, or separate functions.

### Exception as Control Flow
**Signature:** expected outcomes (not found, validation failed) thrown and caught routinely;
`catch (Exception e) {}` swallowing everything.
**First move:** model expected failures as return values (see Result types in
`02-modern-application-patterns.md`), reserve exceptions for genuinely exceptional cases, and
never swallow silently.

## SOLID, stated as detectable smells

| Principle | The smell that violates it |
|---|---|
| **S**ingle Responsibility | The class has more than one reason to change; its name needs "and" |
| **O**pen/Closed | Adding a variant means editing an existing `switch` instead of adding a file |
| **L**iskov Substitution | A subclass throws `UnsupportedOperationException`, or tightens preconditions |
| **I**nterface Segregation | Implementers are forced to stub methods they do not need |
| **D**ependency Inversion | A high-level policy class imports a concrete driver or vendor SDK |

Liskov's classic tell: `Square extends Rectangle` breaks any caller that sets width and height
independently. If a subclass surprises callers of the base type, inheritance was the wrong tool —
use composition.

## Refactoring order

When several smells coexist, sequence matters:

1. **Get a test harness around it first.** Characterisation tests that capture current behaviour,
   even wrong behaviour.
2. **Break dependencies** — introduce seams by injecting what was constructed inline. This is what
   makes everything after it possible.
3. **Extract cohesive pieces** — one at a time, keeping tests green.
4. **Introduce abstractions only where a second implementation now exists.**
5. **Then** consider patterns.

Doing step 5 first is how a big ball of mud becomes a big ball of mud with interfaces.
