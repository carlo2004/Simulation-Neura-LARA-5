"""Optional teaching overlays. These add rendering geoms, never physics bodies."""
from functools import lru_cache
from itertools import product
import mujoco
import numpy as np


COLORS = {
    'UNCHECKED': (.70, .73, .78, 1),
    'CHECKING': (1., .76, .20, 1),
    'PASS': (.18, .95, .42, 1),
    'FAIL': (1., .30, .26, 1),
    'INVALIDATED': (1., .30, .26, 1),
}


@lru_cache(maxsize=1)
def _font():
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size=16)
    except TypeError:  # Pillow 10.0 also works.
        return ImageFont.load_default()


class Overlays:
    def __init__(self, axes=False):
        self.axes = bool(axes)
        self.stack_pair = None
        self.clear_check()

    def clear_check(self):
        self.check_pair = None
        self.samples = []
        self.checking = False
        self.invalidated = False

    def begin_check(self, source, target):
        self.clear_check()
        self.check_pair = (source, target)
        self.checking = True
        if self.stack_pair is not None:
            self.stack_pair = self.check_pair

    def observe(self, robot):
        # A previous success is no longer current after disturbing the stack.
        if (not self.checking and not self.invalidated and len(self.samples) == 20
                and all(self.samples) and not robot.is_stacked(*self.check_pair)):
            self.invalidated = True

    def status(self):
        if self.check_pair != self.stack_pair or not self.samples and not self.checking:
            return 'UNCHECKED'
        if self.checking:
            return 'CHECKING'
        if self.invalidated:
            return 'INVALIDATED'
        return 'PASS' if len(self.samples) == 20 and all(self.samples) else 'FAIL'

    def panels(self, robot):
        """The same text is used in the native viewer and exported images/video."""
        panels = []
        if robot.manual.enabled:
            panels.append(('manual', robot.manual.panel()))
        if self.axes:
            p = robot.data.site_xpos[robot.sid]
            lines = ['WORLD COORDINATES [m]', 'Origin: robot base / table, z=0',
                     'X red | Y green | Z blue | grid 0.10 m',
                     '          X       Y       Z',
                     f'TCP   {p[0]: .3f}  {p[1]: .3f}  {p[2]: .3f}']
            for name in robot.object_names:
                p = robot.position(name)
                lines.append(f'{name:<8} {p[0]: .3f}  {p[1]: .3f}  {p[2]: .3f}')
            lines += ['Object coordinates = centres', 'axes off: hide']
            panels.append(('axes', '\n'.join(lines)))
        if self.stack_pair:
            source, target = self.stack_pair
            d = robot.stack_diagnostics(source, target)
            status = self.status()
            count = f'{sum(self.samples)}/{len(self.samples)}' if self.check_pair == self.stack_pair else '0/0'
            title = {
                'UNCHECKED': 'NOT CHECKED - grey frames',
                'CHECKING': f'CHECKING {len(self.samples)}/20 - amber frames',
                'PASS': 'PASS 20/20 - green frames',
                'FAIL': f'FAIL {count} - red frames',
                'INVALIDATED': 'CHANGED SINCE PASS - check again',
            }[status]
            yes = lambda value: 'OK' if value else 'NO'
            lines = [f'STACK CHECK: {source} on {target}', title,
                     f'Centres XY: {d["xy_error_m"]*1000:.2f} mm < 4 mm [{yes(d["centered"])}]',
                     f'Height error: {d["height_error_m"]*1000:.2f} mm < 3 mm [{yes(d["height_ok"])}]',
                     f'Contact: {yes(d["touching"])} | At rest: {yes(d["stationary"])}',
                     f'Support chain to table: {yes(d["supported"])}',
                     'PASS requires 20 samples / 2 simulation seconds',
                     f'check {source} {target} | stackviz off: hide']
            panels.append(('stack', '\n'.join(lines)))
        return panels

    def viewer_texts(self, robot):
        return [(mujoco.mjtFont.mjFONT_SHADOW,
                 {'axes': mujoco.mjtGridPos.mjGRID_TOPRIGHT,
                  'manual': mujoco.mjtGridPos.mjGRID_TOPLEFT,
                  'stack': mujoco.mjtGridPos.mjGRID_BOTTOMLEFT}[kind],
                 text, '') for kind, text in self.panels(robot)]

    def annotate(self, frame, robot):
        panels = self.panels(robot)
        if not panels:
            return frame
        from PIL import Image, ImageDraw
        image = Image.fromarray(frame).convert('RGBA')
        layer = Image.new('RGBA', image.size)
        draw = ImageDraw.Draw(layer)
        for kind, text in panels:
            bounds = draw.multiline_textbbox((0, 0), text, font=_font(), spacing=4)
            w, h = bounds[2]+20, bounds[3]+20
            x = image.width-w-12 if kind == 'axes' else 12
            y = image.height-h-12 if kind == 'stack' else 12
            draw.rounded_rectangle((x, y, x+w, y+h), radius=7, fill=(18, 24, 32, 230))
            draw.multiline_text((x+10, y+10), text, font=_font(), spacing=4, fill=(235, 240, 245, 255))
        return np.asarray(Image.alpha_composite(image, layer).convert('RGB'))

    def draw(self, scene, robot, clear=False):
        if clear:
            scene.ngeom = 0

        def geom(kind, pos, size=(0, 0, 0), color=(1, 1, 1, 1), label=''):
            if scene.ngeom >= scene.maxgeom:
                raise RuntimeError('Overlay exceeds rendering geometry capacity')
            g = scene.geoms[scene.ngeom]
            mujoco.mjv_initGeom(g, kind, size, pos, np.eye(3).ravel(), color)
            g.category = mujoco.mjtCatBit.mjCAT_DECOR
            g.label = label
            scene.ngeom += 1
            return g

        def line(a, b, color, width=2, arrow=False):
            kind = mujoco.mjtGeom.mjGEOM_ARROW if arrow else mujoco.mjtGeom.mjGEOM_LINE
            g = geom(kind, a, color=color)
            mujoco.mjv_connector(g, kind, width, np.asarray(a), np.asarray(b))

        def label(pos, text, color=(.94, .96, 1, 1)):
            geom(mujoco.mjtGeom.mjGEOM_LABEL, pos, color=color, label=text)

        if robot.manual.enabled and robot.manual.selected is not None:
            point = robot.manual.selected
            geom(mujoco.mjtGeom.mjGEOM_SPHERE, point, (.006, 0, 0), (1, .8, .2, 1))
            line(point, point+[0, 0, .05], (1, .8, .2, 1), 1)
            label(point+[0, 0, .065], 'Selected')

        if self.axes:
            # Lift the XY drawing 2 mm above the plane to avoid z-fighting.
            origin = np.array([0., 0., .002])
            for delta, text, color in [((.66, 0, 0), '+X [m]', (1, .22, .20, 1)),
                                       ((0, .36, 0), '+Y [m]', (.22, 1, .34, 1)),
                                       ((0, 0, .44), '+Z [m]', (.25, .52, 1, 1))]:
                end = origin+delta
                line(origin, end, color, .006, arrow=True)
                label(end+[0, 0, .015], text, color)
            line([0, -.34, .002], origin, (.22, 1, .34, 1))
            for x in np.arange(.2, .601, .1):
                line([x, -.3, .0015], [x, .3, .0015], (.48, .54, .63, 1), 1)
                label([x, -.35, .005], f'{x:.1f}', (1, .65, .62, 1))
            for y in np.arange(-.3, .301, .1):
                line([.2, y, .0015], [.6, y, .0015], (.48, .54, .63, 1), 1)
                label([.64, y, .005], f'{0. if abs(y) < 1e-8 else y:.1f}', (.62, 1, .68, 1))
            p = robot.data.site_xpos[robot.sid].copy()
            geom(mujoco.mjtGeom.mjGEOM_SPHERE, p, (.005, 0, 0), (.25, .95, 1, 1))
            label(p+[0, 0, .025], 'TCP')
            for name, spec in robot.objects.items():
                label(robot.position(name)+[0, 0, spec.dimensions()[2]/2+.018], name)

        if self.stack_pair:
            color = COLORS[self.status()]
            for name in self.stack_pair:
                body = robot.data.body('obj_'+name)
                half = np.array(robot.objects[name].dimensions())/2+.002
                signs = np.array(list(product((-1, 1), repeat=3)))
                corners = (signs*half) @ body.xmat.reshape(3, 3).T+body.xpos
                for i in range(8):
                    for j in range(i+1, 8):
                        if np.count_nonzero(signs[i] != signs[j]) == 1:
                            line(corners[i], corners[j], color, 3)
            a, b = [robot.position(name) for name in self.stack_pair]
            line(a, b, color, 2)
