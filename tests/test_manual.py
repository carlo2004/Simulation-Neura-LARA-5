import contextlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import mujoco
import numpy as np
from stacklab.cli.console import Controller, CommandError
from stacklab.sim.manual import SPACE, ESCAPE, INSERT, DELETE
from stacklab.sim.robot import Simulation


class ManualTests(unittest.TestCase):
    def setUp(self):
        self.robot = Simulation()
        self.controller = Controller(self.robot, output=lambda _: None)

    def tearDown(self):
        self.robot.close()

    def advance(self, seconds=1.):
        for _ in range(round(seconds/.02)):
            self.controller.idle(.02)

    def test_opt_in_and_callback_only_queues(self):
        s = self.robot
        q, ctrl = s.data.qpos.copy(), s.data.ctrl.copy()
        s.manual.on_key(265)
        self.assertTrue(s.manual.pending.empty())
        self.assertFalse(s.manual.enabled)
        with self.assertRaises(CommandError):
            self.controller.execute('manual on')  # A real terminal user needs a viewer.
        s.manual.enable(s)
        s.manual.on_key(265)
        np.testing.assert_array_equal(s.data.qpos, q)
        np.testing.assert_array_equal(s.data.ctrl, ctrl)
        self.assertFalse(s.manual.pending.empty())

    def test_keys_move_real_tcp_without_a_long_backlog(self):
        s = self.robot
        s.manual.enable(s)
        before = s.data.site_xpos[s.sid].copy()
        # A burst of repeats before processing must create at most one step.
        for _ in range(100):
            s.manual.on_key(265)
        self.advance()
        np.testing.assert_allclose(s.data.site_xpos[s.sid], before+[.005, 0, 0], atol=.0005)
        s.manual.on_key(263)
        self.advance()
        s.manual.on_key(268)
        self.advance()
        np.testing.assert_allclose(s.data.site_xpos[s.sid], before+[.005, .005, .005], atol=.0005)
        s.manual.on_key(269)
        self.advance()
        np.testing.assert_allclose(s.data.site_xpos[s.sid], before+[.005, .005, 0], atol=.0005)
        self.assertLessEqual(np.linalg.norm(s.manual.target-s.data.site_xpos[s.sid]), .001)

    def test_stop_escape_and_gripper(self):
        s = self.robot
        s.manual.enable(s)
        s.manual.on_key(DELETE)
        self.advance()
        self.assertTrue(np.all(s.data.qpos[6:8] < .002))
        s.manual.on_key(INSERT)
        self.advance()
        self.assertTrue(np.all(s.data.qpos[6:8] > .03))
        s.manual.on_key(265)
        s.manual.on_key(SPACE)
        before = s.data.qpos.copy()
        s.manual.tick(s)
        np.testing.assert_array_equal(s.data.qpos, before)
        self.assertTrue(s.manual.enabled)
        self.assertTrue(s.manual.pending.empty())
        s.manual.on_key(265)
        s.manual.on_key(ESCAPE)
        s.manual.tick(s)
        self.assertFalse(s.manual.enabled)
        self.assertTrue(s.manual.pending.empty())
        s.manual.on_key(265)
        self.assertTrue(s.manual.pending.empty())

    def test_workspace_rejection_and_terminal_takes_priority(self):
        s = self.robot
        s.move_to([.599, -.12, .26])
        s.manual.enable(s)
        ctrl = s.data.ctrl.copy()
        s.manual.on_key(265)
        s.manual.tick(s)
        self.assertIn('workspace', s.manual.message)
        np.testing.assert_array_equal(ctrl, s.data.ctrl)
        s.manual.on_key(264)
        original = s.step
        def step_with_key(seconds):
            s.manual.on_key(264)  # Key arrives while a terminal command runs.
            original(seconds)
        with patch.object(s, 'step', side_effect=step_with_key):
            self.controller.execute('wait .2')
        self.assertTrue(s.manual.pending.empty())
        before = s.data.site_xpos[s.sid].copy()
        self.advance()
        np.testing.assert_allclose(before, s.data.site_xpos[s.sid], atol=.0005)
        self.controller.execute('reset')
        self.assertFalse(s.manual.enabled)

    def test_selection_transforms_world_and_object_points(self):
        s = self.robot
        pert = mujoco.MjvPerturb()
        fake = SimpleNamespace(lock=contextlib.nullcontext, perturb=pert)
        try:
            s.viewer = fake
            self.assertIsNone(s.selected_point())  # Default world origin isn't a work point.
            pert.select = 0
            pert.localpos[:] = [.42, .10, 0]
            np.testing.assert_allclose(s.selected_point(), [.42, .10, 0])
            pert.select = s.model.body('obj_red').id
            pert.localpos[:] = [.005, .002, .02]
            np.testing.assert_allclose(s.selected_point(), s.position('red')+[.005, .002, .02], atol=1e-5)
            pert.select = s.model.body('link1').id
            self.assertIsNone(s.selected_point())
        finally:
            s.viewer = None

    def test_hover_selection_drives_real_arm_and_rejects_low_height(self):
        s = self.robot
        before = s.data.qpos.copy()
        with self.assertRaises(ValueError):
            s.goto_selected()
        np.testing.assert_array_equal(before, s.data.qpos)
        with patch.object(s, 'selected_point', return_value=np.array([.47, .03, .02])):
            with self.assertRaises(ValueError):
                s.goto_selected(.03)
            np.testing.assert_array_equal(before, s.data.qpos)
            self.controller.execute('goto-selected')
        np.testing.assert_allclose(s.data.site_xpos[s.sid], [.47, .03, .24], atol=.001)


if __name__ == '__main__':
    unittest.main()
