---
name: engineering-architecture
description: Guide for pre-implementation architectural reasoning, formal logic design, state machines, and system invariants. Use when designing new features, refactoring existing modules, implementing state transitions, or making architectural decisions.
---

# Engineering Architecture & Logic-First Design

This skill guides the agent in rigorously analyzing and structuring architectural solutions before writing code.
It prevents rushed, ad-hoc patching, logic flaws, state corruption, and unhandled edge cases.

---

## The 5-Step Architecture Protocol

When tasked with designing a new component, refactoring a module, or solving a non-trivial problem, follow this structured process:

### Step 1: Domain & Boundary Modeling
1. Identify the core domain entities, their ownership hierarchy, and lifecycle states.
2. Define the system boundary: What is internal state vs. external dependency (network, database, audio device)?
3. Establish strong typing for all boundaries: use Pydantic schemas, typed dataclasses, or strict protocol interfaces.

### Step 2: Invariants & Contracts Specification
1. **Preconditions:** What conditions must hold true before each function or transition executes?
2. **Postconditions:** What state mutations are guaranteed upon successful completion?
3. **Invariants:** What fundamental truths must never be violated across concurrent operations?
   *(e.g., "A call session cannot transition to ACTIVE without an allocated audio stream buffer.")*

### Step 3: State Machine & Transition Formulation
If the component involves lifecycles, protocols, or multi-step interactions:
1. Enumerate all discrete states. Avoid boolean flag combinations.
2. Enumerate all external events and signals.
3. Formulate a declarative transition table:
   `State(S) + Event(E) [Guard(G)] -> Action(A) + NextState(S')`
4. Guarantee **Totality**: ensure every event in every state has either a valid transition or an explicit, safe fallback/error response.
5. Guarantee **Run-To-Completion (RTC)**: atomic state updates without interleaved race conditions.

### Step 4: Concurrency & Failure Mode Analysis (FMEA)
1. **Concurrency Model:** Is the component multithreaded, async (event loop), or multiprocess? Where are the synchronization barriers?
2. **Failure Scenarios:**
   - What happens on connection drop?
   - What happens on timeout?
   - What happens on duplicate or re-ordered events?
   - What happens if the process crashes mid-operation? (Idempotency and recovery).
3. **Resource Management:** Ensure all sockets, file descriptors, memory buffers, and DB transactions have guaranteed cleanup (`with`, `try/finally`).

### Step 5: Verification Strategy
1. Define the test matrix: happy path, boundary values, error injection, concurrent access.
2. Define observable metrics: latency trace points, state transition logs, and health status indicators.

---

## Quick Reference Checklist

Before starting implementation, verify:

- [ ] All states, events, and guards are explicitly defined in a single transition table.
- [ ] No hidden boolean flags (`_flag1`, `_flag2`) represent state.
- [ ] All external calls have bounded timeouts and circuit breaking.
- [ ] Concurrency locks or atomic primitives (`SKIP LOCKED`, mutexes) prevent race conditions.
- [ ] Error paths guarantee resource cleanup and state consistency.

---

## Detailed References & Examples

- For deep theoretical patterns, FSM specifications, and concurrency catalogs, see [reference.md](reference.md).
- For concrete real-world architectures in this codebase, see [examples.md](examples.md).
