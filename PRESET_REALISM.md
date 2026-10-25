# How realistic are the presets? — 1.11.0

A comparison of the 25 body presets with published soft-tissue measurements,
plus the data behind the four [material presets](#material-presets).
Short version: **the bare-chest presets bounce at a realistic speed but
settle far too quickly; everything else is art direction rather than
measured data.** [PRESET_GUIDE.md](PRESET_GUIDE.md) already calls the
numbers "engineering choices, not values extracted from these papers" —
this document checks how far they are from the data that does exist.

## How the comparison was made

Every preset is a damped spring defined by a normal-mode frequency (Hz),
a damping ratio (ζ) and a maximum travel (Max Stretch). Published values
were converted into the same terms:

- **Frequency:** `f = sqrt(k / m) / (2π)`. Tangential (sideways) motion in
  the add-on is faster than normal motion: `f_t = f / sqrt(1 − Normal Softness)`.
- **Damping ratio:** `ζ = c / (2·sqrt(k·m))`.
- **Bounces:** amplitude kept per cycle is `exp(−2πζ / sqrt(1 − ζ²))`;
  "visible cycles" counts cycles until the motion falls below 10 %.
- **Travel:** Max Stretch is a one-sided limit, so peak-to-peak travel is
  `2 × Max Stretch`.

The breast spring model reports stiffness and damping but no mass in the
material I could access, so **a mass of 0.3–0.5 kg per breast is assumed**
to convert it to Hz.

## Measured reference values

### Bare breast

Piecewise spring model fitted to running motion capture: 73.5 N/m when the
breast is above its rest position, 658 N/m below it (about **9× stiffer
moving down**), damping 1.83 / 2.07 N·s/m.

| Assumed mass | Rising | Falling | Whole cycle |
|---:|---|---|---:|
| 0.3 kg | 2.5 Hz, ζ 0.19 | 7.5 Hz, ζ 0.07 | ~3.7 Hz |
| 0.4 kg | 2.2 Hz, ζ 0.17 | 6.5 Hz, ζ 0.06 | ~3.2 Hz |
| 0.5 kg | 1.9 Hz, ζ 0.15 | 5.8 Hz, ζ 0.06 | ~2.9 Hz |

Other sources: a finite-element model finds vertical and side-to-side modes
near **5 Hz** with ζ ≈ 0.215; a sports-bra study reports ζ ≈ 0.27.

| Damping ratio | Amplitude kept per cycle | Visible cycles |
|---:|---:|---:|
| 0.06 | 69 % | 6.1 |
| 0.15 | 39 % | 2.4 |
| 0.215 | 25 % | 1.7 |
| 0.273 | 17 % | 1.3 |

Displacement (nipple relative to the trunk): unsupported running
**15.2 ± 4.2 cm** resultant, up to about **20 cm** vertical for D cups;
walking about **4.2 cm**. Bras raise stiffness and damping and reduce
motion, with sports bras the most effective; I found no published
percentages to check magnitudes against.

### Muscle soft tissue (thighs, calves)

After heel strike, muscle soft tissue vibrates at **10–30 Hz** (one
subject: quadriceps 15.2 Hz, hamstrings 21.0 Hz, triceps surae 22.9 Hz)
and is strongly damped; runners adjust damping through muscle activation.
These are small, fast vibrations, not the visible sway of fat.

### Belly, glutes, general fat

I found no measured frequency or amplitude data for visible abdominal or
gluteal fat motion. Studies show soft tissue absorbs a large share of
impact energy (especially in obese walkers) but don't report the numbers
needed here.

## The presets in the same terms

| Preset | Hz (normal) | Hz (sideways) | ζ | Kept / cycle | Visible cycles | Peak-to-peak travel |
|---|---:|---:|---:|---:|---:|---:|
| Soft Skin | 4.0 | 5.4 | 0.50 | 3 % | 0.6 | 5.0 cm |
| Firm Muscle | 10.0 | 10.8 | 0.45 | 4 % | 0.7 | 1.6 cm |
| Heavy / Fat | 1.7 | 2.9 | 0.45 | 4 % | 0.7 | 16.0 cm |
| Extra Bouncy (Stylized) | 2.5 | 3.7 | 0.16 | 36 % | 2.3 | 24.0 cm |
| Chest — Flat | 7.0 | 7.8 | 0.50 | 3 % | 0.6 | 1.2 cm |
| Chest — A cup | 3.5 | 4.2 | 0.35 | 10 % | 1.0 | 3.6 cm |
| Chest — B cup | 3.0 | 3.7 | 0.35 | 10 % | 1.0 | 6.0 cm |
| Chest — C cup | 2.6 | 3.4 | 0.35 | 10 % | 1.0 | 9.0 cm |
| Chest — D cup | 2.2 | 3.0 | 0.35 | 10 % | 1.0 | 12.0 cm |
| Sports Bra — A | 6.5 | 7.5 | 0.65 | 0 % | 0.4 | 1.6 cm |
| Sports Bra — B | 5.8 | 6.7 | 0.65 | 0 % | 0.4 | 2.4 cm |
| Sports Bra — C | 5.1 | 6.1 | 0.65 | 0 % | 0.4 | 3.6 cm |
| Sports Bra — D | 4.5 | 5.4 | 0.65 | 0 % | 0.4 | 5.0 cm |
| Bra — A | 4.7 | 5.6 | 0.50 | 3 % | 0.6 | 2.4 cm |
| Bra — B | 4.2 | 5.2 | 0.50 | 3 % | 0.6 | 4.0 cm |
| Bra — C | 3.7 | 4.8 | 0.50 | 3 % | 0.6 | 6.0 cm |
| Bra — D | 3.2 | 4.3 | 0.50 | 3 % | 0.6 | 8.0 cm |
| Glutes — Soft | 2.8 | 4.0 | 0.45 | 4 % | 0.7 | 10.0 cm |
| Glutes — Tight | 5.5 | 6.6 | 0.50 | 3 % | 0.6 | 4.4 cm |
| Glutes — Firm | 7.0 | 7.8 | 0.55 | 2 % | 0.6 | 3.0 cm |
| Thighs — Soft | 4.0 | 5.2 | 0.45 | 4 % | 0.7 | 6.0 cm |
| Thighs — Firm | 7.0 | 8.1 | 0.50 | 3 % | 0.6 | 3.0 cm |
| Thighs — Tight | 9.0 | 9.8 | 0.50 | 3 % | 0.6 | 2.0 cm |
| Belly — Soft | 2.0 | 3.2 | 0.45 | 4 % | 0.7 | 12.0 cm |
| Belly — Firm | 4.5 | 5.6 | 0.55 | 2 % | 0.6 | 5.0 cm |

At 24 fps nothing above **12 Hz** can be shown (the Nyquist limit), and
motion above about 8 Hz starts to look like flicker.

## Verdict by category

| Category | Measured | Presets | How close |
|---|---|---|---|
| **Bare chest — speed** | ~3–3.7 Hz per cycle (spring model), 5 Hz modes (FE model) | 2.2–3.5 Hz (A–D), ~3–4 Hz sideways | **Good.** Right range; larger cups are slower, as in the data. |
| **Bare chest — damping** | ζ ≈ 0.06–0.27: 1.3–6 visible bounces | ζ 0.35: about 1 bounce | **Too damped.** Real tissue keeps oscillating after a stop or landing; the presets settle almost at once. |
| **Bare chest — travel** | 15 ± 4 cm unsupported running, up to ~20 cm vertical (D), ~4 cm walking | 3.6–12 cm peak-to-peak (A–D) | **Fine for walking and jogging;** caps hard running at roughly 60–75 % of measured. |
| **Up/down asymmetry** | ~9× stiffer moving down than up | One linear spring | **Missing.** Real breasts rise softly and stop hard at the bottom. |
| **Bra / sports bra** | Support raises stiffness and damping and reduces motion | Higher Hz, ζ 0.5 / 0.65, ~40–60 % less travel | **Right direction, magnitude unverified.** |
| **Thighs / glutes** | Muscle buzz at 10–30 Hz, strongly damped | 2.8–9 Hz | **Not comparable.** The measured buzz is a different motion from visible fat sway, and mostly can't be shown at 24 fps. |
| **Belly / Heavy Fat** | No measured data found | 1.7–4.5 Hz, up to 12–16 cm | **Artistic guess.** Plausible-looking, unverified. |
| **Firm Muscle / Thighs — Tight** | Same 10–30 Hz muscle range | 9–11 Hz | Closest to real muscle, but **near the 24 fps limit** and can flicker; fine at 60 fps. |
| **Extra Bouncy (Stylized)** | — | ζ 0.16, 2.3 visible cycles | Labelled stylized, yet its damping is the **closest to measured bare-breast damping**. |

## Biggest realism gaps

1. **Damping is too high.** Every non-stylized preset uses ζ 0.35–0.65 and
   settles in about one bounce; measured bare breasts give 1.3–6 bounces.
2. **No up/down asymmetry.** The solver's springs are linear, so the 9×
   difference between rising and falling stiffness can't be reproduced by
   any single preset.
3. **No tissue coupling.** Real fat carries ripples across its surface.
   Here each vertex is an independent spring and Fold Smoothing only blurs
   neighbours together, so there are no travelling waves. Squash is a
   visual bulge, not volume conservation.
4. **Smooth input.** Real jiggle is largely driven by sharp heel-strike
   impacts. Keyframed animation rarely contains them, so even perfectly
   measured parameters look calmer than footage.

## Suggested retune

The most worthwhile change is lowering bare-chest damping to **ζ ≈
0.15–0.2** (2–3 visible bounces), keeping the current frequencies.
Consider raising Max Stretch for C and D cups if the shot includes hard
running. Bra and sports-bra damping can stay higher, since support is
known to increase it. Glute, thigh and belly presets should stay tuned by
eye against reference footage.

## How solid this is

The measured data is thin. The breast spring values come from one fitted
model, and converting them to Hz needed an assumed mass. The bra studies
report direction, not magnitudes. Most full papers weren't readable for
this comparison, so values were taken from abstracts and summaries. Treat
the chest comparison as reasonably grounded and everything else as
unverified.

## Material presets

Added in 1.11.0. Unlike the body presets, these four start from material
measurements, converted with the same formulas as above. They describe
whole objects (a dessert, a ball, a mattress); on a character they act as
stylized tissue.

| Preset | Measured / derived data | Preset value | Checked in Blender (4.1.1 and 5.1.2) |
|---|---|---|---|
| **Jelly** | 2.4–4.4 Hz, ζ ≈ 0.05 | 3.0 Hz, ζ 0.05, 4 cm limit | 2.99 Hz, keeps 73 % per cycle (~7 wobbles) |
| **Pudding** | 1.0–1.8 Hz, ζ ≈ 0.07–0.18 | 1.2 Hz, ζ 0.15, 5 cm limit | 1.18 Hz, keeps 39 % per cycle (~2.4 wobbles) |
| **Bouncing Ball (Stylized)** | restitution 0.75–0.9 → ζ 0.03–0.09; real squash ~100 Hz | 3.5 Hz, ζ 0.052, restitution 0.85 | 3.48 Hz, keeps 69 % per cycle |
| **Water Bed** | 0.32–0.48 Hz, waves last "several seconds" → ζ ≈ 0.09–0.15 | 0.4 Hz, ζ 0.12, 8 cm limit | 0.40 Hz, keeps 47 % per cycle (~7.5 s to settle) |

Blender figures come from a free-response test: a weighted grid moving
along its normal at 0.1 m/s stops dead, and the frequency (zero crossings)
and per-cycle decay (successive peaks) are measured. All four presets also
pass the regression suite and the 116-profile collision sweep with no
penetration.

### Jelly

Gelatin gels are strongly elastic: measured shear moduli are 1.16, 3.40
and 5.6 kPa for 7 %, 10 % and 15 % gelatin, and another study reports G′
2–10 kPa with G″ only 50–500 Pa. A dessert jelly is more dilute, so
**G ≈ 0.6–1.2 kPa is assumed**. A block fixed to a plate wobbles in its
shear mode at about `f = sqrt(G/ρ) / (4H)`:

| G | H 6 cm | H 8 cm | H 10 cm |
|---:|---:|---:|---:|
| 300 Pa | 2.2 Hz | 1.7 Hz | 1.3 Hz |
| 600 Pa | 3.1 Hz | 2.4 Hz | 1.9 Hz |
| 1160 Pa | 4.4 Hz | 3.3 Hz | 2.6 Hz |

Damping follows from the loss tangent, `ζ ≈ tan δ / 2`. Elastic gels sit
around tan δ 0.02–0.1, so ζ 0.01–0.05; the preset uses the upper end
(0.05) so the wobble still settles within a few seconds. Low contact
friction (slippery) and a springy 0.3 restitution.

### Pudding

Starch puddings and custards are weak gels (G′ > G″ but not by much). A
starch gel at 1 Hz measured G′ 30–137 Pa with tan δ 0.26–0.36; other starch
gels report tan δ 0.13–0.18. With G′ 80–140 Pa and a 5–7 cm pudding the
shear-mode estimate gives **1.0–1.8 Hz**; tan δ 0.13–0.36 gives **ζ
0.07–0.18**. The preset uses 1.2 Hz and ζ 0.15. Puddings also flow
(thixotropic), which this spring model doesn't capture, so it rounds damping
towards the high end, adds a strong contact bulge (Squash 1.0) and no
rebound (restitution 0.02).

### Bouncing Ball (Stylized)

A ball's bounce is described by its coefficient of restitution `e`
(rebound height = e² × drop height): superball ≈ 0.9, rubber ball 0.8–0.9,
tennis ball 0.71–0.75. Treating the contact as a damped spring, restitution
maps to `ζ = −ln e / sqrt(π² + ln² e)`:

| e | ζ | Rebound height |
|---:|---:|---:|
| 0.75 | 0.091 | 56 % |
| 0.85 | 0.052 | 72 % |
| 0.90 | 0.034 | 81 % |

The preset uses e = 0.85 for both its spring damping and its floor/object
**Bounce**. The real squash is far too fast to show: a tennis ball is in
contact for about 5 ms, a half-period of roughly 100 Hz, while 24 fps can
show at most 12 Hz. The preset therefore slows the squash-and-stretch to
**3.5 Hz** — the frequency is animation, the bounciness is physics.

### Water Bed

Waterbeds are about 84 in long and 60–72 in wide (queen / king), filled
8–10 in deep. The first sloshing mode of a tank of length L and depth h is
`f = sqrt(g·k·tanh(k·h)) / 2π` with `k = π/L`:

| Direction | 20 cm deep | 24 cm deep |
|---|---:|---:|
| Length, 84 in | 0.32 Hz | 0.35 Hz |
| Width, king 72 in | 0.38 Hz | 0.41 Hz |
| Width, queen 60 in | 0.45 Hz | 0.48 Hz |

Free-flow mattresses keep waving for "several seconds" because the walls
reflect the waves. Decaying to 10 % in 6–10 s at 0.4 Hz gives ζ 0.09–0.15;
the preset uses 0.4 Hz and ζ 0.12 (about 7.5 s). Waveless mattresses
(baffled, 50–95 % less motion) would need much higher damping. The vinyl
membrane and the sleeper's weight are ignored in the slosh estimate.
Normal softness 0.8 makes the motion mostly up-and-down, and a wide
8-ring Squash Spread imitates water displaced around a contact.

### Limits of the material presets

- **Waves don't travel.** Each vertex is its own spring and Fold Smoothing
  only blurs neighbours, so a water bed sloshes as a body instead of
  sending wave fronts across the surface, and jelly wobbles in place rather
  than rippling.
- **No volume conservation or flow.** Pudding can't slump or flow, and
  squash is a visual bulge.
- **Size matters.** Jelly and pudding frequencies scale with `1/H`: a
  jelly twice as tall wobbles at about half the frequency. Adjust Stiffness
  (frequency ∝ √Stiffness) for objects much larger or smaller than a
  dessert.
- **Assumed inputs.** The dessert moduli, pudding size and waterbed decay
  time are reasonable assumptions, not measurements of a specific product.

## Sources

- [A piecewise mass-spring-damper model of the human breast (J. Biomech.)](https://www.sciencedirect.com/science/article/abs/pii/S0021929017306826) · [ResearchGate entry](https://www.researchgate.net/publication/321798863_A_piecewise_mass-spring-damper_model_of_the_human_breast)
- [Haake & Scurr, A dynamic model of the breast during exercise](https://researchportal.port.ac.uk/en/publications/a-dynamic-model-of-the-breast-during-exercise/) · [Springer](https://link.springer.com/article/10.1007/s12283-010-0046-z)
- [Breast FE natural frequencies (figure)](https://www.researchgate.net/figure/The-first-10-natural-frequencies-of-subject-As-breast-determined-with-and-without_tbl1_236066359)
- [Numerical simulation for sports bra design (damping ratio)](https://www.sciencedirect.com/science/article/pii/S026412751930615X)
- [Scurr et al., Supported and unsupported breast displacement in three dimensions](https://researchportal.port.ac.uk/en/publications/supported-and-unsupported-breast-displacement-in-three-dimensions/)
- [The effect of breast support on kinematics during the running gait cycle](https://researchportal.port.ac.uk/en/publications/the-effect-of-breast-support-on-the-kinematics-of-the-breast-duri/)
- [Breast support review, Frontiers in Sports and Active Living 2022](https://pmc.ncbi.nlm.nih.gov/articles/PMC9237383)
- [ISB 2005 abstract: quadriceps, hamstring and triceps surae frequencies](https://media.isbweb.org/images/conf/2005/abstracts/0998.pdf)
- [Behling et al., soft-tissue vibration and damping in running](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8370632/)
- [Sports Medicine – Open review: 10–30 Hz impact excitation](https://sportsmedicine-open.springeropen.com/articles/10.1186/s40798-022-00524-w)
- [Compression garments and soft-tissue vibration](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8402353/)
- [Pain & Challis, soft-tissue movement in drop landings](https://repository.lboro.ac.uk/articles/The_influence_of_soft_tissue_movement_on_ground_reaction_forces_joint_torques_and_joint_reaction_forces_in_drop_landings/9624947/files/17273561.pdf)
- [Soft-tissue deformation in obese walking](https://lab.vanderbilt.edu/zelik/?p=175)

Material presets:

- [Shear elastic modulus of gelatin phantoms (7–15 %)](https://pubmed.ncbi.nlm.nih.gov/21317078/)
- [Gelatin gelling and melting by oscillatory rheology (G′, G″)](https://www.tandfonline.com/doi/full/10.1080/10942910601128895)
- [Mechanics of gelatin-based hydrogels](https://pmc.ncbi.nlm.nih.gov/articles/PMC9877534/)
- [Starch gel G′ and tan δ at 1 Hz (table)](https://pmc.ncbi.nlm.nih.gov/articles/PMC6049532/table/Tab2)
- [Starch and flour gel tan δ](https://www.synapsesocial.com/papers/69af94da70916d39fea4bcce)
- [Dairy dessert rheology with gums (Food and Bioprocess Technology)](https://avesis.erciyes.edu.tr/yayin/f69ec24b-29f0-43f5-bc84-b52781182834/the-effects-of-different-gums-and-their-interactions-on-the-rheological-properties-of-a-dairy-dessert-a-mixture-design-approach)
- [Physics of bounce (Rod Cross)](https://www.physics.sydney.edu.au/~cross/BOUNCE.htm)
- [Coefficient of restitution values](https://hypertextbook.com/facts/2006/restitution.shtml)
- [Tennis ball contact time at 10,000 fps](https://tennisplayer.net/public/rackets_and_strings/paul_hamori/10000_frames/bounce)
- [Waterbed mattress patent: waves reflect for several seconds](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/4332043)
- [Waterbed types and wave reduction](https://www.goodbed.com/guides/mattress-types/waterbeds/)
- [Waterbed sizes and depth](https://puffy.com/blogs/best-sleep/how-much-does-a-waterbed-weigh-the-ultimate-guide)
