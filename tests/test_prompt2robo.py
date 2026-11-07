import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from stacklab.cli.prompt2robo import messages_for, prompt_for, select, source_files


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
