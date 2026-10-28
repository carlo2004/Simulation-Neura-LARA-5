"""Prompt the local model live while the same MuJoCo scene stays open."""
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import queue
import shlex
import subprocess
import sys
import threading
import time
from console import Controller
from core import Config
from llm_agent import Agent
from llm_evaluation import evaluate, observe
from llm_runtime import ROOT, lock, model_keys
from llm_session import LocalModel

HELP = '''Freie Sprache: z.B. "Bewege den Greifer 5 cm nach rechts."
Oder: "Staple Rot auf Blau und bewege den Greifer danach nach oben."
Richtungen: rechts=+X, links=-X, vorne=+Y, hinten=-Y, hoch=+Z; Weltmeter.
Ohne Abstand sind relative Bewegungen 5 cm. Lange Aufgaben koennen mehrere
Programmbloecke verwenden; jeder Block bekommt echte Ausfuehrungsrueckmeldung.

/stop                    Laufende Generierung oder Bewegung abbrechen
/status                  Tatsächliche Werkzeug-/Objektpositionen anzeigen
/check red blue          Unabhaengige physische Pruefung mit freiem Greifer
/reset                   Szene zuruecksetzen
/axes on|off             Koordinatensystem umschalten
/stackviz red blue|off   Pruefrahmen umschalten
/models                  Modell-Aliasse anzeigen
/model qwen9b            Bereits heruntergeladenes Modell wechseln
/sim BEFEHL              Vorhandene deterministische Roboterkonsole verwenden
/help /quit              Hilfe / beenden
Waehrend einer Aufgabe sind /stop und /quit direkt verfuegbar.
'''


class Presenter:
    def __init__(self, stream=False, show_thinking=False):
        self.events = queue.Queue()
        self.stream, self.show_thinking = stream, show_thinking
        self.characters = 0
        self.last_progress = time.monotonic()

    def event(self, kind, data):
        if kind == 'token':
            self.events.put(data)
        elif kind == 'generating':
            self.characters = 0
            print(f'\nModell generiert Block {data["round"]}/{data["maximum"]} ...', flush=True)
        elif kind == 'program':
            if self.stream:
                print()
            if data['message']:
                print('Modell: '+data['message'], flush=True)
            print('Generierter Python-Code:\n'+(data['code'] or '(keine weitere Aktion)'), flush=True)
        elif kind == 'action':
            if data['phase'] == 'start':
                print('  -> robot.'+data['method']+' '+json.dumps(dict(args=data['args'], kwargs=data['kwargs'])), flush=True)
            elif data.get('error'):
                print('  FEHLER: '+data['error'], flush=True)
            elif 'result' in data:
                print('     Ergebnis: '+json.dumps(data['result']), flush=True)
        elif kind == 'feedback':
            print('Feedback: TCP='+str([round(v, 4) for v in data['observation']['tcp_m']])+
                  ', Fingerkontakt='+str(data['observation']['finger_contact_objects']), flush=True)
            if data['error']:
                print('Ausfuehrungsfehler: '+data['error'], flush=True)
            grading = data['evaluation']
            for check in grading.get('stack_checks', []):
                print(f'Physik: {check["source"]} auf {check["target"]}: '
                      f'{check["stable_checks"]}/20; Greifer frei={check["tool_clear"]}', flush=True)
            if (grading.get('goal') or {}).get('type') == 'move':
                print('Zielabweichung: '+str(grading['tcp_error_m'])+' m', flush=True)

    def drain(self):
        while True:
            try:
                data = self.events.get_nowait()
            except queue.Empty:
                break
            self.characters += len(data['text'])
            if data['kind'] == 'content' and self.stream or data['kind'] == 'reasoning_content' and self.show_thinking:
                print(data['text'], end='', flush=True)
        if self.characters and time.monotonic()-self.last_progress > 8:
            if not self.stream and not self.show_thinking:
                print(f'  Generierung laeuft ({self.characters} Zeichen empfangen) ...', flush=True)
            self.last_progress = time.monotonic()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Live natural-language control through a local model and execution feedback')
    parser.add_argument('--model', default='qwen9b')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--config', type=Path, default=ROOT/'scenes/three_cubes.json')
    parser.add_argument('--axes', action='store_true')
    parser.add_argument('--stackviz', nargs=2, metavar=('SOURCE', 'TARGET'))
    parser.add_argument('--show-settings', action='store_true')
    parser.add_argument('--prompt', action='append', help='Run one or more prompts sequentially, then exit')
    parser.add_argument('--goal-stack', nargs=2, help='Trusted independent goal; available with exactly one --prompt')
    parser.add_argument('--max-rounds', type=int, default=4)
    parser.add_argument('--max-tokens', type=int, default=2048)
    parser.add_argument('--threads', type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument('--thinking', action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument('--thinking-budget', type=int, help='Reasoning token cap; -1 to remove the separate cap')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--generation-timeout', type=int, default=600)
    parser.add_argument('--execution-timeout', type=int, default=120)
    parser.add_argument('--stream', action='store_true', help='Show raw response text while it is generated')
    parser.add_argument('--show-thinking', action='store_true', help='Also show the reasoning stream when provided')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if sys.platform == 'darwin' and not args.headless and not os.environ.get('STACKLAB_MJPYTHON'):
        executable = Path(sys.executable).with_name('mjpython')
        if executable.is_file():
            env = dict(os.environ, STACKLAB_MJPYTHON='1')
            return subprocess.call([str(executable), str(Path(__file__).resolve()), *(argv if argv is not None else sys.argv[1:])], env=env)
    robot = None
    controller = None
    client = None
    agent = None
    stopped = threading.Event()
    busy = threading.Event()
    pending = queue.Queue()
    try:
        lock(args.model)
        if not 1 <= args.max_rounds <= 6 or not 128 <= args.max_tokens <= 4096 or not 1 <= args.threads <= 64:
            raise ValueError('rounds: 1–6; tokens: 128–4096; threads: 1–64')
        if not 10 <= args.generation_timeout <= 1800 or not 10 <= args.execution_timeout <= 600:
            raise ValueError('Invalid generation/execution time limit')
        if args.goal_stack and (not args.prompt or len(args.prompt) != 1):
            raise ValueError('--goal-stack requires exactly one --prompt')
        directory = (args.output or ROOT/'output'/('chat_'+time.strftime('%Y%m%d_%H%M%S'))).resolve()
        if directory.exists() and any(directory.iterdir()):
            raise ValueError('Choose a new output directory')
        directory.mkdir(parents=True, exist_ok=True)
        from simulation import Simulation
        robot = Simulation(replace(Config.load(args.config), seed=args.seed), gui=not args.headless, axes=args.axes,
                           stackviz=args.stackviz, show_settings=args.show_settings)
        controller = Controller(robot)
        client = LocalModel(args.model, threads=args.threads)
        display = Presenter(args.stream, args.show_thinking)

        def tick():
            display.drain()
            if stopped.is_set() or controller.robot.viewer and not controller.robot.viewer.is_running():
                stopped.set()
                agent.stop()
            started = time.monotonic()
            if agent.generating.is_set():
                controller.robot.refresh_view()
            else:
                controller.idle(.02)
            time.sleep(max(0., .02-(time.monotonic()-started)))

        agent = Agent(robot, client, max_rounds=args.max_rounds, max_tokens=args.max_tokens,
                      thinking=args.thinking, seed=args.seed, generation_timeout=args.generation_timeout,
                      thinking_budget=args.thinking_budget,
                      execution_timeout=args.execution_timeout, on_event=display.event, tick=tick)
        print('Lokales Modell: '+client.config['model_id'], flush=True)
        print('Code und Aktionen werden angezeigt. /help fuer Hilfe, /stop zum Abbrechen.', flush=True)
        print('Protokolle: '+str(directory), flush=True)
        sequence = 0
        outcomes = []

        def task(text):
            nonlocal sequence
            sequence += 1
            busy.set()
            manual = controller.robot.manual
            if manual.enabled:
                manual.stop(controller.robot)
            manual.suspended = True
            try:
                goal = dict(type='stack', source=args.goal_stack[0], target=args.goal_stack[1]) if args.goal_stack else None
                if goal:
                    controller.robot._pair(goal['source'], goal['target'])
                result = agent.run_task(text, directory/f'task_{sequence:03d}', goal=goal)
                display.drain()
                outcomes.append(dict(instruction=text, status=result['status'], verified_success=result['success']))
                from core import write_json
                write_json(directory/'session.json', dict(tasks=outcomes))
                print('Status: '+result['status'], flush=True)
                if result.get('error'):
                    print('Fehler: '+result['error'], flush=True)
                if result['success'] is None and result['status'] == 'model_finished':
                    print('Fertigmeldung stammt vom Modell; die gezeigten Physikmessungen sind separat.', flush=True)
                elif result['status'] == 'budget_exhausted':
                    print('Blockbudget erreicht; die Aufgabe ist nicht als abgeschlossen bestaetigt.', flush=True)
                return result['status'] not in ('error', 'cancelled', 'budget_exhausted') and result['success'] is not False
            finally:
                manual.suspended = False
                if manual.enabled:
                    manual.anchor(controller.robot)
                busy.clear()

        if args.prompt:
            ok = True
            for instruction in args.prompt:
                if stopped.is_set():
                    break
                print('\nDu: '+instruction, flush=True)
                ok = task(instruction) and ok
            return 0 if ok and not stopped.is_set() else 1

        def reader():
            while not stopped.is_set():
                try:
                    text = input('llm> ')
                except EOFError:
                    text = '/quit'
                if text.strip() in ('/stop', '/quit'):
                    agent.stop()
                    if text.strip() == '/quit':
                        stopped.set()
                        return
                elif busy.is_set():
                    print('Aufgabe laeuft. /stop bricht sie ab; danach erneut eingeben.', flush=True)
                else:
                    pending.put(text)

        threading.Thread(target=reader, daemon=True).start()
        while not stopped.is_set():
            tick()
            try:
                text = pending.get_nowait().strip()
            except queue.Empty:
                continue
            try:
                if not text:
                    continue
                if text == '/help':
                    print(HELP, flush=True)
                elif text == '/status':
                    print(json.dumps(observe(controller.robot), ensure_ascii=False, indent=2), flush=True)
                elif text == '/models':
                    for key in model_keys():
                        print(key+'  '+lock(key)['model_id'], flush=True)
                elif text.startswith('/model '):
                    selected = text.split(maxsplit=1)[1]
                    config = lock(selected)
                    client.close()
                    client = LocalModel(selected, threads=args.threads)
                    agent.client = client
                    agent.thinking = args.thinking if config.get('supports_thinking_toggle', True) else True
                    print('Modell gewaehlt: '+client.config['model_id'], flush=True)
                    print('Thinking: '+str(config.get('default_thinking', False) if agent.thinking is None else agent.thinking), flush=True)
                elif text.startswith('/check '):
                    pair = shlex.split(text)[1:]
                    if len(pair) != 2:
                        raise ValueError('Use /check SOURCE TARGET')
                    controller.robot._pair(*pair)
                    print(json.dumps(evaluate(controller.robot, dict(type='stack', source=pair[0], target=pair[1])), indent=2), flush=True)
                elif text.startswith('/sim ') or text == '/reset' or text.startswith(('/axes ', '/stackviz ')):
                    command = text[5:] if text.startswith('/sim ') else text[1:]
                    if not controller.execute(command):
                        stopped.set()
                    agent.robot = controller.robot
                    if command == 'reset':
                        agent.recent_tasks.clear()
                elif text.startswith('/'):
                    print('Unbekannter Steuerbefehl. /help zeigt die Befehle.', flush=True)
                else:
                    task(text)
            except (ValueError, RuntimeError, OSError, TypeError) as error:
                print('Fehler: '+str(error), flush=True)
        return 0
    except KeyboardInterrupt:
        if agent:
            agent.stop()
        return 130
    except (ValueError, RuntimeError, OSError) as error:
        print('Fehler: '+str(error), file=sys.stderr)
        return 1
    finally:
        stopped.set()
        if client:
            client.close()
        if controller:
            controller.robot.close()
        elif robot:
            robot.close()


if __name__ == '__main__':
    raise SystemExit(main())
