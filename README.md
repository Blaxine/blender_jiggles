# Skin Jiggle Physics 1.9.0 — Blender 4.1+ Addon

Vertex-group-driven soft tissue simulation built on **Geometry Nodes
Simulation Zones**. Each jiggle layer is one Geometry Nodes modifier masked
by a vertex group, with fully independent physical parameters — so belly,
chest, glutes, arms, cheeks etc. can each behave differently on the same
mesh.

Because the physics runs inside Geometry Nodes (not Python per-frame), it
is multithreaded, cached by Blender's simulation system, and bakeable.

Version 1.9 includes per-body collision defaults and a reproducible live
contact sweep. The sweep found that moving presses can still penetrate, so
the collision values are adjustable starting points. See [the full preset
values and calibration guide](PRESET_GUIDE.md) and [the Blender collision
test results](COLLISION_TESTS.md). Version 1.8 derives
spring values from oscillation frequency and damping ratio. These
are plausible animation presets, not experimentally validated tissue constants.
They assume **one world unit = one metre and Scene Unit Scale = 1**.

---

## Install

1. Open `Edit → Preferences → Add-ons`, then:
   - **Blender 4.2 and later:** open the **▾** menu at the top right and
     choose **Install from Disk…**
   - **Blender 4.1:** click **Install…**
2. Pick `dist/skin_jiggle_physics_<version>.zip` (or
   `skin_jiggle_physics.py`), then enable **Skin Jiggle Physics**.
3. Panel appears in the 3D Viewport sidebar (`N` key) → **Jiggle** tab.

When upgrading, disable and remove the old version first and restart
Blender, so the previous module isn't still loaded.

## Quick start

1. Select your character mesh (armature-deformed or keyframe-animated —
   both work).
2. In Weight Paint mode, paint a vertex group over the tissue you want to
   jiggle. Weight 1 = fully dynamic, 0 = pinned, gradients = smooth
   falloff at the borders (paint soft edges — it matters a lot).
3. `N` panel → Jiggle tab → **Add Jiggle Layer** → pick the vertex group
   and a preset.
4. **Play the timeline.** Simulation zones simulate during playback; they
   reset automatically when you jump back to the scene start frame.
5. Repeat for as many vertex groups as you want — each gets its own layer.

**Modifier order:** layers are added after the Armature modifier and
**above the first Subdivision Surface / Multires** modifier, so the sim
runs on the base mesh (fast) and its vertex count is the same in the
viewport and at render. Keep it that way: if the vertex count reaching a
layer changes (mesh edited, a modifier above it toggled, different
viewport/render subdivision levels above it), the layer restarts from
rest instead of showing scrambled vertices.

**Vertex groups:** a layer finds its group by name. If you rename or
delete the group, the layer row turns red ("Missing group") — press
**Pick** to point it at the right group.

## How the physics works

- The animated (armature-deformed) surface each frame is the **spring
  target**. Every weighted vertex is a damped spring chasing it.
- Displacement is split into **normal vs tangential** components with
  separate stiffness. **Normal Softness** reduces stiffness along the
  normal. This is a simplified directional control, not a universal
  description of tissue: real directional properties vary by body part.
- The sim runs in **world space**, so moving, turning or dropping the
  whole character automatically produces inertia jiggle, gravity always
  points down, and floor collision is trivial to enable.
- Damping and the speed limit act on velocity **relative to the animated
  surface**, so a character moving at constant speed carries its tissue
  along. Only changes in speed or direction make it jiggle. Within each
  frame the target moves smoothly through the substeps, so steady motion
  is followed exactly.
- **Gravity is relative to the modeled pose.** A sculpted body already
  hangs under gravity, so the addon doesn't sag it a second time: in the
  pose it was modeled in (the pose at the simulation's start frame),
  gravity adds nothing. Tissue sags when that part of the body turns
  away from that orientation — lying down, bending over — following the
  surface normal. (Rotation around the normal itself, e.g. a perfectly
  upright handstand, isn't detected.) The sag is capped at half of Max
  Stretch, separately along and across the surface, so tissue never hangs
  against the hard limit with no room left to move.
- Tissue starts at the surface's own velocity, so shots that begin
  mid-motion don't open with a backwards jolt.
- Damping is exponential, so the same Damping value settles the same
  amount per frame at any Substeps setting (and in Animation Mode).
- At the Max Stretch limit, tissue loses its outward velocity instead of
  pressing against the limit and sticking there.
- The vertex-group **weight scales the displayed jiggle**, applied once
  per frame: weight 0.5 shows half the motion with the same timing, at
  any Substeps setting.
- **Fold Smoothing** blurs the dynamic offset across neighbouring
  vertices, so skin moves cohesively and folds in patches instead of
  vibrating per-vertex. Normalized masked smoothing keeps unpainted
  vertices pinned, and the final offset is capped by Max Stretch even
  after squash and smoothing.
- Stability guards: physics substeps, exponential damping, relative
  speed clamping, a stiffness clamp tied to the timestep, and a hard
  **Max Stretch** distance limit. It should be very hard to make it
  explode.
- Collision contacts are detected **once per frame** and reused by every
  substep. Substeps make stiff springs stable; they don't make collision
  detection finer.

## Parameters (per layer)

| Parameter | What it does | Feel |
|---|---|---|
| Stiffness | Spring pull back to the animated surface | low = loose fat, high = firm muscle |
| Normal Softness | Extra softness along the surface normal | higher = more in/out wobble, fleshier |
| Damping | Velocity decay rate in 1/s (physical damping coefficient divided by effective mass) | low = longer oscillation, high = faster settling |
| Mass | Effective spring-model mass, not anatomical mass per vertex | timing depends on Stiffness / Mass |
| Gravity | Sag when the body turns away from its modeled pose (× 9.81) | hang/droop when lying down or bending over; none in the modeled pose; capped at half of Max Stretch |
| Max Stretch | Hard distance limit from the surface (m) | keeps things anatomical, prevents rubbery over-shoot |
| Bounce | Floor and object restitution | realistic presets use low values; collider damping reduces it further |
| Fold Smoothing / Iterations | Cohesion blur of the offset | broader = big soft folds, off = per-vertex shimmer |
| Substeps | Physics steps per frame | raise for stiff, light tissue (high Stiffness ÷ Mass); doesn't affect collision detection, which runs once per frame |
| Blend | Global fade of the effect | animatable — great for dialing jiggle per shot |
| Floor Collision / Height | World-Z floor plane | for tissue resting/slapping on the ground |
| Object Collision | Enable collision with every collider mesh | tissue reacts to props, hands, other (non-jiggling) bodies |
| Collision Distance | Skin offset kept from collider surfaces | prevents visible surface clipping |
| Collision Friction | Tangential drag while sliding on colliders | high = grabby skin, low = slippery |
| Squash Amount | Bulge strength around contacts | compressed tissue pushes surrounding skin outward — flesh pressing on a surface swells around the contact patch |
| Squash Spread | How wide the bulge ring travels | small = tight local swell, large = broad soft displacement |

## Presets

| Preset | Character |
|---|---|
| Soft Skin | 4 Hz normal mode, moderate damping, 2.5 cm travel limit |
| Firm Muscle | 10 Hz, fast settling, 0.8 cm limit |
| Heavy / Fat | 1.7 Hz, slower motion, 8 cm limit |
| Extra Bouncy | 2.5 Hz, low damping, intentionally stylized, 12 cm limit |

### Body presets (v1.8)

| Category | Variants | Character |
|---|---|---|
| Chest | Flat, A, B, C, D cup | Flat: 7 Hz / 0.6 cm limit; A–D: 3.5–2.2 Hz / 1.8–6 cm limits |
| Sports Bra | A–D | 6.5–4.5 Hz, damping ratio 0.65, 0.8–2.5 cm limits |
| Bra | A–D | 4.7–3.2 Hz, damping ratio 0.50, 1.2–4 cm limits |
| Glutes | Soft, Tight, Firm | 2.8 / 5.5 / 7 Hz; 5 / 2.2 / 1.5 cm limits |
| Thighs | Soft, Firm, Tight | 4 / 7 / 9 Hz; 3 / 1.5 / 1 cm limits |
| Belly | Soft, Firm | 2 / 4.5 Hz; 6 / 2.5 cm limits |

The Add Layer dialog's **vertex group field is a search bar** — start
typing and it autocompletes from the object's groups (pre-filled with
the active group). Preset values assume roughly human scale (metres);
for stylized giants/chibis scale Max Stretch accordingly.

Cup letters are relative size labels, not a mass or stiffness measurement.
Preset frequencies are undamped natural frequencies, not imposed bounce
rates. These are starting points — modifier settings can be keyframed.

## Object collision

No collections, no setup on the jiggle layer — **any mesh with Blender's
own Physics > Collision enabled is automatically a collider**:

1. Click the **+** beside Colliders in the Jiggle panel to add an editable
   palm-sized hand proxy at the 3D cursor, or select a prop/character/surface
   and enable its Physics > Collision modifier.
2. That's it. The addon detects it (auto-synced on every frame change,
   or press the refresh button next to the collider counter in the
   Jiggle panel) and the tissue collides with it.

Objects that have jiggle layers themselves (and their cages) are **never
colliders**, even with Collision enabled — so you can leave Collision on
a character for cloth sims. A layer reading its own object would disable
its collision entirely, and two jiggling objects reading each other form
a dependency cycle; as a result two jiggling characters don't collide
with each other.

**Per-object tuning happens on each collider's own Collision panel:**

| Collider setting | Effect on the tissue |
|---|---|
| Thickness Outer | Contact distance / skin offset kept from this object |
| Friction | Sliding drag on this object's surface (0–80) |
| Damping | Reduces the layer's Bounce on this object (1 = no bounce) |

So a rubber mat and an ice sheet in the same scene each behave like
themselves. Each jiggle layer stores its own collision response, so one hand
can press two body regions differently. The contact-style button beside each
layer's preset offers **Body preset**, **Soft hand**, **Firm grip**, and
**Stylized**. These set per-layer Collision Distance, Collision Friction,
Bounce and squash values; each remains editable. Collision Distance adds to
each collider's thickness, and Collision Friction scales that collider's
friction (0.5 = neutral).

The collider list in the Jiggle panel shows each collision object's thickness,
friction and damping. Shape and placement remain ordinary mesh/object controls;
move the hand proxy onto the tissue you want to press.

Colliders can be animated — they are re-sampled every frame. Collision
is against the mesh surface (not a box or hull); inside/outside is
estimated by 3-ray backface voting. Closed, outward-facing meshes give
the best results; thin/open meshes and overlapping shells can be ambiguous. Contacts are
detected once per frame, so raising **Substeps** won't stop very fast
impacts from passing through. Instead, raise the collider's **Thickness
Outer** (or the layer's **Collision Distance**) so contacts are caught
earlier, at the cost of a slightly larger resting gap. The addon maintains a
scene-specific `SJ_Colliders_<scene>` helper collection and a small
**SJ Collider Settings** Geometry Nodes modifier on each collider. This
adds `sj_set` only to evaluated geometry, so objects sharing a mesh can
have different contact settings without altering the shared mesh data.
Use local colliders or library overrides so the settings modifier can be added.

Collision distances and normals are evaluated in world space, including
on nonuniformly scaled objects. Moving collider velocity is not included
in the impact/friction calculation; fast moving props remain an approximation.
Max Stretch and painted pins take priority over contact clearance. If the
pose penetrates farther than the permitted displacement, or display smoothing
pulls tissue across a contact, clipping may remain.

## Performance & Animation Mode (v1.5)

The collision system is engineered for playback speed:

- **Per-frame contact caching** — all expensive spatial queries (nearest
  surface, occupancy rays) run once per frame; the physics substeps
  consume the cached contact as a plane constraint with pure math.
  Zero spatial queries inside the substep loop.
- **Broad phase** — a bounding-box distance gate skips the nearest-surface
  and ray queries when colliders are out of range. Evaluating and realizing
  collider geometry still has a cost, particularly for dense animated meshes.
- **Packed collider settings** — thickness/friction/restitution ride in
  one attribute (one query instead of three).
- **Conditional updates** — the collider scanner checks each frame but
  writes settings and collection membership only when they change.

**Animation Mode** (big toggle at the top of the Jiggle panel,
scene-wide): a fast preview profile for animators. It drops to 1 physics
substep, switches to a light volume test, and reduces the fold/squash
display blurs. An always-on stability clamp keeps 1 substep from
exploding by capping Stiffness at about Mass × (1.2 × fps)². Light,
stiff presets therefore read noticeably softer and slower in preview:
the exact reduction depends on the preset and frame rate. Firm Muscle,
tight thighs, Chest Flat and supported chest profiles are particularly
sensitive. Judge timing with it off, and toggle it off (and bake) for
final quality. The new presets use 6–10 substeps at normal quality.
New layers inherit the current mode automatically.

## Cage Preview (heavy meshes) — per layer

Every jiggle layer has its own **cage button** (the icosphere icon in
the layer row). Pressing it builds a light proxy of JUST that layer's
painted region:

- The cage contains only the vertices painted in the layer's vertex
  group, **decimated once and baked statically** at the panel's Cage
  Ratio when Blender can apply it. The proxy carries a single jiggle layer.
  If Blender cannot apply decimation (for example, because of shape keys),
  it remains a live modifier on the reduced region and costs playback time.
- While a layer's cage is active, that layer is disabled on the heavy
  mesh (the rest of your character stays visible and normal) and the
  cage region jiggles in its place, following the armature/animation.
- Press the button again to turn it off: settings you tuned on the cage
  transfer back to the layer, which re-enables at full resolution.
- With 4 layers you can run 4 independent cages. The trash icon deletes
  a layer's cage; recreate it after repainting the vertex group or
  changing the ratio. Cages never render and stack with Animation Mode.

Judge motion/timing on cages; judge folds and squash on the full mesh —
those two effects need vertex density to read.

## Baking

Use **Bake Simulation** in the panel (wraps Blender's simulation-zone
bake) once you're happy, so scrubbing and rendering are deterministic.
**Delete Bake** frees it. **Reset Simulation** just jumps to the scene
start frame, which clears the live cache.

## Tips for the most skin-like result

- Paint **soft weight gradients**. Hard weight edges = visible seams in
  motion.
- Layer it: a broad low-stiffness "fat" group underneath plus a smaller
  firmer group on top reads far more organic than one group.
- Start with the preset's Max Stretch (usually 0.008–0.08 m). It is a
  safety bound, not a target displacement. Tune timing before raising it.
- Slight Fold Smoothing (0.2–0.5, 1–3 iterations) is the difference
  between "simulation" and "flesh".
- If stiff tissue jitters or overshoots, raise Substeps first. If it
  passes through a collider, Substeps won't help (contacts are found once
  per frame): raise the collider's Thickness Outer instead.

## Limitations / notes

- The jiggle is displayed as a **local-space offset on top of the live
  animated pose**: you can grab and move the object at any time — even
  with keyframes on it, even mid-playback — and the mesh follows in real
  time, carrying its current jiggle deformation, while the simulation
  keeps running. (Standard Blender rules still apply: without autokey,
  keyframed transforms snap back on the next frame — that's Blender's
  animation system, not the sim.)
- The addon creates a hidden helper empty per jiggled object
  (`SJRef_<object name>`, with a Copy Transforms constraint). It gives
  the simulation a real depsgraph link to the object's transform so the
  viewport updates in real time while you move the object — don't delete
  it while layers exist (it is removed automatically with the last
  layer). Duplicated objects (Shift+D) get their own empty automatically.
- Linked characters need a library override before layers can be
  added; helper objects then go into a local collection.
- Removing a layer also deletes its cage.
- Simulation zones evaluate during **timeline playback**; scrubbing
  arbitrary frames without a bake shows the cached result only.
- Self-collision is not simulated, and jiggling objects don't collide
  with each other. Collision with **other objects** is supported (plane
  response from nearest surface + ray voting, best with closed collider
  meshes). Max Stretch + Fold Smoothing cover most remaining
  interpenetration cases for skin.
- Non-uniform object scale is supported, but heavily sheared parenting
  transforms may distort the normal-space split slightly.
- The generated node group `SkinJiggleCore` is shared by all layers; the
  node layout is auto-generated (a grid) but fully inspectable/editable
  if you want to extend it.

## Upgrading to 1.9.0

- Install the new Python file or `dist/skin_jiggle_physics_1.9.0.zip`.
- Press **Upgrade Layers** on existing objects. Their settings are
  preserved, and associated cages upgrade too. To adopt the new calibration,
  explicitly choose a new preset. Delete old bakes and re-bake afterwards.
- This release adds per-body collision defaults, adjustable contact styles
  and an editable hand collider button. It fixes zero-weight drift from smoothing, final stretch-limit
  violations, scale-dependent collision gaps/normals, shared-mesh collider
  settings, cross-scene Animation Mode updates, duplicate cage ownership,
  compression sampling order and bake error handling.

### Notes for 1.7.0 or earlier

- **Presets now apply as written.** Earlier versions stored whole-number
  values (e.g. Stiffness 32) into float inputs; Blender rejected them and
  every layer silently ran at the default Stiffness 60 (and default
  Damping where the preset used a whole number). Layers will now feel
  different — check them by eye, especially anything tuned before.
- Existing layers keep their old engine until you press **Upgrade
  Layers** (the red box in the Jiggle panel). It keeps all settings,
  restarts the simulation, and invalidates existing bakes of those
  layers — re-bake afterwards.
