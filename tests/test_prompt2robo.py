import hashlib
import json
from contextlib import closing
from pathlib import Path
import tempfile
import unittest

from stacklab.cli.prompt2robo import CHECKER, REPLAY_MODE, lara_passes, messages_for, prompt_for, select, source_files


class Prompt2RoboTests(unittest.TestCase):
    def setUp(self):
        self.sample = {
            'id': 'fixture', 'split': 'eval', 'expected_behavior': 'execute',
            'scene': {'objects': {'10': {'color': 'blue', 'position': [.4, -.1, .02]},
                                  '2': {'color': 'red', 'position': [.4, .1, .02]}},
                      'gripper': {'position': [.4, 0, .3], 'angle_deg': 0, 'is_open': True}},
            'user_prompt': 'Objects: 10 (blue), 2 (red)\nPut red on blue.',
            'assistant_answer': 'def run(robot):\n    robot.open_gripper()',
            'destination': {'private_checker_data': True},
        }

    def test_inference_and_training_share_scene_without_leaking_checker_data(self):
        messages = messages_for(self.sample, 'System')
        self.assertEqual(messages[:-1], prompt_for(self.sample, 'System'))
        self.assertEqual([m['role'] for m in messages[:-1]], ['system', 'user'])
        user = json.loads(messages[1]['content'])
        self.assertEqual(set(user), {'user_prompt', 'scene'})
        self.assertEqual(list(user['scene']['objects']), ['2', '10'])
        self.assertEqual(user['scene'], self.sample['scene'])
        self.assertEqual(json.loads(messages[-1]['content']),
                         {'code': self.sample['assistant_answer'], 'message': ''})

    def test_refusal_keeps_text_out_of_code(self):
        sample = dict(self.sample, expected_behavior='refuse', assistant_answer='Please specify the cube.')
        self.assertEqual(json.loads(messages_for(sample, 'System')[-1]['content']),
                         {'code': '', 'message': 'Please specify the cube.'})

    def test_selection_cannot_silently_cross_split(self):
        with self.assertRaisesRegex(ValueError, 'split train'):
            select([self.sample], 'train', ['fixture'], 1)

    def test_local_snapshot_requires_exact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.jsonl'
            path.write_bytes(b'expected')
            lock = {'files': {path.name: hashlib.sha256(b'expected').hexdigest()}}
            self.assertEqual(source_files(lock, [path.name], Path(directory)), path.parent)
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                source_files(lock, [path.name], Path(directory))

    def test_export_requires_a_lara_report_to_claim_lara_validation(self):
        lock = {'repository': 'fixture', 'revision': 'abc', 'files': {CHECKER: 'hash'}}
        manifest = {'dataset': 'fixture', 'revision': 'abc', 'mode': REPLAY_MODE,
                    'checker_sha256': 'hash', 'split': 'eval',
                    'results': [{'id': 'a', 'passed': True}, {'id': 'b', 'passed': False}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'manifest.json'
            path.write_text(json.dumps(manifest), encoding='utf-8')
            self.assertEqual(lara_passes([path], lock), {('eval', 'a')})
            path.write_text(json.dumps(dict(manifest, mode='dataset_reference_replay')), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'LARA 5 replay report'):
                lara_passes([path], lock)

    def test_replay_preserves_an_existing_tower_and_starting_yaw(self):
        import numpy as np
        from stacklab.prompt2robo import LaraReplay, ReplayScene
        from stacklab.sim.robot import Simulation

        scene = self.sample['scene']
        scene['objects']['10']['position'] = [.4, .1, .06]
        scene['gripper'].update(angle_deg=90, is_open=False)
        with closing(Simulation(ReplayScene(scene), visuals=False)) as sim:
            replay = LaraReplay(sim, scene)
            np.testing.assert_allclose(replay.get_object_position(10), [.4, .1, .06], atol=.001)
            self.assertTrue(sim.is_stacked('cube_10', 'cube_2'))
            self.assertAlmostEqual(replay.state()['gripper']['angle_deg'], 90, places=1)
            self.assertFalse(replay.state()['gripper']['is_open'])
            with self.assertRaisesRegex(ValueError, 'outside supported workspace'):
                replay.move_to(.7, 0, .3)

    def test_reference_program_stacks_using_lara_contacts(self):
        from stacklab.prompt2robo import LaraReplay, ReplayScene, run_reference
        from stacklab.sim.robot import Simulation

        code = """def run(robot):
    source, target = (robot.get_object_position(oid) for oid in (2, 10))
    robot.move_to(source[0], source[1], .20)
    robot.move_to(*source)
    robot.close_gripper()
    robot.move_to(source[0], source[1], .20)
    robot.move_to(target[0], target[1], .20)
    robot.move_to(target[0], target[1], target[2] + .041)
    robot.open_gripper()
    robot.move_to(target[0], target[1], .20)
"""
        scene = self.sample['scene']
        with closing(Simulation(ReplayScene(scene), visuals=False)) as sim:
            replay = LaraReplay(sim, scene)
            run_reference(code, replay)
            self.assertTrue(all(sim.check_stack('cube_2', 'cube_10')))
            self.assertEqual(replay.held_objects(), set())
