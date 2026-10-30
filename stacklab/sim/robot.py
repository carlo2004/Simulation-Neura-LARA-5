"""Contact-based stacking using a RoboDK-derived LARA 5 model."""
from pathlib import Path
import xml.etree.ElementTree as E
import time
import numpy as np
import mujoco
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
from stacklab.config import Config
from stacklab.sim.overlays import Overlays
from stacklab.sim.manual import ManualControl
from stacklab.paths import ROOT

def scene_xml(c, *, visuals=True):
    root = E.parse(ROOT/'assets/robots/lara5/lara5.xml').getroot()
    root.find('compiler').set('meshdir', str(ROOT/'assets/robots/lara5/assets'))
    root.find('option').attrib.update(timestep='0.002', gravity='0 0 -9.81', iterations='80', cone='elliptic')
    E.SubElement(root.find('default'), 'default', {'class': 'generic'})
    visual = E.SubElement(root, 'visual')
    E.SubElement(visual, 'global', offwidth='960', offheight='720')
    asset = root.find('asset')
    E.SubElement(asset, 'texture', name='floor', type='2d', builtin='checker', rgb1='.22 .27 .32', rgb2='.25 .30 .35', width='512', height='512')
    E.SubElement(asset, 'material', name='floor', texture='floor', texrepeat='5 5', reflectance='.12')
    w = root.find('worldbody')
    E.SubElement(w, 'geom', name='table', type='plane', size='1 1 .1', material='floor', friction='1 .005 .0001')
    E.SubElement(w, 'light', pos='1 0 2', dir='-0.3 0 -1', diffuse='.7 .7 .7')
    wrist = w.find(".//body[@name='link6']")
    g = E.SubElement(wrist, 'body', name='gripper', pos='0 0 0', quat='1 0 0 0', childclass='generic')
    E.SubElement(g, 'geom', name='palm', type='box', size='.035 .055 .018', pos='0 0 .02', mass='.25', rgba='.17 .20 .24 1')
    E.SubElement(g, 'site', name='tcp', pos='0 0 .09', size='.003', rgba='0 0 0 0')
    for sign, name in [(1, 'left'), (-1, 'right')]:
        b = E.SubElement(g, 'body', name=name+'_finger', pos=f'0 {sign*.009} 0')
        E.SubElement(b, 'joint', name=name, type='slide', axis=f'0 {sign} 0', range='0 .04', damping='3', armature='.001')
        E.SubElement(b, 'geom', name=name+'_pad', type='box', pos='0 0 .077', size='.018 .004 .03', mass='.04', friction='2 .01 .001', condim='4', solref='.005 1', rgba='.10 .12 .14 1')
        E.SubElement(root.find('actuator'), 'position', name=name, joint=name, kp='500', kv='10', ctrlrange='0 .04', forcerange='-15 15')
    positions = c.scene()
    for spec in c.object_specs():
        name = spec.name
        dims = spec.dimensions()
        body = E.SubElement(w, 'body', name='obj_'+name, pos=' '.join(map(str, positions[name])))
        E.SubElement(body, 'freejoint', name=name+'_free')
        if spec.shape == 'mesh':
            path = spec.mesh_path()
            for suffix, filename in [('visual', path), ('hull', path.with_name(path.stem+'_hull.obj'))]:
                E.SubElement(asset, 'mesh', name=name+'_'+suffix, file=str(filename),
                             scale=' '.join(map(str, dims)))
            E.SubElement(body, 'geom', name=name+'_geom', type='mesh', mesh=name+'_hull',
                         mass=str(spec.mass_kg), friction='1 .01 .001', condim='4',
                         solref='.005 1', rgba='0 0 0 0')
            E.SubElement(body, 'geom', name=name+'_visual', type='mesh', mesh=name+'_visual',
                         density='0', contype='0', conaffinity='0', rgba=' '.join(map(str, spec.rgba())))
            continue
        if spec.shape in ('cube', 'box'):
            kind, size = 'box', [d/2 for d in dims]
        elif spec.shape == 'sphere':
            kind, size = 'sphere', [dims[0]/2]
        else:
            kind, size = 'cylinder', [dims[0]/2, dims[2]/2]
        E.SubElement(body, 'geom', name=name+'_geom', type=kind,
                     size=' '.join(map(str, size)), mass=str(spec.mass_kg), friction='1 .01 .001',
                     condim='4', solref='.005 1', rgba=' '.join(map(str, spec.rgba())))
    if not visuals:
        # Explicit body inertia (robot) or zero density (object visuals) keeps
        # these non-colliding meshes independent of the physical mass model.
        for body in w.iter('body'):
            for geom in list(body.findall('geom')):
                if (geom.get('type') == 'mesh' and geom.get('contype') == '0'
                        and geom.get('conaffinity') == '0'
                        and (body.find('inertial') is not None or geom.get('density') == '0')):
                    body.remove(geom)
        used = {geom.get('mesh') for geom in w.iter('geom') if geom.get('mesh')}
        for mesh in list(asset.findall('mesh')):
            if mesh.get('name') not in used:
                asset.remove(mesh)
    return E.tostring(root, encoding='unicode')

class Simulation:
    def __init__(self, config=None, video=None, gui=False, show_settings=False, axes=False, stackviz=None, visuals=True):
        self.config = (config or Config()).validate()
        self.visuals = bool(visuals)
        if not self.visuals and (gui or video):
            raise ValueError('GUI/video require visual geometry; use visuals=True')
        self.show_settings = bool(show_settings)
        self.manual = ManualControl()
        self._push_watch = None
        self._push_had_contact = False
        self.model = mujoco.MjModel.from_xml_string(scene_xml(self.config, visuals=self.visuals))
        self.objects = {spec.name: spec for spec in self.config.object_specs()}
        self.overlays = Overlays(axes)
        if stackviz is not None:
            self.set_stackviz(*stackviz)
        self.data = mujoco.MjData(self.model)
        self.ikdata = mujoco.MjData(self.model)
        self.sid = self.model.site('tcp').id
        self.events = []
        self.record_callback = None
        self.frames = 0
        self._last_view_refresh = None
        self._last_overlay_refresh = None
        self._overlay_view_state = None
        self.writer = self.renderer = self.viewer = None
        self.camera = mujoco.MjvCamera()
        self.camera.lookat[:] = [.25, 0, .22]
        self.camera.distance = 1.35
        self.camera.azimuth = 135
        self.camera.elevation = -25
        self.command = self.ik([.40, -.12, .26], np.array([0, -.5, 1.5, 0, 1., 0]))
        self.data.qpos[:6] = self.command
        self.data.qpos[6:8] = .032
        self.data.ctrl[:6] = self.command
        self.data.ctrl[6:] = .032
        self._initial_qpos = self.data.qpos.copy()
        self._initial_ctrl = self.data.ctrl.copy()
        mujoco.mj_forward(self.model, self.data)
        if video:
            import imageio.v2 as imageio
            self.renderer = mujoco.Renderer(self.model, 720, 960)
            self.writer = imageio.get_writer(str(video), fps=self.config.fps, codec='libx264', quality=8)
        if gui:
            self.open_viewer()
        self.step(.5)

    @property
    def object_names(self):
        return tuple(self.objects)

    def open_viewer(self):
        if not self.visuals:
            raise ValueError('Recreate the simulation with visuals=True before opening a viewer')
        from mujoco import viewer
        self.viewer = viewer.launch_passive(
            self.model, self.data,
            show_left_ui=self.show_settings,
            show_right_ui=self.show_settings,
            key_callback=self.manual.on_key,
        )
        self._last_view_refresh = self._last_overlay_refresh = None
        self._overlay_view_state = None
        with self.viewer.lock():
            self.viewer.cam.lookat[:] = self.camera.lookat
            self.viewer.cam.distance = self.camera.distance
            self.viewer.cam.azimuth = self.camera.azimuth
            self.viewer.cam.elevation = self.camera.elevation
        self.refresh_view()

    def set_stackviz(self, source=None, target=None):
        if source is None and target is None:
            self.overlays.stack_pair = None
            return
        src, dst = self._pair(source, target)
        if src.shape not in ('cube', 'box') or dst.shape not in ('cube', 'box'):
            raise ValueError('Stack visualisation supports cubes/boxes')
        self.overlays.stack_pair = (source, target)

    def refresh_view(self, *, force=False):
        if self.viewer:
            if not self.viewer.is_running():
                raise KeyboardInterrupt
            now = time.monotonic()
            state = (self.overlays.axes, self.overlays.stack_pair, self.manual.enabled)
            changed = state != self._overlay_view_state
            # Also limit refreshes while inference pauses simulation time.
            if (not force and not changed and self._last_view_refresh is not None
                    and now-self._last_view_refresh < 1/self.config.fps):
                return
            self.overlays.observe(self)
            self.manual.selected = self.selected_point() if self.manual.enabled else None
            # Keep the previous rendering geometry/text between 10 Hz updates.
            # Visibility changes and final check results must appear immediately.
            if (force or changed or self._last_overlay_refresh is None
                    or now-self._last_overlay_refresh >= .1):
                with self.viewer.lock():
                    self.overlays.draw(self.viewer.user_scn, self, clear=True)
                self.viewer.set_texts(self.overlays.viewer_texts(self))
                self._last_overlay_refresh = time.monotonic()
                self._overlay_view_state = state
            self.viewer.sync()
            self._last_view_refresh = time.monotonic()
        else:
            self.overlays.observe(self)

    def selected_point(self):
        """World point from MuJoCo's native left-double-click selection, if usable."""
        if not self.viewer:
            return None
        with self.viewer.lock():
            p = self.viewer.perturb
            body = int(p.select)
            if not 0 <= body < self.model.nbody:
                return None
            if body and not self.model.body(body).name.startswith('obj_'):
                return None  # Clicking the robot is not a work-surface target.
            local = p.localpos.copy()
        point = self.data.xpos[body]+self.data.xmat[body].reshape(3, 3)@local
        if not (.20 <= point[0] <= .60 and abs(point[1]) <= .30):
            return None
        return point.copy()

    def goto_selected(self, height=None):
        point = self.selected_point()
        if point is None:
            raise ValueError('Double-click a table/object point in the workspace first (not the robot)')
        height = max(self.config.hover_z_m, point[2]+.06) if height is None else height
        if not np.isfinite(height) or height < point[2]+.04:
            raise ValueError('Height must be finite and at least 0.04 m above the selected point')
        current = self.data.site_xpos[self.sid].copy()
        transport = max(current[2], height, self.config.hover_z_m)
        waypoints = [[current[0], current[1], transport],
                     [point[0], point[1], transport], [point[0], point[1], height]]
        start = self.command.copy()
        for xyz in waypoints:
            self.validate_tcp(xyz)
            start = self.ik(xyz, start)
        for xyz in waypoints:
            if np.linalg.norm(self.data.site_xpos[self.sid]-xyz) > .001:
                self.move_to(xyz)
        return point

    def render_frame(self, renderer):
        """Render the same optional geometry/text for offscreen images or video."""
        self.overlays.observe(self)
        renderer.update_scene(self.data, self.camera)
        self.overlays.draw(renderer.scene, self)
        return self.overlays.annotate(renderer.render(), self)

    def reset(self):
        """Reset the scene and controller while keeping the current viewer open."""
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[:] = self._initial_qpos
        self.data.ctrl[:] = self._initial_ctrl
        self.command = self._initial_qpos[:6].copy()
        self.manual.enabled = False
        self.manual.clear_input()
        self.events.clear()
        self.overlays.clear_check()
        self.frames = 0
        self._last_view_refresh = self._last_overlay_refresh = None
        self._overlay_view_state = None
        mujoco.mj_forward(self.model, self.data)
        self.step(.5)

    def ik(self, xyz, start=None):
        target = np.diag([1, -1, -1])
        start = self.command if start is None else start
        def residual(q):
            self.ikdata.qpos[:6] = q
            mujoco.mj_forward(self.model, self.ikdata)
            rotation = target @ self.ikdata.site_xmat[self.sid].reshape(3, 3).T
            return np.r_[self.ikdata.site_xpos[self.sid]-xyz, .3*Rotation.from_matrix(rotation).as_rotvec()]
        bounds = (self.model.jnt_range[:6, 0]+.001, self.model.jnt_range[:6, 1]-.001)
        result = least_squares(residual, start, bounds=bounds, xtol=1e-10, ftol=1e-10, gtol=1e-10, max_nfev=150)
        if np.linalg.norm(residual(result.x)) > 1e-4:
            raise RuntimeError(f'Unreachable tool pose: {xyz}')
        return result.x

    def step(self, seconds):
        for _ in range(round(seconds/self.model.opt.timestep)):
            interrupt = getattr(self, 'command_interrupt', None)
            if interrupt is not None:
                interrupt()
            # Ideal model-based gravity/Coriolis feedforward for arm and fingers.
            # The free objects receive no external support or scripted motion.
            self.data.qfrc_applied[:8] = self.data.qfrc_bias[:8]
            mujoco.mj_step(self.model, self.data)
            if self._push_watch is not None and not self._push_had_contact:
                source_id, pads = self._push_watch
                self._push_had_contact = any(
                    int(c.geom1) == source_id and int(c.geom2) in pads
                    or int(c.geom2) == source_id and int(c.geom1) in pads
                    for c in self.data.contact)
            if not np.all(np.isfinite(self.data.qpos)):
                raise RuntimeError('Nonfinite simulation state')
            record = getattr(self, 'record_callback', None)
            if record is not None:
                record(self)
            target_frame = int(self.data.time*self.config.fps)
            if target_frame > self.frames:
                self.frames = target_frame
                if self.renderer:
                    self.last_frame = self.render_frame(self.renderer)
                    self.writer.append_data(self.last_frame)
                if self.viewer:
                    started = time.monotonic()
                    self.refresh_view()
                    time.sleep(max(0., 1/self.config.fps-(time.monotonic()-started)))
                elif not self.renderer:
                    self.overlays.observe(self)

    def position(self, name):
        """Ground-truth object centre in world metres; no vision pipeline."""
        if name not in self.objects: raise ValueError(f'Unknown object: {name}')
        return self.data.body('obj_'+name).xpos.copy()

    @staticmethod
    def validate_tcp(xyz):
        xyz = np.asarray(xyz, dtype=float)
        if xyz.shape != (3,) or not np.isfinite(xyz).all() or not (.20 <= xyz[0] <= .60 and abs(xyz[1]) <= .30 and .01 <= xyz[2] <= .45):
            raise ValueError('TCP outside supported workspace')
        return xyz

    def move_to(self, xyz, duration=None):
        """Move TCP in metres, with fixed downward orientation and smooth waypoints."""
        xyz = self.validate_tcp(xyz)
        if duration is not None and (not np.isfinite(duration) or duration <= 0):
            raise ValueError('Duration must be positive and finite')
        start = self.data.site_xpos[self.sid].copy()
        duration = duration or max(.8, np.linalg.norm(xyz-start)/(self.config.speed_mm_s/1000)*1.5)
        n = int(np.ceil(duration/.02))
        for i in range(1, n+1):
            u = i/n
            smooth = 10*u**3-15*u**4+6*u**5
            self.command = self.ik(start+smooth*(xyz-start))
            self.data.ctrl[:6] = self.command
            self.step(.02)
        self.step(.3)

    def gripper(self, closed):
        self.data.ctrl[6:] = 0 if closed else .032
        self.step(.7)

    def push(self, name, dx, dy):
        """Simple tabletop push with closed fingers; all object motion is contact-driven."""
        if name not in self.objects:
            raise ValueError('Unknown object: '+name)
        delta = np.asarray([dx, dy], dtype=float)
        distance = np.linalg.norm(delta)
        if not np.isfinite(delta).all() or not .01 <= distance <= .12:
            raise ValueError('Push distance must be 0.01–0.12 m')
        before = self.position(name)
        spec = self.objects[name]
        if before[2] > spec.dimensions()[2]/2+.02:
            raise ValueError('push is for tabletop objects; use manual control to disturb a tower')
        direction = delta/distance
        radius = np.dot(np.abs(direction), np.array(spec.dimensions()[:2])/2)
        finger_radius = np.dot(np.abs(direction), [.018, .013])
        gap = .015
        start_xy = before[:2]-direction*(radius+finger_radius+gap)
        end_xy = start_xy+direction*(distance+gap)
        z = max(.02, min(.03, before[2]))
        waypoints = [[*start_xy, self.config.hover_z_m], [*start_xy, z],
                     [*end_xy, z], [*end_xy, self.config.hover_z_m]]
        seed = self.command.copy()
        for xyz in waypoints:
            self.validate_tcp(xyz)
            seed = self.ik(xyz, seed)
        self._push_watch = (self.model.geom(name+'_geom').id,
                            {self.model.geom(n+'_pad').id for n in ('left', 'right')})
        self._push_had_contact = False
        try:
            self.gripper(True)
            for xyz in waypoints:
                self.move_to(xyz)
            self.step(1)
        finally:
            self._push_watch = None
        after = self.position(name)
        return dict(object=name, requested_xy_m=delta.tolist(), before_m=before.tolist(),
                    after_m=after.tolist(), displacement_m=(after-before).tolist(),
                    finger_contact_seen=bool(self._push_had_contact))

    def record(self, label):
        positions = {name: self.position(name).tolist() for name in self.object_names}
        event = dict(phase=label, time_s=float(self.data.time), objects=positions)
        # Keep the previous red/blue log fields for existing reports.
        event.update({name: positions[name] for name in ('red', 'blue') if name in positions})
        self.events.append(event)
        print(label, positions, flush=True)

    def _pair(self, source, target):
        if source == target or source not in self.objects or target not in self.objects:
            raise ValueError('Choose two different objects from: '+', '.join(self.object_names))
        return self.objects[source], self.objects[target]

    def stack(self, source='red', target='blue'):
        """Stack a graspable cube/box on a cube/box, using finger contact."""
        src, dst = self._pair(source, target)
        if src.shape not in ('cube', 'box') or dst.shape not in ('cube', 'box'):
            raise ValueError('Automatic stacking supports cubes/boxes; spheres/cylinders are scene objects')
        dx, dy, dz = src.dimensions()
        if not (.03 <= dx <= .10 and .035 <= dy <= .05 and .035 <= dz <= .06):
            raise ValueError('Source exceeds tested gripper dimensions: x .03–.10, y .035–.05, z .035–.06 m')
        a, b = self.position(source), self.position(target)
        h = self.config.hover_z_m
        place_z = b[2]+(dz+dst.dimensions()[2])/2+.001
        if h < max(a[2], place_z)+.07:
            raise ValueError('Transport height too low for this stack; increase hover_z_m')
        self.gripper(False)
        self.move_to([a[0], a[1], h])
        self.move_to(a)
        self.gripper(True)
        self.record('grasp')
        self.move_to([a[0], a[1], h])
        self.record('lift')
        if self.position(source)[2] < h-.04:
            raise RuntimeError('Grasp failed: object did not lift')
        self.move_to([b[0], b[1], h])
        self.move_to([b[0], b[1], place_z])
        self.gripper(False)
        self.record('release')
        self.move_to([b[0], b[1], h])
        self.step(1)
        checks = self.check_stack(source, target)
        self.record('settled')
        return dict(success=all(checks), stable_checks=sum(checks), checks=len(checks), seed=self.config.seed,
                    source=source, target=target, events=self.events,
                    physics='MuJoCo contact dynamics; no attachment constraints',
                    robot='NEURA LARA 5 with generic parallel gripper',
                    model_variant='RoboDK-derived geometry and kinematics; approximate dynamics and collisions',
                    manufacturer_validated=False, simulation_seconds=float(self.data.time))

    def _touching(self, first, second):
        pair = {self.model.geom(first).id, self.model.geom(second).id}
        return any({int(c.geom1), int(c.geom2)} == pair for c in self.data.contact)

    def _stationary(self, name):
        start = self.model.jnt_dofadr[self.model.joint(name+'_free').id]
        # Same threshold as the previous two-cube evaluator.
        return np.linalg.norm(self.data.qvel[start:start+6]) < .02

    def _supported(self, name, seen):
        """A flat object must rest on the table or a contact-supported object below."""
        if name in seen or not self._stationary(name):
            return False
        spec = self.objects[name]
        if spec.shape not in ('cube', 'box'):
            return False
        pos = self.position(name)
        height = spec.dimensions()[2]
        if abs(pos[2]-height/2) < .003 and self._touching(name+'_geom', 'table'):
            return True
        for other, below in self.objects.items():
            if other == name or other in seen or below.shape not in ('cube', 'box'):
                continue
            base = self.position(other)
            distance = (height+below.dimensions()[2])/2
            if (abs(pos[2]-base[2]-distance) < .003
                    and np.linalg.norm(pos[:2]-base[:2]) < .004
                    and self._touching(name+'_geom', other+'_geom')
                    and self._supported(other, seen | {name})):
                return True
        return False

    def stack_diagnostics(self, source, target):
        """Shared numeric criteria for evaluation and the optional overlay."""
        src, dst = self._pair(source, target)
        a, b = self.position(source), self.position(target)
        distance = (src.dimensions()[2]+dst.dimensions()[2])/2
        xy_error = float(np.linalg.norm(a[:2]-b[:2]))
        height_error = float(abs(a[2]-b[2]-distance))
        d = dict(xy_error_m=xy_error, height_error_m=height_error,
                 shapes_ok=src.shape in ('cube', 'box') and dst.shape in ('cube', 'box'),
                 centered=xy_error < .004, height_ok=height_error < .003,
                 stationary=bool(self._stationary(source) and self._stationary(target)),
                 touching=self._touching(source+'_geom', target+'_geom'),
                 supported=self._supported(target, {source}))
        d['valid'] = all(d[k] for k in ('shapes_ok', 'centered', 'height_ok', 'stationary', 'touching', 'supported'))
        return d

    def is_stacked(self, source, target):
        return self.stack_diagnostics(source, target)['valid']

    def check_stack(self, source, target):
        """Twenty real samples over two simulation seconds, also driving the overlay."""
        self._pair(source, target)
        self.overlays.begin_check(source, target)
        try:
            for _ in range(20):
                self.step(.1)
                self.overlays.samples.append(self.is_stacked(source, target))
        finally:
            self.overlays.checking = False
            self.refresh_view(force=True)
            if self.renderer:
                # Include the completed result rather than leaving a 19/20 frame.
                self.last_frame = self.render_frame(self.renderer)
                self.writer.append_data(self.last_frame)
        return self.overlays.samples.copy()

    def close(self):
        if self.writer: self.writer.close()
        if self.renderer: self.renderer.close()
        if self.viewer: self.viewer.close()
