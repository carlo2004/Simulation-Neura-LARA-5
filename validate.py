"""Repeatable integration benchmark; exits nonzero on any failed run."""
import contextlib, io, platform, time
from dataclasses import asdict
from pathlib import Path
import mujoco, numpy, scipy
from core import Config, write_json
from simulation import Simulation

def main():
    cases = [('default', Config(), 'red', 'blue')]
    cases += [(f'jitter_{seed}', Config(seed=seed, random_jitter_m=.025),
               'red' if seed%2==0 else 'blue', 'blue' if seed%2==0 else 'red') for seed in range(10)]
    cases += [(f'size_{size}', Config(cube_size_m=size), 'red', 'blue') for size in [.035, .045, .05]]
    results = []
    start = time.time()
    for label, config, source, target in cases:
        sim = None
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                sim = Simulation(config)
                if sim.is_stacked(source, target): raise AssertionError('Unstacked initial scene classified as success')
                result = sim.stack(source, target)
            result.update(label=label, config=asdict(config))
        except Exception as e:
            result = dict(label=label, success=False, error=str(e), config=asdict(config))
        finally:
            if sim: sim.close()
        results.append(result)
        print(label, result['success'], result.get('error', ''), flush=True)
    report = dict(passed=sum(r['success'] for r in results), total=len(results), elapsed_s=time.time()-start,
                  python=platform.python_version(), platform=platform.platform(), mujoco=mujoco.__version__,
                  numpy=numpy.__version__, scipy=scipy.__version__, results=results)
    write_json(Path(__file__).with_name('output')/'validation.json', report)
    return 0 if report['passed']==report['total'] else 1

if __name__ == '__main__': raise SystemExit(main())
