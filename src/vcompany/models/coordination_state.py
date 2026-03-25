"""Pydantic v2 models for coordination state: interface change records and logs.

InterfaceChangeRecord and InterfaceChangeLog define the schema for
interface_changes.json -- the append-only audit trail for interface contract
changes proposed, reviewed, and applied across agents.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class InterfaceChangeRecord(BaseModel):
    """Single interface change event record."""

    timestamp: datetime
    agent_id: str
    action: Literal["proposed", "approved", "rejected", "applied"]
    description: str
    diff: str
    reviewer_note: str = ""


class InterfaceChangeLog(BaseModel):
    """Persistent interface change history (serialized to interface_changes.json)."""

    project: str = ""
    records: list[InterfaceChangeRecord] = []
