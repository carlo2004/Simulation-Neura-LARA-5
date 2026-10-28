"""Observations and physical checks, outside the generated program's API."""
import numpy as np


def tool_clear(robot, source):
    object_id = robot.model.geom(source+'_geom').id
    fingers = {robot.model.geom(n).id for n in ('palm', 'left_pad', 'right_pad')}
    contact = any(int(c.geom1) == object_id and int(c.geom2) in fingers
                  or int(c.geom2) == object_id and int(c.geom1) in fingers for c in robot.data.contact)
    return not contact and float(np.linalg.norm(robot.data.site_xpos[robot.sid]-robot.position(source))) > .075


def observe(robot):
    pads = {robot.model.geom(n).id for n in ('left_pad', 'right_pad')}
    contacts = []
    for name in robot.object_names:
        geom = robot.model.geom(name+'_geom').id
        if any(int(c.geom1) == geom and int(c.geom2) in pads
               or int(c.geom2) == geom and int(c.geom1) in pads for c in robot.data.contact):
            contacts.append(name)
    return dict(tcp_m=robot.data.site_xpos[robot.sid].tolist(),
                gripper_command='closed' if float(robot.data.ctrl[6]) < .016 else 'open',
                finger_contact_objects=contacts, simulation_time_s=float(robot.data.time),
                objects=[dict(name=n, shape=s.shape, size_m=s.dimensions(),
                              centre_m=robot.position(n).tolist()) for n, s in robot.objects.items()])


def evaluate(robot, goal=None):
    """Check a trusted benchmark goal, or report observed stacks without grading language."""
    if goal and goal['type'] == 'move':
        robot.step(.2)
        position = robot.data.site_xpos[robot.sid].copy()
        error = float(np.linalg.norm(position-np.asarray(goal['target_m'])))
        return dict(success=error < .004, goal=goal, tcp_error_m=error, tolerance_m=.004)
    if goal and goal['type'] != 'stack':
        raise ValueError('Unsupported evaluator goal')
    names = [n for n, s in robot.objects.items() if s.shape in ('cube', 'box')]
    pairs = [(goal['source'], goal['target'])] if goal else [
        (a, b) for a in names for b in names if a != b
        and robot.position(a)[2] > robot.position(b)[2]+.01
        and np.linalg.norm(robot.position(a)[:2]-robot.position(b)[:2]) < .12]
    shown = robot.overlays.stack_pair
    if not goal and shown and shown not in pairs:
        pairs.append(shown)
    samples = {pair: [] for pair in pairs}
    if goal or robot.overlays.stack_pair in pairs:
        pair = pairs[0] if goal else robot.overlays.stack_pair
        robot.overlays.begin_check(*pair)
    try:
        for _ in range(20 if pairs else 0):
            robot.step(.1)
            for pair in pairs:
                valid = bool(robot.is_stacked(*pair) and tool_clear(robot, pair[0]))
                samples[pair].append(valid)
                if robot.overlays.check_pair == pair:
                    robot.overlays.samples.append(valid)
    finally:
        robot.overlays.checking = False
        robot.refresh_view()
    checks = [dict(source=a, target=b, success=all(samples[a, b]), stable_checks=sum(samples[a, b]),
                   checks=20, tool_clear=bool(tool_clear(robot, a)),
                   diagnostics=robot.stack_diagnostics(a, b)) for a, b in pairs]
    # Live arbitrary instructions have no independently specified semantic goal.
    return dict(success=checks[0]['success'] if goal else None, goal=goal, stack_checks=checks)


def physics_state(robot):
    return dict(time_s=float(robot.data.time), qpos=robot.data.qpos.tolist(), qvel=robot.data.qvel.tolist(),
                ctrl=robot.data.ctrl.tolist(), qacc_warmstart=robot.data.qacc_warmstart.tolist())
