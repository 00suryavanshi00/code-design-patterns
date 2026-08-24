# Design Evaluation Rubric

Use this twice: to self-check a design before presenting it, and as the structure for reviewing
someone else's.

Score each dimension 0–3. **Total 30.** A design scoring below 20 should be revised before it is
shown. Any single 0 is a blocker regardless of the total — a design that is beautifully factored
but silently loses data under concurrency is not a good design.

---

## The ten dimensions

### 1. Requirements fidelity
Does the design actually solve the stated problem, with assumptions made explicit?

- **0** — Solves a different or invented problem; requirements never restated.
- **1** — Covers the happy path; ambiguities silently resolved without saying so.
- **2** — All stated requirements covered; key assumptions stated.
- **3** — Requirements enumerated and traceable to design elements; ambiguities named with the
  assumption taken; non-goals declared.

### 2. Responsibility allocation (SRP / cohesion)
Does each class have one reason to change?

- **0** — One god class holds most of the logic.
- **1** — Classes exist but responsibilities overlap heavily; a `Manager` does everything.
- **2** — Clean separation; names reflect single responsibilities.
- **3** — Cohesive units whose boundaries follow the *reasons for change*, not just topic
  similarity; I/O separated from decision logic.

### 3. Extensibility along the stated axis (OCP)
Adding the thing most likely to be added — is it cheap?

- **0** — Any extension requires editing core logic in several places.
- **1** — Extension possible but touches multiple unrelated files.
- **2** — The main axis of change is behind an interface; extension means adding a class.
- **3** — The design explicitly names the axis of change, and includes a concrete walkthrough
  of adding a new variant that touches ≤2 files.

### 4. Interface quality
Are the abstractions the right shape?

- **0** — No interfaces; concrete classes depend on each other directly.
- **1** — Interfaces exist but leak implementation (ORM types, SQL, vendor SDK types).
- **2** — Clean, minimal interfaces owned by the consumer; a second implementation is plausible.
- **3** — Interfaces are minimal and hard to misuse: illegal states unrepresentable, no boolean
  traps, errors modelled in the signature, no method that must be called before another without
  the type enforcing it.

### 5. Pattern selection and justification
Right patterns, for named reasons, with alternatives considered.

- **0** — Patterns applied decoratively; a Singleton, a Factory over `new`, or a Strategy with one
  implementation.
- **1** — Reasonable patterns, no justification given.
- **2** — Each pattern traced to a specific force in the requirements.
- **3** — Also names a credible rejected alternative and why; and demonstrates restraint by
  choosing a plain function/map where a pattern would have been overkill.

**This dimension caps at 1 if any pattern in the design cannot be traced to a requirement.**

### 6. Concurrency and state correctness

- **0** — Shared mutable state with no synchronisation, or a check-then-act race on a critical
  resource.
- **1** — "Add a lock" mentioned without saying what it guards or what the atomic unit is.
- **2** — Shared state identified, protection specified, atomic units correct.
- **3** — Contention profile considered (lock vs. RWLock vs. CAS vs. sharding vs. confinement);
  no lock held across I/O; lifecycle and shutdown addressed; the reasoning for the choice given.

If the problem is genuinely single-threaded, say so explicitly and score on that basis.

### 7. Failure handling
- **0** — Failure never mentioned; every call assumed to succeed.
- **1** — Errors thrown but not modelled; no timeouts on remote calls.
- **2** — Expected failures modelled distinctly from bugs; timeouts and retries where remote.
- **3** — Partial failure reasoned about: what is idempotent, what compensates, what the caller
  sees when a dependency is down, and what is *not* recoverable.

### 8. Testability
- **0** — Requires a live database or network to test anything; time and randomness called inline.
- **1** — Testable with heavy mocking of concrete classes.
- **2** — Dependencies injected; domain logic testable in isolation.
- **3** — Seams are obvious, non-determinism (clock, UUID, random) injected, the design names
  which tests would exist and at what level, **and it says how each pattern introduced would be
  observed in production** — one metric per breaker, queue, or cache, and what would page
  someone. See `09-operability.md`. A component nobody can observe is not operable, however
  testable it is.

### 9. Data modelling
- **0** — Primitives everywhere; invalid states representable and reachable.
- **1** — Classes exist but are anemic data bags with public setters.
- **2** — Value objects for key concepts; invariants enforced somewhere.
- **3** — Invariants enforced *at construction*, aggregate boundaries deliberate, identity vs.
  value distinguished, and the persistence shape not dictating the domain shape.

### 10. Communication of trade-offs
- **0** — Presented as the one correct answer.
- **1** — Trade-offs mentioned generically ("this is more flexible").
- **2** — Specific costs named for specific choices.
- **3** — States what the design is *bad* at, when it would be rewritten, and what the simpler
  version would be if a requirement were dropped.

---

## Automatic red flags

Any of these caps the total at 20 regardless of other scores. They are the recurring failure modes
in machine-generated designs specifically.

| Red flag | Why |
|---|---|
| A Singleton that is not process-wide immutable config | Hidden dependency, untestable, unsafe |
| A Strategy/Factory interface with exactly one implementation and no stated second | Ceremony without benefit |
| An Observer with no described subscriber | Speculative machinery |
| Check-then-act on a contended resource | A real race condition |
| Unbounded queue or unbounded thread creation | Turns load into OOM |
| Domain classes importing framework, ORM, or vendor types | The layering is decorative |
| A remote call with no timeout | The most common production outage |
| Retry on a non-idempotent operation with no idempotency key | Duplicate charges and duplicate sends |
| Every class name ends in `Manager`, `Service`, `Helper`, or `Handler` | Responsibilities were never actually identified |
| More than five patterns named in one small design | Pattern-stuffing |
| A circuit breaker, bounded queue, or cache with no stated metric | Unobservable in production; failure is undiagnosable |
| Writing to a database and a queue as two separate commits | Dual writes — silent data loss |
| A UML diagram whose classes never appear in the code, or vice versa | The design was not thought through as one artefact |

---

## How to report a review

```
## Verdict
[One or two sentences: what this design gets right, and the single thing most worth changing.]

## Score: NN/30
| Dimension | Score | Note |
| ... | ... | one line each |

## The two things that matter most
1. [Problem] — [why it bites in practice] — [concrete first move]
2. ...

## Smaller notes
[Bulleted, brief. No more than five.]

## What this design does well
[Genuine, specific. Not filler — if a reviewer cannot find anything, the review is probably
uncharitable.]
```

Order matters: verdict before detail, and the two-things section before the long tail. Reviews
that open with a list of eleven equally-weighted issues do not get acted on.

---

## Worked example

**Design under review:** a parking-lot system with `ParkingLotManager` (a singleton) holding a
`List<Spot>`; a `getSpot(VehicleType)` method with a `switch` over vehicle types choosing a spot;
fee calculated inside `Ticket.close()` using `System.currentTimeMillis()`; `VehicleFactory`
producing `Car`, `Bike`, `Truck`, which differ only in an enum field.

| Dimension | Score | Note |
|---|---|---|
| 1. Requirements fidelity | 2 | Covers park/unpark/pay; multi-floor and concurrency unaddressed |
| 2. Responsibility allocation | 1 | Manager does allocation, pricing, and persistence |
| 3. Extensibility | 1 | New vehicle type edits the `switch` *and* the factory |
| 4. Interface quality | 1 | No interfaces; `getSpot` returns null on failure |
| 5. Pattern selection | 0 | Singleton unjustified; `VehicleFactory` wraps `new` over classes that should be one class with a type field |
| 6. Concurrency | 0 | Two entrances can allocate the same spot — check-then-act |
| 7. Failure handling | 1 | Null return for "lot full"; no payment failure path |
| 8. Testability | 0 | Singleton plus inline clock — fees cannot be tested deterministically |
| 9. Data modelling | 1 | `Ticket` is a data bag; fee as `double`; no `Money` |
| 10. Trade-offs | 1 | None stated |

**Total: 8/30**, with red flags (unjustified Singleton, check-then-act, factory over `new`).

**The two things that matter most:**

1. **The spot allocation race.** Two entrances calling `getSpot` concurrently can both receive the
   same free spot. First move: make claiming a spot a single atomic operation — a CAS on the
   spot's status, or allocation behind a per-floor lock — and have it return `Optional<Spot>` so
   "full" is a modelled outcome rather than a null.
2. **Allocation policy is welded into the manager.** The `switch` means every new rule (EV bays,
   reserved spots, oversize handling) edits the same method. First move: extract
   `SpotAllocationStrategy` — this is the stated axis of change, so it earns the interface, unlike
   the `VehicleFactory`, which should be deleted in favour of a single `Vehicle` with a
   `VehicleType`.

**Smaller notes:** inject a `Clock` so fee calculation is testable; replace `double` fees with a
`Money` value object; drop the singleton and construct one `ParkingLot` at startup; model `Ticket`
as `ActiveTicket`/`ClosedTicket` so a closed ticket cannot be closed twice.

**What it does well:** the entity decomposition (`Lot`/`Floor`/`Spot`/`Ticket`) is the right
skeleton, and keeping fee calculation attached to the ticket rather than a separate service is a
defensible call.
