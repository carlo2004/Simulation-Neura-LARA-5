"""Small sampled pose records; rendering is deferred until a person needs a clip."""
import hashlib
import json
from pathlib import Path
import time


def model_signature(config):
    from stacklab.paths import ROOT
    from stacklab.sim.robot import scene_xml
    xml = scene_xml(config).replace(str(ROOT), '$PROJECT')
    return hashlib.sha256(xml.encode('utf-8')).hexdigest()


class MotionRecorder:
    def __init__(self, robot, path, fps=10):
        import mujoco
        if type(fps) is not int or not 1 <= fps <= 60:
            raise ValueError('Motion sampling must be an integer from 1 to 60 Hz')
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open('w', encoding='utf-8', buffering=65536)
        self.fps, self.samples, self.error = fps, 0, None
        self.last_bucket = None
        self.started = time.monotonic()
        header = dict(kind='header', schema_version=1, fps=fps, nq=robot.model.nq,
                      visual_meshes_loaded=robot.visuals,
                      model_sha256=model_signature(robot.config), mujoco=mujoco.__version__,
                      note='Sampled actual qpos. Visual replay only; physical grading is stored separately.')
        self.file.write(json.dumps(header)+'\n')
        self.capture(robot, force=True)

    def capture(self, robot, force=False):
        if self.error or self.file.closed:
            return
        bucket = int(float(robot.data.time)*self.fps+1e-8)
        if not force and bucket == self.last_bucket:
            return
        try:
            self.file.write(json.dumps(dict(kind='pose', time_s=float(robot.data.time),
                wall_seconds=time.monotonic()-self.started, qpos=robot.data.qpos.tolist()),
                separators=(',', ':'))+'\n')
            self.samples += 1
            self.last_bucket = bucket
            if force or self.samples % self.fps == 0:
                self.file.flush()
        except OSError as error:
            # Recording failure must not turn a correct motion into a model error.
            self.error = type(error).__name__+': '+str(error)

    def close(self, robot):
        self.capture(robot, force=True)
        if not self.file.closed:
            try:
                self.file.write(json.dumps(dict(kind='end', samples=self.samples, error=self.error))+'\n')
                self.file.close()
            except OSError as error:
                self.error = type(error).__name__+': '+str(error)
            finally:
                if not self.file.closed:
                    try:
                        self.file.close()
                    except OSError as error:
                        self.error = self.error or type(error).__name__+': '+str(error)
        return dict(path=self.path.name, fps=self.fps, samples=self.samples, error=self.error)


def render_replay(directory, output=None):
    """Render recorded poses without calling mj_step, IK, the LLM or the evaluator."""
    import imageio.v2 as imageio
    import mujoco
    import numpy as np
    from stacklab.config import Config, write_json
    from stacklab.sim.robot import scene_xml
    directory = Path(directory).resolve()
    config = Config.load(directory/'scene.json')
    output = Path(output).resolve() if output else directory/'simulation.mp4'
    if output.exists():
        raise ValueError('Replay output already exists; choose a new output path')
    # Check geometry hashes against the frozen experiment, if it is available.
    manifest = directory.parent/'manifest.json'
    if manifest.is_file():
        from stacklab.experiments import load_plan
        from stacklab.llm.catalog import sha256
        from stacklab.paths import ROOT
        plan = load_plan(directory.parent)
        for relative, expected in plan['source_hashes'].items():
            if relative.startswith('assets/robots/lara5/') and sha256(ROOT/relative) != expected:
                raise ValueError('Robot geometry changed since recording; use the original assets')
    with (directory/'motion.jsonl').open(encoding='utf-8') as source:
        header = json.loads(next(source))
        if (header.get('kind') != 'header' or header.get('schema_version') != 1
                or header.get('model_sha256') != model_signature(config)
                or header.get('mujoco') != mujoco.__version__):
            raise ValueError('Motion file, scene or MuJoCo version differs from the recording')
        model = mujoco.MjModel.from_xml_string(scene_xml(config))
        if header.get('nq') != model.nq:
            raise ValueError('Motion coordinates do not match this model')
        data = mujoco.MjData(model)
        camera = mujoco.MjvCamera()
        camera.lookat[:] = [.25, 0, .22]
        camera.distance, camera.azimuth, camera.elevation = 1.35, 135, -25
        output.parent.mkdir(parents=True, exist_ok=True)
        frames, complete = 0, False
        renderer = mujoco.Renderer(model, 480, 640)
        try:
            with imageio.get_writer(str(output), fps=header['fps'], codec='libx264', quality=7) as writer:
                for line in source:
                    try:
                        record = json.loads(line)
                    except ValueError:
                        break  # An interrupted last line is retained as a partial replay.
                    if record.get('kind') == 'end':
                        complete = not record.get('error') and record.get('samples') == frames
                        break
                    qpos = np.asarray(record.get('qpos'), dtype=float)
                    if record.get('kind') != 'pose' or qpos.shape != (model.nq,) or not np.isfinite(qpos).all():
                        raise ValueError('Invalid recorded pose')
                    data.qpos[:] = qpos
                    data.time = record['time_s']
                    mujoco.mj_forward(model, data)
                    renderer.update_scene(data, camera)
                    writer.append_data(renderer.render())
                    frames += 1
        finally:
            renderer.close()
    if not frames:
        raise ValueError('No recorded poses are available')
    metadata = dict(frames=frames, fps=header['fps'], complete=complete, source='motion.jsonl',
                    evaluation_repeated=False, model_called=False,
                    note='One recorded pose per frame. Sampled visualization; not a new physics run.')
    write_json(output.with_suffix('.replay.json'), metadata)
    return metadata
