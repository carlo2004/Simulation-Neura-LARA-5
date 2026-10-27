import json, unittest
import numpy as np
import mujoco
from simulation import ROOT, scene_xml
from core import Config

class LaraModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.params = json.loads((ROOT/'models/lara5/parameters.json').read_text())
        cls.m = mujoco.MjModel.from_xml_string(scene_xml(Config()))
        cls.d = mujoco.MjData(cls.m)

    def test_joint_limits_match_source(self):
        np.testing.assert_allclose(np.degrees(self.m.jnt_range[:6]), self.params['limits_deg'], atol=1e-10)
        self.assertEqual(self.m.nq, 22)

    def test_forward_kinematics_100_poses(self):
        # A separate closed-form DHM matrix product checks the MuJoCo body tree.
        rng = np.random.default_rng(105)
        limits = np.radians(self.params['limits_deg'])
        for q in rng.uniform(limits[:, 0], limits[:, 1], size=(100, 6)):
            T = np.eye(4)
            for angle, row in zip(q, self.params['modified_dh']):
                alpha, a, offset, d = row
                a /= 1000
                d /= 1000
                c, s = np.cos(offset+angle), np.sin(offset+angle)
                ca, sa = np.cos(alpha), np.sin(alpha)
                T = T@np.array([[c, -s, 0, a], [s*ca, c*ca, -sa, -d*sa], [s*sa, c*sa, ca, d*ca], [0, 0, 0, 1]])
            self.d.qpos[:6] = q
            mujoco.mj_forward(self.m, self.d)
            actual = self.d.site('attachment_site')
            np.testing.assert_allclose(actual.xpos, T[:3, 3], atol=1e-10)
            np.testing.assert_allclose(actual.xmat.reshape(3, 3), T[:3, :3], atol=1e-10)

    def test_model_identity(self):
        self.assertEqual(self.params['model'], 'NEURA LARA 5')
        self.assertEqual(len(self.params['modified_dh']), 6)
        self.assertEqual(self.m.neq, 0)
        for i in range(1, 7): self.assertGreater(self.m.body(f'link{i}').mass[0], 0)

if __name__ == '__main__': unittest.main()
