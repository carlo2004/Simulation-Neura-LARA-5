import contextlib
import io
from pathlib import Path
import tempfile
import unittest
import numpy as np
from stacklab.cli.console import Controller, CommandError, run_batch
from stacklab.sim.robot import Simulation

class ConsoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.robot = Simulation()
    @classmethod
    def tearDownClass(cls): cls.robot.close()
    def setUp(self):
        self.robot.reset()
        self.lines = []
        self.controller = Controller(self.robot, self.lines.append)

    def test_read_state(self):
        for command in ('status', 'pos red', 'pos blue', 'pos tcp', 'joints', 'help'):
            self.assertTrue(self.controller.execute(command))
        self.assertTrue(any('Arm angles:' in line for line in self.lines))
        self.assertTrue(any('tcp' in line for line in self.lines))
        self.assertTrue(self.controller.execute('# comment'))
        self.assertFalse(self.controller.execute('quit # comment'))

    def test_invalid_commands_do_not_act(self):
        initial = self.robot.data.qpos.copy()
        start_time = self.robot.data.time
        for command in ('move 1 2', 'move nan 0 0', 'move .4 inf .2', 'jog a .01',
                        'wait -1', 'wait 61', 'stack red red', 'stack red',
                        'pos green', 'open extra', 'print(1)', '__import__("os")', '"'):
            with self.subTest(command=command), self.assertRaises(CommandError):
                self.controller.execute(command)
        np.testing.assert_array_equal(initial, self.robot.data.qpos)
        self.assertEqual(start_time, self.robot.data.time)

    def test_jog_and_reset(self):
        target = self.robot.data.site_xpos[self.robot.sid].copy()
        target[2] += .01
        self.controller.execute('jog z .01')
        np.testing.assert_allclose(self.robot.data.site_xpos[self.robot.sid], target, atol=.001)
        self.controller.execute('close')
        self.controller.execute('wait .2')
        self.controller.execute('reset')
        self.assertAlmostEqual(self.robot.data.time, .5, places=5)
        np.testing.assert_allclose(self.robot.data.site_xpos[self.robot.sid], [.4, -.12, .26], atol=.001)
        self.assertTrue(np.all(self.robot.data.qpos[6:8] > .03))
        self.assertFalse(self.robot.is_stacked('red', 'blue'))

    def test_negative_check(self):
        with self.assertRaises(CommandError): self.controller.execute('check red blue')

    def test_batch_stops_on_error(self):
        start_time = self.robot.data.time
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'commands.txt'
            path.write_text('wait -1\nmove .4 -.12 .15\n')
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(run_batch(self.controller, path), 1)
        self.assertEqual(start_time, self.robot.data.time)

if __name__ == '__main__': unittest.main()
