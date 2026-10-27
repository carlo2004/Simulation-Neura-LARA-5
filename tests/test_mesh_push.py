from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import mujoco
import numpy as np
import trimesh
import core
import mesh_import
from core import Config, ObjectSpec, write_json
from console import Controller
from simulation import Simulation


class MeshTests(unittest.TestCase):
    def test_all_input_formats_and_glb_up_axis(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(core, 'ROOT', root), patch.object(mesh_import, 'ROOT', root):
                for suffix in ('.obj', '.stl', '.ply', '.glb'):
                    source = root/('box'+suffix)
                    trimesh.creation.box(extents=[2, 1, 1.5]).export(source)
                    spec = mesh_import.prepare_mesh('toy', source, [.5, 0], .08)
                    expected = [.08, .06, .04] if suffix == '.glb' else [.08, .04, .06]
                    np.testing.assert_allclose(spec.dimensions(), expected, atol=1e-6)

    def test_import_scale_collision_and_portable_scene(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root/'test_box.stl'
            trimesh.creation.box(extents=[2, 1, 1.5]).export(source)
            # Isolate prepared test assets; the application uses its own model directory.
            with patch.object(core, 'ROOT', root), patch.object(mesh_import, 'ROOT', root):
                spec = mesh_import.prepare_mesh('toy', source, [.5, 0], .08)
                np.testing.assert_allclose(spec.dimensions(), [.08, .04, .06], atol=1e-6)
                self.assertFalse(Path(spec.mesh_file).is_absolute())
                source.unlink()  # Original download isn't needed after import.
                config = Config(objects=[spec.to_dict()])
                path = root/'scene.json'
                write_json(path, config.to_dict())
                s = Simulation(Config.load(path))
                try:
                    s.step(1)
                    self.assertEqual(s.model.joint('toy_free').type[0], mujoco.mjtJoint.mjJNT_FREE)
                    self.assertTrue(s._touching('toy_geom', 'table'))
                    self.assertAlmostEqual(s.position('toy')[2], .03, delta=.001)
                    visual = s.model.geom('toy_visual')
                    self.assertEqual(int(visual.contype[0]), 0)
                    self.assertEqual(int(visual.conaffinity[0]), 0)
                    initial = s.data.qpos.copy()
                    with self.assertRaises(ValueError):
                        s.stack('toy', 'other')
                    np.testing.assert_array_equal(initial, s.data.qpos)
                finally:
                    s.close()

    def test_invalid_meshes_and_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            planar = root/'flat.obj'
            planar.write_text('v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3\nf 1 3 4\n')
            for path in (planar, root/'missing.obj', root/'file.exe'):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    mesh_import.prepare_mesh('toy', path, [.5, 0], .08)
            for path in ('../escape.obj', '/outside.obj'):
                with self.assertRaises(ValueError):
                    ObjectSpec('toy', shape='mesh', size_m=[.04]*3, mesh_file=path).validate()


class PushTests(unittest.TestCase):
    def test_cube_moves_from_finger_contact_and_neighbour_stays(self):
        s = Simulation()
        try:
            blue = s.position('blue')
            result = s.push('red', .06, 0)
            self.assertTrue(result['finger_contact_seen'])
            self.assertGreater(result['displacement_m'][0], .04)
            self.assertLess(abs(result['displacement_m'][1]), .005)
            self.assertAlmostEqual(result['displacement_m'][2], 0, delta=.002)
            np.testing.assert_allclose(blue, s.position('blue'), atol=.001)
            self.assertEqual(s.model.neq, 0)
            self.assertFalse(np.any(s.data.qfrc_applied[8:]))
            self.assertFalse(np.any(s.data.xfrc_applied))
        finally:
            s.close()

    def test_invalid_push_does_not_move(self):
        s = Simulation()
        try:
            before, time = s.data.qpos.copy(), s.data.time
            for name, dx, dy in [('missing', .05, 0), ('red', 0, 0), ('red', .2, 0),
                                 ('red', float('nan'), 0), ('red', -.12, -.12)]:
                with self.subTest(name=name, dx=dx), self.assertRaises(ValueError):
                    s.push(name, dx, dy)
            np.testing.assert_array_equal(before, s.data.qpos)
            self.assertEqual(s.data.time, time)
        finally:
            s.close()


if __name__ == '__main__':
    unittest.main()
