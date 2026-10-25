"""Jiggle-bone regression suite.

Run with: blender --background --factory-startup --python-exit-code 1
          --python tests/check_bones.py
"""
import importlib.util
import math
import os
from pathlib import Path
import tempfile

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sjp", ROOT / "skin_jiggle_physics.py")
sjp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sjp)
sjp.register()
tmpdir = tempfile.mkdtemp(prefix="sj_bones_")
scene = bpy.context.scene
scene.render.fps = 24
scene.frame_start, scene.frame_end = 1, 60
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(f"SJ_BONES {'PASS' if ok else 'FAIL'} {name} {detail}")


for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

# rig: Chest -> Breast -> BreastTip chain, plus a Hand bone
arm = bpy.data.objects.new("Rig", bpy.data.armatures.new("Rig"))
scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
eb = arm.data.edit_bones
chest = eb.new("Chest"); chest.head, chest.tail = (0, 0, 1.0), (0, 0, 1.4)
br = eb.new("Breast"); br.head, br.tail = (0, -0.10, 1.30), (0, -0.20, 1.30); br.parent = chest
tip = eb.new("BreastTip"); tip.head, tip.tail = (0, -0.20, 1.30), (0, -0.28, 1.30)
tip.parent = br; tip.use_connect = True
hand = eb.new("Hand"); hand.head, hand.tail = (0.3, 0, 1.0), (0.3, 0, 0.9)
bpy.ops.object.mode_set(mode='OBJECT')

# body deformed by the rig, Collision on
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.2, location=(0, 0, 1.25))
body = bpy.context.object
body.name = "Body"
body.vertex_groups.new(name="Chest").add(range(len(body.data.vertices)), 1.0, 'REPLACE')
body.modifiers.new("Armature", 'ARMATURE').object = arm
body.parent = arm
body.modifiers.new("Collision", 'COLLISION')

# chest rises 0.3 m/s for 9 frames then stops
pc = arm.pose.bones["Chest"]
pc.location = (0, 0, 0); pc.keyframe_insert("location", index=1, frame=1)
pc.location = (0, 0.3 * 9 / 24, 0); pc.keyframe_insert("location", index=1, frame=10)
act = arm.animation_data.action
fcs = getattr(act, "fcurves", None)
if fcs is None:
    from bpy_extras import anim_utils
    fcs = anim_utils.action_get_channelbag_for_slot(act, arm.animation_data.action_slot).fcurves
for fc in fcs:
    for kp in fc.keyframe_points:
        kp.interpolation = 'LINEAR'
pc.location = (0, 0, 0)

# 1 operator path in Pose Mode with two selected bones
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='POSE')
for b in arm.data.bones:
    target = arm.pose.bones[b.name] if hasattr(arm.pose.bones[b.name], "select") else b
    target.select = b.name in {"Breast", "BreastTip"}
arm.data.bones.active = arm.data.bones["Breast"]
r = bpy.ops.skin_jiggle.add_bone_jiggle(preset='JELLY')
bones = [pb.name for pb in sjp._jiggle_bones(arm)]
check("operator adds two jiggle bones in Pose Mode", r == {'FINISHED'} and
      sorted(bones) == ["Breast", "BreastTip"], str(bones))
bpy.ops.object.mode_set(mode='OBJECT')
h_br = sjp._bone_helper(arm.pose.bones["Breast"])
h_tip = sjp._bone_helper(arm.pose.bones["BreastTip"])
check("helpers parented to each bone's parent",
      h_br.parent_bone == "Chest" and h_tip.parent_bone == "Breast",
      f"{h_br.parent_bone}, {h_tip.parent_bone}")
check("body with Collision is not a collider (no cycle)",
      not sjp._is_collider(body))

# 2 every preset converts to an isotropic bone spring
bad = []
mod = sjp._jiggle_modifiers(h_br)[0]
ng = mod.node_group
im = sjp._input_ident_map(ng)
for key, (_, vals) in sjp.PRESETS.items():
    r = bpy.ops.skin_jiggle.apply_preset(modifier_name=mod.name,
                                         object_name=h_br.name, preset=key)
    want = vals['Stiffness'] * max(1 - vals['Normal Softness'], .02)
    if (r != {'FINISHED'} or abs(mod[im['Stiffness']] - want) > 1e-3
            or mod[im['Normal Softness']] != 0.0 or mod['sj_body_preset'] != key):
        bad.append(key)
check("all presets apply to a bone as isotropic springs", not bad,
      f"{len(sjp.PRESETS) - len(bad)}/{len(sjp.PRESETS)}")
r = bpy.ops.skin_jiggle.contact_style(modifier_name=mod.name,
                                      object_name=h_br.name, style='GRIP')
check("contact style targets the bone's helper",
      r == {'FINISHED'} and mod['sj_contact_style'] == 'GRIP')
bpy.ops.skin_jiggle.apply_preset(modifier_name=mod.name, object_name=h_br.name,
                                 preset='JELLY')
for h in (h_br, h_tip):
    m = sjp._jiggle_modifiers(h)[0]
    sjp._set_value(m, m.node_group, "Gravity", 0.0)
    h.update_tag()

# 3 hand collider bone-parented to the same rig, in front of the tip
bpy.context.scene.cursor.location = (0, -0.30, 1.30)
bpy.ops.skin_jiggle.add_collider()
handc = next(o for o in scene.objects if o.get('sj_managed_collider'))
handc.scale = (1, 1, 1)
mw = handc.matrix_world.copy()
handc.parent = arm; handc.parent_type = 'BONE'; handc.parent_bone = "Hand"
bpy.context.view_layer.update(); handc.matrix_world = mw
col, n = sjp._sync_colliders(scene, force=True)
check("bone-parented hand collider stays a collider", handc.name in col.objects,
      str([o.name for o in col.objects]))

# 4 simulate: chain moves, tip respects the collider, no cycle
amp = {"Breast": 0.0, "BreastTip": 0.0}
inside_helper, inside_tail = 9.0, 9.0


def ellipsoid(world_pt, ob_eval):
    # collider is a 0.06 m sphere scaled (1, .72, .42): >= 1 means outside
    loc = ob_eval.matrix_world.inverted() @ world_pt
    return math.sqrt((loc.x / .06) ** 2 + (loc.y / .06) ** 2 + (loc.z / .06) ** 2)


swing = []
for f in range(1, 61):
    scene.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    ae = arm.evaluated_get(dg)
    swing.append((ae.matrix_world @ ae.pose.bones["Breast"].tail
                  - h_br.evaluated_get(dg).matrix_world.translation).z)
    for name, h in (("Breast", h_br), ("BreastTip", h_tip)):
        tail = ae.matrix_world @ ae.pose.bones[name].tail
        amp[name] = max(amp[name], (tail - h.evaluated_get(dg).matrix_world.translation).length)
    if f >= 3:
        he = handc.evaluated_get(dg)
        te = h_tip.evaluated_get(dg)
        me = te.to_mesh()
        centroid = sum((te.matrix_world @ v.co for v in me.vertices), Vector()) / len(me.vertices)
        te.to_mesh_clear()
        inside_helper = min(inside_helper, ellipsoid(centroid, he))
        inside_tail = min(inside_tail, ellipsoid(ae.matrix_world @ ae.pose.bones["BreastTip"].tail, he))
x = swing[10:]
zc = [i + x[i] / (x[i] - x[i + 1]) for i in range(len(x) - 1) if x[i] * x[i + 1] < 0]
hz = (len(zc) - 1) / (2 * (zc[-1] - zc[0]) / 24) if len(zc) > 2 else 0.0
want = 3.0 * math.sqrt(1 - .05 ** 2)          # Jelly: 3 Hz, damping ratio 0.05
check("bone swings at the preset's frequency", abs(hz / want - 1) < .05,
      f"{hz:.2f} Hz (Jelly {want:.2f} Hz)")
check("both chain bones jiggle", amp["Breast"] > 1e-3 and amp["BreastTip"] > 1e-3,
      f"{amp['Breast']*100:.2f} / {amp['BreastTip']*100:.2f} cm")
check("tip's simulated point stays outside the hand collider", inside_helper >= 0.98,
      f"min ellipsoid radius helper {inside_helper:.3f}, bone tail {inside_tail:.3f} (1 = surface)")

# 5 stretch toggle
pb = arm.pose.bones["Breast"]
bpy.context.view_layer.objects.active = arm
bpy.ops.skin_jiggle.bone_stretch(bone_name="Breast")
s1 = sjp._bone_constraint(pb).type
bpy.ops.skin_jiggle.bone_stretch(bone_name="Breast")
s2 = sjp._bone_constraint(pb).type
check("stretch toggles Damped Track <-> Stretch To",
      s1 == 'STRETCH_TO' and s2 == 'DAMPED_TRACK' and sjp._bone_helper(pb) is h_br,
      f"{s1} -> {s2}")

# 6 reset defaults keeps bone springs isotropic
bpy.ops.skin_jiggle.reset_defaults()
m = sjp._jiggle_modifiers(h_br)[0]
check("reset defaults: bone layer is isotropic Soft Skin",
      m[im['Normal Softness']] == 0.0 and m['sj_body_preset'] == 'SOFT_SKIN')

# 7 bake from the armature (needs a saved file)
path = os.path.join(tmpdir, "bone_bake_test.blend")
bpy.ops.wm.save_as_mainfile(filepath=path)
bpy.context.view_layer.objects.active = arm
bpy.ops.skin_jiggle.apply_preset(modifier_name=m.name, object_name=h_br.name,
                                 preset='JELLY')
scene.frame_set(1)
try:
    r = bpy.ops.skin_jiggle.bake()
except Exception as exc:
    r = str(exc).splitlines()[-1]
def tip_offset():
    dg = bpy.context.evaluated_depsgraph_get()
    ae = arm.evaluated_get(dg)
    tail = ae.matrix_world @ ae.pose.bones["Breast"].tail
    return (tail - h_br.evaluated_get(dg).matrix_world.translation).z


jumped = {}
for f in (16, 15, 14, 13, 12, 11):          # backwards: only a bake can answer
    scene.frame_set(f)
    jumped[f] = tip_offset()
files = sum(len(fs) for root, _, fs in os.walk(os.path.join(tmpdir, "sj_bake")))
r2 = bpy.ops.skin_jiggle.free_bake()
played = {}
scene.frame_set(1)
for f in range(2, 17):
    scene.frame_set(f)
    if f >= 11:
        played[f] = tip_offset()
err = max(abs(jumped[f] - played[f]) for f in played)
peak = max(abs(v) for v in played.values())
check("bake from the armature bakes its jiggle bones",
      r == {'FINISHED'} and err < 1e-5 and peak > 1e-3,
      f"jumped vs played frames 11-16: max diff {err*100:.4f} cm, peak {peak*100:.2f} cm, bake files {files}")
check("delete bake from the armature", r2 == {'FINISHED'}, str(r2))

# 8 remove: constraint, helper, mesh and reference empty all go
ref_name = h_tip.get("sj_ref", "")
helper_name, mesh_name = h_tip.name, h_tip.data.name
bpy.ops.skin_jiggle.remove_bone_jiggle(bone_name="BreastTip")
check("remove deletes constraint, helper, mesh and reference",
      sjp._bone_constraint(arm.pose.bones["BreastTip"]) is None
      and helper_name not in bpy.data.objects and mesh_name not in bpy.data.meshes
      and (not ref_name or ref_name not in bpy.data.objects))
bpy.ops.skin_jiggle.remove_bone_jiggle(bone_name="Breast")
check("removing the last jiggle bone clears the rig flag",
      "sj_jiggle_bones" not in arm and sjp._is_collider(body))

# 9 squash & stretch: amount scales the stretch, Volume sets the thickness
stretch_scene = bpy.data.scenes.new("Stretch test")
stretch_scene.render.fps = 24
stretch_scene.frame_start, stretch_scene.frame_end = 1, 40
bpy.context.window.scene = stretch_scene
cases = [(0.0, 1.0), (1.0, 1.0), (2.0, 1.0), (1.0, 0.0), (1.0, 2.0)]
rigs = []
for i, (amount, volume) in enumerate(cases):
    rig = bpy.data.objects.new(f"StretchRig{i}", bpy.data.armatures.new(f"StretchRig{i}"))
    stretch_scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    base = rig.data.edit_bones.new("Base"); base.head, base.tail = (0, 0, 1.0), (0, 0, 1.2)
    tipb = rig.data.edit_bones.new("Tip"); tipb.head, tipb.tail = (0, 0, 1.2), (0, 0.2, 1.2)
    tipb.parent = base
    bpy.ops.object.mode_set(mode='OBJECT')
    rig.location.x = i * 1.0
    # jerk 3 cm along the Tip bone's axis over 3 frames, then stop dead
    rig.location.y = 0.0; rig.keyframe_insert("location", index=1, frame=1)
    rig.location.y = 0.03; rig.keyframe_insert("location", index=1, frame=4)
    act = rig.animation_data.action
    fcs = getattr(act, "fcurves", None)
    if fcs is None:
        from bpy_extras import anim_utils
        fcs = anim_utils.action_get_channelbag_for_slot(act, rig.animation_data.action_slot).fcurves
    for fc in fcs:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
    rig.location.y = 0.0
    pbt = rig.pose.bones["Tip"]
    helper = sjp._create_bone_jiggle(bpy.context, rig, pbt, 'JELLY', True)
    if i == 4:   # rigs are offset sideways: the helper must still sit at the tip
        bpy.context.view_layer.update()
        gap = (helper.matrix_world.translation - rig.matrix_world @ pbt.tail).length
        check("helper is placed at the bone tip on a moved rig", gap < 1e-5,
              f"gap {gap*100:.4f} cm")
    m = sjp._jiggle_modifiers(helper)[0]
    sjp._set_value(m, m.node_group, "Gravity", 0.0)
    sjp._set_value(m, m.node_group, "Stretch Amount", amount)
    sjp._bone_constraint(pbt).bulge = volume
    helper.update_tag()
    rigs.append((amount, volume, rig))

peak = {}
for f in range(1, 41):
    stretch_scene.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    for amount, volume, rig in rigs:
        pbe = rig.evaluated_get(dg).pose.bones["Tip"]
        ratio = (pbe.tail - pbe.head).length / 0.2
        thick = pbe.matrix.to_3x3().col[0].length
        if abs(ratio - 1) > abs(peak.get((amount, volume), (1.0, 1.0))[0] - 1):
            peak[(amount, volume)] = (ratio, thick)
dev = {k: abs(v[0] - 1) for k, v in peak.items()}
check("stretch scales with Stretch Amount (0x / 1x / 2x)",
      dev[(1.0, 1.0)] > .01 and dev[(0.0, 1.0)] < .1 * dev[(1.0, 1.0)]
      and abs(dev[(2.0, 1.0)] / dev[(1.0, 1.0)] - 2) < .2,
      "peak length change " + ", ".join(f"amount {a:g}: {dev[(a, 1.0)]*100:.2f}%"
                                        for a in (0.0, 1.0, 2.0)))
thick_err = max(abs(peak[k][1] - peak[k][0] ** (-k[1] / 2)) for k in ((1.0, 0.0), (1.0, 1.0), (1.0, 2.0)))
check("thickness follows Volume: length^(-Volume/2)", thick_err < .005,
      "; ".join(f"Volume {k[1]:g}: length x{peak[k][0]:.3f}, thickness x{peak[k][1]:.3f}"
                f" (expected x{peak[k][0] ** (-k[1] / 2):.3f})"
                for k in ((1.0, 0.0), (1.0, 1.0), (1.0, 2.0))))
pbv = rigs[4][2].pose.bones["Tip"]
hv = sjp._bone_helper(pbv)
bpy.context.view_layer.objects.active = rigs[4][2]
bpy.ops.skin_jiggle.bone_stretch(bone_name="Tip")
bpy.ops.skin_jiggle.bone_stretch(bone_name="Tip")
check("Volume survives toggling Squash & Stretch off and on",
      abs(sjp._bone_constraint(pbv).bulge - 2.0) < 1e-6,
      f"bulge {sjp._bone_constraint(pbv).bulge}")

print(f"SJ_BONES_SUMMARY {sum(results)}/{len(results)} passed")
sjp.unregister()
if not all(results):
    raise SystemExit(1)
