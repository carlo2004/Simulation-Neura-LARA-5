"""Separate context components from their native-chat transport representation."""
import hashlib
import json
import os
from pathlib import Path

from stacklab.paths import ROOT

COMPONENTS = ('world_info', 'observation', 'runtime_info', 'few_shot', 'user_prompt')


def model_json(value):
    # Keep precise physics separately; avoid floating-point tails in model input.
    def compact(item):
        if isinstance(item, float):
            return round(item, 6)
        if isinstance(item, dict):
            return {key: compact(v) for key, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [compact(v) for v in item]
        return item
    return json.dumps(compact(value), ensure_ascii=False, allow_nan=False)


class PromptContext:
    """Load static context once, then supply fresh observations for every task.

    Native templates receive one initial system message and one user turn.
    Named context blocks remain distinct in the user turn's JSON and in the log;
    no fake assistant acknowledgements or demonstration answers are inserted.
    """
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get('STACKLAB_CONTEXT_CONFIG',
                                              ROOT/'config/prompts/context.json')).expanduser().resolve()
        raw = self.path.read_bytes()
        settings = json.loads(raw)
        if (not isinstance(settings, dict) or settings.get('schema_version') != 1
                or set(settings) != {'schema_version', 'system_prompt_file', 'world_info_file', 'few_shot_file', 'order'}):
            raise ValueError('Unsupported prompt context configuration')
        order = settings['order']
        if (not isinstance(order, list) or not all(isinstance(name, str) for name in order)
                or len(order) != len(COMPONENTS) or set(order) != set(COMPONENTS)):
            raise ValueError('Context order must contain each context component exactly once')
        self.order = order
        self.source_hashes = {'layout': hashlib.sha256(raw).hexdigest()}
        files = {}
        for key in ('system_prompt', 'world_info', 'few_shot'):
            name = settings[key+'_file']
            if not isinstance(name, str) or not name:
                raise ValueError('Context source filenames must be nonempty strings')
            data = (self.path.parent/name).read_bytes()
            self.source_hashes[key] = hashlib.sha256(data).hexdigest()
            files[key] = data.decode('utf-8')
        self.system_prompt = files['system_prompt']
        self.static_world = json.loads(files['world_info'])
        self.few_shot = json.loads(files['few_shot'])
        if not isinstance(self.static_world, dict) or not isinstance(self.few_shot, list):
            raise ValueError('World info must be an object and few-shot examples must be a list')
        for example in self.few_shot:
            if (not isinstance(example, dict) or set(example) != {'input', 'solution'}
                    or not isinstance(example['input'], str) or not example['input'].strip()
                    or not isinstance(example['solution'], str) or not example['solution'].strip()):
                raise ValueError('Each few-shot example needs nonempty input and solution strings')

    def assemble(self, robot, instruction, observation, runtime_info):
        # These values come from the actual loaded simulation, not prompt literals.
        world = dict(self.static_world, table_surface_z_m=float(robot.model.geom('table').pos[2]),
                     tcp_bounds_m={axis: list(bounds) for axis, bounds in zip('xyz', robot.TCP_BOUNDS)},
                     suggested_transport_z_m=robot.config.hover_z_m,
                     objects=[dict(name=s.name, shape=s.shape, full_size_m=s.dimensions())
                              for s in robot.config.object_specs()])
        components = dict(system_prompt=self.system_prompt, world_info=world, observation=observation,
                          runtime_info=runtime_info, few_shot=self.few_shot, user_prompt=instruction)
        turn = {name: components[name] for name in self.order if name != 'few_shot' or self.few_shot}
        messages = [dict(role='system', content=self.system_prompt),
                    dict(role='user', content=model_json(turn))]
        return dict(schema_version=1, order=['system_prompt', *self.order],
                    source_hashes=self.source_hashes, components=components, messages=messages,
                    transport='initial system message; ordered named JSON context blocks in user turn')


def context_source_hashes():
    """Include external context overrides in experiment integrity checks, too."""
    return {'prompt_context/'+key: value for key, value in PromptContext().source_hashes.items()}
