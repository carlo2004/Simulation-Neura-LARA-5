"""Main-thread terminal presentation shared by live chat and benchmark workers."""
import json
import queue
import sys
import time
from stacklab.cli.speed import format_speed


class Presenter:
    def __init__(self, stream=False, show_thinking=False, stats_stream=None):
        self.events = queue.Queue()
        self.stream, self.show_thinking = stream, show_thinking
        self.characters = 0
        self.last_progress = time.monotonic()
        self.stats_stream = sys.stderr if stats_stream is None else stats_stream
        self.metrics = None
        self.metrics_received = None
        self.speed_width = 0

    def end_speed_line(self):
        if self.speed_width:
            print(file=self.stats_stream, flush=True)
            self.speed_width = 0

    def show_speed(self, value, final=False):
        text = '[Inferenz] '+format_speed(value)
        inline = self.stats_stream.isatty() and not self.stream and not self.show_thinking and not final
        if inline:
            print('\r'+text.ljust(self.speed_width), end='', file=self.stats_stream, flush=True)
            self.speed_width = len(text)
        else:
            self.end_speed_line()
            print(text, file=self.stats_stream, flush=True)
        self.last_progress = time.monotonic()

    def event(self, kind, data):
        if kind in ('token', 'inference'):
            self.events.put(dict(event=kind, **data))
        elif kind == 'generating':
            self.drain()
            self.end_speed_line()
            self.metrics = None
            self.characters = 0
            print(f'\nModell generiert Block {data["round"]}/{data["maximum"]} ...', flush=True)
        elif kind == 'program':
            self.drain()
            self.end_speed_line()
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
            if data['event'] == 'inference':
                self.metrics = data
                self.metrics_received = time.monotonic()
                if data['phase'] == 'finished':
                    self.show_speed(data, final=True)
                continue
            self.characters += len(data['text'])
            if data['kind'] == 'content' and self.stream or data['kind'] == 'reasoning_content' and self.show_thinking:
                self.end_speed_line()
                print(data['text'], end='', flush=True)
        if self.metrics and self.metrics['phase'] != 'finished' and time.monotonic()-self.last_progress >= 1:
            value = dict(self.metrics)
            elapsed = value.get('total_seconds')
            if elapsed is None:
                elapsed = value.get('request_seconds') or 0
            value['total_seconds'] = elapsed+time.monotonic()-self.metrics_received
            self.show_speed(value)
