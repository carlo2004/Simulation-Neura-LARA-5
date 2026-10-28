"""Interactive terminal control of the LARA simulation. No eval/exec or LLM needed."""
from stacklab.paths import ROOT
import argparse
import math
from dataclasses import replace
from stacklab.config import Config, ObjectSpec, write_json
import queue
import shlex
import sys
import threading
import time
from pathlib import Path

HELP = '''Commands (metres / seconds):
  status / objects          Show object names, shapes, positions and TCP
  pos NAME|tcp              Show one position
  joints                    Show six arm angles in degrees
  move X Y Z                Move the tool; fixed downward orientation
  jog x|y|z DELTA            Move relative to the current tool position
  manual on [STEP]|off      Opt-in 3D-window keyboard jogging; default step 0.005 m
  goto-selected [Z]         Hover over a point selected by left double-click
  push NAME DX DY           Push a tabletop object through real finger contact
  axes on|off               Toggle world axes, 10 cm grid and coordinates
  stackviz SOURCE TARGET    Show frames and the check criteria for this pair
  stackviz off              Hide the stack-check overlay
  open / close              Open / close the gripper
  wait SECONDS              Let physics advance (0 to 60 seconds)
  stack SOURCE TARGET       Stack named cubes/boxes (e.g. green blue)
  check SOURCE TARGET       Check a stable stack over 2 seconds
  place NAME X Y            Change a start position; reset the whole scene
  add NAME cube X Y SIDE    Add a cube; reset the whole scene
  add NAME box X Y SX SY SZ Add a box with full side lengths
  add NAME sphere X Y D     Add a sphere with diameter D
  add NAME cylinder X Y D H Add a cylinder with diameter D and height H
  add-mesh NAME FILE X Y SIZE [MASS]  Import OBJ/STL/PLY/GLB; SIZE = longest side
  remove NAME               Remove an object; reset the whole scene
  randomize SEED [JITTER]   Random starts; reset the scene (default +/-0.02 m)
  save-scene PATH           Save the current start configuration as JSON
  load-scene PATH           Load a configuration; reset the whole scene
  reset                     Restore the configured starts
  help / quit               Show commands / exit
Example: add green cube 0.50 0.00 0.04
Scene edits reset every object and the arm. Use stack for physical movement.
Coordinates: world metres, origin at the base centre on the table (z=0).
Object positions are centres; move/jog command the TCP. Overlays start hidden.
Viewer: focus the 3D window, then Tab / Shift+Tab toggle left / right settings.
'''

class CommandError(ValueError):
    pass

def number(token):
    try:
        result = float(token)
    except ValueError:
        raise CommandError(f'Expected a number: {token}') from None
    if not math.isfinite(result):
        raise CommandError('Numbers must be finite')
    return result

def format_position(value):
    return '['+', '.join(f'{float(x):.4f}' for x in value)+'] m'

class Controller:
    def __init__(self, robot, output=print):
        self.robot = robot
        self.output = output

    def _pair(self, args):
        if len(args) != 2 or args[0] == args[1] or any(n not in self.robot.object_names for n in args):
            raise CommandError('Choose two different objects: '+', '.join(self.robot.object_names))
        return args

    def _rebuild(self, config):
        from stacklab.sim.robot import Simulation
        config.validate()
        if self.robot.writer:
            raise CommandError('Scene edits are unavailable during video recording')
        # Keep the launch preference when a scene edit rebuilds the viewer.
        pair = self.robot.overlays.stack_pair
        specs = {s.name: s for s in config.object_specs()}
        if pair and any(n not in specs or specs[n].shape not in ('cube', 'box') for n in pair):
            pair = None
        # Keep visibility, but discard any check of the old physical scene.
        new_robot = Simulation(config, show_settings=self.robot.show_settings,
                               axes=self.robot.overlays.axes, stackviz=pair)
        had_viewer = self.robot.viewer is not None
        self.robot.close()
        self.robot = new_robot
        if had_viewer:
            new_robot.open_viewer()
        self.output('Scene rebuilt; arm and all objects reset to configured starts')

    def _spec_dicts(self):
        return [spec.to_dict() for spec in self.robot.config.object_specs()]

    def execute(self, line):
        # Terminal commands take priority. Never replay keys typed during a stack
        # or another blocking command afterwards.
        manual = self.robot.manual
        if manual.enabled:
            manual.stop(self.robot)
        manual.suspended = True
        try:
            return self._execute(line)
        finally:
            manual.suspended = False
            if self.robot.manual.enabled:
                self.robot.manual.anchor(self.robot)

    def idle(self, seconds=.02):
        self.robot.manual.tick(self.robot, seconds)
        self.robot.step(seconds)

    def _execute(self, line):
        """Execute one known command; False means quit. Errors leave the console open."""
        try:
            parts = shlex.split(line, comments=True)
        except ValueError as e:
            raise CommandError(str(e)) from None
        if not parts:
            return True
        command, *args = parts
        robot = self.robot
        if command in ('quit', 'exit') and not args:
            return False
        if command == 'help' and not args:
            self.output(HELP)
        elif command in ('status', 'objects') and not args:
            self.output(f'Simulation: {robot.data.time:.2f} s')
            self.output('tcp  '+format_position(robot.data.site_xpos[robot.sid]))
            for name in robot.object_names:
                self.output(name+' ('+robot.objects[name].shape+') '+format_position(robot.position(name)))
        elif command == 'pos' and len(args) == 1 and args[0] in (*robot.object_names, 'tcp'):
            value = robot.data.site_xpos[robot.sid] if args[0] == 'tcp' else robot.position(args[0])
            self.output(args[0]+' '+format_position(value))
        elif command == 'joints' and not args:
            self.output('Arm angles: ['+', '.join(f'{math.degrees(float(q)):.2f}' for q in robot.data.qpos[:6])+'] deg')
        elif command == 'move' and len(args) == 3:
            robot.move_to([number(x) for x in args])
            self.output('tcp '+format_position(robot.data.site_xpos[robot.sid]))
        elif command == 'jog' and len(args) == 2 and args[0] in ('x', 'y', 'z'):
            target = robot.data.site_xpos[robot.sid].copy()
            target['xyz'.index(args[0])] += number(args[1])
            robot.move_to(target)
            self.output('tcp '+format_position(robot.data.site_xpos[robot.sid]))
        elif command == 'manual' and args == ['off']:
            robot.manual.stop(robot, disable=True)
            robot.refresh_view()
            self.output('Manual control off')
        elif command == 'manual' and len(args) in (1, 2) and args[0] == 'on':
            if robot.viewer is None:
                raise CommandError('Keyboard control needs the 3D viewer; run python -m stacklab console without --headless')
            robot.manual.enable(robot, number(args[1]) if len(args) == 2 else None)
            robot.refresh_view()
            self.output(robot.manual.panel())
        elif command == 'goto-selected' and len(args) <= 1:
            point = robot.goto_selected(number(args[0]) if args else None)
            self.output('Selected surface point '+format_position(point))
            self.output('tcp '+format_position(robot.data.site_xpos[robot.sid]))
        elif command == 'push' and len(args) == 3:
            result = robot.push(args[0], number(args[1]), number(args[2]))
            displacement = result['displacement_m']
            self.output(f'Push finished: finger contact={result["finger_contact_seen"]}; '
                        f'object moved {displacement[0]:.4f}, {displacement[1]:.4f}, {displacement[2]:.4f} m')
        elif command == 'axes' and len(args) == 1 and args[0] in ('on', 'off'):
            robot.overlays.axes = args[0] == 'on'
            robot.refresh_view()
            self.output('World axes / coordinates '+args[0])
        elif command == 'stackviz' and args == ['off']:
            robot.set_stackviz()
            robot.refresh_view()
            self.output('Stack visualisation off')
        elif command == 'stackviz' and len(args) == 2:
            robot.set_stackviz(*self._pair(args))
            robot.refresh_view()
            self.output(f'Stack visualisation: {args[0]} on {args[1]}; check to run 20 samples')
        elif command in ('open', 'close') and not args:
            robot.gripper(closed=command == 'close')
            self.output('Gripper '+('opened' if command == 'open' else 'closed'))
        elif command == 'wait' and len(args) == 1:
            seconds = number(args[0])
            if not 0 <= seconds <= 60:
                raise CommandError('wait must be between 0 and 60 seconds')
            robot.step(seconds)
            self.output(f'Simulation: {robot.data.time:.2f} s')
        elif command == 'stack':
            source, target = self._pair(args)
            result = robot.stack(source, target)
            if not result['success']:
                raise CommandError('Stack did not meet stability criteria; use reset to start again')
            self.output(f'SUCCESS: {source} on {target}, {result["stable_checks"]}/{result["checks"]} stability checks')
        elif command == 'check':
            source, target = self._pair(args)
            checks = robot.check_stack(source, target)
            if not all(checks):
                raise CommandError(f'Not a stable stack: {sum(checks)}/20 checks')
            self.output(f'SUCCESS: {source} on {target}, 20/20 stability checks')
        elif command == 'place' and len(args) == 3:
            name, x, y = args
            if name not in robot.object_names:
                raise CommandError('Unknown object: '+name)
            specs = self._spec_dicts()
            for spec in specs:
                if spec['name'] == name:
                    spec['xy_m'] = [number(x), number(y)]
            self._rebuild(replace(robot.config, objects=specs, random_jitter_m=0))
        elif command == 'add' and len(args) >= 5:
            name, shape, x, y, *sizes = args
            count = {'cube': 1, 'box': 3, 'sphere': 1, 'cylinder': 2}.get(shape)
            if count is None or len(sizes) != count:
                raise CommandError('Size: cube=side, box=x y z, sphere=diameter, cylinder=diameter height')
            dims = [number(v) for v in sizes]
            spec = ObjectSpec(name, shape=shape, xy_m=[number(x), number(y)], size_m=dims[0] if count == 1 else dims).validate()
            self._rebuild(replace(robot.config, objects=self._spec_dicts()+[spec.to_dict()]))
        elif command == 'add-mesh' and len(args) in (5, 6):
            name, filename, x, y, size, *mass = args
            if name in robot.object_names:
                raise CommandError('Object name already exists: '+name)
            from stacklab.sim.meshes import prepare_mesh
            spec = prepare_mesh(name, filename, [number(x), number(y)], number(size),
                                number(mass[0]) if mass else .06)
            self._rebuild(replace(robot.config, objects=self._spec_dicts()+[spec.to_dict()]))
            self.output('Mesh imported: solid colour; convex-hull collision, including filled cavities')
        elif command == 'remove' and len(args) == 1:
            if args[0] not in robot.object_names:
                raise CommandError('Unknown object: '+args[0])
            self._rebuild(replace(robot.config, objects=[s for s in self._spec_dicts() if s['name'] != args[0]]))
        elif command == 'randomize' and len(args) in (1, 2):
            try:
                seed = int(args[0])
            except ValueError:
                raise CommandError('Seed must be an integer') from None
            jitter = number(args[1]) if len(args) == 2 else (robot.config.random_jitter_m or .02)
            self._rebuild(replace(robot.config, seed=seed, random_jitter_m=jitter))
        elif command == 'save-scene' and len(args) == 1:
            write_json(Path(args[0]), robot.config.to_dict())
            self.output('Saved starting configuration: '+args[0])
        elif command == 'load-scene' and len(args) == 1:
            self._rebuild(Config.load(Path(args[0])))
        elif command == 'reset' and not args:
            robot.reset()
            self.output('Scene reset')
        else:
            raise CommandError('Unknown command or incorrect arguments. Type help.')
        return True

def run_batch(controller, path):
    """Run a text command file. A failed command stops the file with exit code 1."""
    for line_number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        print('lara> '+line, flush=True)
        try:
            if not controller.execute(line):
                return 0
        except (ValueError, RuntimeError, OSError) as e:
            print(f'{path.name}:{line_number}: {e}', file=sys.stderr, flush=True)
            return 1
    return 0

def run_interactive(controller):
    # Only the main thread touches MuJoCo. The input thread reads the terminal.
    pending = queue.Queue(maxsize=1)
    acknowledged = threading.Event()
    stopped = threading.Event()

    def read_input():
        while not stopped.is_set():
            try:
                line = input('lara> ')
            except EOFError:
                line = 'quit'
            acknowledged.clear()
            pending.put(line)
            acknowledged.wait()

    threading.Thread(target=read_input, daemon=True).start()
    try:
        while True:
            robot = controller.robot
            started = time.monotonic()
            if robot.viewer and not robot.viewer.is_running():
                return 0
            try:
                line = pending.get_nowait()
            except queue.Empty:
                # Keep physics and the 3D view alive while waiting for a command.
                controller.idle(.02)
                time.sleep(max(0., .02-(time.monotonic()-started)))
                continue
            try:
                if not controller.execute(line):
                    return 0
            except (ValueError, RuntimeError, OSError) as e:
                print('Error: '+str(e), flush=True)
            finally:
                # Do not show another prompt until the previous command finishes.
                if line.split('#', 1)[0].strip() in ('quit', 'exit'):
                    stopped.set()
                acknowledged.set()
    finally:
        stopped.set()
        acknowledged.set()

def main(argv=None):
    parser = argparse.ArgumentParser(description='Control the simulated LARA 5 from a terminal')
    parser.add_argument('--headless', action='store_true', help='Run without the 3D viewer')
    parser.add_argument('--show-settings', action='store_true', help='Start with MuJoCo settings visible (Tab / Shift+Tab toggle panels)')
    parser.add_argument('--axes', action='store_true', help='Start with world axes and coordinates visible')
    parser.add_argument('--manual', action='store_true', help='Start with optional keyboard control (3D window only)')
    parser.add_argument('--stackviz', nargs=2, metavar=('SOURCE', 'TARGET'), help='Start with the optional stack-check overlay')
    parser.add_argument('--commands', type=Path, help='Run a plain text command file, then exit')
    parser.add_argument('--config', type=Path, default=ROOT/'scenes/default.json')
    args = parser.parse_args(argv)
    robot = None
    controller = None
    try:
        # Check inputs before opening the viewer.
        if args.commands and not args.commands.is_file():
            raise ValueError(f'Command file not found: {args.commands}')
        if args.manual and (args.headless or args.commands):
            raise ValueError('--manual needs the interactive 3D viewer (without --headless/--commands)')
        from stacklab.config import Config
        from stacklab.sim.robot import Simulation
        robot = Simulation(Config.load(args.config), gui=not args.headless, show_settings=args.show_settings,
                           axes=args.axes, stackviz=args.stackviz)
        controller = Controller(robot)
        if args.manual:
            controller.execute('manual on')
        if args.commands:
            return run_batch(controller, args.commands)
        print('LARA 5 simulation console. Type help for commands. Coordinates are metres.', flush=True)
        print('Physics keeps running while you type. Use reset for a fresh scene.', flush=True)
        if not args.headless:
            print('3D window: Tab toggles left settings; Shift+Tab toggles right settings.', flush=True)
        return run_interactive(controller)
    except KeyboardInterrupt:
        print('\nSimulation stopped.')
        return 130
    except (ValueError, RuntimeError, OSError) as e:
        print('Error: '+str(e), file=sys.stderr)
        return 1
    finally:
        if controller:
            controller.robot.close()
        elif robot:
            robot.close()

if __name__ == '__main__':
    raise SystemExit(main())
