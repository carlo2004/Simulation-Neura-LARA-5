"""Prepare a local model for a portable scene with an explicit convex collider."""
from hashlib import sha256
from pathlib import Path
import numpy as np
from stacklab.config import ROOT, ObjectSpec, finite_number, write_json


def prepare_mesh(name, filename, xy, longest_m=.08, mass_kg=.06):
    import trimesh
    path = Path(filename).expanduser().resolve()
    if path.suffix.lower() not in ('.obj', '.stl', '.ply', '.glb'):
        raise ValueError('Supported mesh formats: OBJ, STL, PLY, GLB (uncompressed rigid geometry)')
    if not path.is_file() or not 0 < path.stat().st_size <= 25*1024*1024:
        raise ValueError('Mesh must be a local file of at most 25 MiB')
    if not finite_number(longest_m) or not .02 <= longest_m <= .12:
        raise ValueError('Longest mesh dimension must be 0.02–0.12 m')
    # Validate ordinary fields before parsing or writing an asset.
    ObjectSpec(name, xy_m=xy, mass_kg=mass_kg).validate()
    try:
        loaded = trimesh.load_scene(path, allow_remote=False, process=True, skip_materials=True)
        mesh = loaded.to_mesh()
        if path.suffix.lower() == '.glb':
            # glTF's +Y-up convention -> this simulation's +Z-up convention.
            mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2, [1, 0, 0]))
        if not 4 <= len(mesh.vertices) <= 100000 or not 4 <= len(mesh.faces) <= 200000:
            raise ValueError('Mesh must have 4–100000 vertices and 4–200000 triangles')
        if not np.isfinite(mesh.vertices).all():
            raise ValueError('Mesh contains nonfinite vertices')
        extents = mesh.extents
        if not np.isfinite(extents).all() or min(extents) <= 0:
            raise ValueError('Mesh must have positive finite extents in all three axes')
        dims = extents*(longest_m/max(extents))
        if not np.isfinite(dims).all() or min(dims) < .005:
            raise ValueError('After scaling, every mesh dimension must be at least 5 mm')
        # Canonical unit bounding box. MJCF applies the requested full dimensions.
        normalized = (mesh.vertices-mesh.bounds.mean(axis=0))/extents
        visual = trimesh.Trimesh(vertices=normalized, faces=mesh.faces, process=True)
        visual.fix_normals()
        hull = visual.convex_hull
        if not hull.is_volume or hull.volume <= 1e-6:
            raise ValueError('Mesh needs a nondegenerate 3D convex hull')
        visual_text = visual.export(file_type='obj', include_texture=False, include_color=False)
        hull_text = hull.export(file_type='obj', include_texture=False, include_color=False)
    except (ValueError, OSError):
        raise
    except Exception as e:
        raise ValueError('Could not prepare mesh: '+str(e)) from e
    digest = sha256(visual_text.encode()).hexdigest()[:20]
    directory = ROOT/'assets/objects'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory/(digest+'.obj')
    target.write_text(visual_text, encoding='utf-8')
    target.with_name(digest+'_hull.obj').write_text(hull_text, encoding='utf-8')
    write_json(directory/(digest+'.json'), dict(
        source_filename=path.name, source_sha256=sha256(path.read_bytes()).hexdigest(),
        conversion='Centred unit bounding box; textures discarded; GLB Y-up to Z-up',
        collision='Convex hull; cavities/concavities are filled',
        mass='User/default assumption, not inferred from source',
        vertices=len(visual.vertices), triangles=len(visual.faces), trimesh=trimesh.__version__))
    return ObjectSpec(name, shape='mesh', xy_m=xy, size_m=dims.tolist(), mass_kg=mass_kg,
                      mesh_file=target.relative_to(ROOT).as_posix()).validate()
