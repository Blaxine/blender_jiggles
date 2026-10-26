# Validation — version 1.13.1

Validated with the installed Blender **4.1.1** and **5.1.2** executables using
factory-startup background sessions. No existing user scenes were opened or
modified.

Run from the repository root (replace `blender` with the installed executable):

```text
blender --background --factory-startup --python-exit-code 1 --python tests/check_blender.py
blender --background --factory-startup --python-exit-code 1 --python tests/check_bones.py
```

`tests/check_bones.py` (19 checks, all passing on 4.1.1 and 5.1.2) covers
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
  remain stable when both objects are prepared again.
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
