"""Behavioural checks: overlays cannot move bodies or manufacture success."""
import contextlib
import io
import unittest
import mujoco
import numpy as np
from stacklab.cli.console import Controller, CommandError
from stacklab.sim.robot import Simulation


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.robot = Simulation()
        self.controller = Controller(self.robot, output=lambda _: None)

    def tearDown(self):
        self.controller.robot.close()

    def test_hidden_by_default_and_toggling_does_not_change_physics(self):
        s = self.robot
        scene = mujoco.MjvScene(s.model, maxgeom=200)
        self.assertEqual(s.overlays.panels(s), [])
        s.overlays.draw(scene, s, clear=True)
        self.assertEqual(scene.ngeom, 0)
        q, v, ctrl, t = s.data.qpos.copy(), s.data.qvel.copy(), s.data.ctrl.copy(), s.data.time
        self.controller.execute('axes on')
        self.controller.execute('stackviz red blue')
        s.overlays.draw(scene, s, clear=True)
        self.assertGreater(scene.ngeom, 30)
        self.assertEqual(s.overlays.status(), 'UNCHECKED')
        self.assertIn('NOT CHECKED', s.overlays.panels(s)[1][1])
        self.controller.execute('axes off')
        self.controller.execute('stackviz off')
        s.overlays.draw(scene, s, clear=True)
        self.assertEqual(scene.ngeom, 0)
        self.assertEqual(s.overlays.viewer_texts(s), [])
        for a, b in ((q, s.data.qpos), (v, s.data.qvel), (ctrl, s.data.ctrl)):
            np.testing.assert_array_equal(a, b)
        self.assertEqual(s.data.time, t)
        self.assertEqual(s.model.neq, 0)

    def test_failed_check_is_shown_and_bad_commands_leave_selection(self):
        self.controller.execute('stackviz red blue')
        for command in ('axes yes', 'stackviz red red', 'stackviz green blue', 'stackviz red'):
            with self.assertRaises(ValueError):
                self.controller.execute(command)
        self.assertEqual(self.robot.overlays.stack_pair, ('red', 'blue'))
        start = self.robot.data.time
        with self.assertRaises(CommandError):
            self.controller.execute('check red blue')
        self.assertAlmostEqual(self.robot.data.time-start, 2., places=6)
        self.assertEqual(self.robot.overlays.status(), 'FAIL')
        self.assertEqual(self.robot.overlays.samples, [False]*20)
        self.controller.execute('reset')
        self.assertEqual(self.robot.overlays.status(), 'UNCHECKED')

    def test_visual_state_survives_scene_rebuild_but_check_does_not(self):
        self.controller.execute('axes on')
        self.controller.execute('stackviz red blue')
        self.robot.check_stack('red', 'blue')
        self.controller.execute('add green cube .5 0 .04')
        s = self.controller.robot
        self.assertTrue(s.overlays.axes)
        self.assertEqual(s.overlays.stack_pair, ('red', 'blue'))
        self.assertEqual(s.overlays.status(), 'UNCHECKED')
        self.controller.execute('remove red')
        self.assertIsNone(self.controller.robot.overlays.stack_pair)
        self.assertTrue(self.controller.robot.overlays.axes)

    def test_air_gap_is_explained_even_when_centres_match(self):
        s = self.robot
        addr = s.model.jnt_qposadr[s.model.joint('red_free').id]
        # Test fixture only; actual manipulation never writes object positions.
        s.data.qpos[addr:addr+3] = s.position('blue')+[0, 0, .041]
        s.data.qpos[addr+3:addr+7] = [1, 0, 0, 0]
        s.data.qvel[:] = 0
        mujoco.mj_forward(s.model, s.data)
        d = s.stack_diagnostics('red', 'blue')
        self.assertTrue(d['centered'])
        self.assertTrue(d['height_ok'])
        self.assertFalse(d['touching'])
        self.assertFalse(d['valid'])
        self.controller.execute('stackviz red blue')
        self.assertEqual(s.overlays.status(), 'UNCHECKED')
        self.assertIn('Contact: NO', s.overlays.panels(s)[0][1])

    def test_real_stack_pass_then_disturbance_invalidates_result(self):
        s = self.robot
        self.controller.execute('axes on')
        self.controller.execute('stackviz red blue')
        with contextlib.redirect_stdout(io.StringIO()):
            result = s.stack('red', 'blue')
        self.assertTrue(result['success'])
        self.assertEqual(s.overlays.status(), 'PASS')
        self.assertIn('PASS 20/20', s.overlays.panels(s)[1][1])
        self.assertTrue(s.stack_diagnostics('red', 'blue')['valid'])
        # A velocity disturbance must remove green before another check runs.
        addr = s.model.jnt_dofadr[s.model.joint('red_free').id]
        s.data.qvel[addr] = .05
        s.refresh_view()
        self.assertEqual(s.overlays.status(), 'INVALIDATED')
        s.data.qvel[addr] = 0
        s.step(.3)
        self.assertEqual(s.overlays.status(), 'INVALIDATED')
        self.assertTrue(all(s.check_stack('red', 'blue')))
        self.assertEqual(s.overlays.status(), 'PASS')
        self.controller.execute('reset')
        self.assertEqual(s.overlays.status(), 'UNCHECKED')


if __name__ == '__main__':
    unittest.main()
