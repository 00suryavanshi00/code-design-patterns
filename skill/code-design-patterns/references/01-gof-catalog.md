# The 23 GoF Patterns, Weighted by Real-World Use

Each entry: the force it resolves, where it actually shows up in code people ship, the minimal
shape, and — most importantly — when it is the wrong answer.

## Contents

- [Creational](#creational) — Factory Method, Abstract Factory, Builder, Prototype, Singleton
- [Structural](#structural) — Adapter, Decorator, Facade, Proxy, Composite, Bridge, Flyweight
- [Behavioural](#behavioural) — Strategy, Observer, State, Command, Template Method, Iterator,
  Chain of Responsibility, Visitor, Mediator, Memento, Interpreter

---

## Creational

### Factory Method — Tier 1

**Force:** the caller needs an object but should not know which concrete class, or construction
requires knowledge the caller lacks.

**In the wild:** Kubernetes builds clients and informers through factory functions rather than
exported constructors, so the concrete type can change without breaking callers. Spring's whole
bean container is a factory. `java.util.Collection.iterator()` is the textbook case.

```java
interface PaymentGateway { Receipt charge(Money m); }

final class GatewayFactory {
    static PaymentGateway forCountry(CountryCode c) {
        return switch (c) {
            case IN -> new RazorpayGateway();
            case US -> new StripeGateway();
            default -> new FallbackGateway();
        };
    }
}
```

**Not this when:** construction is `new Thing(a, b)`. Wrapping a one-line constructor in a
factory adds a file and buys nothing. Also not when a plain map from key to supplier is clearer
— that *is* the pattern, just without the ceremony.

### Abstract Factory — Tier 2

**Force:** you need *families* of objects that must be used together and must not be mixed —
a `PostgresConnection` must pair with a `PostgresDialect`, never a `MySQLDialect`.

**In the wild:** UI toolkit theming, database driver families, cloud provider abstractions
(`AwsResourceFactory` producing a matched queue + blob store + secret client).

**Not this when:** there is only one family, or the objects do not actually constrain each
other. One family means you wrote an interface and called it a factory. This is the most
over-applied creational pattern in interview answers.

### Builder — Tier 1

**Force:** an object has many optional parameters, or its construction is multi-step, or it
should be immutable once built.

**In the wild:** `StringBuilder`; Java's `HttpRequest.newBuilder()`; Kubernetes' `PodBuilder`
in test fixtures; Go's functional-options idiom is Builder wearing a different hat:

```go
type Server struct{ port int; tls *tls.Config; timeout time.Duration }
type Option func(*Server)

func WithTLS(c *tls.Config) Option { return func(s *Server) { s.tls = c } }
func New(opts ...Option) *Server { /* apply defaults, then opts */ }
```

**Not this when:** there are three parameters and all are required. A constructor is fine.
Builders shine past roughly four optional fields or when telescoping constructors appear.

### Prototype — Tier 3

**Force:** creating a fresh instance is expensive, but copying a configured one is cheap.

**In the wild:** rare in modern code — most languages give you `copy`, `clone`, `structuredClone`,
or a copy constructor. Survives in game engines (entity templates) and object pools.

**Not this when:** almost always. Reach for the language's copy idiom. Deep-vs-shallow copy bugs
are the usual reward for hand-rolling this.

### Singleton — Tier 3, usually a smell

**Force:** exactly one instance should exist, with global access.

**Why it is a trap:** the "global access" half is the problem, not the "one instance" half. A
singleton hides a dependency (callers do not declare it), makes tests order-dependent and
non-parallelisable, and is a data race waiting to happen under concurrency. Kubernetes' Go
codebase uses very few globals outside configuration for exactly this reason.

**What to do instead:** create one instance at the composition root (`main`, the DI container,
the app bootstrap) and inject it. You keep "exactly one" and lose the global.

```go
// If you must: at least make it race-free and initialised once.
var once sync.Once
var instance *Registry
func GetInstance() *Registry { once.Do(func(){ instance = &Registry{} }); return instance }
```

**Legitimate uses:** process-wide immutable configuration, a logger facade, a connection pool
that genuinely must be shared. Even then, prefer injection.

---

## Structural

### Adapter — Tier 1

**Force:** an existing component does the right thing with the wrong interface, and you cannot
or should not change it.

**In the wild:** everywhere at integration boundaries. Prometheus adapts many exporter formats
to a common scrape interface. In Domain-Driven Design this is the Anti-Corruption Layer: a
third-party model gets translated at the boundary so its vocabulary never leaks into your domain.

**Not this when:** you own both sides. Fix the interface instead of papering over it.

### Decorator — Tier 1

**Force:** behaviour should be added to individual objects, stackably, without subclass explosion.

**In the wild:** `java.io` streams (`new BufferedReader(new InputStreamReader(...))`); HTTP
middleware in every web framework — logging, auth, compression, and tracing wrapped around a
handler are decorators, and the fact that order matters is the pattern working correctly.

```typescript
type Handler = (req: Request) => Promise<Response>;
const withLogging = (next: Handler): Handler => async (req) => {
  const t = Date.now();
  const res = await next(req);
  log(req.url, Date.now() - t);
  return res;
};
```

**Not this when:** only one decoration will ever exist — then it is just a wrapper class, and
naming it a Decorator oversells it. Also watch stack depth: five layers of decoration makes
debugging miserable.

### Facade — Tier 1

**Force:** a subsystem is correct but has too many moving parts for the common case.

**In the wild:** `kubectl` over the API machinery; `requests` over `urllib3`; any `*Service`
class that orchestrates three repositories behind one method.

**Not this when:** the facade grows methods until it *is* the subsystem. A facade that needs
updating every time the subsystem changes is not a facade, it is a second copy.

### Proxy — Tier 1

**Force:** access to an object must be controlled, deferred, cached, or made remote — without
the caller knowing.

**In the wild:** the single most load-bearing pattern in Spring. `@Transactional`, `@Cacheable`,
and `@Async` all work by wrapping your bean in a generated proxy (JDK dynamic proxy when an
interface exists, CGLIB subclass otherwise). ORMs use lazy-loading proxies for relations.
Service meshes are the network-level version.

**Not this when:** the added indirection is invisible in a way that will confuse people — proxy
magic that changes semantics (self-invocation not going through the proxy is a classic Spring
bug) is a real cost.

### Composite — Tier 1

**Force:** clients should treat individual objects and groups of them uniformly, in a tree.

**In the wild:** every DOM and UI widget tree; filesystem directories; nested permission groups;
query predicate trees (`And(Or(a, b), c)`).

**Not this when:** the tree is one level deep, or leaves and containers genuinely need different
interfaces and you are forcing a shared one with methods that throw on leaves.

### Bridge — Tier 2

**Force:** two dimensions vary independently and you are about to write M×N subclasses.

**In the wild:** rendering backends × shapes; notification channels × message types; JDBC's
driver abstraction separating the API from vendor implementations.

**Not this when:** only one dimension actually varies. Recognise it by the smell it prevents:
class names like `WindowsPngRenderer`, `LinuxPngRenderer`, `WindowsSvgRenderer`.

### Flyweight — Tier 2

**Force:** huge numbers of objects share most of their state, and memory is the constraint.

**In the wild:** string interning; glyph caches in text renderers; tile/sprite reuse in games;
Java's `Integer.valueOf` cache for small values.

**Not this when:** you have not measured a memory problem. This is an optimisation that costs
mutability safety — shared intrinsic state must be immutable or you get action at a distance.

---

## Behavioural

### Strategy — Tier 1, the workhorse

**Force:** an algorithm or policy must vary, independently of the code that uses it.

**In the wild:** Kubernetes scheduler plugins; sorting comparators; retry policies; pricing and
allocation rules. If you learn one pattern, learn this one — it is the most frequently correct
answer in LLD problems.

```java
interface SpotAllocationStrategy { Optional<Spot> allocate(Floor f, VehicleType t); }
final class NearestToEntrance implements SpotAllocationStrategy { /* ... */ }
final class SpreadAcrossFloors implements SpotAllocationStrategy { /* ... */ }
```

**Not this when:** the strategy has no state and the language has first-class functions — pass
the function. A one-method interface is a function with paperwork. (Java's `Comparator` is
fine because it also carries combinators.)

### Observer / Publish-Subscribe — Tier 1

**Force:** something happened, and an unknown set of parties needs to know, without the source
depending on them.

**In the wild:** Kubernetes informers and watch loops; DOM event listeners; Prometheus'
notification fan-out; every event bus.

**Critical distinction:** in-process Observer is synchronous and shares the caller's thread and
failure domain — a slow listener blocks the publisher, and a throwing listener can break it.
Pub/Sub over a broker is asynchronous with independent failure. Do not silently substitute one
for the other in a design; say which you mean.

**Not this when:** there is exactly one known listener. Call it directly. Also beware
lapsed-listener leaks: unsubscription must be as easy as subscription.

### State — Tier 1

**Force:** an object's behaviour changes with its lifecycle stage, and you are writing
`if (status == ...)` in five methods.

**In the wild:** vending machines, order/payment lifecycles, TCP connection state, circuit
breakers (Closed → Open → Half-Open), CI job status.

**The tell you need it:** the same conditional on a status field appears in more than two
methods, and adding a new status means editing all of them.

**Not this when:** three states, no per-state data, and one transition method. An enum with a
transition table is smaller and easier to see whole.

### Command — Tier 1

**Force:** an action must be first-class — queued, logged, retried, scheduled, or undone.

**In the wild:** undo/redo stacks; job queues where a task is serialised and executed elsewhere;
`Runnable`/`Callable`; database migration steps; the Memento pairing for editors.

**Not this when:** the action is invoked immediately and never needs to be stored. That is a
method call.

### Template Method — Tier 1

**Force:** several algorithms share a skeleton and differ in a few steps.

**In the wild:** Spring's `JdbcTemplate`, `RestTemplate`, `JmsTemplate` — the boilerplate of
acquire-connection, execute, translate-exceptions, release is fixed, and your callback is the
varying step. Test frameworks' setup/teardown lifecycles.

**Not this when:** the shared skeleton is two lines, or the subclass hooks start needing each
other's data. Modern preference: pass the varying step as a lambda (a Strategy) rather than
requiring inheritance — it composes better and does not consume the single base class.

### Iterator — Tier 1

**Force:** traverse a collection without exposing its internals, and without loading it all.

**In the wild:** built into most languages now (`Iterable`, generators, `range`, `IEnumerable`).
The pattern still matters when you write a custom paginated API client that yields pages lazily.

**Not this when:** the language already gives it to you. Hand-rolling `hasNext`/`next` over an
array is a red flag in a modern codebase.

### Chain of Responsibility — Tier 2

**Force:** a request should be offered to a sequence of handlers until one takes it, and the
sender should not know which.

**In the wild:** servlet filter chains; expense-approval ladders; log-level handler chains;
event bubbling in UI.

**Overlap warning:** middleware is usually a Decorator chain (every layer runs) not a
Chain of Responsibility (first match wins). Interviewers notice the difference.

**Not this when:** you know statically which handler applies — dispatch on a map instead of
walking a chain. Also, unhandled requests falling off the end silently is a common bug; decide
what happens there.

### Visitor — Tier 2

**Force:** you need to add many *operations* over a *stable* class hierarchy without editing
every class.

**In the wild:** compiler and AST work — type checking, code generation, and pretty-printing are
three visitors over the same node types. Kubernetes uses a visitor over resource collections in
its CLI machinery.

**The trade-off that decides it:** Visitor makes new operations cheap and new *types* expensive
(every visitor must be updated). If your types churn more than your operations, Visitor is
exactly backwards. Ask which axis changes before recommending it.

**Not this when:** the language has pattern matching or multiple dispatch — a `match` on a sealed
type does this with far less machinery.

### Mediator — Tier 2

**Force:** N components all talk to each other and the graph has become unmanageable.

**In the wild:** air-traffic-control-style coordinators; chat room servers; complex form controls
where field A enables field B and disables C.

**Not this when:** the mediator becomes a god object that knows everything about everyone —
which is the usual outcome. You may have moved the mess rather than removed it.

### Memento — Tier 2

**Force:** capture and restore an object's state without exposing its internals.

**In the wild:** editor undo (paired with Command); game saves; transaction rollback snapshots;
React's state history in time-travel debuggers.

**Not this when:** the state is large and snapshots are frequent — store a diff or a command log
instead.

### Interpreter — Tier 3

**Force:** a simple language needs evaluating and you control the grammar.

**In the wild:** rules engines, query filters, feature-flag targeting expressions.

**Not this when:** almost always. Grammar work grows teeth fast — use a parser generator, an
expression library (CEL, JSONLogic, JEXL), or an embedded scripting language. Hand-rolled
interpreters in production tend to acquire operator precedence bugs.

---

## Cross-cutting notes

**Patterns that get confused for each other:**

| Pair | The distinguishing question |
|---|---|
| Strategy vs. State | Does the *caller* choose it (Strategy), or does the object switch itself as its lifecycle advances (State)? |
| Decorator vs. Proxy | Same structure. Decorator *adds* behaviour; Proxy *controls access* to the same behaviour. |
| Adapter vs. Facade | Adapter changes an interface's shape; Facade simplifies a whole subsystem. |
| Factory Method vs. Abstract Factory | One product vs. a family of products that must match. |
| Chain of Responsibility vs. Decorator | First handler wins vs. every layer runs. |
| Observer vs. Mediator | Broadcast to unknown subscribers vs. coordinate known components. |

**Language shifts that made some patterns vanish:** first-class functions absorbed Strategy and
Command in their simplest forms; generics absorbed much of Abstract Factory; pattern matching on
sealed types absorbed Visitor; language-level iteration absorbed Iterator; `sync.Once`, `lazy`,
and module systems absorbed Singleton. Recommending the heavyweight form in a language that has
the light one is a sign of pattern knowledge without current practice.
