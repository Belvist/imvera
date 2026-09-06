"""Committed dialogue facts with provenance."""

from pydantic import BaseModel


class FactRecord(BaseModel):
    field: str
    value: str
    source_quote: str
    turn_id: int
    source_utterance_id: str = ""
    subject: str = "elder"
    temporal_scope: str = "now"
    negated: bool = False
    revision: int = 1
    active: bool = True
