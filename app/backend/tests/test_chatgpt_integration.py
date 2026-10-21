"""Run API/queue tests in isolation from the legacy service namespace fixtures."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class SubscriptionIntegrationTests(unittest.TestCase):
    def test_connection_approval_and_queue_scenarios(self):
        backend = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = {**os.environ, "PYTHONPATH": str(backend), "KNITTING_DATA_DIR": str(root / "data"),
                   "KNITTING_LOG_DIR": str(root / "logs")}
            result = subprocess.run([sys.executable, str(backend / "tests" / "subscription_scenarios.py")],
                                    env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
