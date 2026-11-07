"""Run one pinned Prompt2Robo sample on the shared LARA 5 simulation."""
import argparse
import base64
from contextlib import ExitStack
import importlib.util
import io
import json
import math
from pathlib import Path
import sys
import time
from types import ModuleType


LIVE_FPS = 12
EXPORT_FPS = 16


def trace_value(value):
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is str:
        return value[:100]
    if type(value) is float and math.isfinite(value):
        return value
    return f'<{type(value).__name__}>'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checker', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('sample_id')
    image_output = parser.add_mutually_exclusive_group()
    image_output.add_argument('--video', nargs='?', const='full', choices=('full', 'preview'),
                              help='Encode an MP4 for export')
    image_output.add_argument('--live', action='store_true', help='Stream sampled rendered frames over stdout')
    parser.add_argument('--gui', action='store_true')
    parser.add_argument('--generated', action='store_true', help='Use the bounded model-policy evaluator')
    parser.add_argument('--unscored', action='store_true', help='Execute a free prompt without a dataset goal')
    args = parser.parse_args()
    payload = json.load(sys.stdin)
    sample, response = payload['sample'], payload['response']
    sample['assistant_answer'] = response['code'] or response['message']
    if sample['id'] != args.sample_id:
        raise ValueError('Wrong sample in worker')

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import mujoco
    from stacklab.config import Config, write_json
    from stacklab.prompt2robo import FPS, LaraReplay, ReplayScene, run_reference
    from stacklab.sim.robot import Simulation

    video_path = args.output / f'{args.sample_id}.mp4'
    partial = video_path.with_suffix('.partial.mp4')
    speed_mm_s = payload.get('speed_mm_s', Config.speed_mm_s)
    fps = EXPORT_FPS if args.video == 'preview' else FPS
    preview = args.live or args.video == 'preview'
    height, width = (480, 640) if preview else (720, 960)
    observed = None
    initial_state = None
    frame_count = 0
    stage = 'text_check' if not response['code'] else 'setup'

    def emit(event, **data):
        if args.live:
            print(json.dumps(dict(event=event, **data), ensure_ascii=True, allow_nan=False), flush=True)

    with ExitStack() as cleanup:
        def execute(scene, code):
            nonlocal observed, initial_state, stage, frame_count
            config = ReplayScene(scene, speed_mm_s=speed_mm_s, fps=fps)
            sim = Simulation(config, visuals=args.video or args.gui or args.live)
            cleanup.callback(sim.close)
            observed = LaraReplay(sim, scene)
            initial_state = observed.state()
            if args.gui:
                sim.open_viewer()
            frame = None
            if args.live or args.video:
                if preview:
                    sim.model.vis.quality.offsamples = 0
                renderer = mujoco.Renderer(sim.model, height=height, width=width)
                if args.video:
                    sim.renderer = renderer
                else:
                    cleanup.enter_context(renderer)
                if preview:
                    renderer.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = 0
                    renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = 0
            if args.live:
                from PIL import Image
                next_frame = 0.

                def frame(current, force=False):
                    nonlocal next_frame
                    if not force and time.monotonic() < next_frame:
                        return
                    buffer = io.BytesIO()
                    Image.fromarray(current.render_frame(renderer)).save(buffer, 'JPEG', quality=78)
                    emit('frame', jpeg=base64.b64encode(buffer.getvalue()).decode('ascii'),
                         time_s=round(float(current.data.time), 3))
                    next_frame = time.monotonic() + 1 / LIVE_FPS

                frame(sim, force=True)
                sim.record_callback = frame
            first_frame = sim.frames
            if args.video:
                import imageio.v2 as imageio
                sim.writer = imageio.get_writer(partial, fps=fps, codec='libx264', quality=8,
                                                ffmpeg_params=['-movflags', '+faststart'])
                sim.writer.append_data(sim.render_frame(sim.renderer))
            stage = 'execution'
            try:
                if args.generated:
                    from stacklab.workbench_policy import WorkbenchPolicy

                    def trace(phase, action):
                        nonlocal stage
                        stage = 'execution'
                        values = action['args']
                        emit('action', phase=phase, step=len(runner.actions), method=action['method'],
                             args=[trace_value(value) for value in values[:4]],
                             extra_args=max(0, len(values) - 4),
                             kwargs=list(action['kwargs'])[:4],
                             time_s=round(float(sim.data.time), 3),
                             status=action.get('status'), error=action.get('error', '')[:500],
                             result=[trace_value(value) for value in action.get('result', [])])

                    stage = 'policy'
                    runner = WorkbenchPolicy(observed, on_action=trace)
                    runner.run(code)
                else:
                    run_reference(code, observed)
                sim.step(.75)
            except Exception as error:
                return observed.state(), f'{type(error).__name__}: {error}', observed
            finally:
                if frame is not None:
                    frame(sim, force=True)
                if sim.writer:
                    last_frame = sim.render_frame(sim.renderer)
                    for _ in range(fps):
                        sim.writer.append_data(last_frame)
                    frame_count = sim.frames - first_frame + 1 + fps
            stage = 'goal_check'
            return observed.state(), None, observed

        # The dataset checker imports robot.execute at call time. Supply our
        # implementation before loading it. Only check.py is fetched from tools/.
        backend = ModuleType('robot')
        backend.execute = execute
        sys.modules['robot'] = backend
        spec = importlib.util.spec_from_file_location('prompt2robo_goals', args.checker)
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        if args.unscored:
            reasons = []
            if response['code']:
                try:
                    _, error, _ = execute(sample['scene'], response['code'])
                except Exception as failure:
                    error = str(failure)
                if error:
                    reasons.append(error)
            passed = None
        elif not response['code'] and sample['expected_behavior'] == 'execute':
            passed, reasons = False, ['Expected a robot program but received a text response']
        else:
            passed, reasons = checker.check(sample)

    if frame_count:
        partial.replace(video_path)
    else:
        partial.unlink(missing_ok=True)
    report = {'id': args.sample_id, 'split': sample['split'], 'category': sample['category'],
              'subcategory': sample['subcategory'], 'passed': passed, 'stage': stage, 'reasons': reasons,
              'request': sample['user_prompt'].partition('\n')[2], 'message': response['message'],
              'initial_state': initial_state, 'final_state': observed.state() if observed is not None else None,
              'held_object_ids': sorted(observed.held_objects(), key=int) if observed is not None else [],
              'simulation_seconds': round(float(observed.data.time), 3) if observed is not None else None,
              'speed_mm_s': speed_mm_s, 'video': video_path.name if frame_count else None,
              'frames': frame_count, 'fps': fps}
    write_json(args.output / f'{args.sample_id}.json', report)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
