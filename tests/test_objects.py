import contextlib, io, tempfile, unittest
from dataclasses import replace
from pathlib import Path
import mujoco
import numpy as np
from stacklab.config import Config, ObjectSpec
from stacklab.cli.console import Controller
from stacklab.sim.robot import ROOT, Simulation

class ObjectDescriptionTests(unittest.TestCase):
    def test_dimensions_and_colors(self):
        for shape, size, expected in [('cube', .04, (.04,.04,.04)), ('box',[.06,.04,.05],(.06,.04,.05)),
                                      ('sphere',.04,(.04,.04,.04)),('cylinder',[.04,.06],(.04,.04,.06))]:
            spec=ObjectSpec('green',shape=shape,size_m=size).validate()
            self.assertEqual(spec.dimensions(),expected)
            self.assertGreater(spec.rgba()[1],spec.rgba()[0])

    def test_reject_bad_objects(self):
        base=Config.load(ROOT/'scenes/three_cubes.json')
        for item in [dict(name='green'),dict(name='bad name'),dict(name='tcp'),dict(name='a',shape='mesh'),
                     dict(name='a',size_m=-.04),dict(name='a',shape='box',size_m=[.04,.04]),
                     dict(name='a',color=[1,2,0,1]),dict(name='a',mass_kg=float('nan'))]:
            with self.subTest(item=item), self.assertRaises(ValueError):
                replace(base,objects=base.objects+[item]).validate()
        with self.assertRaises(ValueError):
            replace(base,objects=[dict(name='a'),dict(name='b')]).validate()

    def test_custom_randomization_repeatable(self):
        c=replace(Config.load(ROOT/'scenes/three_cubes.json'),random_jitter_m=.02,seed=11)
        self.assertEqual(c.scene(),c.scene())
        self.assertNotEqual(c.scene(),replace(c,seed=12).scene())
        for name,p in c.scene().items():self.assertAlmostEqual(p[2],.02)

class ObjectPhysicsTests(unittest.TestCase):
    def test_primitives_are_free_and_settle(self):
        sim=Simulation(Config.load(ROOT/'scenes/mixed_objects.json'))
        try:
            sim.step(1)
            for name,spec in sim.objects.items():
                self.assertEqual(sim.model.joint(name+'_free').type[0],mujoco.mjtJoint.mjJNT_FREE)
                self.assertAlmostEqual(sim.position(name)[2],spec.dimensions()[2]/2,delta=.002)
                self.assertTrue(sim._touching(name+'_geom','table'))
            before=sim.data.qpos.copy()
            with self.assertRaises(ValueError):sim.stack('ball','blue')
            np.testing.assert_array_equal(before,sim.data.qpos)
        finally:sim.close()

    def test_terminal_scene_edits_and_roundtrip(self):
        controller=Controller(Simulation(),output=lambda _:None)
        try:
            controller.execute('place red .38 -.14')
            np.testing.assert_allclose(controller.robot.position('red')[:2],[.38,-.14],atol=.001)
            controller.execute('add green cube .50 0 .04')
            self.assertEqual(set(controller.robot.object_names),{'red','blue','green'})
            self.assertEqual(controller.robot.model.nq,29)
            np.testing.assert_allclose(controller.robot.position('green'),[.5,0,.02],atol=.001)
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'scene.json'
                controller.execute(f'save-scene "{path}"')
                controller.execute('randomize 8 .01')
                randomized=controller.robot.position('green').copy()
                self.assertGreater(np.linalg.norm(randomized[:2]-[.5,0]),1e-5)
                controller.execute('remove green')
                self.assertNotIn('green',controller.robot.object_names)
                controller.execute(f'load-scene "{path}"')
                self.assertIn('green',controller.robot.object_names)
                np.testing.assert_allclose(controller.robot.position('green')[:2],[.5,0],atol=.001)
            old=controller.robot
            with self.assertRaises(ValueError):controller.execute('add blue sphere .5 .2 .04')
            self.assertIs(controller.robot,old) # Invalid edit leaves the previous scene intact.
        finally:controller.robot.close()

if __name__=='__main__':unittest.main()
