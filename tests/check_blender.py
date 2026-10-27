"""Run with Blender --background --factory-startup --python tests/check_blender.py."""
import importlib.util
import math
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('skin_jiggle', ROOT / 'skin_jiggle_physics.py')
sj = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sj)
sj.register()
ng = sj._build_core_group()
assert ng.get('sj_build') == sj.BUILD_TAG
assert sj._build_core_group() is ng
for key, (_, values) in sj.PRESETS.items():
    spec_values = sj._PRESET_SPECS[key]
    f, zeta = spec_values[1:3]
    kn = values['Stiffness'] * max(1 - values['Normal Softness'], .02)
    omega = math.sqrt(kn / values['Mass'])
    assert math.isclose(omega / (2 * math.pi), f)
    assert math.isclose(values['Damping'] / (2 * omega), zeta)
    for name, _, _, lo, hi, _, _ in sj._SOCKET_DEFS:
        if name in values and lo is not None:
            assert lo <= values[name] <= hi, (key, name, values[name])
    # At 24 fps presets should run at their requested stiffness.
    dt = 1 / (24 * values['Substeps'])
    assert values['Stiffness'] <= values['Mass'] * (1.2 / dt)**2
    assert key in sj._CONTACT_PRESET_BASE
    gap, friction, squash, object_bounce, spread = sj._CONTACT_PRESET_BASE[key]
    assert .0005 <= gap <= .003 and 0 <= friction <= 1
    assert 0 <= object_bounce <= 1 and 0 <= spread <= 16 and squash <= 5

print('SJ_CHECK: built', len(ng.nodes), 'nodes;', len(sj.PRESETS), 'presets valid', flush=True)

def mesh_object(name, coords, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(coords, [], faces)
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def layer(ob, weights, preset='SOFT_SKIN'):
    vg = ob.vertex_groups.new(name='Tissue')
    for i, weight in enumerate(weights):
        if weight:
            vg.add([i], weight, 'REPLACE')
    mod = ob.modifiers.new('SkinJiggle_test', 'NODES')
    mod.node_group = ng
    sj._set_vertex_group(mod, ng, vg.name)
    sj._apply_preset(mod, ng, preset)
    sj._set_object(mod, ng, 'Reference Object', sj._ensure_ref_empty(ob))
    return mod


def values(mod, **params):
    for name, value in params.items():
        sj._set_value(mod, ng, name.replace('_', ' '), value)
    mod.id_data.update_tag()


def positions(ob):
    bpy.context.view_layer.update()
    evaluated = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    coords = [evaluated.matrix_world @ v.co for v in mesh.vertices]
    evaluated.to_mesh_clear()
    return coords


scene = bpy.context.scene
scene.render.fps = 24
scene.frame_start = 1
scene.frame_end = 30
quad = [(-.1, -.1, 0), (.1, -.1, 0), (.1, .1, 0), (-.1, .1, 0)]
ob = mesh_object('Mask and limit', quad, [(0, 1, 2, 3)])
mod = layer(ob, [0, 1, 1, 1])
values(mod, Floor_Collision=True, Floor_Height=.05, Max_Stretch=.025,
       Fold_Smoothing=.7, Squash_Amount=3.0)
for frame in range(1, 8):
    scene.frame_set(frame)
    coords = positions(ob)
assert abs(coords[0].z) < 1e-6, ('unpainted vertex moved', coords[0])
assert coords[1].z > .01, ('simulation did not advance', coords)
# The floor needs 50 mm of travel, Max Stretch allows 25 mm of jiggle:
# Contact Reach (default 100 mm) lets the collision win instead of clipping.
reach = mod[sj._input_ident_map(ng)['Contact Reach']]
assert all(v.z >= .05 - 1e-4 for v in coords[1:]), ('skin clipped through floor', coords)
assert all((v - ob.matrix_world @ ob.data.vertices[i].co).length <= .025 + reach + 1e-5
           for i, v in enumerate(coords)), ('contact reach exceeded', coords)
# With no Contact Reach, Max Stretch is still the hard limit.
values(mod, Contact_Reach=0.0)
scene.frame_set(1)
for frame in range(2, 8):
    scene.frame_set(frame)
    coords = positions(ob)
assert all((v - ob.matrix_world @ ob.data.vertices[i].co).length <= .02501
           for i, v in enumerate(coords)), ('stretch exceeded', coords)
values(mod, Contact_Reach=reach)
for strength in (0.0, 0.25, 1.0):
    values(mod, Blend=strength)
    scene.frame_set(1)
    for frame in range(2, 8):
        scene.frame_set(frame)
        coords = positions(ob)
    assert abs(coords[0].z) < 1e-6, ('Strength moved pinned vertex', strength)
    assert all(v.z >= .05 - 1e-4 for v in coords[1:]), ('Strength weakened floor contact', strength, coords)
print('SJ_CHECK: playback, pinned mask, contact reach and stretch limit pass', flush=True)

# Duplicated modifiers can inherit explicit bake paths. Keep the original's
# cache and assign independent storage to the copy, stable across calls.
bake_copy = ob.copy()
bpy.context.scene.collection.objects.link(bake_copy)
mod.bake_directory = '//sj_bake/shared_test/'
copy_bake_mod = sj._jiggle_modifiers(bake_copy)[0]
copy_bake_mod.bake_directory = mod.bake_directory
sj._ensure_bake_dirs([bake_copy])
assert copy_bake_mod.bake_directory != mod.bake_directory
copy_path = copy_bake_mod.bake_directory
sj._ensure_bake_dirs([ob, bake_copy])
assert copy_bake_mod.bake_directory == copy_path
assert mod.bake_directory == '//sj_bake/shared_test/'
bpy.data.objects.remove(bake_copy, do_unlink=True)
# Baked first, copied afterwards: preparing the ORIGINAL again (re-bake,
# Delete Bake) must keep its folder, which holds the bake; the copy moves.
mod.bake_directory = '//sj_bake/original_test/'
sj._ensure_bake_dirs([ob])
bake_copy = ob.copy()
bpy.context.scene.collection.objects.link(bake_copy)
copy_bake_mod = sj._jiggle_modifiers(bake_copy)[0]
# Blender 4.2+ clears the folder on copy; share it as an inherited one would
copy_bake_mod.bake_directory = mod.bake_directory
sj._ensure_bake_dirs([ob])
assert mod.bake_directory == '//sj_bake/original_test/', mod.bake_directory
sj._ensure_bake_dirs([bake_copy])
assert copy_bake_mod.bake_directory != mod.bake_directory
copy_path = copy_bake_mod.bake_directory
sj._ensure_bake_dirs([ob, bake_copy])
assert copy_bake_mod.bake_directory == copy_path
assert mod.bake_directory == '//sj_bake/original_test/'
bpy.data.objects.remove(bake_copy, do_unlink=True)
print('SJ_CHECK: copied bake paths separated and stable', flush=True)

for key, (_, preset_values) in sj.PRESETS.items():
    sj._apply_preset(mod, ng, key)
    assert mod['sj_body_preset'] == key
    for style in ('BODY', 'HAND', 'GRIP', 'STYLIZED'):
        sj._apply_contact_style(mod, key, style)
        assert mod['sj_contact_style'] == style
        actual_gap = mod[sj._input_ident_map(ng)['Collision Distance']]
        assert 0 <= actual_gap <= .01
print(f'SJ_CHECK: all {len(sj.PRESETS) * 4} body/contact profile combinations load', flush=True)

# Reset All must reset the preset and contact labels with the values, or the
# panel shows the old preset and Contact Style uses its contact defaults.
sj._apply_preset(mod, ng, 'CHEST_D')
sj._apply_contact_style(mod, 'CHEST_D', 'STYLIZED')
bpy.context.view_layer.objects.active = ob
assert bpy.ops.skin_jiggle.reset_defaults() == {'FINISHED'}
assert mod['sj_body_preset'] == 'SOFT_SKIN', mod['sj_body_preset']
assert mod['sj_contact_style'] == 'BODY', mod['sj_contact_style']
assert sj._preset_label(mod) == 'Soft Skin'
idents = sj._input_ident_map(ng)
for name, value in sj.PRESETS['SOFT_SKIN'][1].items():
    assert math.isclose(mod[idents[name]], value, rel_tol=1e-5), (name, mod[idents[name]], value)
print('SJ_CHECK: Reset All restores Soft Skin values and labels', flush=True)

scene.cursor.location = (5, 5, 5)
assert bpy.ops.skin_jiggle.add_collider('EXEC_DEFAULT') == {'FINISHED'}
added = next(ob for ob in scene.objects if ob.get('sj_managed_collider'))
assert added.type == 'MESH' and any(m.type == 'COLLISION' for m in added.modifiers)
assert math.isclose(added.collision.thickness_outer, .004, abs_tol=1e-6), added.collision.thickness_outer
assert math.isclose(added.collision.cloth_friction, 56.0, abs_tol=1e-6), added.collision.cloth_friction
print('SJ_CHECK: add collider operator creates a tuned hand proxy', flush=True)

# Objects sharing a mesh must retain separate evaluated collider settings.
a = mesh_object('Collider A', quad, [(0, 1, 2, 3)])
b = bpy.data.objects.new('Collider B', a.data)
scene.collection.objects.link(b)
for collider, thickness in ((a, .01), (b, .04)):
    collider.modifiers.new('Collision', 'COLLISION')
    collider.collision.thickness_outer = thickness
    sj._stamp_collider(collider)
assert a.data is b.data
assert a.data.attributes.get('sj_set') is None
for collider, thickness in ((a, .01), (b, .04)):
    bpy.context.view_layer.update()
    evaluated = collider.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    assert math.isclose(mesh.attributes['sj_set'].data[0].vector.x,
                        thickness, abs_tol=1e-6)
    evaluated.to_mesh_clear()
col1, _ = sj._sync_colliders(scene)
other = bpy.data.scenes.new('Other scene')
col2, count = sj._sync_colliders(other)
assert col1 is not col2 and count == 0 and len(col2.objects) == 0
assert a in list(col1.objects) and b in list(col1.objects)
print('SJ_CHECK: shared mesh settings and scene isolation pass', flush=True)

# Duplicate object must never delete its original's cage.
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
cage, error = sj._create_layer_cage(bpy.context, ob, mod, 1.0)
assert cage is not None, error
# A cage sharing the layer's bake folder: the layer keeps it, the cage
# moves, and syncing cage settings back must not hand ownership over.
cage_mod = cage.modifiers[mod.name]
cage_mod.bake_directory = mod.bake_directory
layer_path = mod.bake_directory
sj._ensure_bake_dirs([ob])
assert mod.bake_directory == layer_path, mod.bake_directory
sj._ensure_bake_dirs([cage])
assert cage_mod.bake_directory != layer_path
sj._sync_layer_params(cage, ob)
sj._ensure_bake_dirs([ob])
assert mod.bake_directory == layer_path, mod.bake_directory
print('SJ_CHECK: preview cage never takes its layer\'s bake folder', flush=True)
copy = ob.copy()
scene.collection.objects.link(copy)
copy_mod = sj._jiggle_modifiers(copy)[0]
assert sj._layer_cage(copy_mod) is None
sj._delete_layer_cage(copy_mod)
assert sj._layer_cage(mod) is cage
ob.name = 'Renamed source'
mod.name = 'Renamed layer'
assert sj._cage_source(cage) == (ob, mod.name)
sj._delete_layer_cage(mod)
print('SJ_CHECK: cage duplicate ownership and rename pass', flush=True)

# Legacy operator retry must propagate errors to the outer UI handler.
calls = []
def fake_cache(**kwargs):
    calls.append(kwargs)
    if kwargs:
        raise TypeError('legacy signature')
    raise RuntimeError('expected fallback error')
try:
    sj._call_cache_operator(fake_cache)
except RuntimeError as exc:
    assert str(exc) == 'expected fallback error'
else:
    raise AssertionError('fallback failure was swallowed')
assert calls == [{'selected': False}, {}]
try:
    sj._call_cache_operator(lambda **kwargs: {'CANCELLED'})
except RuntimeError:
    pass
else:
    raise AssertionError('cancelled bake reported success')
print('SJ_CHECK: cache failures propagate correctly', flush=True)

collision_scene = bpy.data.scenes.new('World collision check')
bpy.context.window.scene = collision_scene
bpy.ops.mesh.primitive_cube_add(size=2)
box = bpy.context.object
box.scale = (5, 5, .1)
box.modifiers.new('Collision', 'COLLISION')
box.collision.thickness_outer = .02
probes = []
for index, scale in enumerate(((1, 1, 1), (.5, 2, 3))):
    probe = mesh_object('Scaled probe', quad, [(0, 1, 2, 3)])
    probe.location = (-1 + 2 * index, 0, .11)
    probe.scale = scale
    pm = layer(probe, [1] * 4)
    values(pm, Gravity=0, Fold_Smoothing=0, Squash_Amount=0,
           Max_Stretch=.2, Collision_Distance=.002, Blend=0.25 * index)
    probes.append(probe)
sj._sync_colliders(collision_scene)
for frame in range(1, 10):
    collision_scene.frame_set(frame)
    for probe in probes:
        result = positions(probe)
        if frame == 9:
            assert all(abs(p.z - .122) < .0001 for p in result), (probe.scale[:], result)
print('SJ_CHECK: world collision gap invariant under nonuniform scale', flush=True)

for fps in (24, 60):
    motion_scene = bpy.data.scenes.new('Timing ' + str(fps))
    motion_scene.render.fps = fps
    bpy.context.window.scene = motion_scene
    probe = mesh_object('Motion probe', quad, [(0, 1, 2, 3)])
    pm = layer(probe, [1] * 4)
    values(pm, Gravity=0, Fold_Smoothing=0, Squash_Amount=0,
           Object_Collision=False, Max_Stretch=.2)
    offsets = []
    amplitude, drive_hz = .02, 1.0
    for frame in range(1, fps * 4 + 2):
        t = (frame - 1) / fps
        probe.location.z = amplitude * math.sin(2 * math.pi * drive_hz * t)
        motion_scene.frame_set(frame)
        p = positions(probe)[0]
        if 3 <= t < 4:
            offsets.append(p.z - probe.location.z)
    measured = math.sqrt(2 * sum(x*x for x in offsets) / len(offsets))
    # Relative damped spring frequency response, x'' + d(x'-y') + w²(x-y)=0.
    ratio, zeta = drive_hz / 4.0, .5
    expected = amplitude * ratio**2 / math.sqrt((1-ratio**2)**2 + (2*zeta*ratio)**2)
    assert abs(measured / expected - 1) < .15, (fps, measured, expected)
    print('SJ_CHECK: forced response', fps, 'fps:', round(measured, 6),
          'm; analytic:', round(expected, 6), 'm', flush=True)

sj.unregister()
