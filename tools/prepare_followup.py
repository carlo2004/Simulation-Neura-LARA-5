"""Prepare a paired prompt study with CPU physics controls, never allocate a VM."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stacklab.cli.benchmark import case_definition
from stacklab.config import Config, write_json
from stacklab.experiments import create_plan, source_hashes, digest
from stacklab.llm.catalog import lock
from stacklab.llm.agent import resolve_prompt_profile
from stacklab.policy import Interpreter
from stacklab.evaluation import evaluate
from stacklab.provenance import software_provenance

REFERENCE = '''a = robot.position("red")
b = robot.position("blue")
robot.gripper(closed=False)
robot.move_to([a[0], a[1], 0.24])
robot.move_to(a)
robot.gripper(closed=True)
robot.move_to([a[0], a[1], 0.24])
robot.move_to([b[0], b[1], 0.24])
robot.move_to([b[0], b[1], b[2] + 0.041])
robot.gripper(closed=False)
robot.move_to([b[0], b[1], 0.24])
robot.step(1)
'''


def prepare(output, *, recipe, server_url=None):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Choose a new empty output directory')
    spec = json.loads(Path(recipe).read_text(encoding='utf-8'))
    if spec.get('schema_version') != 1 or spec.get('blocks') != [1]:
        raise ValueError('Expected a version-1 one-block recipe')
    if spec['prompt_profiles'] not in (['legacy', 'one-shot'], ['one-shot', 'legacy']):
        raise ValueError('Compare each of legacy and one-shot exactly once')
    if not spec['cases'] or any(name not in ('move-right', 'red-on-blue-jitter') for name in spec['cases']):
        raise ValueError('This reference recipe supports move-right and red-on-blue-jitter only')
    for key in ('models', 'cases', 'scene_seeds', 'generation_seeds'):
        values = spec[key]
        if not values or len(set(values)) != len(values):
            raise ValueError('Recipe needs nonempty, distinct '+key)
    for key in ('scene_seeds', 'generation_seeds'):
        if any(type(seed) is not int or not 0 <= seed <= 2**31-1 for seed in spec[key]):
            raise ValueError('Recipe seeds must be integers in the supported range')
    if len(spec['scene_seeds']) != len(spec['generation_seeds']):
        raise ValueError('Scene and generation seeds must be paired')
    for profile in spec['prompt_profiles']:
        resolve_prompt_profile(1, profile)
    for model in spec['models']:
        lock(model)  # Validate names without downloading weights or starting a model.
    definitions = [case_definition(name, seed) for name in spec['cases'] for seed in spec['scene_seeds']]
    if any(c['source'] not in (None, 'red') or c['target'] not in (None, 'blue') for c in definitions):
        raise ValueError('This reference recipe supports movement and red-on-blue only')
    output.mkdir(parents=True, exist_ok=True)
    from stacklab.sim.robot import Simulation
    controls = []
    for case in definitions:
        robot = Simulation(Config(**case['config']), visuals=False)
        try:
            goal = case['goal'].copy()
            if goal['type'] == 'move':
                goal = dict(type='move', target_m=(robot.data.site_xpos[robot.sid]+goal['delta_m']).tolist())
                code = 'robot.jog("x", 0.05)' if case['name'] == 'move-right' else None
                if code is None:
                    raise ValueError('The movement reference supports move-right only')
            else:
                code = REFERENCE
            runner = Interpreter(robot)
            runner.run(code)
            grading = evaluate(robot, goal)
            controls.append(dict(case=case['name'], scene_seed=case['scene_seed'], code=code,
                                 evaluation=grading, actions=runner.actions))
            write_json(output/'controls.json', dict(note='Handwritten CPU controls, not model outcomes',
                        software=software_provenance(), results=controls))
            print('CPU control: '+case['name']+' / '+str(case['scene_seed'])+' / '+str(grading['success']), flush=True)
            if not grading['success']:
                raise ValueError('Physics reference failed; no inference plans were created')
        finally:
            robot.close()
    proposal = dict(status='proposal_only', recipe=spec, software=software_provenance(),
                    source_hashes=source_hashes(), recipe_sha256=digest(spec),
                    controls_passed=len(controls), model_inference_started=False,
                    vm_allocation='none; this tool only reuses an explicitly supplied HTTP server')
    write_json(output/'proposal.json', proposal)
    if server_url:
        options = {k: spec[k] for k in ('models', 'cases', 'scene_seeds', 'generation_seeds', 'blocks',
                    'max_tokens', 'generation_timeout', 'execution_timeout', 'recording', 'motion_fps', 'video', 'gui')}
        for profile in spec['prompt_profiles']:
            plan = create_plan(output/profile, server_url=server_url, paired_seeds=True,
                               prompt_profile=profile, **options)
            print(str(len(plan['episodes']))+' episodes frozen: '+str(output/profile), flush=True)
        proposal['status'] = 'remote_plans_frozen'
        write_json(output/'proposal.json', proposal)
    return proposal


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--recipe', type=Path, default=ROOT/'experiments/one-shot-followup.json')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--server-url', help='Optional existing loopback server; freezes plans but does not run inference')
    args = p.parse_args(argv)
    try:
        proposal = prepare(args.output, recipe=args.recipe, server_url=args.server_url)
        print('Prepared: '+str(args.output.resolve())+' ('+proposal['status']+')')
        return 0
    except (ValueError, OSError, RuntimeError, KeyError) as error:
        print('Preparation failed: '+str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
