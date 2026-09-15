"""Contextual annotation schema (reviewer item 4) — for future meaning extraction.

One row = ONE user turn with its pending question and short context.
Facts carry spans (character offsets into text), subject, polarity, time,
and links (correction_of / elaborates). answer/skip/garbage labels CANNOT
train subject/negation/time — this schema replaces them for that job.

Fields:
  id, text, pending_question, context_before (<=2 prior Vera questions),
  facts[]: {span:[start,end], quote, kind, subject, polarity, time,
            link:{type, target} | null}
  expected_routes: understanding decision the planner may rely on
  family: source family id (GroupKFold; variants inherit it)

Validate: python3 tools/voice_lab/validate_annotations.py
"""

from __future__ import annotations

SCHEMA_VERSION = 1

KINDS = ("symptom", "medication", "sleep", "mood", "nutrition", "request",
         "refusal", "repair", "question", "meta")
SUBJECTS = ("speaker", "other_person", "unknown")
POLARITIES = ("positive", "negative", "uncertain", "na")
TIMES = ("now", "today", "past", "unknown")
LINKS = ("correction_of", "elaborates", None)
