"""Run one validated generated policy in a separate process, then evaluate independently."""
import argparse
from pathlib import Path
import time
from llm_evaluation import tool_clear, evaluate
from core import Config, write_json
from policy_language import Interpreter, PolicyError, validate



def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--code', type=Path)
    p.add_argument('--result', type=Path, required=True)
    p.add_argument('--source')
    p.add_argument('--target')
    p.add_argument('--gui', action='store_true')
    p.add_argument('--axes', action='store_true')
    p.add_argument('--stackviz', action='store_true')
    p.add_argument('--move-delta', type=float, nargs=3)
    p.add_argument('--feedback-rounds', type=int, default=0)
    p.add_argument('--model')
    p.add_argument('--instruction')
    p.add_argument('--max-tokens', type=int, default=2048)
    p.add_argument('--threads', type=int, default=8)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--thinking', action=argparse.BooleanOptionalAction, default=None)
    p.add_argument('--thinking-budget', type=int)
    p.add_argument('--generation-timeout', type=int, default=600)
    p.add_argument('--execution-timeout', type=int, default=120)
    args = p.parse_args()
    result = dict(success=False, stage='validation', actions=[])
    robot = None
    interpreter = None
    started = time.monotonic()
    try:
        if args.code is not None:
            code = args.code.read_text(encoding='utf-8')
            validate(code)
        if bool(args.source or args.target) == bool(args.move_delta):
            raise ValueError('Choose a source/target pair or a movement delta')
        from simulation import Simulation
        robot = Simulation(Config.load(args.config), gui=args.gui, axes=args.axes,
                           stackviz=(args.source, args.target) if args.stackviz and args.source else None)
        if args.source:
            robot._pair(args.source, args.target)
            goal = dict(type='stack', source=args.source, target=args.target)
        else:
            goal = dict(type='move', target_m=(robot.data.site_xpos[robot.sid]+args.move_delta).tolist())
        if args.code is None:
            from llm_agent import Agent
            from llm_session import LocalModel
            if not args.instruction:
                raise ValueError('Feedback evaluation needs --instruction')
            with LocalModel(args.model, threads=args.threads) as client:
                agent = Agent(robot, client, max_rounds=max(1, args.feedback_rounds), max_tokens=args.max_tokens,
                              thinking=args.thinking, seed=args.seed, generation_timeout=args.generation_timeout,
                              thinking_budget=args.thinking_budget,
                              execution_timeout=args.execution_timeout,
                              on_event=lambda kind, data: print(kind, str(data)[:500], flush=True) if kind != 'token' else None)
                report = agent.run_task(args.instruction, args.result.parent/'episode', goal=goal)
                result.update(report, stage='feedback_evaluated' if args.feedback_rounds else 'evaluated',
                              mode='closed_loop_feedback' if args.feedback_rounds else 'open_loop')
        else:
            result['initial_positions'] = {n: robot.position(n).tolist() for n in robot.object_names}
            result['stage'] = 'execution'
            interpreter = Interpreter(robot)
            interpreter.run(code)
            if args.move_delta:
                grading = evaluate(robot, goal)
                result.update(grading, stage='evaluated', simulation_seconds=float(robot.data.time))
            else:
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
