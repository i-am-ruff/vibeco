"""GsdLifecycle — compound state machine for GSD agents (TYPE-01).

Extends the ContainerLifecycle pattern by making ``running`` a compound
state containing GSD phase sub-states (IDLE, DISCUSS, PLAN, EXECUTE, UAT,
SHIP). HistoryState preserves the inner phase across sleep/wake and
error/recover cycles.

This FSM replaces external WorkflowOrchestrator state tracking with
agent-internal phase ownership.
"""

from __future__ import annotations

from statemachine import HistoryState, State, StateMachine


class GsdLifecycle(StateMachine):
    """Lifecycle FSM for GsdAgent with nested phase states inside running.

    Extends the ContainerLifecycle pattern by making ``running`` a compound
    state containing GSD phase sub-states (TYPE-01).
    """

    creating = State(initial=True)

    class running(State.Compound):
        """Compound running state containing GSD phase sub-states."""

        idle = State(initial=True)
        discuss = State()
        plan = State()
        execute = State()
        uat = State()
        ship = State()
        h = HistoryState()

        # Phase transitions (inner)
        start_discuss = idle.to(discuss)
        start_plan = discuss.to(plan)
        start_execute = plan.to(execute)
        start_uat = execute.to(uat)
        start_ship = uat.to(ship)

    sleeping = State()
    errored = State()
    stopped = State()
    destroyed = State(final=True)

    # Outer lifecycle transitions
    start = creating.to(running)
    sleep = running.to(sleeping)
    wake = sleeping.to(running.h)
    error = creating.to(errored) | running.to(errored) | sleeping.to(errored)
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
