"""Repeatable physical pushes and scripted key input, without pretending to test a desktop."""
from stacklab.paths import RUNS_ROOT
import argparse
from unittest.mock import patch
import mujoco
import numpy as np
from stacklab.config import Config, ObjectSpec, write_json
from stacklab.cli.console import Controller
from stacklab.sim.manual import SPACE, ESCAPE
from stacklab.sim.robot import ROOT, Simulation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--images', action='store_true', help='Use EGL/OpenGL for visual evidence')
    args = parser.parse_args()
    (RUNS_ROOT).mkdir(parents=True, exist_ok=True)
    results = []
    for label, config, name, delta in [
        ('cube_x', Config(), 'red', (.06, 0)),
        ('cube_y', Config(), 'blue', (0, -.06)),
        ('ball', Config(objects=[ObjectSpec('ball', shape='sphere').to_dict()]), 'ball', (.06, 0)),
        ('cylinder', Config(objects=[ObjectSpec('can', shape='cylinder', size_m=[.04, .06]).to_dict()]), 'can', (.06, 0)),
        ('duck_mesh', Config.load(ROOT/'scenes/duck.json'), 'duck', (.05, 0)),
    ]:
        robot = Simulation(config, axes=args.images)
        try:
            if args.images and label == 'duck_mesh':
                save_image(robot, 'duck_before_push.png')
            result = robot.push(name, *delta)
            direction = np.array(delta)/np.linalg.norm(delta)
            progress = float(np.dot(result['displacement_m'][:2], direction))
            result.update(label=label, progress_m=progress,
                          success=bool(result['finger_contact_seen'] and progress > .03))
            assert not np.any(robot.data.qfrc_applied[8:]) and not np.any(robot.data.xfrc_applied)
            results.append(result)
            if args.images and label == 'duck_mesh':
                save_image(robot, 'duck_after_push.png')
            print(label, result['success'], f'{progress*1000:.2f} mm', flush=True)
        finally:
            robot.close()

    robot = Simulation(Config.load(ROOT/'scenes/duck.json'), axes=args.images)
    try:
        controller = Controller(robot, output=lambda _: None)
        before = robot.data.site_xpos[robot.sid].copy()
        robot.manual.enable(robot)
        for key in (265, 263, 268):
            robot.manual.on_key(key)
            for _ in range(50):
                controller.idle(.02)
        expected = before+[.005, .005, .005]
        error = float(np.linalg.norm(robot.data.site_xpos[robot.sid]-expected))
        assert error < .001
        robot.manual.selected = robot.position('duck')+[0, 0, .035]
        if args.images:
            save_image(robot, 'manual_preview.png')
        robot.manual.on_key(SPACE)
        controller.idle(.02)
        assert robot.manual.enabled and robot.manual.pending.empty()
        robot.manual.on_key(ESCAPE)
        controller.idle(.02)
        assert not robot.manual.enabled
        with patch.object(robot, 'selected_point', return_value=np.array([.48, .03, .02])):
            controller.execute('goto-selected')
        np.testing.assert_allclose(robot.data.site_xpos[robot.sid], [.48, .03, .24], atol=.001)
        results.append(dict(label='scripted_keys_and_selected_point', success=True, tcp_error_m=error,
                            note='Real physics; key events and selected point injected, not desktop input'))
    finally:
        robot.close()
    report = dict(success=all(r['success'] for r in results), passed=sum(r['success'] for r in results),
                  total=len(results), mujoco=mujoco.__version__, native_window_manually_tested=False,
                  results=results)
    write_json(RUNS_ROOT/'controls_validation.json', report)
    return 0 if report['success'] else 1


def save_image(robot, filename):
    from PIL import Image
    renderer = mujoco.Renderer(robot.model, 720, 960)
    try:
        Image.fromarray(robot.render_frame(renderer)).save(RUNS_ROOT/filename)
    finally:
        renderer.close()


if __name__ == '__main__':
    raise SystemExit(main())
