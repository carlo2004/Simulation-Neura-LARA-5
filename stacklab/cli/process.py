"""Keep a worker's complete log while forwarding its inference progress live."""
import os
import signal
import subprocess
import time


def stop_worker(process):
    if process.poll() is not None:
        return
    try:
        if os.name == 'nt':
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGINT)
        process.wait(timeout=5)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()


def run_logged(command, log, *, cwd, env, timeout, on_progress=print):
    options = ({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else
               {'start_new_session': True})
    started = time.monotonic()
    with subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, **options) as process:
        try:
            with open(log.name, encoding='utf-8', errors='replace') as reader:
                pending = ''

                def forward(final=False):
                    nonlocal pending
                    pending += reader.read()
                    lines = pending.split('\n')
                    pending = lines.pop()
                    if final and pending:
                        lines.append(pending)
                        pending = ''
                    for line in lines:
                        if line.startswith('[Inferenz]'):
                            on_progress(line.rstrip())

                while process.poll() is None:
                    forward()
                    if time.monotonic()-started >= timeout:
                        raise subprocess.TimeoutExpired(command, timeout)
                    time.sleep(.1)
                forward(final=True)
            return subprocess.CompletedProcess(command, process.returncode)
        except BaseException:
            stop_worker(process)
            raise
