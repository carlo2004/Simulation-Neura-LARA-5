"""Regression for named objects, varied sizes and three-cube support chains."""
from stacklab.paths import ROOT
from stacklab.paths import RUNS_ROOT
import argparse,contextlib,io,time,platform
from dataclasses import replace
from pathlib import Path
import mujoco,numpy,scipy
from stacklab.config import Config,write_json
from stacklab.sim.robot import Simulation

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--images',action='store_true',help='Render mixed scene and final tower')
    args=parser.parse_args()
    (RUNS_ROOT).mkdir(parents=True,exist_ok=True)
    three=Config.load(ROOT/'scenes/three_cubes.json')
    cases=[(f'green_jitter_{seed}',replace(three,seed=seed,random_jitter_m=.02),[('green','blue' if seed%2==0 else 'red')]) for seed in range(4)]
    source_box=[dict(s) for s in three.objects]
    source_box[2].update(shape='box',size_m=[.06,.045,.05])
    cases.append(('box_on_cube',replace(three,objects=source_box),[('green','blue')]))
    target_box=[dict(s) for s in three.objects]
    target_box[1].update(shape='box',size_m=[.06,.055,.045])
    cases.append(('cube_on_box',replace(three,objects=target_box),[('green','blue')]))
    mixed=Config.load(ROOT/'scenes/mixed_objects.json')
    cases.append(('mixed_scene',mixed,[('red','blue')]))
    cases.append(('three_cube_tower',three,[('red','blue'),('green','red')]))
    results=[];start=time.time()
    if args.images:
        from PIL import Image
        sim=Simulation(mixed)
        try:
            renderer=mujoco.Renderer(sim.model,720,960)
            try:
                renderer.update_scene(sim.data,sim.camera)
                Image.fromarray(renderer.render()).save(RUNS_ROOT/'mixed_scene.png')
            finally:renderer.close()
        finally:sim.close()
    for label,config,steps in cases:
        sim=None
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                sim=Simulation(config)
                attempts=[sim.stack(a,b) for a,b in steps]
                # Also verify that all previously built levels remain supported.
                checks=[sim.is_stacked(a,b) for a,b in steps]
                sim.step(2)
                checks += [sim.is_stacked(a,b) for a,b in steps]
            success=all(r['success'] for r in attempts) and all(checks)
            result=dict(label=label,success=success,steps=attempts,final_checks=checks,
                        positions={name:sim.position(name).tolist() for name in sim.object_names},config=config.to_dict())
            if args.images and label=='three_cube_tower':
                from PIL import Image
                renderer=mujoco.Renderer(sim.model,720,960)
                try:
                    renderer.update_scene(sim.data,sim.camera)
                    Image.fromarray(renderer.render()).save(RUNS_ROOT/'three_cube_tower.png')
                finally:renderer.close()
        except Exception as e:result=dict(label=label,success=False,error=str(e),config=config.to_dict())
        finally:
            if sim:sim.close()
        results.append(result);print(label,result['success'],result.get('error',''),flush=True)
    report=dict(passed=sum(r['success'] for r in results),total=len(results),elapsed_s=time.time()-start,
                python=platform.python_version(),mujoco=mujoco.__version__,numpy=numpy.__version__,scipy=scipy.__version__,results=results)
    write_json(RUNS_ROOT/'objects_validation.json',report)
    return 0 if report['passed']==report['total'] else 1

if __name__=='__main__':raise SystemExit(main())
