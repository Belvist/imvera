"""PgRecorder: dialogue-turn + result persistence in Postgres.

Drop-in for the file-based ``adapters.postgres_results.Recorder``: same
``new_call`` / ``add_turn`` / ``summary_path`` surface, so ``CallContext``
and ``Serve`` need no interface change. In addition to writing rows to
``call_sessions`` / ``dialogue_turns`` / ``call_results``, it keeps the
in-memory ``self.call`` mirror the HTTP ``GET /calls/{id}`` endpoint reads.

The file Recorder stays for offline/legacy mode; PgRecorder is selected by
Serve when Postgres is available.
"""

import datetime
import os

from adapters.pg import PgUnavailable


class PgRecorder:
    def __init__(self, pg, outdir=None):
        self.pg = pg
        self.base = outdir
        self.call = None
        self.dir = None

    def _guard(self):
        if not getattr(self.pg, "available", False):
            raise PgUnavailable("Postgres unavailable")

    def new_call(self, call_id=None):
        self._guard()
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        cid = (call_id or f"call-{ts}").replace("/", "_").replace("..", "")
        self.pg.new_call(cid)
        self.call = {"id": cid, "start": ts, "turns": []}
        if self.base:
            self.dir = os.path.join(self.base, cid)
            os.makedirs(self.dir, exist_ok=True)
        return self.call

    def add_turn(self, role, text, audio_path=None, source="stt",
                 confidence=None, audio_key=None):
        if self.call is None:
            self.new_call()
        cid = self.call["id"]
        turn_id = self.pg.add_turn(
            cid, role, text, source=source, confidence=confidence,
            audio_key=audio_key)
        self.call["turns"].append({
            "role": role, "text": text, "audio": audio_path,
            "source": source, "confidence": confidence,
            "audio_key": audio_key, "turn_id": turn_id,
        })

    def finalize(self, verdict, confidence=None, notes=None,
                 family_status=None, reasons=None, summary_for_family=None,
                 scenario_version=None, safety_rules_version=None,
                 technical_error=None):
        """Persist the verdict + close the session (Phase 2 / E2)."""
        self._guard()
        if self.call is None:
            return
        self.pg.finalize_call(
            self.call["id"], verdict, confidence=confidence, notes=notes,
            family_status=family_status, reasons=reasons,
            summary_for_family=summary_for_family,
            scenario_version=scenario_version,
            safety_rules_version=safety_rules_version,
            technical_error=technical_error)

    def summary_path(self):
        """Summary is derived in Postgres/UI; kept for interface parity."""
        return None