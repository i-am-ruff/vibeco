"""Restart strategies for supervision tree (SUPV-02, SUPV-03, SUPV-04)."""

from enum import Enum


class RestartStrategy(str, Enum):
    """Erlang-style restart strategies for supervisors.

    ONE_FOR_ONE: Restart only the failed child, siblings untouched.
    ALL_FOR_ONE: Stop all children in reverse order, restart all in forward order.
    REST_FOR_ONE: Stop failed child + later children in reverse order, restart in forward order.
    """

    ONE_FOR_ONE = "one_for_one"
    ALL_FOR_ONE = "all_for_one"
    REST_FOR_ONE = "rest_for_one"
