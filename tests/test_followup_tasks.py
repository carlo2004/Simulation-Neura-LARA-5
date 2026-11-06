"""Regressions at the new task boundaries using real MuJoCo contacts."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from stacklab.config import Config
from stacklab.evaluation import evaluate, observe, resolve_goal
from stacklab.llm.agent import Agent
from stacklab.llm.responses import parse_reply
from stacklab.paths import ROOT
from stacklab.policy import Interpreter, PolicyError
from stacklab.sim.robot import Simulation
from stacklab.tasks import task_definition


class FollowupTests(unittest.TestCase):
    def robot_for(self, name):
        case = task_definition(name, 42)
        robot = Simulation(Config(**case['config']), visuals=False)
        self.addCleanup(robot.close)
        return robot, case

    def test_drop_needs_a_physical_release_at_the_required_height(self):
        robot, case = self.robot_for('drop')
        goal = resolve_goal(robot, case['goal'])
        actions = Interpreter(robot).run('''p = robot.position("red")
robot.move_to([p[0], p[1], .24])
robot.move_to(p)
robot.gripper(True)
robot.move_to([p[0], p[1], .24])
robot.move_to([.45, .13, .24])
robot.move_to([.45, .13, .16])
robot.gripper(False)
robot.move_to([.45, .13, .24])''')
        grade = evaluate(robot, goal, actions=actions)
        self.assertTrue(grade['success'], grade)
        self.assertGreater(grade['diagnostics']['release_centres_m'][0][2], .12)
        self.assertFalse(evaluate(robot, goal)['success'])

    def test_bottom_orientation_is_reachable_and_joint_limits_reject_before_motion(self):
        robot, case = self.robot_for('orient-bottom')
        time_before = robot.data.time
        with self.assertRaisesRegex(PolicyError, 'arm limits'):
            Interpreter(robot).run('robot.move_joints([9, 0, 0, 0, 0, 0])')
        self.assertEqual(robot.data.time, time_before)
        goal = resolve_goal(robot, case['goal'])
        Interpreter(robot).run(f'robot.move_to({goal["target_m"]!r}, orientation="bottom", yaw_deg={goal["yaw_deg"]})')
        grade = evaluate(robot, goal)
        self.assertTrue(grade['success'], grade)

    def test_pyramid_example_runs_through_the_public_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)/'pyramid'
            result = subprocess.run([sys.executable, '-m', 'stacklab', 'tasks', 'run', 'pyramid',
                                     '--code', str(ROOT/'examples/pyramid.py'), '--output', str(output)],
                                    capture_output=True, timeout=75)
            report = json.loads((output/'execution.json').read_text(encoding='utf-8'))
            self.assertEqual(result.returncode, 0, report)
            self.assertEqual(report['stable_checks'], 20)
            upper = next(match for match in report['diagnostics']['matches'] if match['object'] == 'green')
            self.assertTrue(upper['contacts'])
            self.assertCountEqual(upper['supports'], ['red', 'blue'])

    def test_colour_slots_reject_cubes_at_the_right_positions_with_the_wrong_colour(self):
        robot, _ = self.robot_for('sort-colour')
        slots = [dict(centre_m=robot.position(name).tolist(), color=robot.objects[name].color_name())
                 for name in robot.object_names]
        goal = dict(type='layout', slots=slots)
        self.assertTrue(evaluate(robot, goal)['success'])
        slots[0]['color'] = 'blue'
        self.assertFalse(evaluate(robot, goal)['success'])

    def test_ambiguous_colour_requires_a_clarification_and_keeps_the_trusted_goal_private(self):
        class ClarifyingModel:
            config = {'model_key': 'fixture'}
            calls = 0

            def complete(self, messages, directory, **kwargs):
                self.calls += 1
                self.messages = messages
                Path(directory).mkdir()
                return json.dumps(dict(code='', done=True, intent='clarify', message='red_a oder red_b?')), {}

            def cancel(self):
                pass

        robot, case = self.robot_for('ambiguous-colour')
        model = ClarifyingModel()
        with tempfile.TemporaryDirectory() as temp:
            report = Agent(robot, model, max_rounds=4).run_task(case['instruction'], temp, goal=case['goal'])
        self.assertTrue(report['success'], report)
        self.assertEqual(model.calls, 1)
        wire = json.loads(model.messages[1]['content'])
        self.assertNotIn('goal', wire)
        reds = [o['name'] for o in wire['observation']['objects'] if o['color'] == 'red']
        self.assertEqual(reds, ['red_a', 'red_b'])
        with self.assertRaises(ValueError):
            parse_reply(json.dumps(dict(code='robot.gripper(True)', done=True, intent='clarify', message='Which?')))
        self.assertFalse(evaluate(robot, case['goal'], initial=observe(robot),
                                  reply=dict(code='', done=True, intent='no_op', message='Already done.'))['success'])
