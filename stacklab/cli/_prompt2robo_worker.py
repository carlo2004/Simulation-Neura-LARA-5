"""Isolated process for the pinned dataset checker and optional rendering."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tools', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('sample_id')
    parser.add_argument('--video', action='store_true')
    parser.add_argument('--gui', action='store_true')
    args = parser.parse_args()
    payload = json.load(sys.stdin)
    sample, response = payload['sample'], payload['response']
    sample['assistant_answer'] = response['code'] or response['message']
    if sample['id'] != args.sample_id:
        raise ValueError('Wrong sample in worker')

    sys.path.insert(0, str(args.tools))
    import check
    import mujoco
    import robot

    video_path = args.output / f'{args.sample_id}.mp4'
    partial = video_path.with_suffix('.partial.mp4')
    original_sim = robot.Sim
    observed = None
    frame_count = 0
    fps = 24
    with ExitStack() as cleanup:
        writer = None
        renderer = None
        viewer = None
        next_frame = 0.
        camera = mujoco.MjvCamera()
        camera.lookat[:] = [.38, 0, .49]
        camera.distance = 1.85
        camera.azimuth = 130
        camera.elevation = -27

        class ObservedSim(original_sim):
            def _step(self, q_target=None):
                nonlocal observed, renderer, viewer, next_frame, frame_count
                super()._step(q_target)
                observed = self
                if not (args.video or args.gui) or self.data.time < next_frame:
                    return
                if args.video:
                    if renderer is None:
                        headlight = self.model.vis.headlight
                        headlight.ambient[:] = .42
                        headlight.diffuse[:] = .78
                        headlight.specular[:] = .15
                        renderer = cleanup.enter_context(mujoco.Renderer(self.model, height=480, width=640))
                    renderer.update_scene(self.data, camera=camera)
                    writer.append_data(renderer.render())
                    frame_count += 1
                if args.gui:
                    if viewer is None:
                        from mujoco import viewer as mj_viewer
                        viewer = cleanup.enter_context(mj_viewer.launch_passive(self.model, self.data))
                        with viewer.lock():
                            viewer.cam.lookat[:] = camera.lookat
                            viewer.cam.distance = camera.distance
                            viewer.cam.azimuth = camera.azimuth
                            viewer.cam.elevation = camera.elevation
                    if not viewer.is_running():
                        raise robot.RobotError('Viewer closed')
                    viewer.sync()
                    time.sleep(1 / fps)
                next_frame += 1 / fps

        if args.video and response['code']:
            import imageio.v2 as imageio
            writer = cleanup.enter_context(imageio.get_writer(
                partial, fps=fps, codec='libx264', quality=5,
                ffmpeg_params=['-movflags', '+faststart']))
        robot.Sim = ObservedSim
        try:
            passed, reasons = check.check(sample)
        finally:
            robot.Sim = original_sim
        if frame_count:
            renderer.update_scene(observed.data, camera=camera)
            final_frame = renderer.render()
            for _ in range(fps):
                writer.append_data(final_frame)
            frame_count += fps
    if frame_count:
        partial.replace(video_path)
    elif partial.exists():
        partial.unlink()
    report = {'id': args.sample_id, 'split': sample['split'], 'category': sample['category'],
              'subcategory': sample['subcategory'], 'passed': passed, 'reasons': reasons,
              'request': sample['user_prompt'].partition('\n')[2],
              'message': response['message'],
              'final_state': observed.state() if observed is not None else None,
              'video': video_path.name if frame_count else None, 'frames': frame_count, 'fps': fps}
    receipt = args.output / f'{args.sample_id}.json'
    receipt.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
