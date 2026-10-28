"""Exercise the real render pipeline and console, with before/after evidence."""
from stacklab.paths import RUNS_ROOT
import contextlib
import io
import mujoco
import numpy as np
from PIL import Image
from stacklab.cli.console import Controller, CommandError
from stacklab.config import write_json
from stacklab.sim.robot import ROOT, Simulation


def main():
    output = RUNS_ROOT
    output.mkdir(exist_ok=True)
    robot = Simulation()
    renderer = mujoco.Renderer(robot.model, 720, 960)
    controller = Controller(robot, output=lambda _: None)
    results = {}
    try:
        assert not robot.overlays.axes and robot.overlays.stack_pair is None
        base = robot.render_frame(renderer)
        baseline = robot.data.qpos.copy()
        controller.execute('axes on')
        controller.execute('stackviz red blue')
        np.testing.assert_array_equal(robot.data.qpos, baseline)
        before = robot.render_frame(renderer)
        assert np.any(base != before)
        Image.fromarray(before).save(output/'overlays_before.png')
        results['initial_status'] = robot.overlays.status()

        controller.execute('move .40 -.12 .24')
        np.testing.assert_allclose(robot.data.site_xpos[robot.sid], [.40, -.12, .24], atol=.001)
        controller.execute('jog z .03')
        np.testing.assert_allclose(robot.data.site_xpos[robot.sid], [.40, -.12, .27], atol=.001)
        results['move_and_jog_passed'] = True
        try:
            controller.execute('check red blue')
        except CommandError:
            pass
        else:
            raise AssertionError('Separate cubes must fail the check')
        assert robot.overlays.status() == 'FAIL'
        Image.fromarray(robot.render_frame(renderer)).save(output/'overlays_failed.png')
        results['negative_check'] = robot.overlays.samples.copy()

        controller.execute('reset')
        assert robot.overlays.status() == 'UNCHECKED'
        with contextlib.redirect_stdout(io.StringIO()):
            controller.execute('stack red blue')
        assert robot.overlays.status() == 'PASS'
        controller.execute('check red blue')
        assert robot.overlays.status() == 'PASS'
        results['positive_check'] = robot.overlays.samples.copy()
        results['diagnostics'] = robot.stack_diagnostics('red', 'blue')
        results['tcp_m'] = robot.data.site_xpos[robot.sid].tolist()
        results['objects_m'] = {name: robot.position(name).tolist() for name in robot.object_names}
        Image.fromarray(robot.render_frame(renderer)).save(output/'overlays_pass.png')

        # Exercise MuJoCo's actual text API in an offscreen GL context.
        # The GUI uses Handle.set_texts with these same font/grid/text tuples.
        ctx = mujoco.MjrContext(robot.model, mujoco.mjtFontScale.mjFONTSCALE_150)
        try:
            mujoco.mjr_setBuffer(mujoco.mjtFramebuffer.mjFB_OFFSCREEN, ctx)
            viewport = mujoco.MjrRect(0, 0, 960, 720)
            mujoco.mjr_render(viewport, renderer.scene, ctx)
            for font, grid, text1, text2 in robot.overlays.viewer_texts(robot):
                mujoco.mjr_overlay(font, grid, viewport, text1, text2, ctx)
            pixels = np.empty((720, 960, 3), dtype=np.uint8)
            mujoco.mjr_readPixels(pixels, None, viewport, ctx)
            Image.fromarray(np.flipud(pixels)).save(output/'overlays_native_text.png')
        finally:
            ctx.free()
        results['native_text_rendered'] = True

        baseline = robot.data.qpos.copy()
        controller.execute('axes off')
        controller.execute('stackviz off')
        frame = robot.render_frame(renderer)
        np.testing.assert_array_equal(robot.data.qpos, baseline)
        assert robot.overlays.panels(robot) == []
        Image.fromarray(frame).save(output/'overlays_off.png')
        results.update(success=True, toggles_preserve_physics=True, overlays_off_after_test=True,
                       mujoco=mujoco.__version__, native_window_manually_tested=False)
        write_json(output/'overlays_validation.json', results)
        print('PASS: hidden defaults, toggles, move/jog, negative and positive checks, EGL geometry/text')
        return 0
    finally:
        renderer.close()
        robot.close()


if __name__ == '__main__':
    raise SystemExit(main())
