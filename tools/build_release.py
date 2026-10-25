"""Build the single-file add-on ZIP and refresh the documented preset table.

Uses the standard library only; does not import bpy or execute the add-on.
"""
import ast
import math
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
source = root / 'skin_jiggle_physics.py'
tree = ast.parse(source.read_text(encoding='utf-8'))
constants = {}
for node in tree.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in {'BUILD_TAG', '_PRESET_SPECS', 'bl_info'}:
                constants[target.id] = ast.literal_eval(node.value)

# The ZIP is named from BUILD_TAG while Blender's Preferences show
# bl_info['version']; refuse to build (or touch the guide) if they disagree.
bl_version = '.'.join(str(part) for part in constants['bl_info']['version'])
if bl_version != constants['BUILD_TAG']:
    raise SystemExit(f"Version mismatch: bl_info version {bl_version} != "
                     f"BUILD_TAG {constants['BUILD_TAG']}. Update both in "
                     f"{source.name} before building.")

rows = [
    '| Preset | Normal Hz | Damping ratio | Stiffness | Damping (1/s) | Effective mass | Normal softness | Max travel (cm) | Substeps | Collider gap (mm) | Layer friction | Object bounce | Contact squash | Contact spread |',
    '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
]
contact = ast.literal_eval(next(node.value for node in tree.body
    if isinstance(node, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id == '_CONTACT_PRESET_BASE'
        for target in node.targets)))
for key, spec in constants['_PRESET_SPECS'].items():
    label, hz, zeta, mass, softness, travel, steps, fold, squash, bounce = spec
    stiffness = mass * (2*math.pi*hz)**2 / max(1-softness, .02)
    damping = 4*math.pi*zeta*hz
    gap, friction, contact_squash, contact_bounce, spread = contact[key]
    rows.append(f'| {label} | {hz:.1f} | {zeta:.2f} | {stiffness:.2f} | {damping:.2f} | {mass:.2f} | {softness:.2f} | {travel*100:.1f} | {steps} | {gap*1000:.1f} | {friction:.2f} | {contact_bounce:.2f} | {contact_squash:.2f} | {spread} |')
guide = root / 'PRESET_GUIDE.md'
text = guide.read_text(encoding='utf-8')
start = '<!-- PRESET_TABLE_START -->'
end = '<!-- PRESET_TABLE_END -->'
before, rest = text.split(start, 1)
_, after = rest.split(end, 1)
guide.write_text(before + start + '\n' + '\n'.join(rows) + '\n' + end + after,
                 encoding='utf-8')
destination = root / 'dist' / f"skin_jiggle_physics_{constants['BUILD_TAG']}.zip"
destination.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    archive.write(source, source.name)
print(destination)
