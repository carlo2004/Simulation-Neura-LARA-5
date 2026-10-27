import unittest
import numpy as np
import mujoco
from core import Config
from simulation import Simulation

class ConfigurationTests(unittest.TestCase):
    def test_repeatable_scene(self):
        c = Config(seed=7, random_jitter_m=.02)
        self.assertEqual(c.scene(), c.scene())
        self.assertNotEqual(c.scene(), Config(seed=8, random_jitter_m=.02).scene())

    def test_invalid_inputs(self):
        for kwargs in [dict(seed=True), dict(cube_size_m=.01), dict(red_xy_m=[.4]),
                       dict(red_xy_m=[float('nan'), 0]), dict(blue_xy_m=[.4, -.12]),
                       dict(fps=30.5), dict(speed_mm_s=-1), dict(hover_z_m=.05)]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): Config(**kwargs).validate()

class PhysicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.sim = Simulation()
    @classmethod
    def tearDownClass(cls): cls.sim.close()

    def test_initial_scene_not_stacked(self):
        self.assertFalse(self.sim.is_stacked('red', 'blue'))
        self.assertFalse(self.sim.is_stacked('blue', 'red'))

    def test_no_attachment_constraints(self):
        self.assertEqual(self.sim.model.neq, 0)
        for name in ('red', 'blue'):
            self.assertEqual(self.sim.model.joint(name+'_free').type[0], mujoco.mjtJoint.mjJNT_FREE)

    def test_reject_bad_moves(self):
        for xyz in ([9, 0, 0], [float('nan'), 0, .2], [.4, .1], [.4, .1, -.2]):
            with self.assertRaises(ValueError): self.sim.move_to(xyz)
        with self.assertRaises(ValueError): self.sim.move_to([.4, 0, .2], duration=-1)

    def test_no_contact_is_not_success(self):
        # Test fixture only: a 1 mm air gap must defeat a pose-only success metric.
        s = self.sim
        q, v = s.data.qpos.copy(), s.data.qvel.copy()
        try:
            addr = s.model.jnt_qposadr[s.model.joint('red_free').id]
            s.data.qpos[addr:addr+3] = s.position('blue')+[0, 0, s.config.cube_size_m+.001]
            s.data.qpos[addr+3:addr+7] = [1, 0, 0, 0]
            s.data.qvel[:] = 0
            mujoco.mj_forward(s.model, s.data)
            self.assertFalse(s.is_stacked('red', 'blue'))
        finally:
            s.data.qpos[:] = q
            s.data.qvel[:] = v
            mujoco.mj_forward(s.model, s.data)

if __name__ == '__main__': unittest.main()
