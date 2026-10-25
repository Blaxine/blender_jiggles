# Validation — version 1.9.0

Validated with the installed Blender **4.1.1** and **5.1.2** executables using
factory-startup background sessions. No existing user scenes were opened or
modified.

Run from the repository root (replace `blender` with the installed executable):

```text
blender --background --factory-startup --python-exit-code 1 --python tests/check_blender.py
```

The regression script checks:

- The generated 410-node graph builds and is reusable.
- All 25 presets match their declared frequency and damping ratio, stay
  within every exposed parameter range, and avoid the stiffness stability
  clamp at 24 fps with their normal-quality substep settings.
- Actual evaluated simulation advances across frames.
- Zero-weight vertices remain pinned with smoothing and collision enabled.
- The displayed displacement respects Max Stretch even with squash enabled
  and a floor contact that demands more travel than the permitted limit.
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

The live 100-profile collision sweep is documented in
[COLLISION_TESTS.md](COLLISION_TESTS.md). It measures up to 11 mm of
penetration during an animated press/release even though the static collision
gap check passes. The current once-per-frame contact query needs further work
for moving collisions; these results are recorded as a known limitation, not
as a successful dynamic collision calibration.

Interactive playback speed, rendering/bake round trips, clothing interaction,
complex rigs with shape keys, sheared parents, library overrides and
subject-specific motion still require scene-level assessment. The code does
not claim that every supported Blender version or every production rig has
been tested. See PRESET_GUIDE.md for the physical model's limitations.

Rebuild the installable ZIP and refresh the preset table with:

```text
python tools/build_release.py
```
