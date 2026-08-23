"""Worker entry point: CLI for the call-agent service (mirrors call_agent.main)."""

import argparse
import os

from worker.mossvoice_agent import run, default_outdir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9400)
    ap.add_argument("--host", default=os.environ.get("MOSS_BIND_HOST", "127.0.0.1"),
                    help="bind address; loopback by default, other values are "
                         "for isolated networks (Docker)")
    ap.add_argument("--tts-port", type=int, default=None, help="fixed TTS daemon port (else reads --tts-port-file)")
    ap.add_argument("--tts-port-file", default=None, help="path to TTS port file")
    ap.add_argument("--tts-host", default=None,
                    help="TTS daemon host (Docker: the 'voice' service name); "
                         "default resolves env MOSS_TTS_HOST then 127.0.0.1")
    ap.add_argument("--outdir", default=default_outdir())
    ap.add_argument("--tmpdir", default="/tmp/mossvoice_turns",
                    help="staging dir for JSON-referenced audio uploads")
    ap.add_argument("--ref", action="append", default=[], help="reference WAV path(s)")
    ap.add_argument("--reference-text", default="")
    ap.add_argument("--inference-steps", type=int, default=12, help="TTS diffusion steps (lower=faster, default 12)")
    ap.add_argument("--no-style", action="store_true", help="disable style transfer for faster TTS")
    args = ap.parse_args()
    args.refs = args.ref
    run(args)


if __name__ == "__main__":
    main()