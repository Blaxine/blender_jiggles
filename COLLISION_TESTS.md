# Animated collision sweep — 1.10.0

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

## Results (1.10.0, Blender 4.1.1 and 5.1.2 — identical)

| Contact style | Profiles | Worst measured penetration | Mean peak travel | Worst release overshoot |
|---|---:|---:|---:|---:|
| Body preset | 25 | 0.00 mm | 15.62 mm | 11.29 mm |
| Soft hand | 25 | 0.00 mm | 15.29 mm | 10.69 mm |
| Firm grip | 25 | 0.00 mm | 15.05 mm | 10.24 mm |
| Stylized | 25 | 0.00 mm | 17.00 mm | 11.29 mm |

In 1.9.0 the same sweep measured up to **11 mm** (worst: Chest — Flat /
Stylized). The cause was the display step capping every offset at Max
Stretch, which cut off collision pushes on presets with small travel limits
(Chest — Flat allows 6 mm, the press needs about 15 mm). 1.10.0 lets a
collider push up to Max Stretch + Contact Reach (default 0.1 m) and keeps
contact vertices out of the fold smoothing. Contacts are still sampled once
per frame; substeps improve spring integration, not collision sampling.

The contact-style values were retained as editable art-direction defaults;
the sweep does **not** establish a real-life optimum or validate soft tissue
against human measurements. For animation shots, use the hand collider, test
the actual motion at playback speed, and increase `Thickness Outer` or layer
`Collision Distance` when the press moves faster. A larger contact distance
reduces tunneling by starting response earlier but also creates a larger
visible resting gap. Increase `Contact Reach` (not Max Stretch) if the press
is deeper than the tissue may be pushed.

The harness is deliberately reproducible and writes the per-profile data to
`dist/collision_sweep_<version>.csv`. It is a flat quad against a broad closed
collider, so it does not cover curved breast meshes, hand articulation,
multi-object contacts, skin self-collision, or scene-specific rig behavior.
