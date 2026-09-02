"""Minimal disciplined finite-state machine (UML/Harel statechart principles).

Used by the dialogue engine (core/dialogue.DialogueFSM) and intended for any
stateful control flow in MossVoice. Engineering rules are the point of this
module — they are the ones that keep a state machine from "cracking":

  * ONE transition table per machine. All control flow is visible in a
    declarative list (src, event, guard, action, dst); there is no scattered
    if/elif chain to maintain.

  * Guards are PURE predicates over the extended state (ctx). They never
    mutate anything. UML: "guard expressions should have no side effects" —
    otherwise the order in which same-trigger guards are evaluated matters,
    which is a latent bug source.

  * Actions mutate extended state and return a result; they never decide
    which transition fired. Order: guard -> exit source, run action, enter
    target. Entry/exit are implicit (the action that built dst runs there).

  * Run-to-completion (RTC): one event is fully processed before the next.
    The framework does not lock for you — the caller must not re-enter from
    another thread while an event is being processed.

  * An event with no matching transition raises UnhandledEvent. The caller
    decides the safe fallback; a state machine must NEVER silently swallow
    an input it does not understand.

  * Determinism: transitions for the same (state, event) are evaluated in
    declaration order; the FIRST whose guard passes fires. Keep guards
    non-overlapping so the order does not matter, or rely on explicit order.

  * Hierarchy (Harel): a `*` source means "any state" — used to factor out
    the common behavior (danger, done, repair) that would otherwise be
    repeated in every state. This is what prevents state explosion.
"""
from __future__ import annotations


class UnhandledEvent(RuntimeError):
    """Raised when (state, event) has no transition whose guard passes."""

    def __init__(self, state, event):
        self.state = state
        self.event = event
        super().__init__("no transition for %s on %s" % (state, event))


class Transition:
    """One row of the transition table.

    src/dst may be "*" (any state). event may be "*" (any event).
    guard:  callable(ctx, event) -> bool   (PURE, never mutates)
    action: callable(ctx, event) -> result (may mutate, returns the result)
    """

    __slots__ = ("src", "event", "dst", "guard", "action", "name")

    def __init__(self, src, event, dst, action=None, guard=None, name=None):
        self.src = src
        self.event = event
        self.dst = dst
        self.guard = guard
        self.action = action
        self.name = name or "%s/%s -> %s" % (src, event, dst)

    def __repr__(self):
        return "<Transition %s>" % self.name


class StateMachine:
    """Small, explicit state machine with run-to-completion dispatch.

    ctx is an opaque "extended state" object (e.g. the dialogue Agent) that
    guards read and actions write. The machine itself holds only the state
    variable (the qualitative phase); all counters/flags live on ctx.
    """

    def __init__(self, name, initial):
        self.name = name
        self.state = initial
        self._transitions = []
        self._index = {}

    def add(self, src, event, dst, action=None, guard=None, name=None):
        """Declare one transition. Guard/action take (ctx, event)."""
        t = Transition(src, event, dst, action, guard, name)
        self._transitions.append(t)
        key = (src, event)
        self._index.setdefault(key, []).append(t)
        return t

    # ---- matching ------------------------------------------------------
    def _candidates(self, event):
        st = self.state
        # Priority:
        #   1. exact local transition
        #   2. local fallback for any event
        #   3. cross-cutting any-state event (danger/done/repair)
        #   4. total-machine catch-all
        #
        # A local wildcard is more specific than a global event transition;
        # cross-cutting events still beat the final catch-all.
        out = []
        for key in ((st, event), (st, "*"), ("*", event), ("*", "*")):
            out.extend(self._index.get(key, ()))
        return out

    def handle(self, ctx, event):
        """Process one event (run-to-completion). Returns the action result.

        Raises UnhandledEvent when no transition matches."""
        for t in self._candidates(event):
            if t.guard is not None and not t.guard(ctx, event):
                continue
            return self._fire(ctx, t, event)
        raise UnhandledEvent(self.state, event)

    def _fire(self, ctx, t, event):
        result = t.action(ctx, event) if t.action else None
        if t.dst is not None and t.dst != "*":
            self.state = t.dst
        return result

    def in_state(self, *states):
        return self.state in states

    # ---- introspection -------------------------------------------------
    def dump(self):
        return "\n".join(repr(t) for t in self._transitions)