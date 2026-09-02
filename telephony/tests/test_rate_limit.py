"""Unit tests for the bounded single-node ingress limiter."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.rate_limit import TokenBucketLimiter  # noqa: E402


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class TokenBucketLimiterTests(unittest.TestCase):
    def test_capacity_reject_and_refill(self):
        clock = _Clock()
        limiter = TokenBucketLimiter(clock=clock)
        self.assertEqual(limiter.allow("family:a", 2, 10), (True, 0))
        self.assertEqual(limiter.allow("family:a", 2, 10), (True, 0))
        allowed, retry = limiter.allow("family:a", 2, 10)
        self.assertFalse(allowed)
        self.assertEqual(retry, 5)

        clock.now = 5
        self.assertEqual(limiter.allow("family:a", 2, 10), (True, 0))

    def test_high_cardinality_is_memory_bounded(self):
        limiter = TokenBucketLimiter(max_entries=3)
        for index in range(20):
            limiter.allow("peer:%d" % index, 1, 60)
        self.assertEqual(len(limiter._buckets), 3)
        self.assertNotIn("peer:0", limiter._buckets)

    def test_invalid_configuration_fails_closed(self):
        limiter = TokenBucketLimiter()
        with self.assertRaises(ValueError):
            limiter.allow("x", 0, 60)
        with self.assertRaises(ValueError):
            limiter.allow("x", 1, 0)


if __name__ == "__main__":
    unittest.main()
