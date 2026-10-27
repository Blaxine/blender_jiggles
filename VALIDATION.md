# Validation — version 1.13.1

Validated with the installed Blender **4.5.4** and **5.2.2** executables using
factory-startup background sessions (earlier 1.13.1 builds: 4.1.1 and
5.1.2). No existing user scenes were opened or modified.

Run from the repository root (replace `blender` with the installed executable):

```text
blender --background --factory-startup --python-exit-code 1 --python tests/check_blender.py
blender --background --factory-startup --python-exit-code 1 --python tests/check_bones.py
blender --background --factory-startup --python-exit-code 1 --python tests/collision_sweep.py
```

`tests/check_bones.py` (20 checks, all passing on 4.5.4 and 5.2.2) covers
jiggle bones: adding them in Pose Mode, helper parenting, all 29 presets
converting to isotropic bone springs, contact style and Squash & Stretch
toggles, a two-bone chain, swing frequency (Jelly: 2.99 Hz measured vs 3.00
Hz), a rig-deformed body with Collision excluded from colliders (no
dependency cycle), a bone-parented hand collider keeping the tip's simulated
point outside it, Reset All, removal, and baking from the armature (frames
reached by jumping after the bake match normal playback exactly).
Squash & Stretch is checked by jerking a rig 3 cm along the bone: peak
length change 0.00 / 5.89 / 11.77 % at Stretch Amount 0 / 1 / 2 (exactly
2x), and thickness at Volume 0 / 1 / 2 equal to (rest length / length)^
(Volume/2) — 1.000 / 0.972 / 0.944 at 5.9 % stretch. Volume survives
toggling Squash & Stretch, and helpers are placed exactly at the bone tip
on a rig that was just moved.

The regression script checks:

- The generated 456-node graph builds and is reusable.
- Floor contacts remain resolved at Strength 0, 0.25 and 1; pinned vertices
  stay fixed. Cube contacts remain resolved at Strength 0 and 0.25.
- Copied bake paths are separated without changing the original path, and
  remain stable when both objects are prepared again. This holds whichever
  is prepared first: re-baking the original after copying it keeps its
  folder, and a preview cage never takes its layer's folder, even after its
  settings are synced back to the layer.
- Reset All restores Soft Skin values together with the preset and contact
  style labels.
- All 232 preset x contact style x bone combinations leave distinct socket
  values (closest pair: 17.2 % apart in Collision Friction), and the values
  applying them writes match the table exactly, so a layer's labels could be
  recognised from its socket values alone.
- Labels decode from socket values: the preset by which one matches the most
  of the 7 fields only a preset sets (unique, at least 5; every two presets
  differ in at least 2), the contact style likewise from its 5 fields (at
  least 3; styles differ in at least 4). Every combination decodes to itself;
  any one field edited by any amount still decodes correctly; with two edits
  the decode gave up 24 of 2436 times and never named a different preset.
- A layer without stored labels (a file from an earlier version) shows them
  from its values, counts edits as "+N" but not a lowered Strength, and
  Contact Style uses its own preset's contact defaults instead of Soft Skin's.
  When the preset cannot be told, Contact Style refuses.
- All 29 presets (25 body, 4 material) match their declared frequency and
  damping ratio, stay
  within every exposed parameter range, and avoid the stiffness stability
  clamp at 24 fps with their normal-quality substep settings.
- Actual evaluated simulation advances across frames.
- Zero-weight vertices remain pinned with smoothing and collision enabled.
- A floor contact needing 50 mm of travel against a 25 mm Max Stretch is
  resolved (skin rests on the floor, within Max Stretch + Contact Reach);
  with Contact Reach 0 the displacement still respects Max Stretch, squash
  included.
- Two collider objects sharing one mesh retain different evaluated thickness
  attributes while the shared source mesh remains unchanged.
- Collider helper collections are isolated between scenes.
- A duplicate cannot delete its original object's cage; source and layer
  renaming still resolve the cage correctly.
- A layer's own data (preset, contact style, bone flag) follows a modifier
  rename and is forgotten when the layer is removed, so a new layer of the
  same name starts clean. Preset and contact style survive saving and
  reopening the file, together with the layer's values and vertex group.
- Legacy bake-call fallback errors and Blender CANCELLED results are surfaced.
- A cube contact produces the same 22 mm surface gap on unit-scale and
  nonuniformly scaled probes (20 mm collider thickness plus 2 mm layer offset).
- A 4 Hz / damping ratio 0.5 spring driven by 1 Hz, 20 mm translation has the
  expected steady relative response. Analytic amplitude: **1.288 mm**;
  measured: **1.183 mm at 24 fps** and **1.270 mm at 60 fps** in both versions.
  The test permits 15% integration/sampling error; observed errors are about
  8.2% and 1.4% respectively. This is one controlled mathematical comparison,
  not validation against human motion capture.

During testing a Blender 4.1 scene-switch crash exposed unsafe creation of
helper collections during a dependency-graph rebuild. Empty scenes now do no
collision work; structural collider changes are deferred to the repair timer.
The complete suite passes after that change.

The live 116-profile collision sweep is documented in
[COLLISION_TESTS.md](COLLISION_TESTS.md). Since 1.10.0 it measures no
penetration in any profile (1.9.0: up to 11 mm). Contacts are still sampled
once per frame, so very fast presses against thin colliders remain an
approximation.

The four material presets were also measured in a free-response test (a
weighted grid stopping dead along its normal) on both Blender versions:
Jelly 2.99 Hz / 73 % amplitude kept per cycle (spec 3.00 Hz / 73 %),
Pudding 1.18 Hz / 39 % (1.19 / 39 %), Bouncing Ball 3.48 Hz / 69 %
(3.50 / 72 %), Water Bed 0.40 Hz / 47 % (0.40 / 47 %). See
[PRESET_REALISM.md](PRESET_REALISM.md#material-presets) for how the targets
were derived.

## Blender 5.2

Blender 5.2 removed custom properties from modifiers (`mod[key]` raises
`TypeError`). Group inputs are now read and written through
`mod.properties.inputs.<identifier>` (`value`, `type`, `attribute_name`),
and older versions keep using the modifier's keys; the helpers
`_get_input`, `_put_input`, `_use_attribute` and `_draw_input` hide the
difference. The add-on's own per-layer data moved to the object
(`sj_layer_meta`, keyed by the modifier's persistent uid).

While it lived on the modifier, that data never survived a reload: Blender
4.5 and 5.2 rebuild a Geometry Nodes modifier's keys from its node group when
a file loads. Files saved before this change therefore open with their layer
values and vertex groups intact (5.2 converts them itself), but show the
preset as Custom and the contact style as Body until a preset is applied
again. Bone layers are still recognised from their helper object. A file
saved by 4.5 with this version opens in 5.2 with all layer data, and every
property the layer panel draws resolves in both versions. Upgrade Layers and
syncing a preview cage back were also checked on both.
Blender 4.1 has no modifier uid, so there the data is keyed by modifier name
and does not follow a rename; 4.1 was not retested for this change.

The 1.10.0 panel was checked by opening Blender 4.1.1 and 5.1.2 with a test
scene and screenshotting the Jiggle sidebar (layer list, Layer Settings,
empty state); no drawing errors were reported.

Interactive playback speed, rendering/bake round trips, clothing interaction,
complex rigs with shape keys, sheared parents, library overrides and
subject-specific motion still require scene-level assessment. The code does
not claim that every supported Blender version or every production rig has
been tested. See PRESET_GUIDE.md for the physical model's limitations.

Rebuild the installable ZIP and refresh the preset table with:

```text
python tools/build_release.py
```
