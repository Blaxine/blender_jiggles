# Skin Jiggle Physics 1.10.0 — preset calibration

These are plausible animation starting points for an adult human at actual
scale, with **one Blender world unit equal to one metre** (Scene Unit Scale 1).
They are not measured properties of a particular person. Body composition,
muscle activation, attachment area, posture, garment fit and the painted region
all affect the result. Cup letters are retained as relative size labels;
they do not uniquely determine breast volume, mass or stiffness.

## What the numbers mean

The solver follows an animated target with independent damped springs. For a
fixed target, before collisions and hard limits:

```
normal stiffness = Stiffness * max(1 - Normal Softness, 0.02)
normal natural frequency (Hz) = sqrt(normal stiffness / Mass) / (2*pi)
normal damping ratio = Damping / (2*sqrt(normal stiffness / Mass))
```

The presets start with a chosen frequency and damping ratio and derive the
displayed values. `Damping` is a velocity decay rate in **1/s**, equivalent to
physical damping coefficient divided by effective mass. Do not paste a value
in N s/m from a paper directly into this control. `Mass` is an effective
spring-model parameter, not a mass assigned to each mesh vertex or a measured
total body-part mass. Increasing Mass alone slows motion. Changing Mass and
Stiffness by the same factor preserves spring timing.

The table's frequency is the undamped normal-mode frequency. Underdamped free
motion oscillates at `f * sqrt(1-zeta*zeta)`; tangential motion is faster because
its stiffness is higher. The free-response amplitude envelope decays roughly
as `exp(-Damping*t/2)`. A damping ratio of 1 is critical damping; smaller ratios
oscillate. The finite integration steps introduce some numerical error.

## All presets

The travel column is a safety limit, not the expected amplitude of every motion.
Gravity is **1.0** for all presets. Blend is **1.0** and Fold Iterations **2**.
The contact columns configure each tissue layer's added surface gap, friction
multiplier, object-impact restitution, and contact squash. Collider Thickness
Outer is added to each layer's gap. The new hand proxy starts at 4 mm outer
thickness, friction 56/80, and damping 0.95.

<!-- PRESET_TABLE_START -->
| Preset | Normal Hz | Damping ratio | Stiffness | Damping (1/s) | Effective mass | Normal softness | Max travel (cm) | Substeps | Collider gap (mm) | Layer friction | Object bounce | Contact squash | Contact spread |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Soft Skin | 4.0 | 0.50 | 229.69 | 25.13 | 0.20 | 0.45 | 2.5 | 6 | 1.5 | 0.55 | 0.03 | 0.35 | 3 |
| Firm Muscle | 10.0 | 0.45 | 696.68 | 56.55 | 0.15 | 0.15 | 0.8 | 10 | 1.0 | 0.45 | 0.02 | 0.20 | 2 |
| Heavy / Fat | 1.7 | 0.45 | 325.98 | 9.61 | 1.00 | 0.65 | 8.0 | 6 | 3.0 | 0.70 | 0.04 | 0.65 | 4 |
| Extra Bouncy (Stylized) | 2.5 | 0.16 | 274.16 | 5.03 | 0.50 | 0.55 | 12.0 | 6 | 2.0 | 0.65 | 0.30 | 0.80 | 3 |
| Chest — Flat | 7.0 | 0.50 | 193.44 | 43.98 | 0.08 | 0.20 | 0.6 | 8 | 0.8 | 0.40 | 0.02 | 0.15 | 2 |
| Chest — A cup | 3.5 | 0.35 | 103.63 | 15.39 | 0.15 | 0.30 | 1.8 | 6 | 1.5 | 0.52 | 0.03 | 0.30 | 3 |
| Chest — B cup | 3.0 | 0.35 | 136.66 | 13.19 | 0.25 | 0.35 | 3.0 | 6 | 2.0 | 0.56 | 0.03 | 0.38 | 3 |
| Chest — C cup | 2.6 | 0.35 | 177.92 | 11.44 | 0.40 | 0.40 | 4.5 | 6 | 2.5 | 0.60 | 0.03 | 0.45 | 4 |
| Chest — D cup | 2.2 | 0.35 | 208.45 | 9.68 | 0.60 | 0.45 | 6.0 | 6 | 3.0 | 0.64 | 0.03 | 0.52 | 4 |
| Sports Bra — A | 6.5 | 0.65 | 333.59 | 53.09 | 0.15 | 0.25 | 0.8 | 8 | 0.5 | 0.34 | 0.01 | 0.10 | 2 |
| Sports Bra — B | 5.8 | 0.65 | 442.68 | 47.38 | 0.25 | 0.25 | 1.2 | 8 | 0.7 | 0.36 | 0.01 | 0.12 | 2 |
| Sports Bra — C | 5.1 | 0.65 | 586.76 | 41.66 | 0.40 | 0.30 | 1.8 | 8 | 1.0 | 0.38 | 0.01 | 0.15 | 2 |
| Sports Bra — D | 4.5 | 0.65 | 685.23 | 36.76 | 0.60 | 0.30 | 2.5 | 8 | 1.2 | 0.40 | 0.01 | 0.18 | 3 |
| Bra — A | 4.7 | 0.50 | 186.87 | 29.53 | 0.15 | 0.30 | 1.2 | 6 | 1.0 | 0.42 | 0.02 | 0.20 | 2 |
| Bra — B | 4.2 | 0.50 | 267.85 | 26.39 | 0.25 | 0.35 | 2.0 | 6 | 1.2 | 0.45 | 0.02 | 0.24 | 3 |
| Bra — C | 3.7 | 0.50 | 360.31 | 23.25 | 0.40 | 0.40 | 3.0 | 6 | 1.5 | 0.48 | 0.02 | 0.28 | 3 |
| Bra — D | 3.2 | 0.50 | 441.01 | 20.11 | 0.60 | 0.45 | 4.0 | 6 | 2.0 | 0.51 | 0.02 | 0.32 | 3 |
| Glutes — Soft | 2.8 | 0.45 | 402.36 | 15.83 | 0.65 | 0.50 | 5.0 | 6 | 3.0 | 0.70 | 0.04 | 0.70 | 4 |
| Glutes — Tight | 5.5 | 0.50 | 682.41 | 34.56 | 0.40 | 0.30 | 2.2 | 8 | 1.5 | 0.55 | 0.03 | 0.38 | 3 |
| Glutes — Firm | 7.0 | 0.55 | 725.42 | 48.38 | 0.30 | 0.20 | 1.5 | 8 | 1.0 | 0.45 | 0.02 | 0.22 | 2 |
| Thighs — Soft | 4.0 | 0.45 | 421.10 | 22.62 | 0.40 | 0.40 | 3.0 | 6 | 2.0 | 0.58 | 0.03 | 0.40 | 3 |
| Thighs — Firm | 7.0 | 0.50 | 567.44 | 43.98 | 0.22 | 0.25 | 1.5 | 8 | 1.2 | 0.44 | 0.02 | 0.25 | 2 |
| Thighs — Tight | 9.0 | 0.50 | 677.17 | 56.55 | 0.18 | 0.15 | 1.0 | 10 | 0.8 | 0.38 | 0.01 | 0.16 | 2 |
| Belly — Soft | 2.0 | 0.45 | 315.83 | 11.31 | 0.80 | 0.60 | 6.0 | 6 | 3.0 | 0.70 | 0.04 | 0.70 | 4 |
| Belly — Firm | 4.5 | 0.55 | 491.96 | 31.10 | 0.40 | 0.35 | 2.5 | 6 | 1.5 | 0.50 | 0.02 | 0.32 | 3 |
<!-- PRESET_TABLE_END -->

Choose **Body preset** to restore that tissue preset's collision values. **Soft
hand** reduces bounce and applies a little more contact area; **Firm grip** uses
more friction, no bounce, and stronger squash; **Stylized** uses a wider bulge
and lively rebound. These styles change only the current jiggle layer, so
different layers can press the same hand collider differently. Collision
Distance, Collision Friction, Bounce, Squash Amount and Squash Spread remain
visible and directly editable in the layer controls.

Extra Bouncy is intentionally stylized. The other profiles prioritize low
restitution and bounded displacement. Bare chest motion becomes slower and has
more available travel across the relative size labels. A bra raises frequency
and damping and reduces travel; a sports bra does so further. Firm/tight muscle
profiles settle faster and travel less than loose adipose-dominated profiles.
These choices describe relative behavior, not universal measurements.

## Research basis and limits

The 100-profile animated contact sweep is recorded in
[COLLISION_TESTS.md](COLLISION_TESTS.md). In 1.9.0 it measured up to
**11 mm of penetration**, because the display capped collision pushes at
Max Stretch. Since 1.10.0 a collider may push skin up to Max Stretch +
Contact Reach and the sweep measures **no penetration** in any profile.
The collision values are still adjustable starting points, not a validated
optimum for moving contact; review the result in the target scene.

- [Haake & Scurr, A dynamic model of the breast during exercise (2010)](https://researchportal.port.ac.uk/en/publications/a-dynamic-model-of-the-breast-during-exercise/)
  supports increasing stiffness and damping with everyday and sports-bra
  support. Its subject/model-specific values are not a cup-size lookup table.
- [A piecewise mass-spring-damper model of the human breast (2018)](https://pubmed.ncbi.nlm.nih.gov/29276070/)
  found different stiffness under extension and compression. This add-on's
  linear springs cannot reproduce that nonlinear response with one preset.
- [Wakeling & Nigg, Modification of soft tissue vibrations in the leg by muscular activity (2001)](https://pubmed.ncbi.nlm.nih.gov/11160036/)
  supports increases in frequency and damping with activation and shows that
  direction matters. Our normal/tangent split remains a simplification.
- [Wakeling & Nigg, Soft-tissue vibrations in the quadriceps measured with skin mounted transducers (2001)](https://pubmed.ncbi.nlm.nih.gov/11266679/)
  models impact responses as damped oscillations, motivating frequency and
  damping ratio as calibration controls.

**The exact preset numbers are engineering choices, not values extracted from
these papers.** There is no subject-specific experimental calibration for the
belly, glute or other profiles in this repository. The add-on models visible
secondary motion, not the full spectrum of muscle vibration. It has no volume
conservation, tissue layers, nonlinear elasticity, muscle activation input,
self-contact or two-way force coupling. Squash is a visual approximation.
Clothing presets imitate support; they do not simulate garment contact.

Gravity compensates for the modeled orientation rather than applying full
gravity to an unstressed body. It uses the surface normal, so it cannot recover
all body rotations. Contact detection is once per frame and can tunnel;
substeps improve integration, not collision sampling. Animated colliders change
position, but their material-point velocity is not included in friction or
impact response. Apply sheared parent transforms before judging accuracy.

Zero-weight vertices remain fixed. Max Stretch caps the jiggle (springs,
smoothing and squash); collisions may push up to Contact Reach further. If
contact clearance needs more than Max Stretch + Contact Reach, raise Contact
Reach rather than Max Stretch, so the jiggle keeps its limit. Partial Blend
(Strength) also scales the contact push down.

## Calibrating a character

1. Confirm world scale and modifier order: armature, jiggle, subdivision.
   Paint smooth attachment gradients. Use the full mesh for final review.
2. Use Animation Mode only for blocking. It limits the simulation to one
   substep and can soften stiff profiles. Turn it off for timing decisions.
3. Start with the nearest category. Use a short stop or landing to judge
   oscillation period and settling. With a measured damped frequency `fd` and
   damping ratio `zeta`, the target undamped frequency is
   `f = fd / sqrt(1-zeta*zeta)`. Use a mild motion that does not hit limits.
4. Set `Stiffness = Mass * (2*pi*f)^2 / max(1-Softness, 0.02)` and
   `Damping = 4*pi*zeta*f`. Keep values within the exposed socket ranges.
   For decay fitting, use `zeta = delta / sqrt(4*pi*pi + delta*delta)`, where
   `delta = ln(first_peak / next_same_side_peak)` is measured relative to rest.
5. Adjust Max Stretch to an anatomical safety bound and collision gaps to the
   model. Gravity, folds and squash are secondary adjustments; leave them out
   while fitting oscillation timing. At low frame rates, increase substeps and
   compare the same motion again. Re-bake after changing parameters.

## Upgrade

Install version 1.10.0 and select **Upgrade Layers** on existing objects. This
rebuilds their engine and associated cages while preserving settings. It does
not silently replace shot-specific tuning with the new presets. Reapply a
preset explicitly to use this table, then delete old bakes and bake again.
Existing collider mesh attributes from older versions can remain; the managed
per-object settings modifier overrides them on evaluated geometry.
