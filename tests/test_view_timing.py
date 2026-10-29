"""Frame budgets and GUI throttling, with a fake viewer and real MuJoCo steps."""
from contextlib import nullcontext
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import mujoco
import numpy as np

from stacklab.config import Config
from stacklab.sim.robot import Simulation


class Clock:
    def __init__(self):
        self.now = 0.

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class ViewTimingTests(unittest.TestCase):
    def setUp(self):
        # The timing tests need no robot meshes or actual desktop/GPU.
        self.robot = Simulation.__new__(Simulation)
        s = self.robot
        s.config = Config()
        s.model = mujoco.MjModel.from_xml_string('''<mujoco>
            <option timestep="0.002"/>
            <worldbody><body pos="0 0 1"><freejoint/>
            <geom type="sphere" size="0.02"/></body></worldbody>
            </mujoco>''')
        s.data = mujoco.MjData(s.model)
        s.data.qvel[0] = .1
        mujoco.mj_forward(s.model, s.data)
        s.frames = 0
        s._push_watch = None
        s._last_view_refresh = s._last_overlay_refresh = None
        s._overlay_view_state = None
        s.manual = SimpleNamespace(enabled=False, selected=None)
        s.overlays = Mock(axes=False, stack_pair=None)
        s.overlays.viewer_texts.return_value = []
        s.viewer = Mock()
        s.viewer.is_running.return_value = True
        s.viewer.lock = nullcontext
        s.renderer = s.writer = None
        self.clock = Clock()

    def test_paused_physics_limits_sync_and_overlay_rebuilds_in_real_time(self):
        s = self.robot
        before = s.data.qpos.copy()
        with patch('stacklab.sim.robot.time.monotonic', self.clock):
            for i in range(500):
                self.clock.now = i*.002
                s.refresh_view()
        self.assertGreaterEqual(s.viewer.sync.call_count, 25)
        self.assertLessEqual(s.viewer.sync.call_count, 30)
        self.assertGreaterEqual(s.overlays.draw.call_count, 8)
        self.assertLessEqual(s.overlays.draw.call_count, 10)
        np.testing.assert_array_equal(before, s.data.qpos)
        self.assertEqual(s.data.time, 0.)

    def test_toggle_and_final_check_refresh_immediately_and_closed_viewer_stops(self):
        s = self.robot
        with patch('stacklab.sim.robot.time.monotonic', self.clock):
            s.refresh_view()
            s.overlays.axes = True
            s.refresh_view()
            s.overlays.axes = False
            s.refresh_view()
            s.refresh_view(force=True)
            self.assertEqual(s.overlays.draw.call_count, 4)
            s.viewer.is_running.return_value = False
            with self.assertRaises(KeyboardInterrupt):
                s.refresh_view()

    def test_gui_throttling_does_not_drop_video_frames_or_change_physics(self):
        s = self.robot
        reference = mujoco.MjData(s.model)
        reference.qpos[:] = s.data.qpos
        reference.qvel[:] = s.data.qvel
        mujoco.mj_forward(s.model, reference)
        for _ in range(100):
            reference.qfrc_applied[:8] = reference.qfrc_bias[:8]
            mujoco.mj_step(s.model, reference)
        for gui in (False, True):
            with self.subTest(gui=gui):
                mujoco.mj_resetData(s.model, s.data)
                s.data.qvel[0] = .1
                mujoco.mj_forward(s.model, s.data)
                s.frames = 0
                s.viewer = Mock() if gui else None
                if gui:
                    s.viewer.is_running.return_value = True
                    s.viewer.lock = nullcontext
                s.renderer, s.writer = Mock(), Mock()
                with patch.object(s, 'render_frame', return_value='frame'), \
                        patch('stacklab.sim.robot.time.monotonic', self.clock), \
                        patch('stacklab.sim.robot.time.sleep', self.clock.sleep):
                    # Many short calls must share the same frame budget.
                    for _ in range(10):
                        s.step(.02)
                self.assertEqual(s.writer.append_data.call_count, 6)
                np.testing.assert_array_equal(s.data.qpos, reference.qpos)
                np.testing.assert_array_equal(s.data.qvel, reference.qvel)
                self.assertEqual(s.data.time, reference.time)


if __name__ == '__main__':
    unittest.main()
