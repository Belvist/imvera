"""Committed dialogue facts with provenance."""

from pydantic import BaseModel


class FactRecord(BaseModel):
    field: str
    value: str
    source_quote: str
    turn_id: int
    subject: str = "elder"
    negated: bool = False
    revision: int = 1
    active: bool = True
