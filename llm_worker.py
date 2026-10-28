"""Run one validated generated policy in a separate process, then evaluate independently."""
import argparse
from pathlib import Path
import time
import numpy as np
from core import Config, write_json
from policy_language import Interpreter, PolicyError, validate


def tool_clear(robot, source):
    object_id = robot.model.geom(source+'_geom').id
    fingers = {robot.model.geom(n).id for n in ('palm', 'left_pad', 'right_pad')}
    contact = any(int(c.geom1) == object_id and int(c.geom2) in fingers
                  or int(c.geom2) == object_id and int(c.geom1) in fingers for c in robot.data.contact)
    distance = float(np.linalg.norm(robot.data.site_xpos[robot.sid]-robot.position(source)))
    return not contact and distance > .075


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--code', type=Path, required=True)
    p.add_argument('--result', type=Path, required=True)
    p.add_argument('--source', required=True)
    p.add_argument('--target', required=True)
    p.add_argument('--gui', action='store_true')
    p.add_argument('--axes', action='store_true')
    p.add_argument('--stackviz', action='store_true')
    args = p.parse_args()
    result = dict(success=False, stage='validation', actions=[])
    robot = None
    interpreter = None
    started = time.monotonic()
    try:
        code = args.code.read_text(encoding='utf-8')
        validate(code)
        from simulation import Simulation
        robot = Simulation(Config.load(args.config), gui=args.gui, axes=args.axes,
                           stackviz=(args.source, args.target) if args.stackviz else None)
        robot._pair(args.source, args.target)
        result['initial_positions'] = {n: robot.position(n).tolist() for n in robot.object_names}
        result['stage'] = 'execution'
        interpreter = Interpreter(robot)
        interpreter.run(code)
        robot.step(1)
        checks = []
        robot.overlays.begin_check(args.source, args.target)
        try:
            for _ in range(20):
                robot.step(.1)
                checks.append(bool(robot.is_stacked(args.source, args.target) and tool_clear(robot, args.source)))
                robot.overlays.samples.append(checks[-1])
        finally:
            robot.overlays.checking = False
            robot.refresh_view()
        result.update(success=all(checks), stage='evaluated', stable_checks=sum(checks), checks=20,
                      check_samples=checks, tool_clear=bool(tool_clear(robot, args.source)),
                      diagnostics=robot.stack_diagnostics(args.source, args.target),
                      final_positions={n: robot.position(n).tolist() for n in robot.object_names},
                      simulation_seconds=float(robot.data.time))
        if args.gui:
            print('Test complete; showing the result for ten simulation seconds.', flush=True)
            try:
                robot.step(10)
            except KeyboardInterrupt:
                pass
    except PolicyError as error:
        result.update(stage='api_rejected', error=str(error))
    except Exception as error:
        result.update(stage='simulation_error', error=type(error).__name__+': '+str(error))
    finally:
        if interpreter is not None:
            result['actions'] = interpreter.actions
        result['wall_seconds'] = time.monotonic()-started
        write_json(args.result, result)
        if robot is not None:
            robot.close()
    print('PASS' if result['success'] else 'FAIL', result['stage'], flush=True)
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
