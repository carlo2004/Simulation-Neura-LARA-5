"""Sampling and offline review are independent of physical scoring and inference."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import mujoco
import numpy as np

from stacklab import experiments as exp
from stacklab.config import Config, write_json
from stacklab.review import write_review
from stacklab.llm.catalog import sha256
from stacklab.paths import ROOT
from stacklab.sim.recording import MotionRecorder, render_replay
from stacklab.sim.robot import Simulation, scene_xml


class MotionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.robot = Simulation()
        self.addCleanup(self.robot.close)
        write_json(self.root/'scene.json', self.robot.config.to_dict())

    def record(self):
        recorder = MotionRecorder(self.robot, self.root/'motion.jsonl', 10)
        self.robot.record_callback = recorder.capture
        self.robot.step(.5)
        self.robot.record_callback = None
        return recorder.close(self.robot)

    def test_sampled_states_match_actual_physics_without_changing_it(self):
        reference = Simulation()
        try:
            reference.step(.5)
            result = self.record()
            np.testing.assert_array_equal(self.robot.data.qpos, reference.data.qpos)
            np.testing.assert_array_equal(self.robot.data.qvel, reference.data.qvel)
            self.assertEqual(self.robot.data.time, reference.data.time)
            self.assertGreaterEqual(result['samples'], 6)
            self.assertLessEqual(result['samples'], 8)
            records = [json.loads(line) for line in (self.root/'motion.jsonl').read_text().splitlines()]
            np.testing.assert_array_equal(records[-2]['qpos'], self.robot.data.qpos)
            self.assertEqual(records[-1]['samples'], result['samples'])
        finally:
            reference.close()

    def test_replay_uses_saved_poses_without_stepping_physics_or_grading_again(self):
        result = self.record()
        (self.root/'result.json').write_bytes(b'ORIGINAL PHYSICAL GRADE')
        renderer, writer = Mock(), Mock()
        renderer.render.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
        writer.__enter__ = Mock(return_value=writer)
        writer.__exit__ = Mock(return_value=False)
        seen = []
        renderer.update_scene.side_effect = lambda data, camera: seen.append(data.qpos.copy())
        with patch.object(mujoco, 'Renderer', return_value=renderer), \
                patch.object(mujoco, 'mj_step', side_effect=AssertionError('must not simulate')), \
                patch('stacklab.evaluation.evaluate', side_effect=AssertionError('must not grade')), \
                patch('imageio.v2.get_writer', return_value=writer):
            replay = render_replay(self.root)
        self.assertEqual(replay['frames'], result['samples'])
        self.assertIs(replay['complete'], True)
        self.assertIs(replay['model_called'], False)
        np.testing.assert_array_equal(seen[-1], self.robot.data.qpos)
        self.assertEqual((self.root/'result.json').read_bytes(), b'ORIGINAL PHYSICAL GRADE')

    def test_scene_change_is_rejected_before_rendering(self):
        self.record()
        write_json(self.root/'scene.json', Config(cube_size_m=.045).to_dict())
        with patch.object(mujoco, 'Renderer') as renderer, self.assertRaisesRegex(ValueError, 'differs'):
            render_replay(self.root)
        renderer.assert_not_called()

    def test_recorded_windows_and_linux_project_paths_replay_the_same_scene(self):
        self.record()
        records = [json.loads(line) for line in (self.root/'motion.jsonl').read_text().splitlines()]
        separator = '/' if os.name == 'nt' else '\\'
        other_meshdir = '$PROJECT'+separator+separator.join(('assets', 'robots', 'lara5', 'assets'))
        xml = scene_xml(self.robot.config).replace(str(ROOT/'assets/robots/lara5/assets'), other_meshdir)
        records[0]['model_sha256'] = hashlib.sha256(xml.replace(str(ROOT), '$PROJECT').encode()).hexdigest()
        (self.root/'motion.jsonl').write_text('\n'.join(json.dumps(r) for r in records)+'\n')
        renderer, writer = Mock(), Mock()
        renderer.render.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
        writer.__enter__ = Mock(return_value=writer)
        writer.__exit__ = Mock(return_value=False)
        with patch.object(mujoco, 'Renderer', return_value=renderer), \
                patch.object(mujoco, 'mj_step', side_effect=AssertionError('must not simulate')), \
                patch('imageio.v2.get_writer', return_value=writer):
            replay = render_replay(self.root)
        self.assertTrue(replay['complete'])

    def frozen_clip(self, visuals):
        path = self.root/'episode'
        path.mkdir()
        robot = Simulation(visuals=visuals)
        try:
            write_json(path/'scene.json', robot.config.to_dict())
            recorder = MotionRecorder(robot, path/'motion.jsonl', 10)
            robot.step(.05)
            recorder.close(robot)
        finally:
            robot.close()
        (self.root/'manifest.json').write_text('{}')
        hashes = {name: sha256(ROOT/name) for name in
                  ('assets/robots/lara5/lara5.xml', 'assets/robots/lara5/parameters.json')}
        hashes['assets/robots/lara5/assets/link0_0.obj'] = '0'*64
        return path, hashes

    def test_mesh_free_replay_uses_recorded_mode_without_unused_visual_assets(self):
        path, hashes = self.frozen_clip(False)
        renderer, writer = Mock(), Mock()
        renderer.render.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
        writer.__enter__ = Mock(return_value=writer)
        writer.__exit__ = Mock(return_value=False)
        with patch.object(exp, 'load_plan', return_value=dict(source_hashes=hashes)), \
                patch.object(mujoco, 'Renderer', return_value=renderer) as factory, \
                patch.object(mujoco, 'mj_step', side_effect=AssertionError('must not simulate')), \
                patch('stacklab.evaluation.evaluate', side_effect=AssertionError('must not grade')), \
                patch('imageio.v2.get_writer', return_value=writer):
            replay = render_replay(path)
        self.assertEqual(factory.call_args.args[0].nmesh, 0)
        self.assertFalse(replay['visual_meshes_loaded'])
        self.assertTrue(replay['complete'])
        self.assertFalse(replay['model_called'])

    def test_mesh_free_replay_still_rejects_changed_physical_geometry(self):
        path, hashes = self.frozen_clip(False)
        hashes['assets/robots/lara5/lara5.xml'] = '0'*64
        with patch.object(exp, 'load_plan', return_value=dict(source_hashes=hashes)), \
                patch.object(mujoco, 'Renderer') as renderer, self.assertRaisesRegex(ValueError, 'geometry changed'):
            render_replay(path)
        renderer.assert_not_called()

    def test_full_replay_still_rejects_changed_visual_geometry(self):
        path, hashes = self.frozen_clip(True)
        with patch.object(exp, 'load_plan', return_value=dict(source_hashes=hashes)), \
                patch.object(mujoco, 'Renderer') as renderer, self.assertRaisesRegex(ValueError, 'geometry changed'):
            render_replay(path)
        renderer.assert_not_called()

    def test_recording_io_failure_does_not_interrupt_physics(self):
        recorder = MotionRecorder(self.robot, self.root/'motion.jsonl', 10)
        self.robot.record_callback = recorder.capture
        before = self.robot.data.time
        with patch.object(recorder.file, 'write', side_effect=OSError('controlled disk error')):
            self.robot.step(.2)
        self.assertAlmostEqual(self.robot.data.time-before, .2)
        self.robot.record_callback = None
        result = recorder.close(self.robot)
        self.assertIn('controlled disk error', result['error'])

    def test_headless_model_omits_visual_meshes_but_preserves_mass_dynamics_and_contacts(self):
        compact = Simulation(visuals=False)
        try:
            self.assertEqual(compact.model.nmesh, 0)
            self.assertGreater(self.robot.model.nmesh, 0)
            for name in ('body_mass', 'body_inertia', 'body_ipos', 'body_iquat',
                         'dof_damping', 'dof_armature', 'actuator_gainprm', 'actuator_biasprm'):
                np.testing.assert_array_equal(getattr(compact.model, name), getattr(self.robot.model, name))
            self.robot.step(.5)
            compact.step(.5)
            np.testing.assert_array_equal(compact.data.qpos, self.robot.data.qpos)
            np.testing.assert_array_equal(compact.data.qvel, self.robot.data.qvel)
            self.assertEqual(compact.is_stacked('red', 'blue'), self.robot.is_stacked('red', 'blue'))
        finally:
            compact.close()

    def test_stacking_control_succeeds_identically_without_visual_meshes(self):
        import contextlib
        import io
        compact = Simulation(visuals=False)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                normal_result = self.robot.stack('red', 'blue')
                compact_result = compact.stack('red', 'blue')
            self.assertTrue(normal_result['success'] and compact_result['success'])
            np.testing.assert_allclose(compact.data.qpos, self.robot.data.qpos, atol=1e-12, rtol=0)
            self.assertEqual(compact.check_stack('red', 'blue'), self.robot.check_stack('red', 'blue'))
        finally:
            compact.close()


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with patch.object(exp, 'source_hashes', return_value={}), patch.object(exp, 'environment', return_value={}):
            self.plan = exp.create_plan(self.root, models=['lfm2.6b'], cases=['move-right'],
                                       scene_seeds=[1], generation_seeds=[2], blocks=[1])
        self.episode = self.plan['episodes'][0]
        self.path = self.root/self.episode['episode_id']
        self.path.mkdir()
        write_json(self.path/'manifest.json', dict(schema_version=exp.SCHEMA, **self.episode,
                   plan_sha256=self.plan['plan_sha256']))
        execution = dict(status='verified_success', success=True, evaluation=dict(success=True),
            rounds=[dict(round=1, model_declared_done=True, execution_outcome='executed',
                         generation={}, feedback={})])
        write_json(self.path/'result.json', dict(instruction='<script>unsafe()</script>', execution=execution))
        self.block = self.path/'episode/round_01'
        self.block.mkdir(parents=True)
        write_json(self.block/'response.json', dict(choices=[dict(message=dict(
            content='<img src=x onerror=unsafe()>', reasoning_content='MODEL_REASONING_TEST_SENTINEL'))]))
        (self.block/'generated.py').write_text('robot.jog("x", .05)\n')
        (self.path/'simulation.mp4').write_bytes(b'controlled test placeholder')

    def test_html_escapes_model_and_user_text_and_loads_videos_only_on_demand(self):
        output = write_review(self.root)
        text = output.read_text(encoding='utf-8')
        self.assertIn('&lt;script&gt;unsafe()&lt;/script&gt;', text)
        self.assertIn('&lt;img src=x onerror=unsafe()&gt;', text)
        self.assertNotIn('<script>unsafe()', text)
        self.assertNotIn('MODEL_REASONING_TEST_SENTINEL', text)
        self.assertIn('preload="none"', text)
        self.assertIn('physisch erfolgreich', text)
        self.assertIn('robot.jog', text)

    def test_model_reasoning_is_only_added_when_explicitly_requested(self):
        output = write_review(self.root, include_reasoning=True)
        self.assertIn('MODEL_REASONING_TEST_SENTINEL', output.read_text(encoding='utf-8'))
        self.assertIn('keine verifizierte Erklärung', output.read_text(encoding='utf-8'))

    def test_replay_hint_does_not_embed_the_local_absolute_directory(self):
        (self.path/'simulation.mp4').unlink()
        (self.path/'motion.jsonl').write_text('controlled placeholder')
        text = write_review(self.root).read_text(encoding='utf-8')
        self.assertNotIn(str(self.root), text)
        self.assertIn('python -m stacklab experiment replay', text)
        self.assertIn(self.episode['episode_id'], text)

    def test_external_replay_output_preserves_existing_archived_reports(self):
        from stacklab.cli.experiment import main
        originals = {name: b'ORIGINAL ARCHIVED REPORT' for name in
                     ('summary.json', 'results.csv', 'review.html')}
        for name, content in originals.items():
            (self.root/name).write_bytes(content)
        with patch('stacklab.sim.recording.render_replay', return_value=dict(model_called=False)), \
                contextlib.redirect_stdout(io.StringIO()):
            result = main(['replay', str(self.path), '--output', str(self.root/'separate.mp4')])
        self.assertEqual(result, 0)
        for name, content in originals.items():
            self.assertEqual((self.root/name).read_bytes(), content)


if __name__ == '__main__':
    unittest.main()
