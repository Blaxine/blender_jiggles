# ---------------------------------------------------------------------------
#  Skin Jiggle Physics — soft-tissue jiggle addon for Blender 4.1+
# ---------------------------------------------------------------------------
#  A vertex-group-driven soft tissue simulator built on Geometry Nodes
#  Simulation Zones. Each "jiggle layer" is one Geometry Nodes modifier
#  driven by a shared node group ("SkinJiggleCore"), masked by a vertex
#  group and with its own independent physical parameters.
#
#  Physics model (per vertex, per substep, simulated in WORLD space):
#    * The animated (armature-deformed) surface is the spring target.
#    * Displacement is split into normal / tangential components with
#      independent stiffness -> anisotropic springs = skin-like feel
#      (soft "out/in" along the normal, firmer sliding along the surface).
#    * Semi-implicit Euler integration with substeps, damping and speed
#      clamping relative to the animated surface's velocity, and
#      max-stretch clamping for unconditional stability.
#    * The target moves linearly through each frame's substeps, so steady
#      motion carries the tissue exactly; damping is exponential, so its
#      per-frame decay doesn't depend on the substep count.
#    * Gravity acts relative to the MODELED pose (which already hangs
#      under gravity): only orientation changes since the start (lying
#      down, bending over) make tissue sag, capped at SAG_FRACTION of
#      Max Stretch.
#    * The vertex-group weight scales the displayed offset once per frame
#      (never per substep), so gradients behave the same at any substeps.
#    * Optional world-space floor collision with restitution ("Bounce")
#      and impact friction.
#    * Because the sim runs in world space, moving/rotating the whole
#      character automatically produces inertia jiggle, and gravity is
#      always correct.
#    * A final Blur Attribute pass ("Fold Smoothing") makes neighbouring
#      skin drag together, producing folding / cohesion behaviour.
#
#  Modifier order matters:  Armature  ->  SkinJiggle layer(s)  ->  Subdiv.
# ---------------------------------------------------------------------------

bl_info = {
    "name": "Skin Jiggle Physics",
    "author": "Claude (Anthropic)",
    "version": (1, 12, 0),
    "blender": (4, 1, 0),
    "location": "3D Viewport > Sidebar (N) > Jiggle",
    "description": "High-end vertex-group soft tissue / skin jiggle physics "
                   "built on Geometry Nodes simulation zones",
    "category": "Physics",
}

import bpy
import math
import logging
from bpy.types import Operator, Panel
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.app.handlers import persistent
from mathutils import Matrix

CORE_NAME = "SkinJiggleCore"
SJ_COLL = "SJ_Colliders"
BUILD_TAG = "1.12.0"
_LOG = logging.getLogger(__name__)
SAG_FRACTION = 0.5   # gravity sag may use at most this share of Max Stretch

# ---------------------------------------------------------------------------
#  Interface (modifier inputs) definition
#  (name, socket_type, default, min, max, subtype, description)
# ---------------------------------------------------------------------------
_SOCKET_DEFS = [
    ("Weight", 'NodeSocketFloat', 1.0, 0.0, 1.0, 'FACTOR',
     "Per-vertex influence. Hook this to a vertex group (the addon does "
     "this automatically). 1 = fully dynamic, 0 = pinned, values in "
     "between scale the jiggle"),
    ("Stiffness", 'NodeSocketFloat', 230.0, 0.0, 1000.0, 'NONE',
     "Spring strength pulling tissue back to the animated surface. "
     "Low = loose fat, high = firm muscle"),
    ("Normal Softness", 'NodeSocketFloat', 0.45, 0.0, 1.0, 'FACTOR',
     "How much softer the tissue is along the surface normal than "
     "tangentially. Higher = more in/out wobble = fleshier"),
    ("Damping", 'NodeSocketFloat', 25.13, 0.0, 60.0, 'NONE',
     "Velocity decay rate in 1/s (physical damping coefficient / effective "
     "mass). Damping ratio = Damping / (2 * sqrt(normal stiffness / Mass))"),
    ("Mass", 'NodeSocketFloat', 0.2, 0.01, 100.0, 'NONE',
     "Effective spring mass; not the total anatomical mass or mass per "
     "mesh vertex. Timing depends on Stiffness / Mass"),
    ("Gravity", 'NodeSocketFloat', 1.0, 0.0, 10.0, 'NONE',
     "How strongly tissue sags when the body turns away from its "
     "modeled pose — lying down, bending over (multiplier of 9.81 m/s²). "
     "The modeled shape already includes gravity, so an upright pose "
     "doesn't sag further. Capped at half of Max Stretch"),
    ("Max Stretch", 'NodeSocketFloat', 0.025, 0.001, 10.0, 'DISTANCE',
     "Hard limit (metres, world space) on how far the JIGGLE may move a "
     "vertex from the animated surface. Collisions may push further, up "
     "to Contact Reach more"),
    ("Bounce", 'NodeSocketFloat', 0.05, 0.0, 1.0, 'FACTOR',
     "Restitution for floor and object impacts. Collider damping reduces "
     "this further; soft tissue normally has low restitution"),
    ("Substeps", 'NodeSocketInt', 6, 1, 16, 'NONE',
     "Physics substeps per frame. Raise for stiff, light tissue (high "
     "Stiffness / Mass). Collision contacts are found once per frame, "
     "so this does not stop fast impacts tunneling"),
    ("Fold Smoothing", 'NodeSocketFloat', 0.35, 0.0, 1.0, 'FACTOR',
     "Blurs the jiggle offset across neighbouring vertices so skin moves "
     "cohesively and folds instead of crawling per-vertex"),
    ("Fold Iterations", 'NodeSocketInt', 2, 0, 10, 'NONE',
     "Smoothing spread. More iterations = broader, softer folds"),
    ("Blend", 'NodeSocketFloat', 1.0, 0.0, 1.0, 'FACTOR',
     "Global fade of the whole effect (animatable)"),
    ("Floor Collision", 'NodeSocketBool', False, None, None, 'NONE',
     "Collide dynamic tissue with a world-space horizontal floor"),
    ("Floor Height", 'NodeSocketFloat', 0.0, -10000.0, 10000.0, 'DISTANCE',
     "World Z height of the collision floor"),
    ("Object Collision", 'NodeSocketBool', True, None, None, 'NONE',
     "Collide with any mesh that has Physics > Collision enabled"),
    ("Collider Collection", 'NodeSocketCollection', None, None, None, 'NONE',
     "Managed by the addon: auto-filled with every mesh that has "
     "Physics > Collision enabled"),
    ("Collision Distance", 'NodeSocketFloat', 0.002, 0.0, 1.0, 'DISTANCE',
     "Extra global offset added on top of each collider's own "
     "Thickness Outer setting"),
    ("Collision Friction", 'NodeSocketFloat', 0.5, 0.0, 1.0, 'FACTOR',
     "This layer's multiplier on each collider's own Friction "
     "setting (0.5 = neutral)"),
    ("Squash Amount", 'NodeSocketFloat', 0.35, 0.0, 5.0, 'NONE',
     "Volume-style bulge: tissue compressed by a contact pushes the "
     "surrounding skin outward by this factor"),
    ("Squash Spread", 'NodeSocketInt', 3, 0, 16, 'NONE',
     "How far the contact bulge spreads across neighbouring vertices"),
    ("Animation Mode", 'NodeSocketBool', False, None, None, 'NONE',
     "Animator preview: 1 substep + stability clamp, fast volume test, "
     "reduced fold/squash blurs. Toggled scene-wide from the panel"),
    ("Reference Object", 'NodeSocketObject', None, None, None, 'NONE',
     "Managed by the addon: hidden empty mirroring this object's world "
     "transform, so the sim updates in real time when the object moves"),
    # appended last so existing socket identifiers keep their numbers
    ("Contact Reach", 'NodeSocketFloat', 0.10, 0.0, 1.0, 'DISTANCE',
     "How much FURTHER than Max Stretch a collider may push the skin. "
     "Raise it if skin still clips into a collider; Max Stretch then "
     "keeps limiting only the jiggle"),
]

# Collapsible sections of the active layer: (id, label, icon, inputs)
_LAYER_SECTIONS = [
    ("motion", "Motion", 'FORCE_HARMONIC',
     ["Stiffness", "Damping", "Mass", "Normal Softness"]),
    ("limits", "Limits & Gravity", 'FULLSCREEN_EXIT',
     ["Max Stretch", "Contact Reach", "Gravity"]),
    ("collision", "Collision", 'MOD_PHYSICS',
     ["Object Collision", "Collision Distance", "Collision Friction",
      "Bounce", "Floor Collision", "Floor Height"]),
    ("folds", "Folds & Squash", 'MOD_SMOOTH',
     ["Fold Smoothing", "Fold Iterations", "Squash Amount",
      "Squash Spread"]),
    ("quality", "Quality", 'PREFERENCES', ["Substeps"]),
]

# ---------------------------------------------------------------------------
#  Presets
# ---------------------------------------------------------------------------
def _p(st, ns, dmp, m, g, ms, b, sub, fs, fi, sq, ss):
    """Compact preset builder:
    stiffness, normal softness, damping, mass, gravity, max stretch,
    bounce, substeps, fold smoothing, fold iterations,
    squash amount, squash spread."""
    return {"Stiffness": st, "Normal Softness": ns, "Damping": dmp,
            "Mass": m, "Gravity": g, "Max Stretch": ms, "Bounce": b,
            "Substeps": sub, "Fold Smoothing": fs, "Fold Iterations": fi,
            "Blend": 1.0, "Squash Amount": sq, "Squash Spread": ss}


def _physical_preset(hz, zeta, mass, softness, stretch, substeps=6,
                     fold=0.35, squash=0.35, bounce=0.05):
    """Map normal-mode frequency/ratio to this solver's effective units.

    k_normal = mass * (2*pi*f)**2; decay_rate = 2*zeta*2*pi*f.
    Values are animation starting points, not measured anatomical constants.
    See PRESET_GUIDE.md for calibration assumptions and research sources.
    """
    omega = 2.0 * math.pi * hz
    stiffness = mass * omega * omega / max(1.0 - softness, 0.02)
    return _p(stiffness, softness, 2.0 * zeta * omega, mass, 1.0,
              stretch, bounce, substeps, fold, 2, squash, 3)


# key: (label, normal frequency Hz, damping ratio, effective mass,
#       normal softness, maximum travel m, substeps, fold, squash, bounce)
# Cup letters are relative size labels only. They do not determine tissue mass.
_PRESET_SPECS = {
    'SOFT_SKIN': ('Soft Skin', 4.0, .50, .20, .45, .025, 6, .35, .35, .05),
    'FIRM_MUSCLE': ('Firm Muscle', 10.0, .45, .15, .15, .008, 10, .20, .15, .03),
    'HEAVY_FAT': ('Heavy / Fat', 1.7, .45, 1.0, .65, .080, 6, .50, .60, .08),
    'EXTRA_BOUNCY': ('Extra Bouncy (Stylized)', 2.5, .16, .50, .55, .120, 6, .30, .75, .35),
    'CHEST_FLAT': ('Chest — Flat', 7.0, .50, .08, .20, .006, 8, .25, .20, .03),
    'CHEST_A': ('Chest — A cup', 3.5, .35, .15, .30, .018, 6, .40, .35, .05),
    'CHEST_B': ('Chest — B cup', 3.0, .35, .25, .35, .030, 6, .40, .40, .05),
    'CHEST_C': ('Chest — C cup', 2.6, .35, .40, .40, .045, 6, .45, .45, .05),
    'CHEST_D': ('Chest — D cup', 2.2, .35, .60, .45, .060, 6, .45, .50, .05),
    'SBRA_A': ('Sports Bra — A', 6.5, .65, .15, .25, .008, 8, .30, .15, .02),
    'SBRA_B': ('Sports Bra — B', 5.8, .65, .25, .25, .012, 8, .30, .18, .02),
    'SBRA_C': ('Sports Bra — C', 5.1, .65, .40, .30, .018, 8, .30, .20, .02),
    'SBRA_D': ('Sports Bra — D', 4.5, .65, .60, .30, .025, 8, .30, .25, .02),
    'BRA_A': ('Bra — A', 4.7, .50, .15, .30, .012, 6, .35, .25, .03),
    'BRA_B': ('Bra — B', 4.2, .50, .25, .35, .020, 6, .35, .30, .03),
    'BRA_C': ('Bra — C', 3.7, .50, .40, .40, .030, 6, .35, .35, .03),
    'BRA_D': ('Bra — D', 3.2, .50, .60, .45, .040, 6, .35, .40, .03),
    'GLUTE_SOFT': ('Glutes — Soft', 2.8, .45, .65, .50, .050, 6, .45, .55, .05),
    'GLUTE_TIGHT': ('Glutes — Tight', 5.5, .50, .40, .30, .022, 8, .30, .30, .03),
    'GLUTE_FIRM': ('Glutes — Firm', 7.0, .55, .30, .20, .015, 8, .25, .20, .03),
    'THIGH_SOFT': ('Thighs — Soft', 4.0, .45, .40, .40, .030, 6, .35, .35, .05),
    'THIGH_FIRM': ('Thighs — Firm', 7.0, .50, .22, .25, .015, 8, .25, .20, .03),
    'THIGH_TIGHT': ('Thighs — Tight', 9.0, .50, .18, .15, .010, 10, .20, .15, .03),
    'BELLY_SOFT': ('Belly — Soft', 2.0, .45, .80, .60, .060, 6, .50, .60, .05),
    'BELLY_FIRM': ('Belly — Firm', 4.5, .55, .40, .35, .025, 6, .30, .30, .03),
    # ------------------------------------------------------- materials
    # Derived from material data; see PRESET_REALISM.md for the sources.
    # Jelly: shear-wave wobble of a 6-8 cm gelatin block (G ~0.6-1.2 kPa)
    # is 2.4-4.4 Hz; an elastic gel's tan(delta) ~0.1 gives zeta 0.05.
    'JELLY': ('Jelly', 3.0, .05, .30, .10, .040, 6, .60, .60, .30),
    # Pudding: starch weak gel, G' ~80-140 Pa -> 1.0-1.8 Hz; tan(delta)
    # ~0.3 -> zeta 0.15.
    'PUDDING': ('Pudding', 1.2, .15, .30, .30, .050, 6, .70, 1.0, .02),
    # Bouncing ball: zeta from restitution 0.85 (rebound to 72 % of the
    # drop). Real squash rings at ~100 Hz; slowed to 3.5 Hz to be visible.
    'BOUNCING_BALL': ('Bouncing Ball (Stylized)', 3.5, .052, .30, .60, .050,
                      6, .50, .80, .85),
    # Water bed: first slosh modes of an 84 x 60-72 in, 8-10 in deep
    # mattress are 0.32-0.48 Hz; waves fading over ~7.5 s give zeta 0.12.
    'WATER_BED': ('Water Bed', 0.4, .12, .30, .80, .080, 6, .80, 1.0, .05),
}

# Per-body defaults: added skin clearance (m), collider-friction multiplier,
# soft-contact squash amount, low restitution and local bulge spread.
# These are tunable art defaults; collider Thickness Outer remains per object.
_CONTACT_PRESET_BASE = {
    'SOFT_SKIN': (.0015, .55, .35, .03, 3),
    'FIRM_MUSCLE': (.0010, .45, .20, .02, 2),
    'HEAVY_FAT': (.0030, .70, .65, .04, 4),
    'EXTRA_BOUNCY': (.0020, .65, .80, .30, 3),
    'CHEST_FLAT': (.0008, .40, .15, .02, 2),
    'CHEST_A': (.0015, .52, .30, .03, 3),
    'CHEST_B': (.0020, .56, .38, .03, 3),
    'CHEST_C': (.0025, .60, .45, .03, 4),
    'CHEST_D': (.0030, .64, .52, .03, 4),
    'SBRA_A': (.0005, .34, .10, .01, 2),
    'SBRA_B': (.0007, .36, .12, .01, 2),
    'SBRA_C': (.0010, .38, .15, .01, 2),
    'SBRA_D': (.0012, .40, .18, .01, 3),
    'BRA_A': (.0010, .42, .20, .02, 2),
    'BRA_B': (.0012, .45, .24, .02, 3),
    'BRA_C': (.0015, .48, .28, .02, 3),
    'BRA_D': (.0020, .51, .32, .02, 3),
    'GLUTE_SOFT': (.0030, .70, .70, .04, 4),
    'GLUTE_TIGHT': (.0015, .55, .38, .03, 3),
    'GLUTE_FIRM': (.0010, .45, .22, .02, 2),
    'THIGH_SOFT': (.0020, .58, .40, .03, 3),
    'THIGH_FIRM': (.0012, .44, .25, .02, 2),
    'THIGH_TIGHT': (.0008, .38, .16, .01, 2),
    'BELLY_SOFT': (.0030, .70, .70, .04, 4),
    'BELLY_FIRM': (.0015, .50, .32, .02, 3),
    'JELLY': (.0020, .30, .60, .30, 4),          # slippery, springy rebound
    'PUDDING': (.0020, .60, 1.0, .02, 5),        # sticky, bulges, no rebound
    'BOUNCING_BALL': (.0015, .50, .80, .85, 4),  # restitution 0.85
    'WATER_BED': (.0030, .30, 1.0, .05, 8),      # wide displacement ring
}

_CONTACT_STYLES = [
    ('BODY', 'Body preset', 'Contact defaults tuned for the selected tissue preset'),
    ('HAND', 'Soft hand', 'Low bounce, broad yielding contact with modest grip'),
    ('GRIP', 'Firm grip', 'High friction, no bounce, stronger visible compression'),
    ('STYLIZED', 'Stylized', 'Deliberately larger squash and lively rebound'),
]
def _preset_values(key):
    spec = _PRESET_SPECS[key]
    values = _physical_preset(*spec[1:])
    gap, friction, squash, bounce, spread = _CONTACT_PRESET_BASE[key]
    values.update({'Collision Distance': gap, 'Collision Friction': friction,
                   'Squash Amount': squash, 'Bounce': bounce,
                   'Squash Spread': spread})
    return values


PRESETS = {key: (spec[0], _preset_values(key))
           for key, spec in _PRESET_SPECS.items()}
# Factory reset and a manually added node modifier use the exact Soft Skin
# profile rather than a separately maintained set of rounded constants.
_SOCKET_DEFS = [(name, kind, PRESETS['SOFT_SKIN'][1].get(name, default),
                 lo, hi, subtype, description)
                for name, kind, default, lo, hi, subtype, description in _SOCKET_DEFS]

_PRESET_GROUPS = [
    ("General", ['SOFT_SKIN', 'FIRM_MUSCLE', 'HEAVY_FAT', 'EXTRA_BOUNCY']),
    ("Chest", ['CHEST_FLAT', 'CHEST_A', 'CHEST_B', 'CHEST_C', 'CHEST_D']),
    ("Sports Bra", ['SBRA_A', 'SBRA_B', 'SBRA_C', 'SBRA_D']),
    ("Bra", ['BRA_A', 'BRA_B', 'BRA_C', 'BRA_D']),
    ("Glutes", ['GLUTE_SOFT', 'GLUTE_TIGHT', 'GLUTE_FIRM']),
    ("Thighs", ['THIGH_SOFT', 'THIGH_FIRM', 'THIGH_TIGHT']),
    ("Belly", ['BELLY_SOFT', 'BELLY_FIRM']),
    ("Materials", ['JELLY', 'PUDDING', 'BOUNCING_BALL', 'WATER_BED']),
]

def _build_preset_enum():
    items, idx = [], 0
    for category, keys in _PRESET_GROUPS:
        items.append(("", category, ""))          # separator / header
        for k in keys:
            items.append((k, PRESETS[k][0], "", 'NONE', idx))
            idx += 1
    return items

_PRESET_ENUM = _build_preset_enum()


# ===========================================================================
#  Node group construction
# ===========================================================================
def _build_interface(ng):
    ng.interface.new_socket(name="Geometry", in_out='INPUT',
                            socket_type='NodeSocketGeometry')
    for name, stype, default, mn, mx, subtype, desc in _SOCKET_DEFS:
        s = ng.interface.new_socket(name=name, in_out='INPUT',
                                    socket_type=stype, description=desc)
        try:
            if default is not None:
                s.default_value = default
            if mn is not None:
                s.min_value = mn
            if mx is not None:
                s.max_value = mx
            if subtype and subtype != 'NONE' and hasattr(s, "subtype"):
                s.subtype = subtype
        except (AttributeError, TypeError):
            pass
    ng.interface.new_socket(name="Geometry", in_out='OUTPUT',
                            socket_type='NodeSocketGeometry')


def _build_core_group():
    """Create (or return existing) the shared simulation node group."""
    # an outdated group keeps the base name, so a rebuild lands on
    # "SkinJiggleCore.001" etc. — match any of them by build tag
    for existing in bpy.data.node_groups:
        if (existing.name.startswith(CORE_NAME)
                and existing.get("sj_build") == BUILD_TAG):
            return existing

    ng = bpy.data.node_groups.new(CORE_NAME, 'GeometryNodeTree')
    ng.is_modifier = True
    _build_interface(ng)

    nodes, links = ng.nodes, ng.links

    # -------------------------------------------------------- tiny helpers
    def hook(sock_in, v):
        """Link a socket, or set a constant default value."""
        if isinstance(v, bpy.types.NodeSocket):
            links.new(v, sock_in)
        else:
            sock_in.default_value = v

    def ZS(socket_collection, name="Geometry"):
        """Version-tolerant geometry socket lookup for zone nodes."""
        s = socket_collection.get(name)
        if s is not None:
            return s
        for cand in socket_collection:
            if getattr(cand, "type", "") == 'GEOMETRY':
                return cand
        raise KeyError(f"No geometry socket '{name}' found")

    def VM(op, a, b=None):
        n = nodes.new('ShaderNodeVectorMath')
        n.operation = op
        hook(n.inputs[0], a)
        if b is not None:
            if op == 'SCALE':
                hook(n.inputs['Scale'], b)
            else:
                hook(n.inputs[1], b)
        if op in {'DOT_PRODUCT', 'LENGTH', 'DISTANCE'}:
            return n.outputs['Value']
        return n.outputs['Vector']

    def MT(op, a, b=None):
        n = nodes.new('ShaderNodeMath')
        n.operation = op
        hook(n.inputs[0], a)
        if b is not None:
            hook(n.inputs[1], b)
        return n.outputs[0]

    def STORE(geo, name, value=None, dtype='FLOAT_VECTOR'):
        n = nodes.new('GeometryNodeStoreNamedAttribute')
        n.data_type = dtype
        n.domain = 'POINT'
        links.new(geo, n.inputs['Geometry'])
        n.inputs['Name'].default_value = name
        if value is not None:
            hook(n.inputs['Value'], value)
        return n.outputs['Geometry']

    def NATTR(name, dtype='FLOAT_VECTOR'):
        n = nodes.new('GeometryNodeInputNamedAttribute')
        n.data_type = dtype
        n.inputs['Name'].default_value = name
        return n.outputs['Attribute']

    def SAMPLE(geo, value, index, dtype='FLOAT_VECTOR'):
        n = nodes.new('GeometryNodeSampleIndex')
        n.data_type = dtype
        n.domain = 'POINT'
        links.new(geo, n.inputs['Geometry'])
        links.new(value, n.inputs['Value'])
        links.new(index, n.inputs['Index'])
        return n.outputs['Value']

    def ROT(vec, rot):
        n = nodes.new('FunctionNodeRotateVector')
        hook(n.inputs['Vector'], vec)
        links.new(rot, n.inputs['Rotation'])
        return n.outputs['Vector']

    def INVROT(rot):
        n = nodes.new('FunctionNodeInvertRotation')
        links.new(rot, n.inputs['Rotation'])
        return n.outputs['Rotation']

    def SEP(vec):
        n = nodes.new('ShaderNodeSeparateXYZ')
        hook(n.inputs[0], vec)
        return n

    def COMB(x, y, z):
        n = nodes.new('ShaderNodeCombineXYZ')
        hook(n.inputs['X'], x)
        hook(n.inputs['Y'], y)
        hook(n.inputs['Z'], z)
        return n.outputs['Vector']

    def CMP_LT(a, b):
        n = nodes.new('FunctionNodeCompare')
        n.data_type = 'FLOAT'
        n.operation = 'LESS_THAN'
        hook(n.inputs['A'], a)
        hook(n.inputs['B'], b)
        return n.outputs['Result']

    def BAND(a, b):
        n = nodes.new('FunctionNodeBooleanMath')
        n.operation = 'AND'
        hook(n.inputs[0], a)
        hook(n.inputs[1], b)
        return n.outputs[0]

    def BOR(a, b):
        n = nodes.new('FunctionNodeBooleanMath')
        n.operation = 'OR'
        hook(n.inputs[0], a)
        hook(n.inputs[1], b)
        return n.outputs[0]

    def BNOT(a):
        n = nodes.new('FunctionNodeBooleanMath')
        n.operation = 'NOT'
        hook(n.inputs[0], a)
        return n.outputs[0]

    def POINTS(geo):
        n = nodes.new('GeometryNodeAttributeDomainSize')
        n.component = 'MESH'
        links.new(geo, n.inputs['Geometry'])
        return n.outputs['Point Count']

    def SWITCHF(cond, f, t):
        n = nodes.new('GeometryNodeSwitch')
        n.input_type = 'FLOAT'
        links.new(cond, n.inputs['Switch'])
        hook(n.inputs['False'], f)
        hook(n.inputs['True'], t)
        return n.outputs['Output']

    def SWITCHV(cond, f, t):
        n = nodes.new('GeometryNodeSwitch')
        n.input_type = 'VECTOR'
        links.new(cond, n.inputs['Switch'])
        hook(n.inputs['False'], f)
        hook(n.inputs['True'], t)
        return n.outputs['Output']

    def SWITCHI(cond, f, t):
        n = nodes.new('GeometryNodeSwitch')
        n.input_type = 'INT'
        links.new(cond, n.inputs['Switch'])
        hook(n.inputs['False'], f)
        hook(n.inputs['True'], t)
        return n.outputs['Output']

    def SWITCHB(cond, f, t):
        n = nodes.new('GeometryNodeSwitch')
        n.input_type = 'BOOLEAN'
        links.new(cond, n.inputs['Switch'])
        hook(n.inputs['False'], f)
        hook(n.inputs['True'], t)
        return n.outputs['Output']

    def SWITCHG(cond, geo_false, geo_true):
        n = nodes.new('GeometryNodeSwitch')
        n.input_type = 'GEOMETRY'
        links.new(cond, n.inputs['Switch'])
        links.new(geo_false, n.inputs['False'])
        links.new(geo_true, n.inputs['True'])
        return n.outputs['Output']

    def MIXV(fac, a, b):
        n = nodes.new('ShaderNodeMix')
        n.data_type = 'VECTOR'
        hook(n.inputs[0], fac)   # Factor (float)
        hook(n.inputs[4], a)     # A (vector)
        hook(n.inputs[5], b)     # B (vector)
        return n.outputs[1]      # Result (vector)

    def CLAMP01(v):
        n = nodes.new('ShaderNodeClamp')
        hook(n.inputs['Value'], v)
        n.inputs['Min'].default_value = 0.0
        n.inputs['Max'].default_value = 1.0
        return n.outputs[0]

    def OBJINFO(gi_node):
        # NOTE: 'Self Object' is intentionally NOT used here. It creates
        # no depsgraph relation, so moving the object would not trigger
        # re-evaluation and the viewport shows stale results. Instead we
        # read a hidden reference empty (Copy Transforms of the object)
        # supplied by the addon -> proper dependency, real-time updates.
        o = nodes.new('GeometryNodeObjectInfo')
        o.transform_space = 'ORIGINAL'
        links.new(gi_node.outputs['Reference Object'], o.inputs['Object'])
        return o

    def TO_WORLD(vec_local, oi):
        scaled = VM('MULTIPLY', vec_local, oi.outputs['Scale'])
        rotated = ROT(scaled, oi.outputs['Rotation'])
        return VM('ADD', rotated, oi.outputs['Location'])

    def NORMAL_WORLD(n, oi):
        # Normals use the inverse transpose, not the position transform.
        return VM('NORMALIZE', ROT(VM('DIVIDE', n, oi.outputs['Scale']),
                                   oi.outputs['Rotation']))

    def WORLD_GEOMETRY(geo, oi):
        n = nodes.new('GeometryNodeTransform')
        links.new(geo, n.inputs['Geometry'])
        links.new(oi.outputs['Location'], n.inputs['Translation'])
        links.new(oi.outputs['Rotation'], n.inputs['Rotation'])
        links.new(oi.outputs['Scale'], n.inputs['Scale'])
        return n.outputs['Geometry']

    # ----------------------------------------------------------- group I/O
    gi_pre = nodes.new('NodeGroupInput')
    gi_zone = nodes.new('NodeGroupInput')
    gi_post = nodes.new('NodeGroupInput')
    g_out = nodes.new('NodeGroupOutput')

    def GP(name):  # zone-side parameter
        return gi_zone.outputs[name]

    scene_sec = nodes.new('GeometryNodeInputSceneTime').outputs['Seconds']

    def K_NORM(P, k_t):
        return MT('MULTIPLY', k_t,
                  MT('MAXIMUM', MT('SUBTRACT', 1.0, P("Normal Softness")),
                     0.02))

    def CAPV(v, max_len):
        f = MT('MINIMUM', MT('DIVIDE', max_len,
                             MT('MAXIMUM', VM('LENGTH', v), 1e-9)), 1.0)
        return VM('SCALE', v, f)

    def GRAVITY(P, nrm, n0, k_t, k_n, m):
        """Gravity relative to the MODELED pose. The sculpted shape already
        hangs under gravity, so applying full gravity on top would sag it
        a second time (Heavy/Fat dropped ~15 cm at rest). Only the change
        since the start state counts: the start gravity is rotated along
        with the surface normal (n0 -> nrm) and subtracted, so tissue sags
        when the body lies down or bends over, not when standing as
        modeled. Rotation about the normal itself is not seen.
        The result is split into tangential / normal parts, each capped
        so its sag uses at most SAG_FRACTION of Max Stretch."""
        g = COMB(0.0, 0.0, MT('MULTIPLY', P("Gravity"), -9.81))
        # Rodrigues rotation taking n0 onto nrm, applied to g:
        # g*d + c x g + c (c.g) / (1 + d), with c = n0 x nrm, d = n0.nrm
        c = VM('CROSS_PRODUCT', n0, nrm)
        d = VM('DOT_PRODUCT', n0, nrm)
        g_start = VM('ADD',
                     VM('ADD', VM('SCALE', g, d), VM('CROSS_PRODUCT', c, g)),
                     VM('SCALE', c, MT('DIVIDE', VM('DOT_PRODUCT', c, g),
                                       MT('MAXIMUM', MT('ADD', d, 1.0),
                                          1e-4))))
        g = VM('SUBTRACT', g, g_start)
        g_n = VM('SCALE', nrm, VM('DOT_PRODUCT', g, nrm))
        g_t = VM('SUBTRACT', g, g_n)
        lim = MT('MULTIPLY', P("Max Stretch"), SAG_FRACTION)
        return (CAPV(g_t, MT('DIVIDE', MT('MULTIPLY', lim, k_t), m)),
                CAPV(g_n, MT('DIVIDE', MT('MULTIPLY', lim, k_n), m)))

    def INIT_STATE(geo, oi):
        """Fresh sim state: the animated surface at rest, zero velocity,
        and the surface normal that defines the modeled orientation."""
        p_w = TO_WORLD(nodes.new('GeometryNodeInputPosition').outputs[0], oi)
        n_w = NORMAL_WORLD(nodes.new('GeometryNodeInputNormal').outputs[0], oi)
        s = STORE(geo, "sj_pos", p_w)
        s = STORE(s, "sj_n0", n_w)     # modeled orientation (gravity ref)
        s = STORE(s, "sj_vel", None)   # defaults to (0,0,0)
        s = STORE(s, "sj_tgt", p_w)    # previous-frame target
        s = STORE(s, "sj_hastgt", True, dtype='BOOLEAN')
        s = STORE(s, "sj_started", False, dtype='BOOLEAN')
        s = STORE(s, "sj_sec", scene_sec, dtype='FLOAT')   # state's time
        return s

    # =========================================================== PRE ZONE
    # Initialise the simulation state on the geometry entering the
    # simulation zone (only used on the very first frame).
    oi_pre = OBJINFO(gi_pre)
    g = INIT_STATE(gi_pre.outputs['Geometry'], oi_pre)

    # ------------------------------------------------------ simulation zone
    sim_in = nodes.new('GeometryNodeSimulationInput')
    sim_out = nodes.new('GeometryNodeSimulationOutput')
    sim_in.pair_with_output(sim_out)
    if not len(sim_out.state_items):
        sim_out.state_items.new('GEOMETRY', "Geometry")

    links.new(g, ZS(sim_in.inputs))

    # ---- effective substeps: Animation Mode collapses to 1 substep;
    # the stiffness stability clamp below keeps integration safe.
    sub_eff = SWITCHI(GP("Animation Mode"), GP("Substeps"), 1)

    # substep delta time (clamped so frame-jumps can't explode the sim).
    # Blender caps the zone's Delta Time at ONE frame when frames are
    # skipped (dropped frames, jumping ahead), so the real elapsed time
    # comes from the scene clock against the time stored with the state.
    dt_raw = sim_in.outputs['Delta Time']
    stepping = CMP_LT(1e-6, dt_raw)
    dt_frame = MT('MINIMUM', dt_raw, 0.1)
    elapsed = MT('SUBTRACT', scene_sec, NATTR("sj_sec", 'FLOAT'))
    dt = MT('DIVIDE', dt_frame, sub_eff)

    # ------------------- shared fields / animated target transforms
    idx = nodes.new('GeometryNodeInputIndex').outputs[0]
    pos_f = nodes.new('GeometryNodeInputPosition').outputs[0]
    nrm_f = nodes.new('GeometryNodeInputNormal').outputs[0]

    # Current-frame animated surface, sampled from the (live) group input:
    tgt_local = SAMPLE(gi_zone.outputs['Geometry'], pos_f, idx)
    nrm_local = SAMPLE(gi_zone.outputs['Geometry'], nrm_f, idx)
    weight = SAMPLE(gi_zone.outputs['Geometry'], GP("Weight"), idx,
                    dtype='FLOAT')

    oi_zone = OBJINFO(gi_zone)
    tgt_world = TO_WORLD(tgt_local, oi_zone)
    nrm_world = NORMAL_WORLD(nrm_local, oi_zone)

    # Previous state
    jpos = NATTR("sj_pos")
    jvel = NATTR("sj_vel")

    # Animated surface velocity, from last frame's target (sj_tgt is
    # written once per frame, after the substep loop). Damping and the
    # speed clamp act on velocity RELATIVE to it, so a body moving at
    # constant speed carries its tissue along — only acceleration jiggles.
    # Uses the real elapsed time: after skipped frames the surface covered
    # that distance over several frames, not one. States without a stored
    # target (built by an older version) report zero.
    tgt_step = VM('SCALE', VM('SUBTRACT', tgt_world, NATTR("sj_tgt")),
                  MT('DIVIDE', 1.0, MT('MAXIMUM', elapsed, 1e-6)))
    tgt_ok = BAND(BAND(stepping, CMP_LT(1e-6, elapsed)),
                  NATTR("sj_hastgt", 'BOOLEAN'))
    tgt_vel = SWITCHV(tgt_ok, (0.0, 0.0, 0.0), tgt_step)

    # ============== PER-FRAME CONTACT PASS (runs ONCE, not per substep)
    # All BVH-accelerated queries (nearest surface, occupancy rays) are
    # evaluated here once per frame against the state positions, and the
    # results are cached as attributes. The substep loop consumes the
    # cache with pure math -> ZERO BVH queries inside the loop.
    col_info = nodes.new('GeometryNodeCollectionInfo')
    col_info.transform_space = 'RELATIVE'
    links.new(GP("Collider Collection"), col_info.inputs['Collection'])
    col_real = nodes.new('GeometryNodeRealizeInstances')
    # 4.1: Collection Info's output socket is named 'Instances'
    links.new(ZS(col_info.outputs, "Instances"),
              col_real.inputs['Geometry'])

    # TRUE face normals on the colliders (vertex-interpolated normals
    # break on low-poly hard-surface colliders).
    col_fn = nodes.new('GeometryNodeStoreNamedAttribute')
    col_fn.data_type = 'FLOAT_VECTOR'
    col_fn.domain = 'FACE'
    links.new(WORLD_GEOMETRY(col_real.outputs['Geometry'], oi_zone),
              col_fn.inputs['Geometry'])
    col_fn.inputs['Name'].default_value = "sj_fnrm"
    links.new(nrm_f, col_fn.inputs['Value'])
    col_geo = col_fn.outputs['Geometry']

    col_size = nodes.new('GeometryNodeAttributeDomainSize')
    col_size.component = 'MESH'
    links.new(col_geo, col_size.inputs['Geometry'])
    has_faces = CMP_LT(0.5, col_size.outputs['Face Count'])

    # ---- BROAD PHASE: bounding-box distance gate. All values here are
    # uniform (single values), so the geometry Switch below evaluates
    # lazily: when colliders are out of range the ENTIRE detection chain
    # is skipped for the frame -> near-zero collision cost in open space.
    bb_c = nodes.new('GeometryNodeBoundBox')
    links.new(col_geo, bb_c.inputs['Geometry'])
    bb_s = nodes.new('GeometryNodeBoundBox')
    links.new(WORLD_GEOMETRY(gi_zone.outputs['Geometry'], oi_zone),
              bb_s.inputs['Geometry'])
    gap_a = VM('MAXIMUM',
               VM('SUBTRACT', bb_c.outputs['Min'], bb_s.outputs['Max']),
               (0.0, 0.0, 0.0))
    gap_b = VM('MAXIMUM',
               VM('SUBTRACT', bb_s.outputs['Min'], bb_c.outputs['Max']),
               (0.0, 0.0, 0.0))
    box_dist = VM('LENGTH', VM('ADD', gap_a, gap_b))
    # Outer thickness can be larger than the old fixed 0.3 m margin.
    settings_stat = nodes.new('GeometryNodeAttributeStatistic')
    settings_stat.data_type = 'FLOAT'
    settings_stat.domain = 'POINT'
    links.new(col_geo, settings_stat.inputs['Geometry'])
    links.new(SEP(NATTR('sj_set')).outputs['X'], settings_stat.inputs['Attribute'])
    margin = MT('ADD', GP("Max Stretch"),
                MT('ADD', GP("Collision Distance"), settings_stat.outputs['Max']))
    within = CMP_LT(box_dist, margin)
    col_active = BAND(within, BAND(has_faces, GP("Object Collision")))

    # ---- topology guard: the state is matched to the live mesh by vertex
    # index. If the counts differ (mesh edited, a modifier above toggled,
    # viewport vs render subdivision) the state is meaningless -> restart
    # from the rest state instead of scrambling vertices.
    same_topo = CMP_LT(MT('ABSOLUTE',
                          MT('SUBTRACT', POINTS(ZS(sim_in.outputs)),
                             POINTS(gi_zone.outputs['Geometry']))), 0.5)
    state_geo = SWITCHG(same_topo,
                        INIT_STATE(gi_zone.outputs['Geometry'], oi_zone),
                        ZS(sim_in.outputs))

    # detection is evaluated against last frame's dynamic positions
    pl = jpos

    def SNS(value_field, dtype='FLOAT_VECTOR', sample_position=pl):
        n = nodes.new('GeometryNodeSampleNearestSurface')
        n.data_type = dtype
        links.new(col_geo, n.inputs['Mesh'])
        links.new(value_field, n.inputs['Value'])
        links.new(sample_position, n.inputs['Sample Position'])
        return n.outputs['Value']

    surf_p = SNS(pos_f)                       # closest point on collider
    surf_n = VM('NORMALIZE',
                SNS(NATTR("sj_fnrm")))        # true face normal there
    # Also sample where the animated target is heading. A fast press can
    # otherwise move the target through a thin collider while the inertial
    # state is still outside the one-frame contact query.
    surf_tgt_p = SNS(pos_f, sample_position=tgt_world)
    surf_tgt_n = VM('NORMALIZE',
                    SNS(NATTR("sj_fnrm"), sample_position=tgt_world))

    # Per-object collision settings, packed into ONE vector attribute by
    # the addon (x = Thickness Outer, y = Friction 0..1, z = restitution)
    # -> a single nearest-surface query instead of three.
    setv = SEP(SNS(NATTR("sj_set")))
    cd_eff = MT('ADD', setv.outputs['X'], GP("Collision Distance"))
    fr_eff = CLAMP01(MT('MULTIPLY', setv.outputs['Y'],
                        MT('MULTIPLY', GP("Collision Friction"), 2.0)))
    bn_eff = MT('MULTIPLY', CLAMP01(setv.outputs['Z']), GP("Bounce"))

    to_s = VM('SUBTRACT', surf_p, pl)
    dist_s = VM('LENGTH', to_s)
    dist_tgt = VM('LENGTH', VM('SUBTRACT', surf_tgt_p, tgt_world))

    # ---- volumetric inside test.
    # Full quality: fixed-direction 3-ray backface VOTING (robust on
    # concave, thin and open meshes; >= 2 of 3 must agree).
    # Animation Mode: 1 ray + nearest-face plane sign — cheaper, fine
    # for clean closed colliders in preview.
    def RAY_VOTE(direction, source_position=pl):
        r = nodes.new('GeometryNodeRaycast')
        links.new(col_geo, r.inputs['Target Geometry'])
        links.new(source_position, r.inputs['Source Position'])
        r.inputs['Ray Direction'].default_value = direction
        r.inputs['Ray Length'].default_value = 100000.0
        back = CMP_LT(0.0, VM('DOT_PRODUCT',
                              r.outputs['Hit Normal'], direction))
        return BAND(r.outputs['Is Hit'], back)

    v1 = RAY_VOTE((0.2860, 0.3530, 0.8908))
    votes = MT('ADD',
               MT('ADD', v1, RAY_VOTE((-0.5370, 0.2290, 0.8119))),
               RAY_VOTE((0.4120, -0.6780, -0.6088)))
    inside_full = CMP_LT(1.5, votes)
    plane_neg = CMP_LT(VM('DOT_PRODUCT', VM('SUBTRACT', pl, surf_p),
                          surf_n), 0.0)
    inside_fast = BAND(v1, plane_neg)
    # uniform selector -> only the chosen branch is evaluated
    inside = SWITCHB(GP("Animation Mode"), inside_full, inside_fast)

    # Collision geometry is sampled once per frame. Expand the query radius
    # by the larger of the animated target and free-state travel this frame,
    # so the cached contact exists before a moving tissue point crosses the
    # surface. The response plane still uses the true contact clearance.
    target_sweep = VM('LENGTH', VM('SCALE', tgt_vel, dt_frame))
    tissue_sweep = VM('LENGTH', VM('SCALE', jvel, dt_frame))
    sweep_margin = MT('MAXIMUM', target_sweep, tissue_sweep)
    contact_range = MT('ADD', cd_eff, sweep_margin)
    near = CMP_LT(dist_s, contact_range)
    near_target = CMP_LT(dist_tgt, contact_range)
    # Keep a valid plane cached for every vertex whose free state is allowed
    # to reach the surface this frame. Max Stretch bounds state displacement;
    # including it in the spatial gate prevents a contact flag from expiring
    # while springs and the animated target are crossing in opposite ways.
    within_reach = CMP_LT(dist_s, MT('ADD', GP('Max Stretch'),
                                    MT('ADD', cd_eff, sweep_margin)))
    use_target_contact = BAND(near_target, CMP_LT(dist_tgt, dist_s))
    contact_surf_p = SWITCHV(use_target_contact, surf_p, surf_tgt_p)
    contact_surf_n = SWITCHV(use_target_contact, surf_n, surf_tgt_n)
    pen = BOR(BOR(BOR(inside, near), near_target), within_reach)

    # ---- cache the contact as a plane constraint (world space)
    cp_world = VM('ADD', contact_surf_p,
                  VM('SCALE', contact_surf_n, cd_eff))
    cn_world = contact_surf_n

    c1 = STORE(state_geo, "sj_chit", pen, dtype='BOOLEAN')
    c2 = STORE(c1, "sj_cp", cp_world)
    c3 = STORE(c2, "sj_cn", cn_world)
    c4 = STORE(c3, "sj_cfb",
               COMB(fr_eff, bn_eff, 0.0))

    no_contact = STORE(state_geo, "sj_chit", False, dtype='BOOLEAN')
    geo_pre = SWITCHG(col_active, no_contact, c4)

    # ---- per-frame state prep (once, before the substeps)
    # Skipped frames: the substeps integrate at most one frame, so for the
    # rest of the elapsed time the tissue rides along with the surface
    # instead of being left behind and yanked by the stretch limit.
    catch_up = VM('SCALE', tgt_vel,
                  MT('MAXIMUM', MT('SUBTRACT', elapsed, dt_frame), 0.0))
    geo_pre = STORE(geo_pre, "sj_pos", VM('ADD', jpos, catch_up))
    # First real step: start the tissue at the surface's velocity, so a
    # shot that begins mid-motion doesn't open with a backwards jolt.
    first_step = BAND(stepping, BNOT(NATTR("sj_started", 'BOOLEAN')))
    geo_pre = STORE(geo_pre, "sj_vel", SWITCHV(first_step, jvel, tgt_vel))
    geo_pre = STORE(geo_pre, "sj_tsub", 0.0, dtype='FLOAT')   # substep clock

    # --------------------------------------------------------- repeat zone
    rep_in = nodes.new('GeometryNodeRepeatInput')
    rep_out = nodes.new('GeometryNodeRepeatOutput')
    rep_in.pair_with_output(rep_out)
    if not len(rep_out.repeat_items):
        rep_out.repeat_items.new('GEOMETRY', "Geometry")

    links.new(sub_eff, rep_in.inputs['Iterations'])
    links.new(geo_pre, ZS(rep_in.inputs))

    # --- anisotropic spring with STABILITY CLAMP: stiffness is limited
    # so omega*dt stays in the stable range for the CURRENT timestep.
    # This is what lets Animation Mode run 1 substep without exploding —
    # light, stiff presets soften in preview instead of blowing up (at
    # 24 fps Chest Flat runs at ~1/10 of its stiffness); at each preset's
    # own substep count the clamp stays above its stiffness.
    m_safe = MT('MAXIMUM', GP("Mass"), 1e-4)
    ratio = MT('DIVIDE', 1.2, MT('MAXIMUM', dt, 1e-5))
    k_max = MT('MULTIPLY', m_safe, MT('MULTIPLY', ratio, ratio))
    k_t = MT('MINIMUM', GP("Stiffness"), k_max)

    # Target moved linearly through the frame. The spring compares the
    # position with the target at the same instant (substep start) and the
    # stretch limit applies at the substep end; chasing the end-of-frame
    # target instead makes steadily moving tissue settle AHEAD of it.
    def TGT_AT(t):
        return VM('SUBTRACT', tgt_world,
                  VM('SCALE', tgt_vel,
                     MT('MAXIMUM', MT('SUBTRACT', dt_frame, t), 0.0)))

    t_sub = MT('ADD', NATTR("sj_tsub", 'FLOAT'), dt)
    tgt_sub = TGT_AT(t_sub)

    disp = VM('SUBTRACT', jpos, TGT_AT(NATTR("sj_tsub", 'FLOAT')))
    dot_n = VM('DOT_PRODUCT', disp, nrm_world)
    d_norm = VM('SCALE', nrm_world, dot_n)
    d_tan = VM('SUBTRACT', disp, d_norm)

    k_norm = K_NORM(GP, k_t)

    spring = VM('ADD',
                VM('SCALE', d_tan, k_t),
                VM('SCALE', d_norm, k_norm))

    inv_mass_neg = MT('DIVIDE', -1.0, m_safe)
    acc_spring = VM('SCALE', spring, inv_mass_neg)
    g_t, g_n = GRAVITY(GP, nrm_world, NATTR("sj_n0"), k_t, k_norm, m_safe)
    accel = VM('ADD', acc_spring, VM('ADD', g_t, g_n))

    # --- integrate velocity (semi-implicit Euler), then damp and speed
    # clamp the velocity relative to the animated surface. Exponential
    # damping gives the same decay per frame at any substep count (the
    # linear 1 - c*dt form over-damps at 1 substep and hits 0 for
    # Damping >= fps).
    vel = VM('ADD', jvel, VM('SCALE', accel, dt))
    damp_f = MT('EXPONENT',
                MT('MULTIPLY', GP("Damping"), MT('MULTIPLY', dt, -1.0)))
    rel = VM('SCALE', VM('SUBTRACT', vel, tgt_vel), damp_f)

    speed = VM('LENGTH', rel)
    v_max = MT('MULTIPLY', GP("Max Stretch"), 60.0)
    spd_f = MT('MINIMUM',
               MT('DIVIDE', v_max, MT('MAXIMUM', speed, 1e-6)), 1.0)
    vel = VM('ADD', tgt_vel, VM('SCALE', rel, spd_f))

    # --- integrate position + hard stretch limit
    pos = VM('ADD', jpos, VM('SCALE', vel, dt))
    d2 = VM('SUBTRACT', pos, tgt_sub)
    l2 = VM('LENGTH', d2)
    lim_f = MT('MINIMUM',
               MT('DIVIDE', GP("Max Stretch"), MT('MAXIMUM', l2, 1e-9)), 1.0)
    pos = VM('ADD', tgt_sub, VM('SCALE', d2, lim_f))
    # a vertex held at the limit loses its outward velocity (relative to
    # the surface); otherwise it keeps pressing out and sticks there
    out_dir = VM('NORMALIZE', d2)
    v_out = VM('DOT_PRODUCT', VM('SUBTRACT', vel, tgt_vel), out_dir)
    pressing = BAND(CMP_LT(GP("Max Stretch"), l2), CMP_LT(0.0, v_out))
    vel = SWITCHV(pressing, vel,
                  VM('SUBTRACT', vel, VM('SCALE', out_dir, v_out)))

    # The state runs unweighted; the vertex-group weight is applied once
    # per frame after the loop (see below).
    pos_precol = pos   # reference for contact squash measurement

    # --- world-space floor collision with restitution + impact friction
    sp = SEP(pos)
    below = CMP_LT(sp.outputs['Z'], GP("Floor Height"))
    hit = BAND(below, GP("Floor Collision"))
    pz = SWITCHF(hit, sp.outputs['Z'], GP("Floor Height"))
    pos = COMB(sp.outputs['X'], sp.outputs['Y'], pz)

    sv = SEP(vel)
    moving_down = CMP_LT(sv.outputs['Z'], 0.0)
    impact = BAND(hit, moving_down)
    vz_bounce = MT('MULTIPLY', sv.outputs['Z'],
                   MT('MULTIPLY', GP("Bounce"), -1.0))
    vz = SWITCHF(impact, sv.outputs['Z'], vz_bounce)
    floor_drag = MT('POWER', 0.5, MT('MULTIPLY', dt, 24.0))
    vx = SWITCHF(impact, sv.outputs['X'],
                 MT('MULTIPLY', sv.outputs['X'], floor_drag))
    vy = SWITCHF(impact, sv.outputs['Y'],
                 MT('MULTIPLY', sv.outputs['Y'], floor_drag))
    vel = COMB(vx, vy, vz)

    # --- object collision response from the PER-FRAME CACHE: the cached
    # contact acts as a plane constraint (point sj_cp, normal sj_cn).
    # Pure vector math — no BVH queries in the substep loop.
    chit = NATTR("sj_chit", 'BOOLEAN')
    cp = NATTR("sj_cp")
    cn = NATTR("sj_cn")
    cfb = SEP(NATTR("sj_cfb"))

    d_pen = VM('DOT_PRODUCT', VM('SUBTRACT', pos, cp), cn)
    hit_o = BAND(chit, CMP_LT(d_pen, 0.0))
    pos = SWITCHV(hit_o, pos, VM('SUBTRACT', pos, VM('SCALE', cn, d_pen)))

    vn = VM('DOT_PRODUCT', vel, cn)
    resp = BAND(hit_o, CMP_LT(vn, 0.0))
    vel_tan = VM('SUBTRACT', vel, VM('SCALE', cn, vn))
    fric_f = MT('POWER', MT('MAXIMUM',
                MT('SUBTRACT', 1.0, cfb.outputs['X']), 0.0),
                MT('MULTIPLY', dt, 24.0))
    vel_col = VM('ADD',
                 VM('SCALE', vel_tan, fric_f),
                 VM('SCALE', cn,
                    MT('MULTIPLY', vn,
                       MT('MULTIPLY', cfb.outputs['Y'], -1.0))))
    vel = SWITCHV(resp, vel, vel_col)

    # --- collisions may push beyond the jiggle limit, by up to Contact Reach
    reach = MT('ADD', GP("Max Stretch"), GP("Contact Reach"))
    pos = VM('ADD', tgt_sub, CAPV(VM('SUBTRACT', pos, tgt_sub), reach))

    # --- final state after collision resolution
    pos_final = pos
    vel_final = vel

    # --- write state. Staging attributes keep reads/writes cleanly ordered
    #     (everything above reads only the *previous* sj_pos / sj_vel).
    sg = STORE(ZS(rep_in.outputs), "sj_pos_n", pos_final)
    sg = STORE(sg, "sj_vel_n", vel_final)

    # Contact compression for the squash response: how far collision
    # resolution (floor or objects) had to correct this vertex during
    # the substep. Instant attack, smooth exponential decay so the bulge
    # relaxes instead of popping when contact ends.
    sq_new = VM('LENGTH', VM('SUBTRACT', pos_final, pos_precol))
    sq_decay = MT('EXPONENT', MT('MULTIPLY', dt, -10.0))
    sq = MT('MAXIMUM', sq_new,
            MT('MULTIPLY', NATTR("sj_sq", 'FLOAT'), sq_decay))
    sg = STORE(sg, "sj_sq", sq, dtype='FLOAT')
    # Compression must be evaluated before overwriting the state it reads.
    sg = STORE(sg, "sj_pos", NATTR("sj_pos_n"))
    sg = STORE(sg, "sj_vel", NATTR("sj_vel_n"))
    sg = STORE(sg, "sj_tsub", t_sub, dtype='FLOAT')

    links.new(sg, ZS(rep_out.inputs))

    # ---- once per frame, after the substeps: the displayed jiggle.
    # The weight scales the free state's offset exactly once here. Inside
    # the loop it would compound as w^substeps, so soft weight gradients
    # would act pinned and change with the substep count. The weighted
    # position is re-run through the floor and the cached contact plane so
    # collision stays the final authority on what is displayed.
    def COLLIDE_POS(p):
        s = SEP(p)
        low = BAND(CMP_LT(s.outputs['Z'], GP("Floor Height")),
                   GP("Floor Collision"))
        p = COMB(s.outputs['X'], s.outputs['Y'],
                 SWITCHF(low, s.outputs['Z'], GP("Floor Height")))
        d = VM('DOT_PRODUCT', VM('SUBTRACT', p, cp), cn)
        inside_c = BAND(chit, CMP_LT(d, 0.0))
        return SWITCHV(inside_c, p, VM('SUBTRACT', p, VM('SCALE', cn, d)))

    w = CLAMP01(weight)
    shown = MIXV(w, tgt_world, NATTR("sj_pos"))
    shown = SWITCHV(CMP_LT(0.0, w), tgt_world, COLLIDE_POS(shown))
    shown = VM('ADD', tgt_world,
               CAPV(VM('SUBTRACT', shown, tgt_world), reach))

    # Contact bookkeeping for the display path: how far beyond Max Stretch
    # a collider pushed this vertex (the display cap grows by that much),
    # and whether it rests on a contact (display smoothing must not pull
    # it back into the collider).
    excess = MT('MAXIMUM',
                MT('SUBTRACT', VM('LENGTH', VM('SUBTRACT', shown, tgt_world)),
                   GP("Max Stretch")), 0.0)
    on_plane = BAND(chit, CMP_LT(VM('DOT_PRODUCT', VM('SUBTRACT', shown, cp),
                                    cn), 0.001))
    on_floor = BAND(GP("Floor Collision"),
                    CMP_LT(SEP(shown).outputs['Z'],
                           MT('ADD', GP("Floor Height"), 0.001)))
    touching = BAND(CMP_LT(0.0, w), BOR(on_plane, on_floor))

    # Jiggle offset in LOCAL space, captured at simulation time. The
    # display path applies this on top of the live animated pose, so the
    # mesh rigidly follows any transform change (dragging a keyframed
    # object, parents, drivers) while keeping its jiggle deformation,
    # even when the sim state itself hasn't advanced.
    off_w = VM('SUBTRACT', shown, tgt_world)
    off_l = ROT(off_w, INVROT(oi_zone.outputs['Rotation']))
    off_l = VM('DIVIDE', off_l, oi_zone.outputs['Scale'])
    fg = STORE(ZS(rep_out.outputs), "sj_off", off_l)
    fg = STORE(fg, "sj_cx", excess, dtype='FLOAT')
    fg = STORE(fg, "sj_touch", touching, dtype='BOOLEAN')
    fg = STORE(fg, "sj_tgt", tgt_world)
    fg = STORE(fg, "sj_hastgt", True, dtype='BOOLEAN')
    fg = STORE(fg, "sj_sec", scene_sec, dtype='FLOAT')
    fg = STORE(fg, "sj_started",
               BOR(NATTR("sj_started", 'BOOLEAN'), stepping), dtype='BOOLEAN')
    links.new(fg, ZS(sim_out.inputs))

    # =========================================================== POST ZONE
    # Apply the local-space jiggle offset stored in the sim state on top
    # of the live animated pose. No live-transform inversion here: that
    # is exactly what previously pinned the mesh in world space when the
    # sim wasn't advancing (e.g. dragging a keyframed object).
    idx2 = nodes.new('GeometryNodeInputIndex').outputs[0]
    offset = SAMPLE(ZS(sim_out.outputs), NATTR("sj_off"), idx2)

    blur = nodes.new('GeometryNodeBlurAttribute')
    blur.data_type = 'FLOAT_VECTOR'
    links.new(offset, blur.inputs['Value'])
    # Animation Mode caps the fold blur at 1 iteration (display-side
    # per-frame cost, significant at high iteration counts)
    fi_eff = SWITCHF(gi_post.outputs['Animation Mode'],
                     gi_post.outputs['Fold Iterations'],
                     MT('MINIMUM', gi_post.outputs['Fold Iterations'], 1.0))
    links.new(fi_eff, blur.inputs['Iterations'])
    links.new(gi_post.outputs['Fold Smoothing'], blur.inputs['Weight'])

    # Normalized masked smoothing preserves pinned vertices without applying
    # the weight twice to vertices in a uniformly painted region.
    post_weight = CLAMP01(gi_post.outputs['Weight'])
    weight_blur = nodes.new('GeometryNodeBlurAttribute')
    weight_blur.data_type = 'FLOAT'
    links.new(post_weight, weight_blur.inputs['Value'])
    links.new(fi_eff, weight_blur.inputs['Iterations'])
    links.new(gi_post.outputs['Fold Smoothing'], weight_blur.inputs['Weight'])
    smooth_offset = VM('SCALE', blur.outputs['Value'],
                       MT('DIVIDE', post_weight,
                          MT('MAXIMUM', weight_blur.outputs['Value'], 1e-6)))
    # vertices resting on a contact keep their exact collision-resolved
    # offset: averaging with free neighbours would pull them into the collider
    touch_now = SAMPLE(ZS(sim_out.outputs), NATTR("sj_touch", 'BOOLEAN'),
                       idx2, dtype='BOOLEAN')
    smooth_offset = SWITCHV(touch_now, smooth_offset, offset)

    # --- squash response: compressed tissue bulges the surrounding skin.
    # Blur the per-vertex compression across neighbours; where the
    # blurred value exceeds the local one (the ring AROUND a contact,
    # not the clamped contact patch itself) push outward along the
    # surface normal, masked by the layer weight.
    sq_now = SAMPLE(ZS(sim_out.outputs), NATTR("sj_sq", 'FLOAT'), idx2,
                    dtype='FLOAT')
    sq_blur = nodes.new('GeometryNodeBlurAttribute')
    sq_blur.data_type = 'FLOAT'
    links.new(sq_now, sq_blur.inputs['Value'])
    # Animation Mode skips the squash spread blur entirely
    ss_eff = SWITCHF(gi_post.outputs['Animation Mode'],
                     gi_post.outputs['Squash Spread'], 0.0)
    links.new(ss_eff, sq_blur.inputs['Iterations'])
    sq_blur.inputs['Weight'].default_value = 0.85

    ring = MT('MAXIMUM', MT('SUBTRACT', sq_blur.outputs['Value'], sq_now),
              0.0)
    bulge_len = MT('MULTIPLY',
                   MT('MULTIPLY', ring, gi_post.outputs['Squash Amount']),
                   post_weight)
    nrm_post = nodes.new('GeometryNodeInputNormal').outputs[0]
    oi_post = OBJINFO(gi_post)
    bulge_world = VM('SCALE', NORMAL_WORLD(nrm_post, oi_post), bulge_len)
    bulge_vec = VM('DIVIDE', ROT(bulge_world, INVROT(oi_post.outputs['Rotation'])),
                   oi_post.outputs['Scale'])

    offset_scaled = VM('SCALE',
                       VM('ADD', smooth_offset, bulge_vec),
                       gi_post.outputs['Blend'])
    # Smoothing and squash are display effects; they must respect the same
    # world-distance limit as the solver, including on scaled objects. The
    # limit grows by however far a collider pushed the vertex past Max
    # Stretch — capping that away is what made skin clip into colliders.
    offset_world = ROT(VM('MULTIPLY', offset_scaled, oi_post.outputs['Scale']),
                       oi_post.outputs['Rotation'])
    cx_now = SAMPLE(ZS(sim_out.outputs), NATTR("sj_cx", 'FLOAT'), idx2,
                    dtype='FLOAT')
    offset_world = CAPV(offset_world,
                        MT('ADD', gi_post.outputs['Max Stretch'], cx_now))
    offset_scaled = VM('DIVIDE',
                       ROT(offset_world, INVROT(oi_post.outputs['Rotation'])),
                       oi_post.outputs['Scale'])

    # If the simulation cache has no state for the current frame (e.g.
    # scrubbing before playing from the start frame), the zone outputs
    # empty geometry. Without this guard the sampled positions collapse
    # to the origin and the mesh seems to vanish -> fall back to a zero
    # offset (mesh shows its normal animated pose) instead. The same goes
    # for a state whose vertex count doesn't match the live mesh (e.g. a
    # bake read back under a different subdivision level).
    state_ok = CMP_LT(MT('ABSOLUTE',
                         MT('SUBTRACT', POINTS(ZS(sim_out.outputs)),
                            POINTS(gi_post.outputs['Geometry']))), 0.5)
    offset_final = SWITCHV(state_ok, (0.0, 0.0, 0.0), offset_scaled)

    set_pos = nodes.new('GeometryNodeSetPosition')
    links.new(gi_post.outputs['Geometry'], set_pos.inputs['Geometry'])
    links.new(offset_final, set_pos.inputs['Offset'])
    links.new(set_pos.outputs['Geometry'], g_out.inputs['Geometry'])

    # crude auto-layout so the tree is at least inspectable
    for i, n in enumerate(nodes):
        n.location = ((i % 14) * 230, -(i // 14) * 280)

    # Only completed graphs may be reused after a construction failure.
    ng["sj_build"] = BUILD_TAG
    return ng


# ===========================================================================
#  Modifier plumbing
# ===========================================================================
def _input_ident_map(ng):
    return {item.name: item.identifier
            for item in ng.interface.items_tree
            if getattr(item, "item_type", "") == 'SOCKET'
            and getattr(item, "in_out", "") == 'INPUT'}

def _set_value(mod, ng, name, value):
    # cast to the SOCKET's type: an int stored on a float socket (e.g.
    # preset Stiffness 60) is rejected by Blender and the default is used
    item = next((it for it in ng.interface.items_tree
                 if getattr(it, "item_type", "") == 'SOCKET'
                 and getattr(it, "in_out", "") == 'INPUT'
                 and it.name == name), None)
    if item is None:
        return
    if item.socket_type == 'NodeSocketBool':
        mod[item.identifier] = bool(value)
    elif item.socket_type == 'NodeSocketInt':
        mod[item.identifier] = int(value)
    else:
        mod[item.identifier] = float(value)

def _set_vertex_group(mod, ng, group_name):
    ident = _input_ident_map(ng).get("Weight")
    if ident is None:
        return
    key = f"{ident}_use_attribute"
    # int property up to Blender 4.x, bool from 5.0 (which rejects ints)
    mod[key] = True if isinstance(mod.get(key), bool) else 1
    mod[f"{ident}_attribute_name"] = group_name

def _set_object(mod, ng, name, ob):
    ident = _input_ident_map(ng).get(name)
    if ident is not None:
        mod[ident] = ob


# ---------------------------------------------------------------------------
#  Collider sync: any mesh with Physics > Collision enabled is a collider
# ---------------------------------------------------------------------------
def _stamp_collider(ob):
    """Set per-object evaluated attributes without modifying shared mesh data.

    A small geometry modifier follows the collider's deformation stack.
    Linked duplicates may therefore have different contact settings while
    their source mesh remains shared and editable as usual.
    """
    cs = ob.collision
    vec = (max(float(cs.thickness_outer), 0.001),
           min(max(float(cs.cloth_friction) / 80.0, 0.0), 1.0),
           min(max(1.0 - float(cs.damping), 0.0), 1.0))
    mod = next((m for m in ob.modifiers if m.type == 'NODES'
                and m.node_group and m.node_group.get('sj_collider_settings')), None)
    if mod is None:
        ng = next((g for g in bpy.data.node_groups
                   if g.get('sj_collider_settings') == 1), None)
        if ng is None:
            ng = bpy.data.node_groups.new('SJColliderSettings', 'GeometryNodeTree')
            ng.is_modifier = True
            ng.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
            ng.interface.new_socket(name='Settings', in_out='INPUT', socket_type='NodeSocketVector')
            ng.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
            gi = ng.nodes.new('NodeGroupInput')
            go = ng.nodes.new('NodeGroupOutput')
            stamp = ng.nodes.new('GeometryNodeStoreNamedAttribute')
            stamp.data_type = 'FLOAT_VECTOR'
            stamp.domain = 'POINT'
            stamp.inputs['Name'].default_value = 'sj_set'
            ng.links.new(gi.outputs['Geometry'], stamp.inputs['Geometry'])
            ng.links.new(gi.outputs['Settings'], stamp.inputs['Value'])
            ng.links.new(stamp.outputs['Geometry'], go.inputs['Geometry'])
            ng['sj_collider_settings'] = 1
        mod = ob.modifiers.new('SJ Collider Settings', 'NODES')
        mod.node_group = ng
        mod.show_expanded = False
    ident = _input_ident_map(mod.node_group)['Settings']
    old = mod.get(ident)
    if old is None or any(abs(a - b) > 1e-6 for a, b in zip(old, vec)):
        mod[ident] = vec
        ob.update_tag()
    if not mod.show_viewport:
        mod.show_viewport = True
    if not mod.show_render:
        mod.show_render = True

def _is_collider(ob):
    """Meshes with Physics > Collision enabled, EXCEPT jiggled objects and
    cages: a layer reading its own object would be refused by Collection
    Info (killing all collision for that layer), and two jiggled objects
    reading each other form a dependency cycle. The same cycle forms for a
    mesh deformed by an armature with jiggle bones (helper -> collider
    mesh -> armature -> bone constraint -> helper)."""
    return (ob.type == 'MESH' and ob.collision is not None
            and ob.collision.use and not _jiggle_modifiers(ob)
            and not ob.get("sj_cage_src")
            and not _deformed_by_jiggle_rig(ob))


def _deformed_by_jiggle_rig(ob):
    for m in ob.modifiers:
        if (m.type == 'ARMATURE' and m.object is not None
                and m.object.get("sj_jiggle_bones")):
            return True
    return (ob.parent is not None and ob.parent_type == 'ARMATURE'
            and bool(ob.parent.get("sj_jiggle_bones")))


def _sync_colliders(scene, force=False):
    """Mirror every collider mesh (see _is_collider) into the hidden
    managed collection the node group reads, and stamp their settings.
    Only changed settings write modifier data. Returns (collection, count).
    The collection is owned by the scene, never shared across scenes."""
    col = scene.get('sj_collider_collection')
    # A scene copy may share the property; make its helper independent.
    shared = any(s is not scene and s.get('sj_collider_collection') is col
                 for s in bpy.data.scenes) if col is not None else False
    if not isinstance(col, bpy.types.Collection) or shared:
        col = bpy.data.collections.new(f'{SJ_COLL}_{scene.name}')
        scene['sj_collider_collection'] = col
    if scene and col.name not in {c.name
                                  for c in scene.collection.children}:
        try:
            scene.collection.children.link(col)
        except RuntimeError:
            pass

    desired = {ob for ob in scene.objects if _is_collider(ob)}
    current = set(col.objects)
    for ob in desired - current:
        col.objects.link(ob)
    for ob in current - desired:
        col.objects.unlink(ob)
    for ob in desired:
        try:
            _stamp_collider(ob)
        except (RuntimeError, TypeError, AttributeError) as exc:
            _LOG.warning('Cannot configure collider %s: %s', ob.name, exc)
    for ob in scene.objects:
        for mod in _jiggle_modifiers(ob):
            ident = _input_ident_map(mod.node_group).get('Collider Collection')
            if ident and mod.get(ident) is not col:
                mod[ident] = col
                ob.update_tag()
    return col, len(desired)


@persistent
def _sj_frame_sync(scene, depsgraph=None):
    """Keep colliders and their settings in sync during playback."""
    try:
        # Scene switching also invokes this handler. Creating collections in
        # an empty scene during that rebuild crashes Blender 4.1's depsgraph.
        # Scenes with no layers have no collision work to perform.
        if not any(_jiggle_modifiers(ob) for ob in scene.objects):
            return
        col = scene.get('sj_collider_collection')
        desired = {ob for ob in scene.objects if _is_collider(ob)}
        structural_change = (
            not isinstance(col, bpy.types.Collection)
            or set(col.objects) != desired
            or any(s is not scene and s.get('sj_collider_collection') is col
                   for s in bpy.data.scenes)
            or any(not any(m.type == 'NODES' and m.node_group
                           and m.node_group.get('sj_collider_settings')
                           for m in ob.modifiers) for ob in desired))
        if structural_change:
            # Add/remove dependency relations outside frame/depsgraph rebuilds.
            if not bpy.app.timers.is_registered(_repair_timer):
                bpy.app.timers.register(_repair_timer, first_interval=0.0)
            return
        _sync_colliders(scene)
    except Exception:
        _LOG.exception('Collider synchronization failed')

def _editable_collection(obj, scene):
    """First collection of obj we may link new objects into: not linked
    from a library and not a library override; else the scene root."""
    for c in obj.users_collection:
        if c.library is None and c.override_library is None:
            return c
    return scene.collection


def _ref_owner(ref):
    for c in ref.constraints:
        if c.type == 'COPY_TRANSFORMS':
            return c.target
    return None


def _ensure_ref_empty(obj):
    """Hidden empty that mirrors the object's world transform via a
    Copy Transforms constraint. Reading the transform from it (instead
    of Self Object, which creates no depsgraph relation) makes the sim
    re-evaluate in real time when the object is moved."""
    ref_name = obj.get("sj_ref", "")
    ref = bpy.data.objects.get(ref_name) if ref_name else None
    if ref is not None and _ref_owner(ref) not in (None, obj):
        ref = None   # copied from another object (Shift+D): make our own
    if ref is None:
        ref = bpy.data.objects.new(f"SJRef_{obj.name}", None)
        _editable_collection(obj, bpy.context.scene).objects.link(ref)
        ref.empty_display_size = 0.1
        ref.hide_render = True
        ref.hide_select = True
        ref.hide_viewport = True
        obj["sj_ref"] = ref.name
    if not any(c.type == 'COPY_TRANSFORMS' and c.target is obj
               for c in ref.constraints):
        con = ref.constraints.new('COPY_TRANSFORMS')
        con.target = obj
    return ref

def _cleanup_ref_empty(obj):
    ref_name = obj.get("sj_ref", "")
    ref = bpy.data.objects.get(ref_name) if ref_name else None
    # only delete our OWN empty — a duplicate still pointing at the
    # original's must never take the original's down with it
    if ref is not None and _ref_owner(ref) in (None, obj):
        bpy.data.objects.remove(ref, do_unlink=True)
    if "sj_ref" in obj:
        del obj["sj_ref"]


def _repair_layers(scene):
    """Give every jiggled object its own reference empty and point its
    layers at it. Shift+D copies the modifier AND the sj_ref property,
    so a duplicate would otherwise simulate in the original's transform."""
    for ob in scene.objects:
        if ob.type != 'MESH' or ob.get("sj_cage_src") or ob.library:
            continue
        mods = _jiggle_modifiers(ob)
        if not mods:
            continue
        ref = _ensure_ref_empty(ob)
        for mod in mods:
            ident = _input_ident_map(mod.node_group).get("Reference Object")
            if ident is not None and mod.get(ident) is not ref:
                mod[ident] = ref
                ob.update_tag()


_LAYER_SIG = None

def _repair_timer():
    try:
        scene = bpy.context.scene
        _repair_layers(scene)
        if any(_jiggle_modifiers(ob) for ob in scene.objects):
            _sync_colliders(scene)
    except Exception:
        _LOG.exception('Jiggle reference repair failed')
    return None   # one-shot


@persistent
def _sj_depsgraph_watch(scene, depsgraph=None):
    """Cheap check after every depsgraph update: when the set of jiggled
    objects changes (duplicate, append, rename), schedule a repair outside
    of depsgraph evaluation."""
    global _LAYER_SIG
    try:
        sig = (scene.as_pointer(),
               tuple(sorted((ob.name, ob.as_pointer(),
                             ob.get('sj_ref', '') in bpy.data.objects)
                            for ob in scene.objects
                            if ob.type == 'MESH' and _jiggle_modifiers(ob))),
               tuple(sorted(ob.as_pointer() for ob in scene.objects
                            if _is_collider(ob))))
    except Exception:
        return
    if sig != _LAYER_SIG:
        _LAYER_SIG = sig
        if not bpy.app.timers.is_registered(_repair_timer):
            bpy.app.timers.register(_repair_timer, first_interval=0.0)

def _apply_preset(mod, ng, preset_key):
    values = dict(PRESETS[preset_key][1])
    if mod.get('sj_bone'):
        # A bone tip has no surface: make the spring isotropic at the
        # preset's normal-mode stiffness, so the bone swings at exactly the
        # preset's frequency in every direction. Folds need a surface.
        values['Stiffness'] *= max(1.0 - values['Normal Softness'], 0.02)
        values['Normal Softness'] = 0.0
        values['Fold Smoothing'] = 0.0
    for name, value in values.items():
        _set_value(mod, ng, name, value)
    mod['sj_body_preset'] = preset_key
    mod['sj_contact_style'] = 'BODY'


def _apply_contact_style(mod, preset_key, style):
    """Apply per-layer collision response while preserving body physics."""
    base = _CONTACT_PRESET_BASE.get(preset_key, _CONTACT_PRESET_BASE['SOFT_SKIN'])
    gap, friction, squash, bounce, spread = base
    if style == 'HAND':
        gap, friction, squash, bounce, spread = gap * .8, min(friction * 1.2, 1.0), squash * 1.25, bounce * .4, min(spread + 1, 16)
    elif style == 'GRIP':
        gap, friction, squash, bounce, spread = gap * .65, min(friction * 1.65, 1.0), squash * 1.6, 0.0, min(spread + 1, 16)
    elif style == 'STYLIZED':
        gap, friction, squash, bounce, spread = max(gap, .003), min(friction * .8, 1.0), max(squash * 2.2, .8), .35, min(spread + 2, 16)
    for name, value in (('Collision Distance', gap),
                        ('Collision Friction', friction),
                        ('Squash Amount', squash), ('Bounce', bounce),
                        ('Squash Spread', spread)):
        _set_value(mod, mod.node_group, name, value)
    mod['sj_contact_style'] = style

def _jiggle_modifiers(obj):
    return [m for m in obj.modifiers
            if m.type == 'NODES' and m.node_group
            and m.node_group.name.startswith(CORE_NAME)]

def _refresh(obj):
    obj.update_tag()
    for wm_area in bpy.context.screen.areas if bpy.context.screen else []:
        wm_area.tag_redraw()


def _create_layer(context, obj, group, preset, bone=False):
    """Add a jiggle layer to obj driven by a vertex group. Returns
    (modifier, collider count, name of the modifier it was placed before)."""
    ng = _build_core_group()
    mod = obj.modifiers.new(name=f"SkinJiggle_{group}", type='NODES')
    mod.node_group = ng
    if bone:
        mod['sj_bone'] = True     # before the preset: it converts for bones
    _set_vertex_group(mod, ng, group)
    _apply_preset(mod, ng, preset)
    _set_object(mod, ng, "Reference Object", _ensure_ref_empty(obj))
    col, n_col = _sync_colliders(context.scene, force=True)
    _set_object(mod, ng, "Collider Collection", col)
    _set_value(mod, ng, "Animation Mode", bool(context.scene.sj_anim_mode))
    mod.show_expanded = False
    placed = _place_before_subdivision(context, obj, mod)
    obj.sj_active_layer = list(obj.modifiers).index(mod)
    _refresh(obj)
    return mod, n_col, placed


# ---------------------------------------------------------------------------
#  Jiggle bones: the bone aims at a helper point driven by a normal layer
# ---------------------------------------------------------------------------
SJ_BONE_CON = "SJ Jiggle"
SJ_TIP_GROUP = "SJ_Tip"


def _bone_constraint(pb):
    return next((c for c in pb.constraints if c.name == SJ_BONE_CON
                 and c.type in {'DAMPED_TRACK', 'STRETCH_TO'}), None)


def _bone_helper(pb):
    con = _bone_constraint(pb)
    helper = con.target if con is not None else None
    return helper if helper is not None and helper.get("sj_bone_helper") else None


def _jiggle_bones(arm):
    return [pb for pb in arm.pose.bones if _bone_helper(pb) is not None]


def _layer_objects(obj):
    """Objects whose jiggle layers belong to obj: itself, or for an
    armature the helper points of its jiggle bones."""
    if obj is None:
        return []
    if obj.type == 'ARMATURE':
        return [_bone_helper(pb) for pb in _jiggle_bones(obj)]
    return [obj]


def _create_bone_jiggle(context, arm, pb, preset, stretch):
    """Helper point at the bone's tail, parented to the bone's PARENT (so it
    follows the animation without depending on the jiggled bone), driven by
    an ordinary jiggle layer. The bone then aims at the simulated point."""
    tail = arm.matrix_world @ pb.tail
    rot = (arm.matrix_world @ pb.matrix).to_quaternion()
    size = max(pb.bone.length * max(arm.matrix_world.to_scale()) * 0.03, 0.002)
    me = bpy.data.meshes.new(f"SJBone_{arm.name}_{pb.name}")
    # small quad across the bone; its 4 points move together
    me.from_pydata([(-size, 0, -size), (size, 0, -size), (size, 0, size),
                    (-size, 0, size)], [], [(0, 1, 2, 3)])
    helper = bpy.data.objects.new(me.name, me)
    _editable_collection(arm, context.scene).objects.link(helper)
    world = Matrix.Translation(tail) @ rot.to_matrix().to_4x4()
    helper.parent = arm
    if pb.parent is not None:
        helper.parent_type = 'BONE'
        helper.parent_bone = pb.parent.name
    context.view_layer.update()
    helper.matrix_world = world
    vg = helper.vertex_groups.new(name=SJ_TIP_GROUP)
    vg.add(range(4), 1.0, 'REPLACE')
    helper["sj_bone_helper"] = True
    helper["sj_bone_arm"] = arm
    helper["sj_bone_name"] = pb.name
    helper.display_type = 'WIRE'
    helper.hide_render = True
    helper.hide_select = True
    _create_layer(context, helper, SJ_TIP_GROUP, preset, bone=True)
    helper.hide_viewport = True
    _set_bone_constraint(pb, helper, stretch)
    arm["sj_jiggle_bones"] = True
    arm.update_tag()
    return helper


def _set_bone_constraint(pb, helper, stretch):
    old = _bone_constraint(pb)
    if old is not None:
        pb.constraints.remove(old)
    con = pb.constraints.new('STRETCH_TO' if stretch else 'DAMPED_TRACK')
    con.name = SJ_BONE_CON
    con.target = helper
    con.subtarget = SJ_TIP_GROUP
    if stretch:
        con.rest_length = 0.0      # Blender measures it on first evaluation
        con.volume = 'VOLUME_XZX'
    else:
        con.track_axis = 'TRACK_Y'
    return con


def _remove_bone_jiggle(arm, pb):
    helper = _bone_helper(pb)
    con = _bone_constraint(pb)
    if con is not None:
        pb.constraints.remove(con)
    if helper is not None:
        _cleanup_ref_empty(helper)
        data = helper.data
        bpy.data.objects.remove(helper, do_unlink=True)
        if data.users == 0:
            bpy.data.meshes.remove(data)
    if not _jiggle_bones(arm) and "sj_jiggle_bones" in arm:
        del arm["sj_jiggle_bones"]
    arm.update_tag()


# ===========================================================================
#  Operators
# ===========================================================================
def _vg_search(self, context, edit_text):
    """Autocomplete for the vertex group search bar."""
    obj = context.object
    if not obj or obj.type != 'MESH':
        return []
    text = edit_text.lower()
    return [vg.name for vg in obj.vertex_groups
            if text in vg.name.lower()]


class SJ_OT_add_layer(Operator):
    """Add a jiggle physics layer driven by a vertex group"""
    bl_idname = "skin_jiggle.add_layer"
    bl_label = "Add Jiggle Layer"
    bl_options = {'REGISTER', 'UNDO'}

    vertex_group: StringProperty(
        name="Vertex Group",
        description="Start typing to search this object's vertex groups",
        search=_vg_search)
    preset: EnumProperty(name="Preset", items=_PRESET_ENUM,
                         default='SOFT_SKIN')

    @classmethod
    def poll(cls, context):
        o = context.object
        if o and o.library is not None:
            cls.poll_message_set("Linked object: make it a library "
                                 "override first")
            return False
        return o and o.type == 'MESH'

    def invoke(self, context, event):
        vgs = context.object.vertex_groups
        if not vgs:
            self.report({'ERROR'},
                        "Object has no vertex groups. Paint one first "
                        "(Weight Paint mode) — it defines where the "
                        "tissue jiggles.")
            return {'CANCELLED'}
        if not self.vertex_group and vgs.active:
            self.vertex_group = vgs.active.name
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        obj = context.object
        if self.vertex_group not in {vg.name for vg in obj.vertex_groups}:
            self.report({'ERROR'},
                        f"'{self.vertex_group}' is not a vertex group on "
                        f"this object — pick one from the search field")
            return {'CANCELLED'}
        try:
            mod, n_col, placed = _create_layer(context, obj,
                                               self.vertex_group, self.preset)
        except Exception as exc:
            self.report({'ERROR'},
                        f"Failed to build node group (Blender 4.1+ "
                        f"required): {exc}")
            return {'CANCELLED'}
        self.report({'INFO'},
                    f"Jiggle layer added for '{self.vertex_group}' "
                    f"({n_col} collider(s) detected"
                    + (f"; placed before '{placed}'" if placed else "")
                    + "). Play the timeline to simulate.")
        return {'FINISHED'}


def _place_before_subdivision(context, obj, mod):
    """Move a new layer above the first Subdivision/Multires modifier.
    After it the sim would run on the subdivided mesh (slow), and
    viewport vs render levels would give the state a different vertex
    count at render time. Returns the modifier name it was placed
    before, or None."""
    names = [m.name for m in obj.modifiers]
    target = next((i for i, m in enumerate(obj.modifiers)
                   if m.type in {'SUBSURF', 'MULTIRES'}
                   and i < names.index(mod.name)), None)
    if target is None:
        return None
    before = names[target]
    try:
        with context.temp_override(object=obj, active_object=obj):
            bpy.ops.object.modifier_move_to_index(modifier=mod.name,
                                                  index=target)
    except RuntimeError:
        return None
    return before


class SJ_OT_remove_layer(Operator):
    """Remove this jiggle layer"""
    bl_idname = "skin_jiggle.remove_layer"
    bl_label = "Remove Jiggle Layer"
    bl_options = {'REGISTER', 'UNDO'}

    modifier_name: StringProperty()

    def execute(self, context):
        obj = context.object
        mod = obj.modifiers.get(self.modifier_name)
        if mod:
            _delete_layer_cage(mod)
            obj.modifiers.remove(mod)
            if not _jiggle_modifiers(obj):
                _cleanup_ref_empty(obj)
            _refresh(obj)
        return {'FINISHED'}


class SJ_OT_set_group(Operator):
    """Pick the vertex group that drives this layer (use after renaming
    or deleting a group — a missing group silently disables the layer)"""
    bl_idname = "skin_jiggle.set_group"
    bl_label = "Set Vertex Group"
    bl_options = {'REGISTER', 'UNDO'}

    modifier_name: StringProperty()
    vertex_group: StringProperty(
        name="Vertex Group",
        description="Start typing to search this object's vertex groups",
        search=_vg_search)

    def invoke(self, context, event):
        mod = context.object.modifiers.get(self.modifier_name)
        group = _layer_group(mod) if mod and mod.node_group else ""
        if group in context.object.vertex_groups:
            self.vertex_group = group     # open on the current one
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        obj = context.object
        mod = obj.modifiers.get(self.modifier_name)
        if mod is None or not mod.node_group:
            return {'CANCELLED'}
        if self.vertex_group not in obj.vertex_groups:
            self.report({'ERROR'},
                        f"'{self.vertex_group}' is not a vertex group on "
                        f"this object")
            return {'CANCELLED'}
        _set_vertex_group(mod, mod.node_group, self.vertex_group)
        _refresh(obj)
        return {'FINISHED'}


class SJ_OT_apply_preset(Operator):
    """Apply a physical preset to this jiggle layer"""
    bl_idname = "skin_jiggle.apply_preset"
    bl_label = "Apply Preset"
    bl_options = {'REGISTER', 'UNDO'}

    modifier_name: StringProperty()
    object_name: StringProperty(options={'HIDDEN'})
    preset: EnumProperty(name="Preset", items=_PRESET_ENUM,
                         default='SOFT_SKIN')

    def invoke(self, context, event):
        _obj, mod = _target_layer(context, self.object_name, self.modifier_name)
        if mod is not None and mod.get('sj_body_preset') in PRESETS:
            self.preset = mod['sj_body_preset']   # open on the current one
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        obj, mod = _target_layer(context, self.object_name, self.modifier_name)
        if mod and mod.node_group:
            _apply_preset(mod, mod.node_group, self.preset)
            _refresh(obj)
        return {'FINISHED'}


class SJ_OT_contact_style(Operator):
    """Set this layer's response when it presses against colliders."""
    bl_idname = "skin_jiggle.contact_style"
    bl_label = "Contact Style"
    bl_options = {'REGISTER', 'UNDO'}

    modifier_name: StringProperty()
    object_name: StringProperty(options={'HIDDEN'})
    style: EnumProperty(name='Style', items=_CONTACT_STYLES, default='BODY')

    def invoke(self, context, event):
        _obj, mod = _target_layer(context, self.object_name, self.modifier_name)
        if mod is not None:
            self.modifier_name = mod.name
            self.style = mod.get('sj_contact_style', 'BODY')
        return context.window_manager.invoke_props_dialog(self, width=340)

    def execute(self, context):
        obj, mod = _target_layer(context, self.object_name, self.modifier_name)
        if mod is None or not mod.node_group:
            self.report({'ERROR'}, 'Jiggle layer not found')
            return {'CANCELLED'}
        key = mod.get('sj_body_preset', 'SOFT_SKIN')
        _apply_contact_style(mod, key, self.style)
        _refresh(mod.id_data)
        self.report({'INFO'}, f'{self.style.title()} contact applied; adjust the layer values at any time')
        return {'FINISHED'}


class SJ_OT_add_collider(Operator):
    """Add an editable palm-sized collision proxy at the 3D cursor."""
    bl_idname = 'skin_jiggle.add_collider'
    bl_label = 'Add Collision Object'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.mode == 'OBJECT'

    def execute(self, context):
        old_active = context.view_layer.objects.active
        old_selected = [ob for ob in context.selected_objects]
        try:
            bpy.ops.mesh.primitive_uv_sphere_add(
                segments=24, ring_count=12, radius=0.06,
                location=context.scene.cursor.location)
            ob = context.view_layer.objects.active
            ob.name = 'SJ Hand Collider'
            ob.scale = (1.0, .72, .42)
            ob.color = (.2, .55, 1.0, 1.0)
            ob['sj_managed_collider'] = True
            for polygon in ob.data.polygons:
                polygon.use_smooth = True
            collision = ob.modifiers.new('Collision', 'COLLISION')
            ob.collision.thickness_outer = .004
            ob.collision.cloth_friction = 56.0
            ob.collision.damping = .95
            ob.show_in_front = True
            for selected in list(context.selected_objects):
                selected.select_set(False)
            for selected in old_selected:
                selected.select_set(True)
            context.view_layer.objects.active = old_active
            _sync_colliders(context.scene, force=True)
            if old_active is not None:
                _refresh(old_active)
            self.report({'INFO'}, 'Hand collider added at the 3D cursor. Move, rotate, scale or reshape it around your character.')
        except Exception as exc:
            self.report({'ERROR'}, f'Could not add collider: {exc}')
            _LOG.exception('Could not create hand collider')
            return {'CANCELLED'}
        return {'FINISHED'}


# ---------------------------------------------------------------------------
#  Cage preview v2: per-layer, region-only, statically decimated
# ---------------------------------------------------------------------------
def _cage_source(obj):
    """If obj IS a cage, return (source object, source modifier name)."""
    name = obj.get("sj_cage_src", "")
    src = obj.get('sj_cage_owner') or (bpy.data.objects.get(name) if name else None)
    if src is not None:
        mod = next((m for m in _jiggle_modifiers(src) if _layer_cage(m) is obj), None)
        return src, mod.name if mod else obj.get("sj_cage_mod", "")
    return None, obj.get("sj_cage_mod", "")


def _layer_cage(mod):
    name = mod.get("sj_cage", "")
    cage = bpy.data.objects.get(name) if name else None
    if cage is None:
        return None
    owner = cage.get('sj_cage_owner')
    if owner is not None:
        return cage if owner is mod.id_data else None
    # Shift+D copies the original modifier's cage reference. Never use or
    # delete that original cage on behalf of the new object.
    return cage if cage.get('sj_cage_src') == mod.id_data.name else None


def _delete_layer_cage(mod):
    cage = _layer_cage(mod)
    if cage is not None:
        data = cage.data
        bpy.data.objects.remove(cage, do_unlink=True)
        if data.users == 0:
            bpy.data.meshes.remove(data)
    if "sj_cage" in mod.keys():
        del mod["sj_cage"]


def _sync_layer_params(src_obj, dst_obj):
    """Copy jiggle layer parameters between objects, matched by
    modifier name. Returns number of synced layers."""
    n = 0
    for m in _jiggle_modifiers(src_obj):
        dm = dst_obj.modifiers.get(m.name)
        if dm is None or dm.type != 'NODES':
            continue
        for k in m.keys():
            if k == "sj_cage":
                continue
            try:
                dm[k] = m[k]
            except (TypeError, KeyError):
                pass
        n += 1
    dst_obj.update_tag()
    return n


def _extract_group_region(me, group_index, threshold=0.001):
    """Delete every vertex not painted in the given group (in place)."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    dl = bm.verts.layers.deform.active
    if dl is None:
        bm.free()
        return 0
    doomed = [v for v in bm.verts
              if v[dl].get(group_index, 0.0) <= threshold]
    bmesh.ops.delete(bm, geom=doomed, context='VERTS')
    remaining = len(bm.verts)
    bm.to_mesh(me)
    bm.free()
    return remaining


def _create_layer_cage(context, obj, mod, ratio):
    """Build a light proxy for ONE layer: only the painted region,
    decimated ONCE and baked into static mesh data (no per-frame
    decimation cost), deformed live by the copied armature and driven
    by a copy of that single jiggle layer."""
    ng = mod.node_group
    ident = _input_ident_map(ng).get("Weight")
    vg_name = mod.get(f"{ident}_attribute_name", "") if ident else ""
    vg = obj.vertex_groups.get(vg_name)
    if vg is None:
        return None, "Layer has no valid vertex group"

    cage = obj.copy()
    cage.data = obj.data.copy()
    cage.name = f"{obj.name}_SJCage_{vg_name}"[:60]
    _editable_collection(obj, context.scene).objects.link(cage)
    cage.hide_render = True
    con = cage.constraints.new('COPY_TRANSFORMS')
    con.target = obj

    # keep ONLY this layer's modifier among the jiggle layers
    for m in list(cage.modifiers):
        if (m.type == 'NODES' and m.node_group
                and m.node_group.name.startswith(CORE_NAME)
                and m.name != mod.name):
            cage.modifiers.remove(m)

    # cut the mesh down to the painted region (static, once)
    remaining = _extract_group_region(cage.data, vg.index)
    if remaining < 3:
        data = cage.data
        bpy.data.objects.remove(cage, do_unlink=True)
        bpy.data.meshes.remove(data)
        return None, f"Vertex group '{vg_name}' has no painted region"

    # decimate ONCE on the rest mesh and APPLY, so playback never pays
    # for decimation. Vertex groups survive collapse -> armature and
    # the jiggle weight keep working on the reduced mesh.
    dec = cage.modifiers.new("SJ_Cage_Decimate", 'DECIMATE')
    dec.decimate_type = 'COLLAPSE'
    dec.ratio = ratio
    # Object.modifiers has no portable .move() method. Applying a decimator
    # after the armature would bake the pose and then deform it a second time.
    try:
        with context.temp_override(object=cage, active_object=cage,
                                   selected_objects=[cage]):
            bpy.ops.object.modifier_move_to_index(modifier=dec.name, index=0)
    except RuntimeError as exc:
        data = cage.data
        bpy.data.objects.remove(cage, do_unlink=True)
        if data.users == 0:
            bpy.data.meshes.remove(data)
        return None, f'Cannot prepare cage; try Object Mode: {exc}'
    try:
        with context.temp_override(object=cage, active_object=cage,
                                   selected_objects=[cage]):
            bpy.ops.object.modifier_apply(modifier=dec.name)
    except RuntimeError:
        # applying failed (e.g. shape keys on the copy): fall back to
        # keeping the modifier but FIRST in the stack on the tiny
        # region mesh — still far cheaper than the old design.
        pass

    mod["sj_cage"] = cage.name
    cage["sj_cage_src"] = obj.name
    cage['sj_cage_owner'] = obj
    cage["sj_cage_mod"] = mod.name
    return cage, None


def _resolve_layer(context):
    """Return (source object, modifier) for the operator context,
    following the redirect when a cage itself is selected."""
    obj = context.object
    src, mod_name = _cage_source(obj)
    if src is not None:
        return src, src.modifiers.get(mod_name)
    return obj, None


class SJ_OT_cage_toggle(Operator):
    """Toggle a region-only preview cage for this layer: simulate the
    painted area on a light static proxy while the layer is disabled
    on the heavy mesh. Turning it off transfers the cage's settings
    back to the layer"""
    bl_idname = "skin_jiggle.cage_toggle"
    bl_label = "Toggle Layer Cage"
    bl_options = {'REGISTER', 'UNDO'}

    modifier_name: StringProperty()

    def execute(self, context):
        obj, mod = _resolve_layer(context)
        if mod is None:
            mod = obj.modifiers.get(self.modifier_name)
        if mod is None:
            self.report({'ERROR'}, "Layer not found")
            return {'CANCELLED'}

        cage = _layer_cage(mod)
        if cage is None:
            cage, err = _create_layer_cage(
                context, obj, mod, context.scene.sj_cage_ratio)
            if cage is None:
                self.report({'ERROR'}, err)
                return {'CANCELLED'}
            activate = True
        else:
            activate = cage.hide_viewport

        if activate:
            _sync_layer_params(obj, cage)       # real -> cage
            cage.hide_viewport = False
            mod.show_viewport = False
            self.report({'INFO'},
                        f"Cage ON for '{mod.name}' — layer disabled on "
                        f"the heavy mesh")
        else:
            _sync_layer_params(cage, obj)       # cage -> real
            cage.hide_viewport = True
            mod.show_viewport = True
            self.report({'INFO'},
                        f"Cage OFF — settings transferred back to "
                        f"'{mod.name}'")
        return {'FINISHED'}


class SJ_OT_cage_delete(Operator):
    """Delete this layer's preview cage"""
    bl_idname = "skin_jiggle.cage_delete"
    bl_label = "Delete Layer Cage"
    bl_options = {'REGISTER', 'UNDO'}

    modifier_name: StringProperty()

    def execute(self, context):
        obj, mod = _resolve_layer(context)
        if mod is None:
            mod = obj.modifiers.get(self.modifier_name)
        if mod is None:
            return {'CANCELLED'}
        _delete_layer_cage(mod)
        mod.show_viewport = True
        return {'FINISHED'}


class SJ_OT_sync_colliders(Operator):
    """Rescan the scene for objects with Collision physics enabled and
    update their settings (also runs automatically on frame changes)"""
    bl_idname = "skin_jiggle.sync_colliders"
    bl_label = "Refresh Colliders"

    def execute(self, context):
        col, n = _sync_colliders(context.scene, force=True)
        # repair: make sure every jiggle layer in the scene points at
        # the managed collection
        for ob in context.scene.objects:
            if ob.type != 'MESH':
                continue
            for mod in _jiggle_modifiers(ob):
                _set_object(mod, mod.node_group, "Collider Collection",
                            col)
        _refresh(context.object) if context.object else None
        self.report({'INFO'}, f"{n} collider(s) with Collision physics")
        return {'FINISHED'}


def _old_layers(obj):
    """Layers still driven by a node group from an older build."""
    return [m for m in _jiggle_modifiers(obj)
            if m.node_group.get("sj_build") != BUILD_TAG]


class SJ_OT_upgrade_layers(Operator):
    """Move this object's layers from an older engine version onto the
    current one, keeping their settings. Restarts the simulation; any
    bake of these layers must be redone"""
    bl_idname = "skin_jiggle.upgrade_layers"
    bl_label = "Upgrade Layers"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(_old_layers(o) for o in _layer_objects(context.object))

    def execute(self, context):
        obj = context.object
        try:
            ng = _build_core_group()
        except Exception as exc:
            self.report({'ERROR'}, f"Failed to build node group: {exc}")
            return {'CANCELLED'}
        mods = [m for o in _layer_objects(obj) for m in _old_layers(o)]
        for mod in list(mods):
            cage = _layer_cage(mod)
            if cage is not None:
                mods.extend(_old_layers(cage))
        for mod in mods:
            old_map = _input_ident_map(mod.node_group)
            vals = {name: mod.get(ident) for name, ident in old_map.items()}
            w = old_map.get("Weight")
            vg_name = mod.get(f"{w}_attribute_name", "") if w else ""
            mod.node_group = ng
            for name, v in vals.items():
                if name in {"Geometry", "Weight"} or v is None:
                    continue
                if isinstance(v, bpy.types.ID):
                    _set_object(mod, ng, name, v)
                else:
                    try:
                        _set_value(mod, ng, name, v)
                    except (TypeError, ValueError):
                        pass
            if vg_name:
                _set_vertex_group(mod, ng, vg_name)
        _repair_layers(context.scene)
        context.scene.frame_set(context.scene.frame_start)
        _refresh(obj)
        self.report({'INFO'}, f"{len(mods)} layer(s) upgraded to engine "
                              f"{BUILD_TAG} — re-bake if they were baked")
        return {'FINISHED'}


class SJ_OT_reset_defaults(Operator):
    """Reset every parameter of all jiggle layers on this object to
    factory defaults (vertex group, colliders and internal plumbing
    are kept)"""
    bl_idname = "skin_jiggle.reset_defaults"
    bl_label = "Reset All to Defaults"
    bl_options = {'REGISTER', 'UNDO'}

    # Animation Mode is scene-wide state, not a per-layer parameter
    _SKIP = {"Geometry", "Weight", "Reference Object",
             "Collider Collection", "Animation Mode"}

    @classmethod
    def poll(cls, context):
        return any(_jiggle_modifiers(o) for o in _layer_objects(context.object))

    def execute(self, context):
        obj = context.object
        count = 0
        for mod in [m for o in _layer_objects(obj) for m in _jiggle_modifiers(o)]:
            ng = mod.node_group
            for item in ng.interface.items_tree:
                if (getattr(item, "item_type", "") != 'SOCKET'
                        or getattr(item, "in_out", "") != 'INPUT'
                        or item.name in self._SKIP):
                    continue
                default = getattr(item, "default_value", None)
                if default is None:
                    continue
                try:
                    if isinstance(default, bool):
                        mod[item.identifier] = bool(default)
                    elif isinstance(default, int):
                        mod[item.identifier] = int(default)
                    else:
                        mod[item.identifier] = float(default)
                except (TypeError, KeyError):
                    pass
            if mod.get('sj_bone'):
                # factory = Soft Skin; bone tips need its isotropic form
                _apply_preset(mod, ng, 'SOFT_SKIN')
            count += 1
        for o in _layer_objects(obj):
            o.update_tag()
        _refresh(obj)
        self.report({'INFO'},
                    f"{count} layer(s) reset to factory defaults")
        return {'FINISHED'}


class SJ_OT_reset(Operator):
    """Reset the simulation (jumps to the scene start frame)"""
    bl_idname = "skin_jiggle.reset"
    bl_label = "Reset Simulation"

    def execute(self, context):
        context.scene.frame_set(context.scene.frame_start)
        return {'FINISHED'}


def _call_cache_operator(operator, selected=False):
    """Keep compatibility retries within the caller's error handler."""
    try:
        result = operator(selected=selected)
    except TypeError:
        result = operator()
    if 'FINISHED' not in result:
        raise RuntimeError('Blender cancelled the cache operation; check the console')


def _ensure_bake_dirs(objects):
    """Give every layer its own bake folder. Modifiers created from Python
    start with an empty one, and Blender 4.1 then 'bakes' without writing
    anything. Layers share one node group, hence one bake id, so the folder
    must be unique per object and layer or they would overwrite each other."""
    for ob in objects:
        for mod in _jiggle_modifiers(ob):
            if hasattr(mod, "bake_directory") and not mod.bake_directory:
                mod.bake_directory = (f"//sj_bake/{bpy.path.clean_name(ob.name)}"
                                      f"_{bpy.path.clean_name(mod.name)}/")


def _run_cache_operator(context, operator):
    """Bake/free the active object, or for an armature all helper points
    of its jiggle bones (they hold the simulations)."""
    obj = context.object
    _ensure_bake_dirs(_layer_objects(obj))
    if obj is not None and obj.type == 'ARMATURE':
        helpers = [o for o in _layer_objects(obj) if _jiggle_modifiers(o)]
        if not helpers:
            raise RuntimeError("This armature has no jiggle bones")
        # Blender's cache operators refuse hidden objects: show the helper
        # points only while the operator runs
        hidden = [h for h in helpers if h.hide_viewport]
        for h in hidden:
            h.hide_viewport = False
        context.view_layer.update()
        try:
            with context.temp_override(selected_objects=helpers,
                                       selected_editable_objects=helpers,
                                       active_object=helpers[0],
                                       object=helpers[0]):
                _call_cache_operator(operator, selected=True)
        finally:
            for h in hidden:
                h.hide_viewport = True
        return
    _call_cache_operator(operator)


class SJ_OT_bake(Operator):
    """Bake all simulation zones on this object to the cache"""
    bl_idname = "skin_jiggle.bake"
    bl_label = "Bake Simulation"

    @classmethod
    def poll(cls, context):
        return any(_jiggle_modifiers(o) for o in _layer_objects(context.object))

    def execute(self, context):
        try:
            _run_cache_operator(context, bpy.ops.object.simulation_nodes_cache_bake)
        except Exception as exc:
            self.report({'ERROR'}, f"Bake failed: {exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, "Simulation baked")
        return {'FINISHED'}


class SJ_OT_free_bake(Operator):
    """Delete the baked simulation cache"""
    bl_idname = "skin_jiggle.free_bake"
    bl_label = "Delete Bake"

    def execute(self, context):
        try:
            _run_cache_operator(context, bpy.ops.object.simulation_nodes_cache_delete)
        except Exception as exc:
            self.report({'ERROR'}, f"Delete failed: {exc}")
            return {'CANCELLED'}
        return {'FINISHED'}


def _target_layer(context, object_name, modifier_name):
    """(object, layer) an operator acts on: the named object (a bone's
    helper point), a cage's source layer, or the active object's layer."""
    obj = bpy.data.objects.get(object_name) if object_name else None
    if obj is None:
        obj, mod = _resolve_layer(context)
        if mod is not None:
            return obj, mod
    return obj, (obj.modifiers.get(modifier_name) if obj else None)


def _selected_bones(context):
    bones = list(context.selected_pose_bones or [])
    if not bones and context.active_pose_bone is not None:
        bones = [context.active_pose_bone]
    if not bones and context.object and context.object.type == 'ARMATURE':
        active = context.object.data.bones.active
        if active is not None:
            bones = [context.object.pose.bones[active.name]]
    return bones


class SJ_OT_add_bone_jiggle(Operator):
    """Make the selected bones jiggle with a preset. Each bone aims at a
    hidden helper point at its tip that is simulated exactly like a jiggle
    layer (same presets, collisions and Contact Reach)"""
    bl_idname = "skin_jiggle.add_bone_jiggle"
    bl_label = "Add Jiggle to Selected Bones"
    bl_options = {'REGISTER', 'UNDO'}

    preset: EnumProperty(name="Preset", items=_PRESET_ENUM, default='SOFT_SKIN')
    stretch: BoolProperty(
        name="Stretch",
        description="Let the bone squash and stretch toward its tip "
                    "(Stretch To) instead of only rotating (Damped Track)",
        default=False)

    @classmethod
    def poll(cls, context):
        o = context.object
        if o and o.library is not None:
            cls.poll_message_set("Linked armature: make it a library "
                                 "override first")
            return False
        return o is not None and o.type == 'ARMATURE'

    def invoke(self, context, event):
        if not _selected_bones(context):
            self.report({'ERROR'}, "Select the bones to jiggle (Pose Mode)")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        arm = context.object
        bones = _selected_bones(context)
        if not bones:
            self.report({'ERROR'}, "Select the bones to jiggle (Pose Mode)")
            return {'CANCELLED'}
        added, skipped = [], []
        try:
            for pb in bones:
                if _bone_constraint(pb) is not None:
                    skipped.append(pb.name)
                    continue
                _create_bone_jiggle(context, arm, pb, self.preset, self.stretch)
                added.append(pb.name)
        except Exception as exc:
            self.report({'ERROR'}, f"Could not add jiggle bone: {exc}")
            _LOG.exception("Could not add jiggle bone")
            return {'CANCELLED'}
        if added:
            arm.data.bones.active = arm.data.bones[added[-1]]
        _sync_colliders(context.scene, force=True)
        _refresh(arm)
        msg = f"{len(added)} jiggle bone(s) added"
        if skipped:
            msg += f"; already jiggling: {', '.join(skipped)}"
        self.report({'INFO'}, msg + ". Play the timeline to simulate.")
        return {'FINISHED'}


class SJ_OT_remove_bone_jiggle(Operator):
    """Stop this bone jiggling: removes its constraint and helper point"""
    bl_idname = "skin_jiggle.remove_bone_jiggle"
    bl_label = "Remove Bone Jiggle"
    bl_options = {'REGISTER', 'UNDO'}

    bone_name: StringProperty()

    def execute(self, context):
        arm = context.object
        pb = arm.pose.bones.get(self.bone_name) if arm and arm.type == 'ARMATURE' else None
        if pb is None:
            return {'CANCELLED'}
        _remove_bone_jiggle(arm, pb)
        _sync_colliders(context.scene, force=True)
        _refresh(arm)
        return {'FINISHED'}


class SJ_OT_select_bone(Operator):
    """Select this jiggle bone to edit its settings"""
    bl_idname = "skin_jiggle.select_bone"
    bl_label = "Select Jiggle Bone"
    bl_options = {'REGISTER', 'UNDO'}

    bone_name: StringProperty()

    def execute(self, context):
        arm = context.object
        bone = arm.data.bones.get(self.bone_name) if arm and arm.type == 'ARMATURE' else None
        if bone is None:
            return {'CANCELLED'}
        arm.data.bones.active = bone
        _select_bone(arm, bone.name)
        _refresh(arm)
        return {'FINISHED'}


def _select_bone(arm, name):
    # selection lives on Bone up to Blender 4.x, on PoseBone from 5.0
    pb = arm.pose.bones.get(name)
    if pb is not None and hasattr(pb, "select"):
        pb.select = True
    else:
        arm.data.bones[name].select = True


class SJ_OT_bone_stretch(Operator):
    """Switch between rotating only (Damped Track) and squash & stretch
    (Stretch To)"""
    bl_idname = "skin_jiggle.bone_stretch"
    bl_label = "Bone Stretch"
    bl_options = {'REGISTER', 'UNDO'}

    bone_name: StringProperty()

    def execute(self, context):
        arm = context.object
        pb = arm.pose.bones.get(self.bone_name) if arm and arm.type == 'ARMATURE' else None
        helper = _bone_helper(pb) if pb is not None else None
        if helper is None:
            return {'CANCELLED'}
        stretch = _bone_constraint(pb).type != 'STRETCH_TO'
        _set_bone_constraint(pb, helper, stretch)
        _refresh(arm)
        return {'FINISHED'}


# ===========================================================================
#  UI
# ===========================================================================
def _layer_group(mod):
    """Name of the vertex group driving a layer ('' if none)."""
    ident = _input_ident_map(mod.node_group).get("Weight")
    return mod.get(f"{ident}_attribute_name", "") if ident else ""


def _active_layer(obj):
    """The layer selected in the list, falling back to the first one."""
    mods = _jiggle_modifiers(obj)
    idx = obj.sj_active_layer
    if 0 <= idx < len(obj.modifiers) and obj.modifiers[idx] in mods:
        return obj.modifiers[idx]
    return mods[0] if mods else None


def _feel_summary(mod):
    """Plain-language read-out of a layer's spring: feel, Hz and travel."""
    v = {name: mod.get(ident)
         for name, ident in _input_ident_map(mod.node_group).items()}
    try:
        k_n = v["Stiffness"] * max(1.0 - v["Normal Softness"], 0.02)
        omega = math.sqrt(k_n / max(v["Mass"], 1e-4))
        zeta = v["Damping"] / (2.0 * omega) if omega > 0 else 1.0
        travel = v["Max Stretch"] * 100.0
    except (TypeError, KeyError, ValueError):
        return None
    feel = ("Very bouncy" if zeta < 0.25 else "Bouncy" if zeta < 0.45
            else "Soft" if zeta < 0.7 else "Firm, settles fast")
    return (f"{feel}, {omega / (2 * math.pi):.1f} Hz",
            f"Jiggle travel up to {travel:.1f} cm")


def _preset_label(mod):
    return PRESETS.get(mod.get('sj_body_preset', ''), ("Custom",))[0]


class SJ_UL_layers(bpy.types.UIList):
    """Jiggle layers of the object: its jiggle modifiers only."""

    def filter_items(self, context, data, propname):
        flags = [self.bitflag_filter_item
                 if (m.type == 'NODES' and m.node_group
                     and m.node_group.name.startswith(CORE_NAME)) else 0
                 for m in getattr(data, propname)]
        return flags, []

    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index):
        group = _layer_group(item)
        missing = group not in data.vertex_groups
        row = layout.row(align=True)
        name = row.row(align=True)
        name.alert = missing
        name.label(text=group or "<no group>",
                   icon='ERROR' if missing else 'GROUP_VERTEX')
        cage = _layer_cage(item)
        if cage is not None and not cage.hide_viewport:
            row.label(text="", icon='MESH_ICOSPHERE')
        row.prop(item, "show_viewport", text="", emboss=False)


class _SJPanel:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Jiggle"

    @classmethod
    def poll(cls, context):
        return (context.object is not None
                and context.object.type in {'MESH', 'ARMATURE'})


def _draw_warnings(layout, context, obj):
    if abs(context.scene.unit_settings.scale_length - 1.0) > 1e-6:
        warning = layout.box()
        warning.alert = True
        warning.label(text='Presets assume 1 Blender unit = 1 metre', icon='ERROR')
        warning.label(text='Use Unit Scale 1 and actual human dimensions')
    if min(abs(v) for v in obj.scale) < 1e-6:
        warning = layout.box()
        warning.alert = True
        warning.label(text='Zero object scale: restore a nonzero scale', icon='ERROR')
    n_old = sum(len(_old_layers(o)) for o in _layer_objects(obj))
    if n_old:
        box = layout.box()
        box.alert = True
        box.label(text=f"{n_old} layer(s) use an older engine", icon='ERROR')
        box.operator("skin_jiggle.upgrade_layers", icon='FILE_REFRESH')


def _draw_anim_mode(layout, context):
    row = layout.row(align=True)
    row.scale_y = 1.3
    row.prop(context.scene, "sj_anim_mode",
             icon='PLAY' if not context.scene.sj_anim_mode
             else 'RENDER_ANIMATION', toggle=True)


def _active_jiggle_bone(arm):
    active = arm.data.bones.active
    pb = arm.pose.bones.get(active.name) if active is not None else None
    return pb if pb is not None and _bone_helper(pb) is not None else None


class VIEW3D_PT_skin_jiggle(_SJPanel, Panel):
    bl_label = "Skin Jiggle"

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        layout = self.layout
        obj = context.object
        if not obj or obj.type not in {'MESH', 'ARMATURE'}:
            layout.label(text="Select a mesh or an armature", icon='INFO')
            return
        _draw_warnings(layout, context, obj)
        _draw_anim_mode(layout, context)
        if obj.type == 'ARMATURE':
            self.draw_bones(context, obj)
            return

        if not _jiggle_modifiers(obj):
            box = layout.box()
            col = box.column(align=True)
            col.label(text="No jiggle layers yet", icon='INFO')
            col.label(text="1. Paint a vertex group (Weight Paint)")
            col.label(text="2. Add a layer for it")
            row = layout.row()
            row.scale_y = 1.3
            row.operator("skin_jiggle.add_layer", icon='ADD')
            return

        row = layout.row()
        row.template_list("SJ_UL_layers", "", obj, "modifiers",
                          obj, "sj_active_layer", rows=3)
        side = row.column(align=True)
        side.operator("skin_jiggle.add_layer", text="", icon='ADD')
        active = _active_layer(obj)
        if active is not None:
            op = side.operator("skin_jiggle.remove_layer", text="",
                               icon='REMOVE')
            op.modifier_name = active.name

    def draw_bones(self, context, arm):
        layout = self.layout
        bones = _jiggle_bones(arm)
        if not bones:
            box = layout.box()
            col = box.column(align=True)
            col.label(text="No jiggle bones yet", icon='INFO')
            col.label(text="1. Select bones in Pose Mode")
            col.label(text="2. Add jiggle to them")
        else:
            active = _active_jiggle_bone(arm)
            col = layout.column(align=True)
            for pb in bones:
                # the preset is shown in Layer Settings: a second column
                # would be cut off in a narrow sidebar
                row = col.row(align=True)
                op = row.operator("skin_jiggle.select_bone", text=pb.name,
                                  icon='BONE_DATA', depress=pb == active)
                op.bone_name = pb.name
                op = row.operator("skin_jiggle.remove_bone_jiggle", text="",
                                  icon='X')
                op.bone_name = pb.name
        row = layout.row()
        row.scale_y = 1.3
        row.operator("skin_jiggle.add_bone_jiggle",
                     text="Jiggle Selected Bones", icon='ADD')


def _draw_layer_settings(layout, obj, mod, pb=None):
    """Settings of one layer. With pb, the layer drives that jiggle bone:
    no vertex group, cage, folds or normal softness, plus a Stretch toggle."""
    ident_map = _input_ident_map(mod.node_group)
    owner = obj.name if pb is not None else ""

    def labelled(text):
        split = layout.split(factor=0.28, align=True)
        split.label(text=text)
        return split

    if pb is None:
        group = _layer_group(mod)
        missing = group not in obj.vertex_groups
        row = labelled("Group")
        row.alert = missing
        op = row.operator("skin_jiggle.set_group",
                          text=f"Missing '{group or '-'}': pick"
                          if missing else group,
                          icon='ERROR' if missing else 'GROUP_VERTEX')
        op.modifier_name = mod.name
    else:
        row = labelled("Bone")
        row.label(text=pb.name, icon='BONE_DATA')
    row = labelled("Preset")
    op = row.operator("skin_jiggle.apply_preset",
                      text=_preset_label(mod), icon='PRESET')
    op.modifier_name = mod.name
    op.object_name = owner
    row = labelled("Contact")
    style = mod.get('sj_contact_style', 'BODY')
    op = row.operator('skin_jiggle.contact_style',
                      text=next((label for ident, label, _ in _CONTACT_STYLES
                                 if ident == style), 'Body preset'),
                      icon='PHYSICS')
    op.modifier_name = mod.name
    op.object_name = owner

    ident = ident_map.get("Blend")
    if ident:
        layout.prop(mod, f'["{ident}"]', text="Strength", slider=True)

    summary = _feel_summary(mod)
    if summary:
        col = layout.column(align=True)
        col.scale_y = 0.85
        col.label(text=summary[0], icon='FORCE_HARMONIC')
        col.label(text=summary[1] if pb is None
                  else summary[1].replace("Jiggle travel", "Tip swing"),
                  icon='BLANK1')

    row = layout.row(align=True)
    if pb is None:
        cage = _layer_cage(mod)
        cage_on = cage is not None and not cage.hide_viewport
        op = row.operator("skin_jiggle.cage_toggle",
                          text="Fast Preview Cage: On" if cage_on
                          else "Fast Preview Cage",
                          icon='MESH_ICOSPHERE', depress=cage_on)
        op.modifier_name = mod.name
        if cage is not None:
            op = row.operator("skin_jiggle.cage_delete", text="", icon='TRASH')
            op.modifier_name = mod.name
    else:
        stretch = _bone_constraint(pb).type == 'STRETCH_TO'
        op = row.operator("skin_jiggle.bone_stretch",
                          text="Squash & Stretch: On" if stretch
                          else "Squash & Stretch",
                          icon='CON_STRETCHTO', depress=stretch)
        op.bone_name = pb.name

    for sid, label, icon, names in _LAYER_SECTIONS:
        if pb is not None and sid == "folds":
            continue
        # Limits stay open: Contact Reach is the fix for clipping skin
        header, body = layout.panel(
            f"sj_{sid}", default_closed=sid not in {"motion", "limits"})
        header.label(text=label, icon=icon)
        if body is None:
            continue
        # names inside full-width fields: split labels get cut off
        # in a narrow sidebar ("Max Str...")
        col = body.column(align=True)
        for name in names:
            if pb is not None and name == "Normal Softness":
                continue    # bone tips are isotropic
            ident = ident_map.get(name)
            if ident is not None:
                col.prop(mod, f'["{ident}"]', text=name)
        if sid == "limits":
            tip = body.column(align=True)
            tip.scale_y = 0.8
            if ident_map.get("Contact Reach") is None:
                tip.label(text="Upgrade the layer to get Contact Reach",
                          icon='ERROR')
            elif pb is not None:
                tip.label(text="Max Stretch: how far the", icon='INFO')
                tip.label(text="bone tip may swing.", icon='BLANK1')
            else:
                tip.label(text="Skin clipping into a collider?", icon='INFO')
                tip.label(text="Raise Contact Reach.", icon='BLANK1')
                tip.label(text="Max Stretch: jiggle only.",
                          icon='BLANK1')


class VIEW3D_PT_skin_jiggle_layer(_SJPanel, Panel):
    bl_label = "Layer Settings"
    bl_parent_id = "VIEW3D_PT_skin_jiggle"

    @classmethod
    def poll(cls, context):
        obj = context.object
        if obj is None:
            return False
        if obj.type == 'ARMATURE':
            return _active_jiggle_bone(obj) is not None
        return obj.type == 'MESH' and _active_layer(obj) is not None

    def draw(self, context):
        obj = context.object
        if obj.type == 'ARMATURE':
            pb = _active_jiggle_bone(obj)
            helper = _bone_helper(pb)
            mods = _jiggle_modifiers(helper)
            if mods:
                _draw_layer_settings(self.layout, helper, mods[0], pb)
            return
        _draw_layer_settings(self.layout, obj, _active_layer(obj))


class VIEW3D_PT_skin_jiggle_colliders(_SJPanel, Panel):
    bl_label = "Colliders"
    bl_parent_id = "VIEW3D_PT_skin_jiggle"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        colliders = [ob for ob in context.scene.objects if _is_collider(ob)]
        row = layout.row(align=True)
        row.operator('skin_jiggle.add_collider', text="Add Hand Collider",
                     icon='ADD')
        row.operator("skin_jiggle.sync_colliders", text="",
                     icon='FILE_REFRESH')
        if not colliders:
            col = layout.column(align=True)
            col.scale_y = 0.8
            col.label(text="Any mesh with Physics > Collision", icon='INFO')
            col.label(text="is a collider. None in this scene yet.")
            return
        for collider in colliders:
            box = layout.box()
            box.prop(collider, 'name', text='', emboss=False,
                     icon='VIEW_PAN' if collider.get('sj_managed_collider')
                     else 'MESH_DATA')
            col = box.column(align=True)
            col.use_property_split = True
            col.use_property_decorate = False
            col.prop(collider.collision, 'thickness_outer', text='Thickness')
            col.prop(collider.collision, 'cloth_friction', text='Friction')
            col.prop(collider.collision, 'damping', text='Damping')


class VIEW3D_PT_skin_jiggle_sim(_SJPanel, Panel):
    bl_label = "Simulation & Bake"
    bl_parent_id = "VIEW3D_PT_skin_jiggle"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.operator("skin_jiggle.reset", icon='FILE_REFRESH')
        row = col.row(align=True)
        row.operator("skin_jiggle.bake", icon='RENDER_ANIMATION')
        row.operator("skin_jiggle.free_bake", text="", icon='TRASH')
        layout.operator("skin_jiggle.reset_defaults", icon='LOOP_BACK')
        if context.object.type == 'MESH':
            col = layout.column()
            col.use_property_split = True
            col.use_property_decorate = False
            col.prop(context.scene, "sj_cage_ratio", text="Cage Ratio")


# ===========================================================================
#  Registration
# ===========================================================================
_CLASSES = (
    SJ_OT_add_layer,
    SJ_OT_remove_layer,
    SJ_OT_set_group,
    SJ_OT_apply_preset,
    SJ_OT_contact_style,
    SJ_OT_add_collider,
    SJ_OT_sync_colliders,
    SJ_OT_upgrade_layers,
    SJ_OT_cage_toggle,
    SJ_OT_cage_delete,
    SJ_OT_reset_defaults,
    SJ_OT_reset,
    SJ_OT_bake,
    SJ_OT_free_bake,
    SJ_OT_add_bone_jiggle,
    SJ_OT_remove_bone_jiggle,
    SJ_OT_select_bone,
    SJ_OT_bone_stretch,
    SJ_UL_layers,
    VIEW3D_PT_skin_jiggle,
    VIEW3D_PT_skin_jiggle_layer,
    VIEW3D_PT_skin_jiggle_colliders,
    VIEW3D_PT_skin_jiggle_sim,
)

def _anim_mode_update(self, context):
    """Push the scene-wide Animation Mode toggle into every jiggle layer."""
    val = bool(self.sj_anim_mode)
    for ob in self.objects:
        if ob.type != 'MESH':
            continue
        for mod in _jiggle_modifiers(ob):
            _set_value(mod, mod.node_group, "Animation Mode", val)
        if _jiggle_modifiers(ob):
            ob.update_tag()


def register():
    for c in _CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Object.sj_active_layer = bpy.props.IntProperty(
        name="Active Jiggle Layer", default=0, min=0)
    bpy.types.Scene.sj_cage_ratio = bpy.props.FloatProperty(
        name="Cage Ratio",
        description="Decimation ratio used when creating a preview cage "
                    "(0.1 = 10%% of the original vertex count)",
        default=0.15, min=0.02, max=1.0, subtype='FACTOR')
    bpy.types.Scene.sj_anim_mode = bpy.props.BoolProperty(
        name="Animation Mode",
        description="Fast animator preview: 1 substep with a stability "
                    "clamp, light volume test, reduced fold/squash blurs. "
                    "Turn off (and bake) for final quality",
        default=False, update=_anim_mode_update)
    if _sj_frame_sync not in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.append(_sj_frame_sync)
    if _sj_depsgraph_watch not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_sj_depsgraph_watch)

def unregister():
    if _sj_frame_sync in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.remove(_sj_frame_sync)
    if _sj_depsgraph_watch in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_sj_depsgraph_watch)
    if bpy.app.timers.is_registered(_repair_timer):
        bpy.app.timers.unregister(_repair_timer)
    del bpy.types.Scene.sj_anim_mode
    del bpy.types.Scene.sj_cage_ratio
    del bpy.types.Object.sj_active_layer
    for c in reversed(_CLASSES):
        bpy.utils.unregister_class(c)

if __name__ == "__main__":
    register()
