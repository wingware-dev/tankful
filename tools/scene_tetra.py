"""The neon tetras for tools/build_scene.py: a school as one object.

Runs inside UPBGE's Blender.  Each school (tankful.sim.species.schools)
is built as <school>.Rig, one armature for all its members, with
<school> (every member's body and eyes) and <school>.Fins skinned to it.
Each member has its own bones in the rig, prefixed with its name
("NeonTetra.03:Tail"): a Root bone, which the game places and turns as
the fish swims (tankful.game.fishes), and under it the spine chain
alone (tankful.sim.swim.bones), as the fins are too small to show
strokes of their own.

A tank holds a dozen or more of these, so they are cheap
(docs/harness.md, "Frame budget"):

- three objects per school, not three per fish: in the player each
  object that moves costs time of its own, about 0.4 fps per tetra
  built as separate objects;
- the body material has no caustic projection and no thin film: its
  stripe's shimmer comes from the viewing angle alone;
- the fins are faint and plain, with no shadow or caustic detail on
  them.

Each member is built in its own space as tools/scene_fish.py: +x
forward, +y its left, +z its back, origin halfway along it, in units of
its length, scaled to its size.
"""

import bpy
from mathutils import Vector

import scene_fish
from scene_env import link_object, new_material
from scene_fish import CHAIN, MeshBuilder, Shape, band, fin, spine_weights
from tankful.sim import species as sim_species

# Side profile, snout (u=0) to the tail's base (u=1): (u, top, bottom,
# half-width), in lengths.  Slender and torpedo-shaped, deepest just
# ahead of the middle
TETRA_BODY = (
  (0.00, 0.006, -0.012, 0.010),
  (0.05, 0.034, -0.034, 0.030),
  (0.14, 0.064, -0.062, 0.046),
  (0.28, 0.088, -0.086, 0.054),
  (0.42, 0.095, -0.093, 0.052),
  (0.56, 0.086, -0.083, 0.046),
  (0.70, 0.066, -0.061, 0.036),
  (0.84, 0.045, -0.041, 0.024),
  (1.00, 0.033, -0.030, 0.014),
)
TETRA = Shape(TETRA_BODY, 0.5, 0.76, (0.24, 0.08, -0.06, -0.19), -0.5, 0.1)

# The eye, pupil (0) to the back (1): black, a bronze iris, a blue rim
# that carries the stripe's color forward, then silver
TETRA_EYE = ((0.0, (0.004, 0.004, 0.004)), (0.24, (0.006, 0.006, 0.006)),
             (0.30, (0.42, 0.34, 0.20)), (0.42, (0.10, 0.30, 0.50)),
             (0.55, (0.50, 0.50, 0.48)), (1.0, (0.35, 0.35, 0.34)))


def weights(p, s=0.0, r=0.0):
  return spine_weights(p[0], blend=0.04, joints=TETRA.joints)


def body_x(u):
  return scene_fish.body_x(u, TETRA)


def profile(u):
  return scene_fish.profile(u, TETRA)


# The fins

def add_fins(mb):
  # Caudal: a forked fan from the tail's base
  tail_base = body_x(1.0)

  def caudal_base(s):
    return (tail_base + 0.01, 0.0, -0.028 + 0.056 * s)

  def caudal_tip(s):
    e = 2 * s - 1
    # The fork: the middle rays are short, the outer ones long
    reach = 0.10 + 0.13 * abs(e) ** 1.4
    return (tail_base - reach, 0.0, e * (0.07 + 0.05 * abs(e)))
  fin(mb, caudal_base, caudal_tip, 8, 4, weights)

  # Dorsal: a small sail just behind the middle of the back
  def dorsal_base(s):
    u = 0.46 + 0.14 * s
    return (body_x(u), 0.0, profile(u)[0] - 0.006)

  def dorsal_tip(s):
    u = 0.46 + 0.14 * s
    return (body_x(u) - 0.05 - 0.02 * s, 0.0,
            profile(u)[0] + 0.075 * (1 - s) + 0.012)
  fin(mb, dorsal_base, dorsal_tip, 4, 3, weights)

  # Anal: a long, low fin along the rear of the belly
  def anal_base(s):
    u = 0.55 + 0.32 * s
    return (body_x(u), 0.0, profile(u)[1] + 0.006)

  def anal_tip(s):
    u = 0.55 + 0.32 * s
    return (body_x(u) - 0.03, 0.0, profile(u)[1] - 0.05 * (1 - 0.6 * s))
  fin(mb, anal_base, anal_tip, 6, 3, weights)


# The rig

def build_armature(scene, name, members):
  """One armature for the whole school: per member a Root bone, at rest
  where the armature is with no turn (the game puts the fish's place and
  heading on it), and under it the spine chain, scaled to the member."""
  data = bpy.data.armatures.new(name)
  rig = link_object(scene, name, data, None)
  bpy.context.view_layer.objects.active = rig
  bpy.ops.object.mode_set(mode='EDIT')
  for res in members:
    scale = res.species.length * res.size
    prefix = res.name + ':'
    # Along +y with no roll, so the bone's rest frame is the armature's
    root = data.edit_bones.new(prefix + 'Root')
    root.head = Vector((0, 0, 0))
    root.tail = Vector((0, 0.3 * scale, 0))
    root.roll = 0.0
    xs = (TETRA.snout_x,) + TETRA.joints + (TETRA.tail_end + 0.1,)
    prev = root
    for k, bname in enumerate(CHAIN):
      eb = data.edit_bones.new(prefix + bname)
      eb.head = Vector((xs[k], 0, 0)) * scale
      eb.tail = Vector((xs[k + 1], 0, 0)) * scale
      eb.roll = 0.0
      eb.parent = prev
      eb.use_connect = k > 0
      prev = eb
  bpy.ops.object.mode_set(mode='OBJECT')
  for pb in rig.pose.bones:
    pb.rotation_mode = 'QUATERNION' if pb.name.endswith(':Root') else 'XYZ'
  return rig


# Materials

def body_material():
  mat, t, out = new_material('NeonTetra')
  uv = t.add('ShaderNodeUVMap', {'uv_map': 'Pattern'})
  xyz = t.add('ShaderNodeSeparateXYZ')
  t.link(uv.outputs['UV'], xyz.inputs[0])
  x, z = xyz.outputs['X'], xyz.outputs['Y']

  def ramp_x(lo, hi, rising=True):
    a, b = (0.0, 1.0) if rising else (1.0, 0.0)
    return t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
                 Value=x, From_Min=lo, From_Max=hi, To_Min=a,
                 To_Max=b).outputs[0]

  # Olive-brown along the back, silver on the belly
  back = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
               Value=z, From_Min=-0.03, From_Max=0.05, To_Min=0.0,
               To_Max=1.0).outputs[0]
  color = t.mix(back, (0.62, 0.62, 0.60, 1.0), (0.13, 0.11, 0.06, 1.0))
  # The red: the rear half of the body below the stripe
  below = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
                Value=z, From_Min=-0.004, From_Max=0.008, To_Min=1.0,
                To_Max=0.0).outputs[0]
  red = t.math('MULTIPLY', below, ramp_x(0.10, 0.04, rising=True))
  color = t.mix(red, color, (0.62, 0.03, 0.025, 1.0))
  # The stripe: from the eye back to the adipose fin, a little above the
  # middle, and wide enough to read at a few pixels tall
  stripe = t.math('MULTIPLY', band(t, z, x, 0.022, 0.0, 0.02, 0.012),
                  t.math('MULTIPLY', ramp_x(-0.22, -0.15),
                         ramp_x(0.44, 0.38, rising=True)))
  # Its shimmer: blue facing the viewer, turquoise-green toward grazing,
  # so it changes as the fish turns
  facing = t.add('ShaderNodeLayerWeight', Blend=0.45).outputs['Facing']
  blue = t.ramp(facing, [(0.0, (0.02, 0.42, 0.95)), (0.55, (0.02, 0.62, 0.80)),
                         (1.0, (0.10, 0.72, 0.52))])
  color = t.mix(stripe, color, blue)
  bsdf = t.add('ShaderNodeBsdfPrincipled', Roughness=0.35)
  t.link(color, bsdf.inputs['Base Color'])
  # The stripe and the red glow a little, as they seem to in a tank
  glow = t.mix(stripe, t.mix(red, (0, 0, 0, 1), (0.10, 0.004, 0.003, 1.0)),
               t.mix(0.55, (0, 0, 0, 1), blue))
  t.link(glow, bsdf.inputs['Emission Color'])
  bsdf.inputs['Emission Strength'].default_value = 1.0
  if 'Specular IOR Level' in bsdf.inputs:
    bsdf.inputs['Specular IOR Level'].default_value = 0.6
  t.link(bsdf.outputs[0], out.inputs['Surface'])
  return mat


def fin_material():
  """Faint, nearly clear fins that fade out at their edges."""
  mat, t, out = new_material('NeonTetraFin', blended=True)
  uv = t.add('ShaderNodeUVMap', {'uv_map': 'UVMap'})
  sr = t.add('ShaderNodeSeparateXYZ')
  t.link(uv.outputs['UV'], sr.inputs[0])
  bsdf = t.add('ShaderNodeBsdfPrincipled', Roughness=0.4)
  bsdf.inputs['Base Color'].default_value = (0.70, 0.72, 0.74, 1.0)
  fade = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
               Value=sr.outputs['Y'], From_Min=0.55, From_Max=1.0,
               To_Min=0.32, To_Max=0.0).outputs[0]
  t.link(fade, bsdf.inputs['Alpha'])
  t.link(bsdf.outputs[0], out.inputs['Surface'])
  return mat


# Building

def build_schools(scene):
  mats = {
    'body': body_material(),
    'eye': scene_fish.eye_material('NeonTetraEye', TETRA_EYE),
    'fin': fin_material(),
  }
  for spec in sim_species.schools():
    build_school(scene, spec, mats)


def build_school(scene, spec, mats):
  """The school as three objects: <school>.Rig, the armature, and
  <school> and <school>.Fins, every member's body and fins in one mesh
  each, skinned to it."""
  members = sim_species.school_members(spec)
  rig = build_armature(scene, spec.name + '.Rig', members)
  body, fins = MeshBuilder(1.0), MeshBuilder(1.0)
  for res in members:
    for mb in (body, fins):
      mb.scale = spec.species.length * res.size
      mb.prefix = res.name + ':'
    scene_fish.add_body(body, rings=16, sides=12, shape=TETRA)
    for side in (1, -1):
      scene_fish.add_eye(body, side, 1, segments=10, rings=6, shape=TETRA,
                         u=0.10, r=0.05, height=0.6)
    add_fins(fins)
  meshes = (body.finish(spec.name, [mats['body'], mats['eye']], scene, rig),
            fins.finish(spec.name + '.Fins', [mats['fin']], scene, rig))
  # Small fish cast no shadows either (tools/scene_fish.py)
  for obj in meshes:
    obj.visible_shadow = False
  return rig
