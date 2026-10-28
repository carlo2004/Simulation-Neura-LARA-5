"""Run the LARA 5 stacking demo. See README.md for setup."""
from stacklab.paths import RUNS_ROOT
from stacklab.paths import ROOT
import argparse, os, sys
from pathlib import Path

def main(argv=None):
    p = argparse.ArgumentParser(description='NEURA LARA 5 contact-physics cube stacking')
    p.add_argument('--gui', action='store_true', help='Open the interactive MuJoCo viewer')
    p.add_argument('--show-settings', action='store_true', help='Start with MuJoCo settings visible (Tab / Shift+Tab toggle panels)')
    p.add_argument('--axes', action='store_true', help='Show world axes and coordinates')
    p.add_argument('--stackviz', nargs=2, metavar=('SOURCE', 'TARGET'), help='Show the optional stack-check overlay')
    p.add_argument('--video', action='store_true', help='Save runs/demo.mp4 and final.png')
    p.add_argument('--config', type=Path, default=ROOT/'scenes/default.json')
    p.add_argument('--reverse', action='store_true', help='Stack blue on red')
    p.add_argument('--source', default='red', help='Object to pick')
    p.add_argument('--target', default='blue', help='Object to stack onto')
    p.add_argument('--output', type=Path, default=RUNS_ROOT)
    a = p.parse_args(argv)
    if not a.gui and 'DISPLAY' not in os.environ and sys.platform == 'linux':
        os.environ.setdefault('MUJOCO_GL', 'egl')
    from stacklab.config import Config, write_json
    from stacklab.sim.robot import Simulation
    a.output.mkdir(parents=True, exist_ok=True)
    sim = None
    try:
        sim = Simulation(Config.load(a.config), a.output/'demo.mp4' if a.video else None,
                         a.gui, show_settings=a.show_settings, axes=a.axes, stackviz=a.stackviz)
        result = sim.stack('blue', 'red') if a.reverse else sim.stack(a.source, a.target)
        write_json(a.output/'result.json', result)
        if a.video:
            from PIL import Image
            Image.fromarray(sim.last_frame).save(a.output/'final.png')
        print('SUCCESS: stable physical stack' if result['success'] else 'FAIL: stack criteria not met')
        if a.gui:
            print('Close the viewer to exit. Mouse: rotate and zoom. Tab / Shift+Tab: settings panels.')
            while sim.viewer.is_running(): sim.step(.02)
        return 0 if result['success'] else 1
    except KeyboardInterrupt:
        print('Simulation stopped by user.')
        return 130
    except Exception as e:
        write_json(a.output/'result.json', dict(success=False, error=str(e), events=sim.events if sim else []))
        raise
    finally:
        if sim: sim.close()

if __name__ == '__main__': raise SystemExit(main())
