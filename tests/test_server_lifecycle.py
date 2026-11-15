"""Server cleanup must reach an owned orphan without stopping an unrelated process."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ServerLifecycleTest(unittest.TestCase):
    def test_stop_finds_owned_server_in_another_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = str(root / "server.json")
            processes = []
            try:
                for cfg in [config, str(root / "other.json")]:
                    processes.append(subprocess.Popen([
                        sys.executable, "-c", "import time; time.sleep(120)", "-m", "lightx2v.server",
                        "--config_json", cfg, "--port", "54321"], start_new_session=True))
                pidfile = root / "server.pid"
                pidfile.write_text("999999991\n")  # original launcher has gone away
                pidfile.with_suffix(".meta.json").write_text(json.dumps({
                    "pid": 999999991, "uid": os.getuid(), "start_ticks": 0,
                    "config": config, "port": "54321"}))
                stop = Path(__file__).resolve().parents[1] / "bin/stop_server.sh"
                result = subprocess.run(["bash", str(stop), "--pidfile", str(pidfile)],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIsNotNone(processes[0].poll())
                self.assertIsNone(processes[1].poll())
                self.assertFalse(pidfile.exists())
            finally:
                for proc in processes:
                    if proc.poll() is None:
                        proc.terminate()
                    proc.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
