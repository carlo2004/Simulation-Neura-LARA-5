"""Context separation and delivery to the shared local/remote agent."""
from contextlib import closing
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from stacklab.config import Config
from stacklab.llm.agent import Agent, system_prompt
from stacklab.llm.catalog import lock
from stacklab.llm.context import PromptContext, context_source_hashes
from stacklab.paths import ROOT
from stacklab.sim.robot import Simulation


class ContextTests(unittest.TestCase):
    def context_copy(self, root, **overrides):
        root.mkdir()
        for filename in ('context.json', 'robot_api.md', 'world_info.json', 'few_shot.json'):
            shutil.copyfile(ROOT/'config/prompts'/filename, root/filename)
        settings = json.loads((root/'context.json').read_text(encoding='utf-8'))
        settings.update(overrides)
        (root/'context.json').write_text(json.dumps(settings), encoding='utf-8')
        return root/'context.json'

    def test_number_free_system_and_scene_specific_world_are_separate(self):
        context = PromptContext()
        self.assertNotRegex(system_prompt(), r'\d')
        with closing(Simulation(Config(hover_z_m=.31), visuals=False)) as robot:
            record = context.assemble(robot, 'Staple Rot auf Blau.', {'tcp_m': [.4, 0, .2]}, {'program_block_budget': 4})
        blocks = record['components']
        self.assertEqual(blocks['user_prompt'], 'Staple Rot auf Blau.')
        self.assertNotRegex(blocks['user_prompt'], r'\d')
        self.assertEqual(blocks['world_info']['suggested_transport_z_m'], .31)
        self.assertEqual(blocks['world_info']['tcp_bounds_m']['x'], [.2, .6])
        self.assertEqual(blocks['world_info']['table_surface_z_m'], 0)
        self.assertEqual(blocks['few_shot'], [])
        self.assertEqual(record['messages'][0], {'role': 'system', 'content': system_prompt()})
        wire = json.loads(record['messages'][1]['content'])
        self.assertNotIn('few_shot', wire)
        self.assertEqual(wire['user_prompt'], blocks['user_prompt'])
        self.assertNotIn('goal', wire)

    def test_context_order_examples_and_external_source_hashes_are_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'context'
            order = ['user_prompt', 'few_shot', 'world_info', 'runtime_info', 'observation']
            path = self.context_copy(root, order=order)
            example = {'input': 'A demonstration input.', 'solution': 'A demonstration answer.'}
            (root/'few_shot.json').write_text(json.dumps([example]), encoding='utf-8')
            with patch.dict('os.environ', STACKLAB_CONTEXT_CONFIG=str(path)):
                before = context_source_hashes()
                context = PromptContext()
                with closing(Simulation(Config(), visuals=False)) as robot:
                    record = context.assemble(robot, 'User text', {}, {})
                self.assertEqual(list(json.loads(record['messages'][1]['content'])), order)
                self.assertEqual(record['components']['few_shot'], [example])
                (root/'few_shot.json').write_text('[]', encoding='utf-8')
                self.assertNotEqual(before, context_source_hashes())
                self.assertEqual(context.few_shot, [example])  # Loaded once for this agent.
            for order in ([], ['world_info']*5, ['world_info', {}, None]):
                settings = json.loads(path.read_text(encoding='utf-8'))
                settings['order'] = order
                path.write_text(json.dumps(settings), encoding='utf-8')
                with self.assertRaises(ValueError):
                    PromptContext(path)

    def test_agent_sends_and_logs_the_unmodified_user_task_and_loaded_context(self):
        class RecordingModel:
            config = lock('qwen4b')
            def complete(self, messages, directory, **options):
                self.messages = messages
                Path(directory).mkdir()
                return json.dumps(dict(code='robot.jog("x", 0.05)', done=True)), {}
            def cancel(self):
                pass
        with tempfile.TemporaryDirectory() as temp, closing(Simulation(Config(), visuals=False)) as robot:
            client = RecordingModel()
            # User-specified quantities are never stripped or rewritten.
            instruction = 'Bewege den Greifer um 5 cm nach rechts.'
            result = Agent(robot, client, max_rounds=1).run_task(instruction, Path(temp)/'task')
            record = json.loads((Path(temp)/'task/context.json').read_text(encoding='utf-8'))
            self.assertEqual(record['messages'], client.messages)
            self.assertEqual(record['components']['user_prompt'], instruction)
            self.assertEqual(result['context_source_hashes'], record['source_hashes'])
            self.assertEqual(result['few_shot_count'], 0)
            self.assertEqual(result['protocol_version'], 3)
            self.assertIsNone(result['success'])


if __name__ == '__main__':
    unittest.main()
