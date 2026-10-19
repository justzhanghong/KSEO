import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from kseo.executor import StepFailure, execute


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.variables = {"source_dir": str(self.root)}

    def test_argv_is_not_interpreted_as_shell(self):
        literal = "$(touch SHOULD_NOT_EXIST); literal"
        execute({"command": [sys.executable, "-c", "import sys; print(sys.argv[1])", literal]},
                self.root / "step", self.variables, {}, remaining=5)
        self.assertFalse((self.root / "SHOULD_NOT_EXIST").exists())
        self.assertIn(literal, (self.root / "step/stdout.log").read_text())

    def test_nonzero_exit_is_typed_failure(self):
        with self.assertRaises(StepFailure):
            execute({"command": [sys.executable, "-c", "raise SystemExit(3)"]}, self.root / "step", self.variables, {}, remaining=5)

    def test_timeout_terminates_child_even_when_parent_exits(self):
        marker = self.root / "child.pid"
        child = self.root / "child.py"
        child.write_text("import os,signal,time\nfrom pathlib import Path\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                         f"Path({str(marker)!r}).write_text(str(os.getpid()))\ntime.sleep(60)\n")
        parent = f"import subprocess,sys,time; subprocess.Popen([sys.executable,{str(child)!r}]); time.sleep(60)"
        with self.assertRaises(StepFailure) as raised:
            execute({"command": [sys.executable, "-c", parent], "timeout_seconds": 0.5},
                    self.root / "step", self.variables, {}, remaining=5)
        self.assertTrue(raised.exception.timeout)
        pid = int(marker.read_text())
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            stat = Path(f"/proc/{pid}/stat")
            if not stat.exists() or stat.read_text().rsplit(")", 1)[1].split()[0] == "Z":
                break
            time.sleep(0.02)
        else:
            os.kill(pid, 9)
            self.fail("超时后子进程仍在运行")
