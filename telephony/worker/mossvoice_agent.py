"""Worker: builds and runs the call-agent HTTP service from an argparse namespace."""

import os

from core.orchestrator import Serve
from legacy.call_agent_http import QuietHTTPServer, Handler


def build_server(args):
    """Instantiate Serve and the HTTP server for ``args``.

    Returns (serve, httpd) with ``httpd.serve`` wired to ``serve`` so the
    Handler can reach the orchestrator (matching the original call_agent.main).
    """
    srv = Serve(args)
    httpd = QuietHTTPServer((args.host, args.port), Handler)
    httpd.serve = srv
    return srv, httpd


def run(args):
    """Run the call-agent service until interrupted (original main() body)."""
    srv, httpd = build_server(args)
    print(f"[call-agent] listening on {args.host}:{args.port}", flush=True)
    print(f"[call-agent] tts_ready={srv.tts.ready()}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


def default_outdir():
    """Repo-local calls dir (matches call_agent.py's --outdir default)."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        os.pardir, "calls")