"""Prompt a local or remote model while the same MuJoCo scene stays open."""
from stacklab.paths import ROOT
from stacklab.paths import RUNS_ROOT
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
from stacklab.cli.console import Controller
from stacklab.config import Config
from stacklab.llm.agent import Agent
from stacklab.evaluation import evaluate, observe
from stacklab.llm.catalog import lock, model_keys
from stacklab.llm.runtime import LocalModel
from stacklab.llm.remote import RemoteModel
from stacklab.cli.presentation import Presenter

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
                        Remote: Modell am Server wechseln und Chat neu starten
/sim BEFEHL              Vorhandene deterministische Roboterkonsole verwenden
/help /quit              Hilfe / beenden
Waehrend einer Aufgabe sind /stop und /quit direkt verfuegbar.
'''



def main(argv=None):
    parser = argparse.ArgumentParser(description='Live control through a local or remote model and execution feedback')
    parser.add_argument('--model', help='Model alias; default from config/models.lock.json')
    parser.add_argument('--server-url', help='Remote Stack Lab server through SSH, e.g. http://127.0.0.1:8765')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--config', type=Path, default=ROOT/'scenes/three_cubes.json')
    parser.add_argument('--axes', action='store_true', help='Enable optional coordinate overlays; off by default')
    parser.add_argument('--stackviz', nargs=2, metavar=('SOURCE', 'TARGET'),
                        help='Enable the optional stack overlay; off by default')
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
            return subprocess.call([str(executable), '-m', 'stacklab', 'chat', *(argv if argv is not None else sys.argv[1:])], env=env)
    robot = None
    controller = None
    client = None
    agent = None
    stopped = threading.Event()
    busy = threading.Event()
    pending = queue.Queue()
    try:
        if args.server_url:
            if args.device != 'cpu':
                raise ValueError('--device applies to local inference; choose CUDA on the remote serve command')
            # Connect before opening the GUI; no local weights or CUDA are required.
            client = RemoteModel(args.server_url, args.model)
        else:
            lock(args.model, device=args.device)
        if min(args.max_rounds, args.max_tokens, args.threads) < 1:
            raise ValueError('rounds, tokens and threads must be positive')
        if min(args.generation_timeout, args.execution_timeout) <= 0:
            raise ValueError('Invalid generation/execution time limit')
        if args.goal_stack and (not args.prompt or len(args.prompt) != 1):
            raise ValueError('--goal-stack requires exactly one --prompt')
        directory = (args.output or RUNS_ROOT/('chat_'+time.strftime('%Y%m%d_%H%M%S'))).resolve()
        if directory.exists() and any(directory.iterdir()):
            raise ValueError('Choose a new output directory')
        directory.mkdir(parents=True, exist_ok=True)
        from stacklab.sim.robot import Simulation
        robot = Simulation(replace(Config.load(args.config), seed=args.seed), gui=not args.headless, axes=args.axes,
                           stackviz=args.stackviz, show_settings=args.show_settings)
        controller = Controller(robot)
        if client is None:
            client = LocalModel(args.model, threads=args.threads, device=args.device)
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
        print(('Remote-Modell: ' if args.server_url else 'Lokales Modell: ')+client.config['model_id'], flush=True)
        if args.server_url:
            print('Verbindung: '+args.server_url+'; Simulation und Roboterprogramme laufen lokal.', flush=True)
            print('Server-Threads: '+str(client.info['threads'])+'; lokale --threads gelten nur fuer lokale Inferenz.', flush=True)
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
                from stacklab.config import write_json
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
                    if args.server_url:
                        raise ValueError('Remote-Modell am Server mit serve --model wechseln; danach diesen Chat neu starten.')
                    selected = text.split(maxsplit=1)[1]
                    config = lock(selected, device=args.device)
                    client.close()
                    client = LocalModel(selected, threads=args.threads, device=args.device)
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
