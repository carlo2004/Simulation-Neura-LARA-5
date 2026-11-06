"""Observations and physical checks, outside the generated program's API."""
from contextlib import contextmanager

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.transform import Rotation

from stacklab.policy import READ_METHODS

TASK_GOALS = {'lift', 'drop', 'place', 'joints', 'pose', 'tower', 'layout', 'response'}


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
    return dict(tcp_m=robot.data.site_xpos[robot.sid].tolist(), tcp_orientation_wxyz=robot.orientation('tcp').tolist(),
                joints_rad=robot.joints().tolist(), grasped_objects=[n for n in contacts if robot.grasped(n)],
                gripper_command='closed' if float(robot.data.ctrl[6]) < .016 else 'open',
                finger_contact_objects=contacts, simulation_time_s=float(robot.data.time),
                objects=[dict(name=n, color=s.color_name(), shape=s.shape, size_m=s.dimensions(),
                              centre_m=robot.position(n).tolist(), orientation_wxyz=robot.orientation(n).tolist())
                         for n, s in robot.objects.items()])


def _rotation(wxyz):
    return Rotation.from_quat(np.asarray(wxyz)[[1, 2, 3, 0]])


def _quaternion(rotation):
    return rotation.as_quat()[[3, 0, 1, 2]].tolist()


def _rotation_error(actual, target):
    return float(np.rad2deg((_rotation(target)*_rotation(actual).inv()).magnitude()))


def resolve_goal(robot, goal):
    """Resolve relative coordinates once against the measured initial state."""
    if goal is None:
        return None
    if not isinstance(goal, dict) or goal.get('type') not in TASK_GOALS | {'move', 'stack'}:
        raise ValueError('Unsupported evaluator goal')
    goal = dict(goal)
    kind = goal['type']
    if kind == 'stack':
        robot._pair(goal['source'], goal['target'])
    if kind == 'move' and 'target_m' not in goal:
        goal['target_m'] = (robot.data.site_xpos[robot.sid]+np.asarray(goal['delta_m'])).tolist()
    if kind in ('place', 'drop'):
        source = goal['source']
        if 'target_xy_m' not in goal:
            goal['target_xy_m'] = (robot.position(source)[:2]+np.asarray(goal.get('delta_xy_m', [0, 0]))).tolist()
        if 'yaw_delta_deg' in goal and 'target_orientation_wxyz' not in goal:
            yaw = Rotation.from_euler('z', goal['yaw_delta_deg'], degrees=True)
            goal['target_orientation_wxyz'] = _quaternion(yaw*_rotation(robot.orientation(source)))
    if kind == 'pose' and 'target_orientation_wxyz' not in goal:
        from stacklab.sim.robot import tool_rotation
        goal['target_orientation_wxyz'] = _quaternion(tool_rotation(goal['orientation'], goal.get('yaw_deg', 0)))
    return goal


@contextmanager
def protected_motion(robot, goal):
    """Measure peak displacement of protected objects at every physics step."""
    origins = {name: robot.position(name) for name in (goal or {}).get('protect', [])}
    peaks = dict.fromkeys(origins, 0.)
    if not origins:
        yield peaks
        return
    previous = robot.record_callback

    def capture(current):
        for name, origin in origins.items():
            peaks[name] = max(peaks[name], float(np.linalg.norm(current.position(name)-origin)))
        if previous is not None:
            previous(current)

    robot.record_callback = capture
    try:
        yield peaks
    finally:
        robot.record_callback = previous


def _on_table(robot, name):
    height = robot.objects[name].dimensions()[2]
    return bool(abs(robot.position(name)[2]-height/2) < .003 and robot._touching(name+'_geom', 'table'))


def _placement(robot, goal):
    name = goal['source']
    error = float(np.linalg.norm(robot.position(name)[:2]-np.asarray(goal['target_xy_m'])))
    tolerance = goal.get('tolerance_m', .012)
    details = dict(xy_error_m=error, tolerance_m=tolerance, on_table=_on_table(robot, name),
                   stationary=bool(robot._stationary(name)), tool_clear=bool(tool_clear(robot, name)))
    valid = error <= tolerance and all(details[key] for key in ('on_table', 'stationary', 'tool_clear'))
    if 'target_orientation_wxyz' in goal:
        details['rotation_error_deg'] = _rotation_error(robot.orientation(name), goal['target_orientation_wxyz'])
        valid = valid and details['rotation_error_deg'] <= 5
    return valid, details


def _layout(robot, goal):
    names = goal.get('objects', robot.object_names)
    slots = goal['slots']
    if not names or len(names) != len(slots) or len(set(names)) != len(names):
        raise ValueError('A layout needs one slot per distinct participating object')
    positions = {name: robot.position(name) for name in names}
    colors = {name: robot.objects[name].color_name() for name in names}
    clear = {name: robot._stationary(name) and tool_clear(robot, name) for name in names}
    costs = np.zeros((len(slots), len(names)))
    matches = {}
    for i, slot in enumerate(slots):
        target = np.asarray(slot['centre_m'])
        supports = slot.get('supports', ['table'])
        for j, name in enumerate(names):
            delta = positions[name]-target
            xy_error = float(np.linalg.norm(delta[:2]))
            z_error = float(abs(delta[2]))
            identity_ok = slot.get('name', name) == name and slot.get('color', colors[name]) == colors[name]
            contacts = all(robot._touching(name+'_geom', 'table' if s == 'table' else s+'_geom')
                           and (s == 'table' or positions[name][2] > robot.position(s)[2]) for s in supports)
            valid = bool(identity_ok and contacts and clear[name] and z_error < .003
                         and xy_error <= goal.get('tolerance_m', .012))
            costs[i, j] = xy_error+z_error+(0 if valid else 10)
            matches[i, j] = dict(slot=i, object=name, target_m=slot['centre_m'], xy_error_m=xy_error,
                                 height_error_m=z_error, supports=list(supports), contacts=contacts,
                                 identity_ok=identity_ok, valid=valid)
    rows, columns = linear_sum_assignment(costs)
    selected = [matches[i, j] for i, j in zip(rows, columns)]
    return all(m['valid'] for m in selected), dict(matches=selected)


def _tower(robot, goal):
    names = goal['objects']
    order = list(names) if goal['ordered'] else sorted(names, key=lambda n: robot.position(n)[2])
    pairs = [dict(source=upper, target=lower, **robot.stack_diagnostics(upper, lower))
             for lower, upper in zip(order, order[1:])]
    base_on_table = _on_table(robot, order[0])
    clear = all(tool_clear(robot, name) for name in order)
    return (len(pairs) > 0 and base_on_table and clear and all(p['valid'] for p in pairs),
            dict(bottom_to_top=order, base_on_table=base_on_table, tool_clear=clear, contacts=pairs))


def _response(robot, goal, initial, actions, reply):
    if initial is None:
        raise ValueError('A response goal needs an initial observation')
    observed_intent = (reply or {}).get('intent')
    calls = [a['method'] for a in actions if a['method'] not in READ_METHODS]
    joint_drift = float(np.max(np.abs(robot.joints()-np.asarray(initial['joints_rad']))))
    object_drift = max((float(np.linalg.norm(robot.position(o['name'])-np.asarray(o['centre_m'])))
                        for o in initial['objects']), default=0.)
    angle_drift = max((_rotation_error(robot.orientation(o['name']), o['orientation_wxyz'])
                       for o in initial['objects']), default=0.)
    unchanged = (joint_drift < .015 and object_drift < .003 and angle_drift < 3
                 and (float(robot.data.ctrl[6]) < .016) == (initial['gripper_command'] == 'closed'))
    solved = _placement(robot, goal)[0] if goal['intent'] == 'no_op' and 'target_xy_m' in goal else True
    valid = (observed_intent == goal['intent'] and (reply or {}).get('done') is True
             and not (reply or {}).get('code', '').strip() and bool((reply or {}).get('message', '').strip())
             and not calls and unchanged and solved)
    return dict(success=valid, goal=goal, diagnostics=dict(intent=observed_intent, actuator_calls=calls,
                scene_unchanged=bool(unchanged), object_drift_m=object_drift, joint_drift_rad=joint_drift,
                object_angle_drift_deg=angle_drift, requested_state_satisfied=solved))


def _task_sample(robot, goal, actions):
    kind = goal['type']
    if kind == 'layout':
        return _layout(robot, goal)
    if kind == 'tower':
        return _tower(robot, goal)
    if kind == 'joints':
        error = float(np.max(np.abs(robot.joints()-np.asarray(goal['target_rad']))))
        return error < .015 and float(np.max(np.abs(robot.data.qvel[:6]))) < .03, dict(max_joint_error_rad=error)
    if kind == 'pose':
        error = float(np.linalg.norm(robot.data.site_xpos[robot.sid]-np.asarray(goal['target_m'])))
        angle = _rotation_error(robot.orientation('tcp'), goal['target_orientation_wxyz'])
        return error < .004 and angle <= 5, dict(tcp_error_m=error, rotation_error_deg=angle)
    if kind == 'lift':
        name = goal['source']
        centre = robot.position(name)
        z = float(centre[2])
        offset = float(np.linalg.norm(centre-robot.data.site_xpos[robot.sid]))
        held = robot.grasped(name)
        return (z >= goal['min_z_m'] and held and offset < .02,
                dict(centre_z_m=z, grasped_both_pads=held, tcp_offset_m=offset))
    valid, details = _placement(robot, goal)
    if kind == 'drop':
        releases = [a['release_centres_m'][goal['source']] for a in actions
                    if goal['source'] in a.get('release_centres_m', {})]
        from_height = any(p[2] >= goal['release_min_z_m'] and
                          np.linalg.norm(np.asarray(p[:2])-goal['target_xy_m']) <= goal['tolerance_m'] for p in releases)
        details.update(release_centres_m=releases, released_from_height=from_height)
        valid = valid and from_height
    return valid, details


def evaluate(robot, goal=None, *, initial=None, actions=(), reply=None, protected=None):
    """Check a trusted benchmark goal, or report observed stacks without grading language."""
    if goal and goal['type'] == 'response':
        return _response(robot, goal, initial, actions, reply)
    if goal and goal['type'] in TASK_GOALS:
        samples = []
        for _ in range(20):
            robot.step(.1)
            valid, details = _task_sample(robot, goal, actions)
            samples.append(bool(valid))
        if goal.get('protect'):
            peaks = {name: (protected or {}).get(name) for name in goal['protect']}
            details['protected_peak_displacement_m'] = peaks
            protected_ok = all(value is not None and value <= .005 for value in peaks.values())
        else:
            protected_ok = True
        return dict(success=all(samples) and protected_ok, goal=goal, stable_checks=sum(samples),
                    checks=len(samples), diagnostics=details)
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
