"""Feedback loop shared by the live console and independently graded experiments."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading
import time
from stacklab.config import write_json
from stacklab.llm.catalog import ROOT
from stacklab.llm.runtime import GenerationCancelled
from stacklab.evaluation import evaluate, observe, physics_state
from stacklab.policy import Interpreter, PolicyCancelled, validate

PROTOCOL = '''Return a JSON object with "code" (Python string), "done" (boolean),
and "message" (short explanation for the user). No Markdown around the JSON.
Break long tasks into blocks if needed. Each block gets fresh local variables;
only the physical world persists. Read the execution feedback before continuing.
Set done=true only when your requested task is complete; an empty code string is
allowed to finish without another action. A done claim is not a physical grade.
After actions, you receive feedback before finishing. Confirm completion with an
empty code string and done=true if the observations show the task is complete.
Never repeat an already completed displacement just because feedback is returned.
If an action failed, inspect current observations and correct the program.
'''


def system_prompt():
    text = (ROOT/'config/prompts/robot_api.md').read_text(encoding='utf-8')
    old = 'Return a JSON object with exactly one key, "code", whose string is the program.'
    if old not in text:
        raise ValueError('API reply-format marker missing')
    return text.replace(old, PROTOCOL)


def parse_reply(raw):
    decoder = json.JSONDecoder()
    for i, char in enumerate(raw):
        if char != '{':
            continue
        try:
            value, _ = decoder.raw_decode(raw[i:])
        except json.JSONDecodeError:
            continue
        if (isinstance(value, dict) and 'code' in value and set(value) <= {'code', 'done', 'message'}
                and isinstance(value['code'], str) and type(value.get('done', False)) is bool
                and isinstance(value.get('message', ''), str) and len(value.get('message', '')) <= 2000):
            return dict(code=value['code'], done=value.get('done', False), message=value.get('message', ''))
    raise ValueError('Expected JSON with code:string, done:boolean and optional message:string')


def model_json(value):
    # Micrometre precision is ample for a millimetre-scale task. Keep full precision
    # in the physics logs, but avoid long floating-point tails in model messages.
    def compact(item):
        if isinstance(item, float):
            return round(item, 6)
        if isinstance(item, dict):
            return {key: compact(v) for key, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [compact(v) for v in item]
        return item
    return json.dumps(compact(value), ensure_ascii=False)


def hold(robot):
    # Hold the measured joints through the existing actuators; do not move objects.
    robot.command = robot.data.qpos[:6].copy()
    robot.data.ctrl[:6] = robot.command
    robot.data.ctrl[6:8] = robot.data.qpos[6:8]


class Agent:
    def __init__(self, robot, client, *, max_rounds=4, max_tokens=2048, thinking=None, seed=42,
                 generation_timeout=600, execution_timeout=120, on_event=None, tick=None, thinking_budget=None):
        self.robot, self.client = robot, client
        self.max_rounds, self.max_tokens, self.thinking = max_rounds, max_tokens, thinking
        self.seed = seed
        self.thinking_budget = thinking_budget
        self.generation_timeout, self.execution_timeout = generation_timeout, execution_timeout
        self.on_event = on_event or (lambda kind, data: None)
        self.tick = tick or self.idle
        self.cancelled = threading.Event()
        self.generating = threading.Event()
        self.recent_tasks = []

    def idle(self):
        started = time.monotonic()
        if self.robot.viewer and not self.robot.viewer.is_running():
            self.stop()
        if self.generating.is_set():
            self.robot.refresh_view()
        else:
            self.robot.step(.02)
        time.sleep(max(0., .02-(time.monotonic()-started)))

    def stop(self):
        self.cancelled.set()
        self.client.cancel()

    def check_stop(self):
        if self.cancelled.is_set():
            raise PolicyCancelled('Task cancelled')
        if self.robot.viewer and not self.robot.viewer.is_running():
            self.stop()
            raise PolicyCancelled('Viewer closed')

    def generate(self, messages, directory, seed):
        self.generating.set()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.client.complete, messages, directory, max_tokens=self.max_tokens,
                                     seed=seed, thinking=self.thinking, timeout=self.generation_timeout,
                                     thinking_budget=self.thinking_budget,
                                     cancelled=self.cancelled.is_set,
                                     on_delta=lambda kind, text: self.on_event('token', dict(kind=kind, text=text)))
                try:
                    while not future.done():
                        self.tick()  # MuJoCo and the viewer remain on the main thread.
                        if self.cancelled.is_set():
                            self.client.cancel()
                    return future.result()
                except BaseException:
                    self.stop()
                    raise
        finally:
            self.generating.clear()

    def run_task(self, instruction, directory, goal=None):
        if not instruction.strip() or len(instruction) > 4000:
            raise ValueError('Instruction must contain 1–4000 characters')
        if not 1 <= self.max_rounds <= 6:
            raise ValueError('Choose 1–6 feedback rounds')
        if 'tcp' in self.robot.object_names:
            raise ValueError('The LLM API reserves the object name tcp for the tool centre')
        directory = Path(directory).resolve()
        if directory.exists() and any(directory.iterdir()):
            raise ValueError('Choose a new output directory to preserve previous evidence')
        directory.mkdir(parents=True, exist_ok=True)
        self.cancelled.clear()
        write_json(directory/'scene.json', self.robot.config.to_dict())
        write_json(directory/'initial_physics.json', physics_state(self.robot))
        initial = observe(self.robot)
        request = dict(instruction=instruction, observation=initial, units='world metres',
                       recent_tasks=self.recent_tasks[-3:], program_block_budget=self.max_rounds)
        first = dict(role='user', content=model_json(request))
        system = dict(role='system', content=system_prompt())
        history = []
        report = dict(instruction=instruction, goal=goal, success=False if goal else None,
                      status='budget_exhausted', mode='closed_loop_feedback', max_rounds=self.max_rounds,
                      physics_during_inference='paused; viewer remains responsive',
                      model_observation_decimal_places=6,
                      model=self.client.config, initial_observation=initial, rounds=[])
        write_json(directory/'task.json', report)
        started = time.monotonic()
        with (directory/'trajectory.jsonl').open('w', encoding='utf-8') as trajectory:
            def record(kind, data):
                trajectory.write(json.dumps(dict(event=kind, data=data), ensure_ascii=False)+'\n')
                trajectory.flush()

            try:
                for index in range(1, self.max_rounds+1):
                    if self.cancelled.is_set():
                        raise PolicyCancelled('Task cancelled')
                    path = directory/f'round_{index:02d}'
                    self.on_event('generating', dict(round=index, maximum=self.max_rounds))
                    # Retain the task plus the latest two feedback exchanges, not unbounded chat.
                    messages = [system, first, *history[-4:]]
                    item = dict(round=index, stage='generation', actions=[])
                    report['rounds'].append(item)
                    raw, metadata = self.generate(messages, path, self.seed+index-1)
                    item['generation'] = metadata
                    assistant = dict(role='assistant', content=raw)
                    if self.client.config.get('preserve_reasoning') and (path/'reasoning.txt').is_file():
                        assistant['reasoning_content'] = (path/'reasoning.txt').read_text(encoding='utf-8')
                    history.append(assistant)
                    record('assistant', dict(round=index, content=raw, generation=metadata))
                    reply = None
                    runner = None
                    error = None
                    try:
                        reply = parse_reply(raw)
                        (path/'generated.py').write_text(reply['code'].rstrip()+'\n', encoding='utf-8')
                        self.on_event('program', dict(round=index, **reply))
                        if reply['code'].strip():
                            validate(reply['code'])
                            deadline = time.monotonic()+self.execution_timeout

                            def interrupt():
                                self.check_stop()
                                if time.monotonic() > deadline:
                                    raise TimeoutError('Execution time limit reached')

                            self.robot.command_interrupt = interrupt
                            runner = Interpreter(self.robot, should_stop=self.cancelled.is_set,
                                                 on_action=lambda phase, action: self.on_event('action', dict(phase=phase, **action)))
                            item['stage'] = 'execution'
                            runner.run(reply['code'])
                        elif not reply['done']:
                            raise ValueError('An empty program must set done=true')
                    except PolicyCancelled:
                        raise
                    except Exception as failure:
                        error = type(failure).__name__+': '+str(failure)
                        hold(self.robot)
                    finally:
                        self.robot.command_interrupt = None
                        if runner is not None:
                            item['actions'] = runner.actions
                    if self.cancelled.is_set():
                        raise PolicyCancelled('Task cancelled')
                    self.robot.step(.2)
                    self.robot.command_interrupt = self.check_stop
                    try:
                        grading = evaluate(self.robot, goal)
                    finally:
                        self.robot.command_interrupt = None
                    feedback = dict(error=error, observation=observe(self.robot), evaluation=grading,
                                    actions=item['actions'], local_variables_reset=True,
                                    remaining_blocks=self.max_rounds-index,
                                    model_declared_done=reply['done'] if reply else False)
                    item.update(stage='evaluated', feedback=feedback,
                                model_declared_done=reply['done'] if reply else False)
                    write_json(path/'feedback.json', feedback)
                    write_json(path/'execution.json', item)
                    record('environment_feedback', dict(round=index, **feedback))
                    self.on_event('feedback', feedback)
                    report['evaluation'] = grading
                    if goal and grading['success']:
                        report.update(success=True, status='verified_success')
                        break
                    if not goal and reply and reply['done'] and not reply['code'].strip() and not error:
                        report['status'] = 'model_finished'
                        break
                    reminder = ('You marked the task done. Verify this REAL feedback; confirm with empty code and done=true '
                                'if complete, otherwise correct failures.' if reply and reply['done'] else
                                'Continue the ORIGINAL task using the current state; correct failures.')
                    history.append(dict(role='user', content=model_json(dict(feedback=feedback, reminder=reminder))))
            except (GenerationCancelled, PolicyCancelled) as error:
                hold(self.robot)
                report.update(status='cancelled', error=str(error))
            except KeyboardInterrupt:
                hold(self.robot)
                report.update(status='cancelled', error='KeyboardInterrupt')
                raise
            except Exception as error:
                hold(self.robot)
                report.update(status='error', error=type(error).__name__+': '+str(error))
            finally:
                self.robot.command_interrupt = None
                report.update(wall_seconds=time.monotonic()-started, final_observation=observe(self.robot))
                write_json(directory/'final_physics.json', physics_state(self.robot))
                write_json(directory/'result.json', report)
                record('task_result', dict(status=report['status'], verified_goal_success=report['success']))
        self.recent_tasks.append(dict(instruction=instruction, status=report['status']))
        return report
