"""ContinuousLifecycle — compound state machine for ContinuousAgent (TYPE-03).

Extends the ContainerLifecycle pattern by making ``running`` a compound
state containing cycle sub-states (WAKE, GATHER, ANALYZE, ACT, REPORT,
SLEEP_PREP). HistoryState is used ONLY for error/recover (resume mid-cycle).
Wake always starts a fresh cycle at the wake sub-state.

This FSM defines the ContinuousAgent's repeating cycle behavior.
"""

from __future__ import annotations

from statemachine import HistoryState, State, StateMachine


class ContinuousLifecycle(StateMachine):
    """Lifecycle FSM for ContinuousAgent with nested cycle phases inside running.

    Key difference from GsdLifecycle:
    - ``wake`` transition goes to ``running`` (fresh start at wake sub-state),
      NOT ``running.h`` (HistoryState).
    - ``recover`` transition goes to ``running.h`` (resume mid-cycle after crash).
    """

    creating = State(initial=True)

    class running(State.Compound):
        """Compound running state containing cycle phase sub-states."""

        wake = State(initial=True)
        gather = State()
        analyze = State()
        act = State()
        report = State()
        sleep_prep = State()
        h = HistoryState()

        # Cycle phase transitions (inner)
        start_gather = wake.to(gather)
        start_analyze = gather.to(analyze)
        start_act = analyze.to(act)
        start_report = act.to(report)
        start_sleep_prep = report.to(sleep_prep)

    sleeping = State()
    errored = State()
    stopped = State()
    destroyed = State(final=True)

    # Outer lifecycle transitions
    start = creating.to(running)
    sleep = running.to(sleeping)
    # CRITICAL: wake goes to running (fresh start), NOT running.h
    wake = sleeping.to(running)
    error = creating.to(errored) | running.to(errored) | sleeping.to(errored)
    # CRITICAL: recover uses HistoryState to resume mid-cycle
    recover = errored.to(running.h)
    stop = running.to(stopped) | sleeping.to(stopped) | errored.to(stopped)
    destroy = stopped.to(destroyed) | errored.to(destroyed)

    def after_transition(self, event: str, state: State) -> None:
        """Called after every transition -- notify model if it supports callbacks."""
        if self.model and hasattr(self.model, "_on_state_change"):
            self.model._on_state_change()

    def send_event(self, name: str) -> None:
        """String-based event dispatch for supervisor use."""
        self.send(name)
