"""ContainerLifecycle FSM using python-statemachine.

Defines the 6-state lifecycle for every AgentContainer:
CREATING -> RUNNING -> SLEEPING -> ERRORED -> STOPPED -> DESTROYED

Invalid transitions raise TransitionNotAllowed automatically.
"""

from statemachine import State, StateMachine


class ContainerLifecycle(StateMachine):
    """Lifecycle state machine for agent containers (CONT-01, CONT-02)."""

    # States
    creating = State(initial=True)
    running = State()
    sleeping = State()
    errored = State()
    stopped = State()
    destroyed = State(final=True)

    # Valid transitions
    start = creating.to(running)
    sleep = running.to(sleeping)
    wake = sleeping.to(running)
    error = creating.to(errored) | running.to(errored) | sleeping.to(errored)
    recover = errored.to(running)
    stop = running.to(stopped) | sleeping.to(stopped) | errored.to(stopped)
    destroy = stopped.to(destroyed) | errored.to(destroyed)

    def after_transition(self, event: str, state: State) -> None:
        """Called after every transition -- notify model if it supports callbacks."""
        if self.model and hasattr(self.model, "_on_state_change"):
            self.model._on_state_change()

    def send_event(self, name: str) -> None:
        """String-based event dispatch for supervisor use."""
        self.send(name)
