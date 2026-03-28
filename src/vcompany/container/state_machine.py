"""ContainerLifecycle FSM using python-statemachine.

Defines the 8-state lifecycle for every AgentContainer:
CREATING -> RUNNING -> SLEEPING -> BLOCKED -> STOPPING -> STOPPED -> DESTROYED
                                -> ERRORED

Invalid transitions raise TransitionNotAllowed automatically.
"""

from statemachine import State, StateMachine


class ContainerLifecycle(StateMachine):
    """Lifecycle state machine for agent containers (CONT-01, CONT-02, ARCH-03, LIFE-01)."""

    # States
    creating = State(initial=True)
    running = State()
    sleeping = State()
    blocked = State()   # ARCH-03: real FSM state (not a boolean)
    stopping = State()  # LIFE-01: transitional state before stopped
    errored = State()
    stopped = State()
    destroyed = State(final=True)

    # Valid transitions
    start = creating.to(running)
    sleep = running.to(sleeping)
    wake = sleeping.to(running)
    error = creating.to(errored) | running.to(errored) | sleeping.to(errored) | blocked.to(errored)
    recover = errored.to(running)

    # Block/unblock (ARCH-03)
    block = running.to(blocked)
    unblock = blocked.to(running)

    # Two-phase stop (LIFE-01)
    begin_stop = (running.to(stopping) | sleeping.to(stopping)
                  | errored.to(stopping) | blocked.to(stopping))
    finish_stop = stopping.to(stopped)

    destroy = stopped.to(destroyed) | errored.to(destroyed)

    def after_transition(self, event: str, state: State) -> None:
        """Called after every transition -- notify model if it supports callbacks."""
        if self.model and hasattr(self.model, "_on_state_change"):
            self.model._on_state_change()

    def send_event(self, name: str) -> None:
        """String-based event dispatch for supervisor use."""
        self.send(name)
