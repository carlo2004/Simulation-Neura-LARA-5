"""Opt-in key jogging. The viewer callback queues input; the main thread owns physics."""
import queue
import threading
import numpy as np

# GLFW codes used by MuJoCo's public key_callback. No platform-specific window hooks.
MOVES = {265: (0, 1), 264: (0, -1), 263: (1, 1), 262: (1, -1),
         268: (2, 1), 269: (2, -1)}  # arrows; Home / End
SPACE, ESCAPE, INSERT, DELETE = 32, 256, 260, 261


class ManualControl:
    def __init__(self):
        self.enabled = False
        self.suspended = False
        self.step_m = .005
        self.speed_m_s = .04
        self.pending = queue.Queue(maxsize=1)
        self.stop_requested = threading.Event()
        self.exit_requested = threading.Event()
        self.target = self.reference = None
        self.message = ''
        self.selected = None

    def clear_input(self):
        while True:
            try:
                self.pending.get_nowait()
            except queue.Empty:
                break
        self.stop_requested.clear()
        self.exit_requested.clear()

    def enable(self, robot, step_m=None):
        if step_m is not None:
            if not np.isfinite(step_m) or not .001 <= step_m <= .02:
                raise ValueError('Manual step must be 0.001–0.02 m')
            self.step_m = float(step_m)
        self.enabled = True
        self.anchor(robot)

    def anchor(self, robot):
        self.clear_input()
        self.target = robot.data.site_xpos[robot.sid].copy()
        self.reference = self.target.copy()
        self.message = ''

    def stop(self, robot, disable=False):
        # Hold the current joints with the existing controller; never teleport.
        robot.command = robot.data.qpos[:6].copy()
        robot.data.ctrl[:6] = robot.command
        self.anchor(robot)
        if disable:
            self.enabled = False

    def on_key(self, key):
        if not self.enabled or self.suspended:
            return
        if key in (SPACE, ESCAPE):
            self.stop_requested.set()
            if key == ESCAPE:
                self.exit_requested.set()
        elif key in MOVES or key in (INSERT, DELETE):
            try:
                self.pending.put_nowait(key)
            except queue.Full:
                pass  # No long queue of motion after releasing a key.

    def tick(self, robot, dt=.02):
        if not self.enabled or self.suspended:
            return
        if self.stop_requested.is_set():
            self.stop(robot, disable=self.exit_requested.is_set())
            return
        try:
            key = self.pending.get_nowait()
        except queue.Empty:
            key = None
        if key in (INSERT, DELETE):
            robot.data.ctrl[6:] = .032 if key == INSERT else 0
        elif key in MOVES:
            axis, sign = MOVES[key]
            goal = self.target.copy()
            goal[axis] += sign*self.step_m
            try:
                robot.validate_tcp(goal)
                robot.ik(goal)  # Reject unreachable goals before changing controls.
                if np.linalg.norm(goal-robot.data.site_xpos[robot.sid]) <= .025:
                    self.target = goal
                    self.message = ''
            except (ValueError, RuntimeError) as e:
                self.message = str(e)
        delta = self.target-self.reference
        distance = np.linalg.norm(delta)
        if distance > 1e-7:
            point = self.reference+delta*min(1., self.speed_m_s*dt/distance)
            try:
                command = robot.ik(point)
            except RuntimeError as e:
                self.stop(robot)
                self.message = str(e)
                return
            robot.command = command
            robot.data.ctrl[:6] = command
            self.reference = point

    def panel(self):
        if not self.enabled:
            return None
        lines = [f'MANUAL CONTROL | step {self.step_m*1000:g} mm',
                 'Up/Down: +X/-X | Left/Right: +Y/-Y',
                 'Home/End: +Z/-Z | Insert/Delete: open/close',
                 'Space: stop | Esc: manual off',
                 'Double-click point, then: goto-selected',
                 'World axes; focus the 3D view.']
        if self.target is not None:
            lines.append('Goal [m]: '+', '.join(f'{v:.3f}' for v in self.target))
        if self.message:
            lines.append(self.message)
        return '\n'.join(lines)
