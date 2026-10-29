import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from stacklab.cli.process import run_logged


class WorkerProgressTests(unittest.TestCase):
    def test_progress_is_live_and_the_full_worker_output_is_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'worker.log'
            progress = []
            command = [sys.executable, '-u', '-c',
                       'from pathlib import Path\nimport time\nprint("diagnostic")\n'
                       'print("[Inferenz] Ausgabe: 10.0 Token/s")\n'
                       'for _ in range(100):\n'
                       '    if Path("ack").exists(): break\n'
                       '    time.sleep(.05)\n'
                       'print("acknowledged" if Path("ack").exists() else "missed")']

            def receive(line):
                progress.append(line)
                (Path(temp)/'ack').write_text('received while running')

            with path.open('w', encoding='utf-8') as log:
                result = run_logged(command, log, cwd=temp, env=os.environ.copy(), timeout=10,
                                    on_progress=receive)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(len(progress), 1)
            self.assertIn('10.0 Token/s', progress[0])
            self.assertIn('diagnostic', path.read_text())
            self.assertIn('acknowledged', path.read_text())

    def test_timeout_stops_the_worker_instead_of_waiting_for_its_output(self):
        with tempfile.TemporaryDirectory() as temp:
            with (Path(temp)/'worker.log').open('w', encoding='utf-8') as log:
                with self.assertRaises(subprocess.TimeoutExpired):
                    run_logged([sys.executable, '-c', 'import time; time.sleep(30)'], log,
                               cwd=temp, env=os.environ.copy(), timeout=.2)


if __name__ == '__main__':
    unittest.main()
