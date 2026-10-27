"""Low-level Python program for the supplied LARA 5 environment.

Run: python example_program.py
A hand-written reference, not an LLM-generated evaluation result.
"""
from pathlib import Path
from core import Config, write_json
from simulation import Simulation

def program(robot, source_name='red', target_name='blue'):
    source = robot.position(source_name)
    target = robot.position(target_name)
    height = robot.config.hover_z_m
    robot.move_to([source[0], source[1], height])
    robot.move_to(source)
    robot.gripper(closed=True)
    robot.move_to([source[0], source[1], height])
    if robot.position(source_name)[2] < height-.04:
        raise RuntimeError('Pick failed')
    robot.move_to([target[0], target[1], height])
    robot.move_to([target[0], target[1], target[2]+(robot.objects[source_name].dimensions()[2]+robot.objects[target_name].dimensions()[2])/2+.001])
    robot.gripper(closed=False)
    robot.move_to([target[0], target[1], height])

def main():
    robot = Simulation(Config())
    try:
        program(robot)
        robot.step(1)
        checks = []
        for _ in range(20):
            robot.step(.1)
            checks.append(robot.is_stacked('red', 'blue'))
        result = {'success': all(checks), 'stable_checks': sum(checks), 'checks': 20}
        write_json(Path(__file__).with_name('output')/'example_result.json', result)
        print(result)
        return 0 if result['success'] else 1
    finally:
        robot.close()

if __name__ == '__main__': raise SystemExit(main())
