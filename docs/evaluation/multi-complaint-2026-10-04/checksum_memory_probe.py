"""Python allocation of actual checkpoint checksum; not model/worker RSS."""
import argparse
import hashlib
import json
import time
import tracemalloc
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkpoint', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from services.stt.gigaam_engine import _verify_checksum

    records = {}
    for name, action in (
        ('baseline_whole_file', lambda: hashlib.md5(args.checkpoint.read_bytes()).hexdigest()),
        ('current_bounded_stream', lambda: _verify_checksum(args.checkpoint, 'v3_e2e_rnnt')),
    ):
        tracemalloc.start()
        started = time.perf_counter()
        result = action()
        if result is not None:
            assert result == '2730de7545ac43ad256485a462b0a27a'
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        records[name] = {'python_peak_allocated_bytes': peak, 'elapsed_s': elapsed}
    with args.checkpoint.open('rb') as checkpoint:
        sha256 = hashlib.file_digest(checkpoint, 'sha256').hexdigest()
    report = {'boundary': 'actual official checkpoint; Python traced allocations only',
              'artifact_bytes': args.checkpoint.stat().st_size,
              'sha256': sha256,
              'measurements': records}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
