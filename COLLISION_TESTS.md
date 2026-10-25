# Animated collision sweep — 1.9.0

The collision harness in `tests/collision_sweep.py` evaluates all **25 body
presets × 4 contact styles** with Blender's live Geometry Nodes simulation.
It presses a weighted tissue quad toward a closed cube collider, holds, then
releases it at 24 fps. The cube top is at 0.05 m and has 4 mm outer thickness;
the target travels 120 mm over 40 frames (3 mm per frame), holds for 12 frames,
and releases over 21 frames. The CSV records preset/style, expected clearance,
maximum measured penetration, peak travel, and release overshoot.

Run from the project root:

```text
blender --background --factory-startup --python-exit-code 1 --python tests/collision_sweep.py
```

## Results

| Contact style | Profiles | Worst measured penetration | Mean peak travel | Worst release overshoot |
|---|---:|---:|---:|---:|
| Body preset | 25 | 8.80 mm | 14.30 mm | 11.29 mm |
| Soft hand | 25 | 8.64 mm | 14.02 mm | 10.69 mm |
| Firm grip | 25 | 8.52 mm | 13.81 mm | 10.24 mm |
| Stylized | 25 | 11.00 mm | 15.00 mm | 11.29 mm |

The worst case was **Chest — Flat / Stylized**. The broad static cube-contact
regression in `tests/check_blender.py` passes at the expected 22 mm gap (20 mm
collider thickness plus 2 mm layer distance), but the animated sweep still
shows significant penetration. This means the one-sample-per-frame collision
query does not yet provide reliable continuous contact for a moving press.
Substeps improve spring integration but do not increase collision sampling.

The contact-style values were retained as editable art-direction defaults;
the sweep does **not** establish a real-life optimum or validate soft tissue
against human measurements. For animation shots, use the hand collider, test
the actual motion at playback speed, and increase `Thickness Outer` or layer
`Collision Distance` when the press moves faster. A larger contact distance
reduces tunneling by starting response earlier but also creates a larger
visible resting gap. Increase `Max Stretch` if it prevents the tissue from
reaching the resolved contact plane.

The harness is deliberately reproducible and writes the per-profile data to
`dist/collision_sweep_1.9.0.csv`. It is a flat quad against a broad closed
collider, so it does not cover curved breast meshes, hand articulation,
multi-object contacts, skin self-collision, or scene-specific rig behavior.
