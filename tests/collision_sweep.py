"""Live preset x 4-style contact sweep.

Run via: blender --background --factory-startup --python-exit-code 1
         --python tests/collision_sweep.py
Writes a CSV under dist/ with penetration error, peak displacement and rebound.
"""
import csv
import importlib.util
import os
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('skin_jiggle', ROOT / 'skin_jiggle_physics.py')
sj = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sj)
sj.register()
ng = sj._build_core_group()
scene = bpy.context.scene
scene.render.fps = 24
scene.frame_start, scene.frame_end = 1, 84

# Closed broad floor. Its top face is exactly z=0.05 m.
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, -.95))
ground = bpy.context.object
ground.name = 'Sweep Ground Collider'
ground.scale = (12, 12, 1)
ground.modifiers.new('Collision', 'COLLISION')
ground.collision.thickness_outer = .004
ground.collision.cloth_friction = 56
ground.collision.damping = .95
ground['sj_managed_collider'] = True

quad_mesh = bpy.data.meshes.new('Sweep Tissue Quad')
quad_mesh.from_pydata([(-.08, -.08, 0), (.08, -.08, 0),
                       (.08, .08, 0), (-.08, .08, 0)], [], [(0, 1, 2, 3)])
styles = ('BODY', 'HAND', 'GRIP', 'STYLIZED')
cases = []
profile_specs = [(key, style) for key in sj.PRESETS for style in styles]
if os.environ.get('SJ_SWEEP_SINGLE'):
    profile_specs = [tuple(os.environ['SJ_SWEEP_SINGLE'].split(',', 1))]
for idx, key_style in enumerate(profile_specs):
    key, style = key_style
    ob = bpy.data.objects.new(f'Sweep_{idx:03d}', quad_mesh)
    scene.collection.objects.link(ob)
    ob.location = (((idx % 10) - 4.5) * .4,
                   ((idx // 10) - 4.5) * .4, .16)
    vg = ob.vertex_groups.new(name='Tissue')
    vg.add([0, 1, 2, 3], 1.0, 'REPLACE')
    mod = ob.modifiers.new('Live Collision Sweep', 'NODES')
    mod.node_group = ng
    sj._set_vertex_group(mod, ng, vg.name)
    sj._apply_preset(mod, ng, key)
    sj._apply_contact_style(mod, key, style)
    sj._set_value(mod, ng, 'Gravity', 0.0)
    sj._set_value(mod, ng, 'Fold Smoothing', 0.0)
    sj._set_value(mod, ng, 'Squash Spread', 0)
    sj._set_object(mod, ng, 'Reference Object', sj._ensure_ref_empty(ob))
    cases.append((key, style, ob, mod))

sj._sync_colliders(scene, force=True)
surface_z = .05
metrics = {id(case[2]): {'min_z': float('inf'), 'min_frame': 0,
                         'max_abs_motion': 0.0, 'max_rebound': 0.0}
           for case in cases}
for frame in range(1, 85):
    if frame <= 41:
        target_z = .16 - (frame - 1) * (.12 / 40)
    elif frame <= 52:
        target_z = .04
    elif frame <= 73:
        target_z = .04 + (frame - 52) * (.12 / 21)
    else:
        target_z = .16
    phase = 'press' if frame <= 41 else ('hold' if frame <= 52 else 'release')
    for _, _, ob, _ in cases:
        ob.location.z = target_z
    scene.frame_set(frame)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for key, style, ob, mod in cases:
        evaluated = ob.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        zvals = [(evaluated.matrix_world @ vert.co).z for vert in mesh.vertices]
        evaluated.to_mesh_clear()
        record = metrics[id(ob)]
        minimum = min(zvals)
        if minimum < record['min_z']:
            record['min_z'] = minimum
            record['min_frame'] = frame
        record['max_abs_motion'] = max(record['max_abs_motion'],
                                        abs(minimum - target_z))
        if phase == 'release':
            record['max_rebound'] = max(record['max_rebound'],
                                         max(0.0, minimum - target_z))

rows = []
expected_min_z = surface_z + .004
for key, style, ob, mod in cases:
    gap = sj._get_input(mod, sj._input_ident_map(ng)['Collision Distance'])
    clearance = expected_min_z + gap
    penetration = max(0.0, clearance - metrics[id(ob)]['min_z'])
    rows.append({
        'preset': sj.PRESETS[key][0], 'style': style,
        'clearance_mm': round(gap * 1000 + 4, 3),
        'max_penetration_mm': round(penetration * 1000, 4),
        'max_motion_mm': round(metrics[id(ob)]['max_abs_motion'] * 1000, 3),
        'release_overshoot_mm': round(metrics[id(ob)]['max_rebound'] * 1000, 3),
        'min_frame': metrics[id(ob)]['min_frame'],
    })

output = ROOT / 'dist' / f'collision_sweep_{sj.BUILD_TAG}.csv'
output.parent.mkdir(exist_ok=True)
with output.open('w', newline='', encoding='utf-8') as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
max_pen = max(row['max_penetration_mm'] for row in rows)
for row in sorted(rows, key=lambda item: item['max_penetration_mm'], reverse=True)[:5]:
    print(f"SJ_WORST: {row}", flush=True)
print(f'SJ_COLLISION_SWEEP: {len(rows)} live profiles, {scene.render.fps} fps, '
      f'{max_pen:.4f} mm max penetration; {output}', flush=True)
for style in styles:
    subset = [row for row in rows if row['style'] == style]
    if not subset:
        continue
    print(f"SJ_COLLISION_SWEEP: {style}: max penetration "
          f"{max(r['max_penetration_mm'] for r in subset):.4f} mm; mean travel "
          f"{sum(r['max_motion_mm'] for r in subset)/len(subset):.2f} mm; max "
          f"release overshoot "
          f"{max(r['release_overshoot_mm'] for r in subset):.2f} mm", flush=True)
sj.unregister()
assert rows, 'No collision profiles evaluated'
assert max_pen <= 0.1, f'Collision penetration {max_pen:.4f} mm exceeds 0.1 mm tolerance'
