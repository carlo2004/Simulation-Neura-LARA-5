"""Map Prompt2Robo's scene and Python API onto the shared LARA simulation."""
from __future__ import annotations

import ast
import builtins
import math
import re

import mujoco
import numpy as np

from stacklab.config import COLORS as LAB_COLORS, Config, ObjectSpec, finite_number
from stacklab.sim.robot import Simulation, tool_rotation

FPS = 24
CUBE_SIZE_M = .04
COLORS = {**LAB_COLORS, 'orange': (1, .55, 0, 1), 'white': (.95, .95, .95, 1),
          'black': (.1, .1, .1, 1), 'pink': (1, .5, .7, 1), 'brown': (.5, .3, .1, 1),
          'gray': (.5, .5, .5, 1), 'grey': (.5, .5, .5, 1), 'cyan': (.1, .8, .85, 1)}
METHODS = {'get_object_position', 'get_gripper_position', 'move_to',
           'open_gripper', 'close_gripper', 'rotate_gripper'}
BUILTINS = {name: getattr(builtins, name) for name in (
    'abs', 'min', 'max', 'range', 'len', 'round', 'float', 'int', 'list', 'tuple',
    'dict', 'set', 'enumerate', 'zip', 'sorted', 'sum', 'reversed', 'any', 'all',
    'map', 'filter', 'str', 'bool', 'ValueError', 'Exception', 'isinstance')}


def position(values):
    if not isinstance(values, (list, tuple)) or len(values) != 3 or not all(map(finite_number, values)):
        raise ValueError('Scene positions must contain three finite numbers in metres')
    return values


def angle(value):
    value = float(value)
    if not 0 <= value <= 180:
        raise ValueError('Gripper angle must be in [0, 180] degrees')
    return value


class ReplayScene(Config):
    """A validated snapshot, including touching cubes and existing towers."""

    def __init__(self, scene, *, speed_mm_s=Config.speed_mm_s, fps=FPS):
        super().__init__(fps=fps, cube_size_m=CUBE_SIZE_M, speed_mm_s=speed_mm_s)
        objects = scene['objects']
        if not 1 <= len(objects) <= 12:
            raise ValueError('Expected a scene with 1–12 cubes')
        self.names = {}
        self.positions = {}
        self.objects = []
        for oid, obj in objects.items():
            if not isinstance(oid, str) or not re.fullmatch(r'[1-9][0-9]{0,8}', oid):
                raise ValueError(f'Invalid cube ID {oid!r}')
            xyz = position(obj['position'])
            if abs(xyz[0]) > .98 or abs(xyz[1]) > .98 or not .02 <= xyz[2] <= .8:
                raise ValueError(f'Cube {oid} starts outside the table scene')
            name = 'cube_' + oid
            self.names[oid] = name
            self.positions[name] = list(xyz)
            self.objects.append(ObjectSpec(name, xy_m=tuple(xyz[:2]), size_m=CUBE_SIZE_M,
                                           color=COLORS[obj['color']]).to_dict())

    def validate(self):
        # Config's interactive spawn rules require separated objects on the table.
        # This snapshot has already been checked and must preserve all three axes.
        return self

    def scene(self):
        return self.positions


class LaraReplay:
    """Dataset API, backed by the same actuators and contacts as the live UI."""

    def __init__(self, sim, scene):
        self.sim = sim
        self.data = sim.data
        self.scene = scene
        self.names = sim.config.names
        self.body = {oid: sim.model.body('obj_' + name).id for oid, name in self.names.items()}

        gripper = scene['gripper']
        self.yaw_deg = angle(gripper['angle_deg'])
        if type(gripper['is_open']) is not bool:
            raise ValueError('Gripper is_open must be a boolean')
        xyz = sim.validate_tcp(position(gripper['position']))
        seed = sim.command.copy()
        seed[5] -= math.radians(self.yaw_deg)
        sim.command = sim.ik(xyz, start=seed, rotation=tool_rotation(yaw_deg=self.yaw_deg).as_matrix())

        # Initialize a fresh episode, before recording or running the program.
        mujoco.mj_resetData(sim.model, sim.data)
        sim.frames = 0
        sim.data.qpos[:6] = sim.data.ctrl[:6] = sim.command
        sim.data.qpos[6:8] = sim.data.ctrl[6:] = .032 if gripper['is_open'] else 0.
        mujoco.mj_forward(sim.model, sim.data)
        self.start_positions = {oid: self.get_object_position(oid) for oid in self.names}
        sim.step(.5)
        if np.linalg.norm(self.get_gripper_position() - xyz) > .003:
            raise RuntimeError(f'Initial TCP did not settle at {xyz.tolist()}')
        for oid, start in self.start_positions.items():
            if np.linalg.norm(self.get_object_position(oid) - start) > .003:
                raise RuntimeError(f'Initial cube {oid} moved by more than 3 mm while settling')

    def get_object_position(self, id):
        key = str(id)
        if key not in self.names:
            raise ValueError(f'Unknown object ID {id!r}')
        return self.sim.position(self.names[key])

    def get_gripper_position(self):
        return self.data.site_xpos[self.sim.sid].copy()

    def _move(self, xyz, yaw_deg):
        try:
            self.sim.move_to(xyz, yaw_deg=yaw_deg)
        except (ValueError, RuntimeError) as error:
            raise ValueError(f'LARA 5 TCP {list(xyz)} at {yaw_deg:g}°: {error}') from error
        self.yaw_deg = yaw_deg
        if np.linalg.norm(self.get_gripper_position() - xyz) > .003:
            raise RuntimeError(f'LARA 5 TCP did not reach {list(xyz)}')

    def move_to(self, x, y, z):
        self._move([float(x), float(y), float(z)], self.yaw_deg)

    def open_gripper(self):
        self.sim.gripper(False)

    def close_gripper(self):
        self.sim.gripper(True)

    def rotate_gripper(self, angle_deg):
        self._move(self.get_gripper_position().tolist(), angle(angle_deg))

    def held_objects(self):
        return {oid for oid, name in self.names.items() if self.sim.grasped(name)}

    def state(self):
        finger_axis = self.data.site_xmat[self.sim.sid].reshape(3, 3)[:, 1]
        measured = math.degrees(math.atan2(finger_axis[0], -finger_axis[1]))
        delta = (measured - self.yaw_deg + 180) % 360 - 180
        return {
            'objects': {oid: {'color': self.scene['objects'][oid]['color'],
                              'position': self.get_object_position(oid).round(4).tolist()} for oid in self.names},
            'gripper': {'position': self.get_gripper_position().round(4).tolist(),
                        'angle_deg': round(self.yaw_deg + delta, 2),
                        'is_open': bool(self.data.ctrl[6] >= .016)},
        }


def run_reference(code, robot):
    """Run a checksum-verified dataset program in the dedicated replay worker."""
    tree = ast.parse(code)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef) or tree.body[0].name != 'run':
        raise ValueError('Expected one Python function def run(robot)')
    function = tree.body[0]
    args = function.args
    if ([arg.arg for arg in args.args] != ['robot'] or args.posonlyargs or args.kwonlyargs
            or args.vararg or args.kwarg or args.defaults or function.decorator_list):
        raise ValueError('Expected one Python function def run(robot)')
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal)):
            raise ValueError('Imports and global statements are unavailable in replay')
        if isinstance(node, ast.Attribute):
            if node.attr.startswith('_'):
                raise ValueError('Private attributes are unavailable in replay')
            if isinstance(node.value, ast.Name) and node.value.id == 'robot' and node.attr not in METHODS:
                raise ValueError(f'Unknown robot method {node.attr!r}')
        if isinstance(node, ast.Name) and node.id.startswith('__'):
            raise ValueError('Dunder names are unavailable in replay')
    namespace = {'__builtins__': BUILTINS, 'np': np, 'math': math}
    exec(compile(tree, '<dataset reference>', 'exec'), namespace)
    namespace['run'](robot)
