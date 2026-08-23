"""Recording / summary writer (results persistence adapter)."""

import datetime
import json
import os


class Recorder:
    def __init__(self, dirpath):
        self.base = dirpath
        os.makedirs(dirpath, exist_ok=True)
        self.call = None

    def new_call(self, call_id=None):
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        cid = (call_id or f"call-{ts}").replace("/", "_").replace("..", "")
        # per-call subdirectory so concurrent calls never overwrite each other
        self.dir = os.path.join(self.base, cid)
        os.makedirs(self.dir, exist_ok=True)
        self.call = {"id": cid, "start": ts, "turns": []}
        return self.call

    def add_turn(self, role, text, audio_path=None, source="stt",
                 confidence=None, audio_key=None):
        if self.call is None:
            self.new_call()
        self.call["turns"].append({
            "role": role, "text": text, "audio": audio_path,
            "source": source, "confidence": confidence,
            "audio_key": audio_key,
        })
        with open(os.path.join(self.dir, "result.json"), "w") as f:
            json.dump(self.call, f, ensure_ascii=False, indent=2)

    def summary_path(self):
        if self.call is None:
            return None
        texts = [t["text"] for t in self.call["turns"] if t.get("text")]
        lines = [f"Телефонный разговор от {self.call['start']}"]
        for t in self.call["turns"]:
            if t.get("text"):
                who = "Собеседник" if t["role"] == "user" else "Ассистент"
                lines.append(f"{who}: {t['text']}")
        p = os.path.join(self.dir, "summary.txt")
        with open(p, "w") as f:
            f.write("\n".join(lines))
        return p