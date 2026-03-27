"""EventDrivenLifecycle -- compound state machine for event-driven agents.

Shared by FulltimeAgent (PM, TYPE-04) and CompanyAgent (Strategist, TYPE-05).
The running state contains listening/processing sub-states. HistoryState
preserves the inner sub-state across sleep/wake and error/recover cycles,
so an agent processing an event when interrupted resumes in the same sub-state.
"""

from __future__ import annotations

from statemachine import HistoryState, State, StateMachine


class EventDrivenLifecycle(StateMachine):
    """Lifecycle FSM for event-driven agents with listening/processing sub-states.

    Unlike GsdLifecycle (phase-driven), this FSM models agents that wait for
    events and process them one at a time. The compound running state has just
    two sub-states: listening (waiting for events) and processing (handling one).
    """

    creating = State(initial=True)

    class running(State.Compound):
        """Compound running state with listening/processing sub-states."""

        listening = State(initial=True)
        processing = State()
        h = HistoryState()

        start_processing = listening.to(processing)
        done_processing = processing.to(listening)

    sleeping = State()
    errored = State()
    stopped = State()
    destroyed = State(final=True)

    # Outer lifecycle transitions
    start = creating.to(running)
    sleep = running.to(sleeping)
    wake = sleeping.to(running.h)  # HistoryState -- preserves listening/processing
    error = creating.to(errored) | running.to(errored) | sleeping.to(errored)
    recover = errored.to(running.h)
    stop = running.to(stopped) | sleeping.to(stopped) | errored.to(stopped)
    destroy = stopped.to(destroyed) | errored.to(destroyed)

    def after_transition(self, event: str, state: State) -> None:
        """Called after every transition -- notify model if it supports callbacks."""
        if self.model and hasattr(self.model, "_on_state_change"):
            self.model._on_state_change()
