"""Scene descriptions in SI units, validation, and deterministic start positions."""
from dataclasses import dataclass, asdict
import json, math, random, re
from pathlib import Path

COLORS = {'red': (.90, .19, .16, 1), 'blue': (.12, .43, .90, 1),
          'green': (.15, .72, .34, 1), 'yellow': (.95, .73, .12, 1),
          'duck': (.98, .72, .12, 1)}
from stacklab.paths import ROOT

def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)

@dataclass
class ObjectSpec:
    name: str
    shape: str = 'cube'
    xy_m: tuple = (.4, 0)
    size_m: object = .04
    mass_kg: float = .06
    color: object = None
    mesh_file: object = None

    def dimensions(self):
        if self.shape in ('cube', 'sphere'):
            return (self.size_m,)*3
        if self.shape in ('box', 'mesh'):
            return tuple(self.size_m)
        if self.shape == 'cylinder':
            diameter, height = self.size_m
            return diameter, diameter, height
        raise ValueError('shape must be cube, box, sphere, cylinder or mesh')

    def mesh_path(self):
        if not isinstance(self.mesh_file, str):
            raise ValueError('A mesh needs a prepared mesh_file; use add-mesh')
        relative = self.mesh_file
        if relative.startswith('models/objects/'):
            relative = 'assets/objects/'+relative[len('models/objects/'):]
        path = (ROOT/relative).resolve()
        if not path.is_relative_to((ROOT/'assets/objects').resolve()) or path.suffix != '.obj':
            raise ValueError('mesh_file must be an OBJ inside assets/objects; use add-mesh')
        if not path.is_file() or not path.with_name(path.stem+'_hull.obj').is_file():
            raise ValueError('Prepared mesh or collision hull missing; keep assets/objects with the scene')
        return path

    def rgba(self):
        return self.color if self.color is not None else COLORS.get(self.name, (.65, .67, .71, 1))

    def validate(self):
        if not isinstance(self.name, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', self.name) or self.name in ('tcp', 'phase', 'time_s', 'objects'):
            raise ValueError('Object name: lowercase letters/digits/underscores, unique; tcp is reserved')
        if self.shape not in ('cube', 'box', 'sphere', 'cylinder', 'mesh'):
            raise ValueError('shape must be cube, box, sphere, cylinder or mesh')
        if self.shape in ('cube', 'sphere'):
            if not finite_number(self.size_m): raise ValueError('cube/sphere size_m must be a number')
        else:
            count = 3 if self.shape in ('box', 'mesh') else 2
            if not isinstance(self.size_m, (list, tuple)) or len(self.size_m) != count or not all(finite_number(v) for v in self.size_m):
                raise ValueError('box size_m is [x,y,z]; cylinder size_m is [diameter,height]')
        lower = .005 if self.shape == 'mesh' else .02
        if not all(lower <= v <= .12 for v in self.dimensions()):
            raise ValueError('Object dimensions must be 0.02–0.12 m')
        if self.shape == 'mesh':
            self.mesh_path()
        elif self.mesh_file is not None:
            raise ValueError('mesh_file only applies to mesh objects')
        if not isinstance(self.xy_m, (list, tuple)) or len(self.xy_m) != 2 or not all(finite_number(v) for v in self.xy_m):
            raise ValueError('xy_m must contain two finite numbers')
        if not .25 <= self.xy_m[0] <= .55 or not -.25 <= self.xy_m[1] <= .25:
            raise ValueError('Scene bounds: x .25–.55, y ±.25 m')
        if not finite_number(self.mass_kg) or not .005 <= self.mass_kg <= .5:
            raise ValueError('Object mass_kg must be 0.005–0.5')
        color = self.rgba()
        if not isinstance(color, (list, tuple)) or len(color) != 4 or not all(finite_number(v) and 0 <= v <= 1 for v in color):
            raise ValueError('color must contain four RGBA values between 0 and 1')
        return self

    def to_dict(self):
        return asdict(self)

@dataclass
class Config:
    seed: int = 42
    cube_size_m: float = .04
    red_xy_m: tuple = (.40, -.12)
    blue_xy_m: tuple = (.40, .12)
    hover_z_m: float = .24
    speed_mm_s: float = 80
    fps: int = 30
    random_jitter_m: float = 0
    objects: object = None

    def object_specs(self):
        if self.objects is None:
            return [ObjectSpec('red', xy_m=self.red_xy_m, size_m=self.cube_size_m),
                    ObjectSpec('blue', xy_m=self.blue_xy_m, size_m=self.cube_size_m)]
        try:
            return [ObjectSpec(**item) for item in self.objects]
        except TypeError as e:
            raise ValueError('Invalid object description: '+str(e)) from None

    def validate(self):
        for value in (self.cube_size_m, self.hover_z_m, self.speed_mm_s, self.fps, self.random_jitter_m):
            if not finite_number(value): raise ValueError('Numeric parameters must be finite numbers')
        if type(self.seed) is not int: raise ValueError('seed must be an integer')
        if not .035 <= self.cube_size_m <= .05: raise ValueError('Legacy cube_size_m must be 0.035–0.05')
        if not 0 <= self.random_jitter_m <= .03: raise ValueError('random_jitter_m must be 0–0.03')
        if not 10 <= self.speed_mm_s <= 120: raise ValueError('speed_mm_s must be 10–120')
        if type(self.fps) is not int or not 10 <= self.fps <= 60: raise ValueError('fps must be integer 10–60')
        if not .12 < self.hover_z_m <= .4: raise ValueError('hover_z_m must be above 0.12 and at most 0.4 m')
        if self.objects is None:
            if not self.hover_z_m > 3*self.cube_size_m: raise ValueError('hover_z_m too low')
        elif not isinstance(self.objects, list) or not 1 <= len(self.objects) <= 12 or not all(isinstance(o, dict) for o in self.objects):
            raise ValueError('objects must be a list of 1–12 object descriptions')
        specs = [s.validate() for s in self.object_specs()]
        if len({s.name for s in specs}) != len(specs): raise ValueError('Object names must be unique')
        for i, a in enumerate(specs):
            for b in specs[i+1:]:
                # Conservative axis-aligned footprint clearance, including all jitter.
                clear = [(a.dimensions()[k]+b.dimensions()[k])/2 + 2*self.random_jitter_m + .025 for k in (0, 1)]
                if all(abs(a.xy_m[k]-b.xy_m[k]) < clear[k] for k in (0, 1)):
                    raise ValueError(f'Insufficient starting clearance: {a.name} / {b.name}')
        return self

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data, dict): raise ValueError('Scene must be a JSON object')
        try:
            return cls(**data).validate()
        except TypeError as e:
            raise ValueError('Invalid scene fields: '+str(e)) from None

    def scene(self):
        self.validate()
        rng = random.Random(self.seed)
        return {s.name: [s.xy_m[0]+rng.uniform(-self.random_jitter_m, self.random_jitter_m),
                         s.xy_m[1]+rng.uniform(-self.random_jitter_m, self.random_jitter_m),
                         s.dimensions()[2]/2] for s in self.object_specs()}

    def to_dict(self):
        return asdict(self)

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8')
    tmp.replace(path)
