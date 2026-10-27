"""Rebuild the supplied model from the pinned public RoboDK LARA 5 file.

The .robot binary layout is inferred. Only the exact source checksum is accepted.
No RoboDK runtime or internet is needed. This importer is not manufacturer certified.
"""
import pathlib, struct, json, hashlib, zlib
import numpy as np
import xml.etree.ElementTree as E
from scipy.spatial.transform import Rotation
ROOT = pathlib.Path(__file__).resolve().parent
EXPECTED_SHA = '4dc8df5ff0e8396c86a2388f9f0a582ba3d8c34c9a310fb8f98d290a25dee3c3'

def convert(*, preserve_definition=False):
    source_bytes = (ROOT/'source/Neura-LARA-5.robot').read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != EXPECTED_SHA:
        raise ValueError('Unrecognized source version: refusing to guess its layout')
    raw = zlib.decompress(source_bytes[4:])
    assert len(raw) == struct.unpack('>I', source_bytes[:4])[0]
    h = np.frombuffer(raw[:32000], dtype='<f8')
    assert h[1] == 4000 and h[21] == 6 and h[22] == 7
    assert ''.join(chr(int(x)) for x in h[1800:1900] if x) == 'Neura LARA 5'
    dh = h[200:320].reshape(6, 20)[:, :4]
    np.testing.assert_array_equal(dh, h[2200:2320].reshape(6, 20)[:, :4])
    limits = np.array([h[600:606], h[620:626]]).T
    assert np.all(limits[:, 0] < limits[:, 1])
    assert struct.unpack_from('<Q', raw, 32000)[0] == 7
    links = []
    offset = 32008
    for link in range(7):
        count = struct.unpack_from('<Q', raw, offset)[0]
        offset += 8
        surfaces = []
        for surface in range(count):
            nt, *rgba = struct.unpack_from('<Q4f', raw, offset)
            offset += 24
            assert 0 < nt < 1000000
            ar = np.ndarray(nt*3, dtype=[('p', '<f4', 3), ('n', '<u2')], buffer=raw, offset=offset)
            offset += nt*42
            verts = ar['p'].copy().reshape(nt, 3, 3)
            assert np.isfinite(verts).all()
            # Interpret the packed spherical normals to orient the triangle faces.
            packed = ar['n'].astype(float)
            az = np.floor(packed/256)*2*np.pi/255
            polar = np.mod(packed, 256)*np.pi/255
            normals = np.array([np.cos(az)*np.sin(polar), np.sin(az)*np.sin(polar), np.cos(polar)]).T.reshape(nt, 3, 3).mean(1)
            cross = np.cross(verts[:, 1]-verts[:, 0], verts[:, 2]-verts[:, 0])
            flip = np.sum(normals*cross, axis=1) < 0
            verts[flip] = verts[flip][:, [0, 2, 1]]
            surfaces.append((rgba, verts.reshape(-1, 3)))
        assert raw[offset:offset+16] == bytes(16)
        offset += 16
        links.append(surfaces)
    assert offset == len(raw)
    rootpath = ROOT/'models/lara5'
    (rootpath/'assets').mkdir(parents=True, exist_ok=True)
    root = E.Element('mujoco', model='NEURA_LARA_5_RoboDK_derived')
    E.SubElement(root, 'compiler', angle='radian', meshdir='assets', autolimits='true')
    E.SubElement(root, 'option', integrator='implicitfast')
    default = E.SubElement(root, 'default')
    E.SubElement(default, 'joint', damping='1', armature='.05')
    asset = E.SubElement(root, 'asset')
    world = E.SubElement(root, 'worldbody')
    acts = E.SubElement(root, 'actuator')
    body = E.SubElement(world, 'body', name='base')
    # Assumed per-link masses and bounding-box inertias; not manufacturer data.
    masses = [3.5, 4, 6, 3.5, 3, 2, 1]
    params = dict(model='NEURA LARA 5', source='https://cdn.robodk.com/downloads-library/library-robots/Neura-LARA-5.robot',
                  sha256=hashlib.sha256(source_bytes).hexdigest(),
                  dh_columns=['alpha_rad', 'a_mm', 'theta_offset_rad', 'd_mm'],
                  modified_dh=dh.tolist(), limits_deg=limits.tolist(), assumed_masses_kg=masses,
                  manufacturer_validated=False,
                  notes='Geometries and kinematic parameters decoded from the pinned RoboDK model. Masses, inertias, collision proxies and control gains are assumptions. Import is not independently checked against a real controller.')
    for i, surfaces in enumerate(links):
        if i:
            alpha, aa, theta, dd = dh[i-1]
            rx = Rotation.from_rotvec([alpha, 0, 0])
            rz = Rotation.from_rotvec([0, 0, theta])
            quat = (rx*rz).as_quat()[[3, 0, 1, 2]]
            pos = rx.apply([aa/1000, 0, dd/1000])
            body = E.SubElement(body, 'body', name=f'link{i}', pos=' '.join(map(str, pos)), quat=' '.join(map(str, quat)))
            E.SubElement(body, 'joint', name=f'joint{i}', axis='0 0 1', range=' '.join(map(str, np.radians(limits[i-1]))))
            E.SubElement(acts, 'position', name=f'joint{i}', joint=f'joint{i}', kp='2000' if i<4 else '500', kv='180' if i<4 else '50', forcerange='-150 150' if i<4 else '-30 30')
        points = np.concatenate([v for col, v in surfaces])/1000
        lo, hi = points.min(0), points.max(0)
        com, span = (lo+hi)/2, hi-lo
        inertia = masses[i]/12*np.array([span[1]**2+span[2]**2, span[0]**2+span[2]**2, span[0]**2+span[1]**2])
        E.SubElement(body, 'inertial', mass=str(masses[i]), pos=' '.join(map(str, com)), diaginertia=' '.join(map(str, inertia)))
        colors = {tuple(np.round(col, 5)) for col, v in surfaces}
        for j, color in enumerate(sorted(colors)):
            triangles = np.concatenate([v for col, v in surfaces if tuple(np.round(col, 5)) == color])/1000
            vertices, ids = np.unique(triangles, axis=0, return_inverse=True)
            faces = ids.reshape(-1, 3)+1
            filename = f'link{i}_{j}.obj'
            with (rootpath/'assets'/filename).open('w') as f:
                for xyz in vertices: f.write('v '+' '.join(f'{x:.8f}' for x in xyz)+'\n')
                for indices in faces: f.write('f '+' '.join(map(str, indices))+'\n')
            name = f'link{i}_{j}'
            E.SubElement(asset, 'mesh', name=name, file=filename)
            E.SubElement(body, 'geom', type='mesh', mesh=name, rgba=' '.join(map(str, color)), contype='0', conaffinity='0', group='2')
        # Capsule/sphere approximations for contact, separated from visual meshes.
        axis = int(np.argmax(span))
        radius = float(min(np.delete(span, axis))/2*.85)
        p0, p1 = com.copy(), com.copy()
        p0[axis], p1[axis] = lo[axis]+radius, hi[axis]-radius
        if np.linalg.norm(p1-p0) < .005:
            E.SubElement(body, 'geom', name=f'collision{i}', type='sphere', pos=' '.join(map(str, com)), size=str(radius), group='3', rgba='.6 .5 .1 .2')
        else:
            E.SubElement(body, 'geom', name=f'collision{i}', type='capsule', fromto=' '.join(map(str, np.r_[p0, p1])), size=str(radius), group='3', rgba='.6 .5 .1 .2')
    E.SubElement(body, 'site', name='attachment_site', size='.002')
    contact = E.SubElement(root, 'contact')
    E.SubElement(contact, 'exclude', body1='base', body2='link1')
    E.indent(root)
    if not preserve_definition or not (rootpath/'lara5.xml').is_file():
        E.ElementTree(root).write(rootpath/'lara5.xml', encoding='unicode')
    if not preserve_definition or not (rootpath/'parameters.json').is_file():
        (rootpath/'parameters.json').write_text(json.dumps(params, indent=2)+'\n')
    print('Converted LARA 5:', len(links), 'links,', sum(len(v)//3 for s in links for c, v in s), 'triangles')

if __name__ == '__main__': convert()
