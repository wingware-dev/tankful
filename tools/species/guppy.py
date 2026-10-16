"""The guppies for tools/build_scene.py: a shoal as one object.

Runs inside UPBGE's Blender.  The shoal (tankful.sim.species.guppy.SHOAL)
is built as the neon tetras' school is (tools/species/neon_tetra.py):
<shoal>.Rig, one armature for all its members, with <shoal> (every
member's body and eyes) and <shoal>.Fins skinned to it.  Each member has
its own bones, prefixed with its name ("Guppy.M0:Caudal"): a Root bone,
which the game places and turns as the fish swims (tankful.game.fishes),
and under it the bones of tankful.sim.species.guppy.BONES.

The two sexes are built apart:

- females: larger, deep-bellied and plain olive-silver, with a dark
  spot by the vent and a modest, faintly tinted tail;
- males: smaller and slim, their bodies flecked with color, and with a
  big fan tail and a long flag of a dorsal fin, each male in a color of
  his own (MALE_COLORS).

Plain materials (docs/harness.md, "Frame budget"): no caustic projection
and no thin film.  The colorful fins are drawn opaque, dithered only at
their faded edge, as the angelfish's are, since blended fins with
detail break up in the player's frame accumulation; the clear pectorals
stay blended.

Each member is built in its own space as tools/scene_fish.py: +x
forward, +y its left, +z its back, origin halfway along it, in units of
its length, scaled to its size.
"""

import math

import bpy
from mathutils import Vector

import scene_fish
from scene_env import link_object, new_material
from scene_fish import (CHAIN, WATER_TINT, MeshBuilder, Shape, band, fin,
                        spine_weights)
from tankful.sim.species import guppy as sim_guppy

# Side profiles, snout (u=0) to the tail's base (u=1): (u, top, bottom,
# half-width), in lengths.  The female is deep-bellied behind the head,
# the male slim, with a longer tail fan behind a shorter body
FEMALE_BODY = (
  (0.00, 0.006, -0.012, 0.010),
  (0.05, 0.040, -0.040, 0.032),
  (0.14, 0.074, -0.080, 0.052),
  (0.28, 0.094, -0.116, 0.062),
  (0.42, 0.097, -0.118, 0.060),
  (0.56, 0.084, -0.090, 0.050),
  (0.70, 0.062, -0.058, 0.036),
  (0.85, 0.045, -0.040, 0.024),
  (1.00, 0.036, -0.032, 0.015),
)
MALE_BODY = (
  (0.00, 0.006, -0.010, 0.009),
  (0.05, 0.034, -0.032, 0.028),
  (0.14, 0.060, -0.058, 0.042),
  (0.30, 0.074, -0.074, 0.046),
  (0.46, 0.074, -0.070, 0.043),
  (0.62, 0.064, -0.058, 0.036),
  (0.78, 0.052, -0.046, 0.026),
  (1.00, 0.044, -0.040, 0.016),
)
FEMALE = Shape(FEMALE_BODY, 0.5, 0.66, (0.26, 0.10, -0.04, -0.13), -0.5,
               0.1)
MALE = Shape(MALE_BODY, 0.5, 0.58, (0.28, 0.14, 0.02, -0.06), -0.5, 0.1)

# The eye, pupil (0) to the back (1): black, a gold iris, then silver
GUPPY_EYE = ((0.0, (0.004, 0.004, 0.004)), (0.26, (0.006, 0.006, 0.006)),
             (0.32, (0.50, 0.40, 0.16)), (0.45, (0.42, 0.36, 0.22)),
             (0.55, (0.55, 0.55, 0.52)), (1.0, (0.38, 0.38, 0.36)))

# Each male's tail and dorsal, by his place among the males: the color
# at the fan's base, its middle, and its edge, and the color of its
# spots
MALE_COLORS = (
  # Red-orange, deepening to red at the edge
  ((0.80, 0.30, 0.06), (0.85, 0.16, 0.05), (0.60, 0.04, 0.04),
   (0.03, 0.02, 0.02)),
  # Blue and turquoise, the edge violet
  ((0.10, 0.40, 0.55), (0.08, 0.30, 0.75), (0.30, 0.10, 0.55),
   (0.02, 0.02, 0.05)),
  # Yellow to orange, with black spots
  ((0.85, 0.70, 0.10), (0.90, 0.48, 0.06), (0.75, 0.28, 0.04),
   (0.02, 0.02, 0.02)),
)

# Material slots: the body mesh's, and the fin mesh's (one per male color)
BODY_FEMALE, BODY_MALE, EYE = 0, 1, 2
FIN_FEMALE, FIN_PEC, FIN_MALE = 0, 1, 2


def shape_of(sex):
  return MALE if sex == sim_guppy.MALE else FEMALE


def tail_base(shape):
  return scene_fish.body_x(1.0, shape)


# The fins

def add_fins(mb, shape, sex, mat):
  """The fins of a guppy of shape and sex, the colorful ones with
  material slot mat."""
  male = sex == sim_guppy.MALE
  body_x = lambda u: scene_fish.body_x(u, shape)
  profile = lambda u: scene_fish.profile(u, shape)

  def body(p, s=0.0, r=0.0):
    return spine_weights(p[0], shape.joints, blend=0.04)

  def on(bone, share):
    """Spine weights at the base, giving way to bone toward the tip."""
    def weights(p, s, r):
      w = {b: v * (1 - share * r) for b, v in body(p).items()}
      w[bone] = w.get(bone, 0.0) + share * r
      return w
    return weights

  # Caudal: a fan from the tail's base.  The male's is a broad delta,
  # its edge nearly straight; the female's smaller and rounded
  x0 = tail_base(shape)
  root = 0.034 if male else 0.030

  def caudal_base(s):
    return (x0 + 0.01, 0.0, (2 * s - 1) * root)

  def caudal_tip(s):
    e = 2 * s - 1
    if male:
      return (shape.tail_end - 0.03 + 0.03 * e * e, 0.0, e * 0.23)
    return (shape.tail_end + 0.03 + 0.06 * e * e, 0.0, e * 0.11)
  fin(mb, caudal_base, caudal_tip, 10, 6, on('Caudal', 0.9),
      mat if male else FIN_FEMALE)

  # Dorsal: the male's a long flag trailing back over the tail's base,
  # the female's small
  u0, u1 = (0.42, 0.66) if male else (0.48, 0.62)

  def dorsal_base(s):
    u = u0 + (u1 - u0) * s
    return (body_x(u), 0.0, profile(u)[0] - 0.006)

  def dorsal_tip(s):
    u = u0 + (u1 - u0) * s
    if male:
      return (body_x(u) - 0.16 - 0.06 * s, 0.0,
              profile(u)[0] + 0.12 * (1 - 0.7 * s) + 0.01)
    return (body_x(u) - 0.05, 0.0, profile(u)[0] + 0.06 * (1 - 0.7 * s))
  fin(mb, dorsal_base, dorsal_tip, 5, 4, on('Dorsal', 0.8),
      mat if male else FIN_FEMALE)

  # Anal: small and low, behind the belly (the male's narrow, as his is
  # the gonopodium)
  a0, a1 = (0.50, 0.60) if male else (0.58, 0.74)

  def anal_base(s):
    u = a0 + (a1 - a0) * s
    return (body_x(u), 0.0, profile(u)[1] + 0.006)

  def anal_tip(s):
    u = a0 + (a1 - a0) * s
    reach = 0.09 if male else 0.05
    return (body_x(u) - reach, 0.0, profile(u)[1] - reach * (1 - 0.6 * s))
  fin(mb, anal_base, anal_tip, 3, 2, body, FIN_FEMALE)

  # Pectorals: small clear fans behind the gill cover
  for side, bone in ((1, 'Pec.L'), (-1, 'Pec.R')):
    top, bot, half = profile(0.26)
    px = body_x(0.26)

    def pec_base(s, px=px, side=side, half=half):
      return (px, side * half * 0.85, -0.03 + 0.03 * s)

    def pec_tip(s, px=px, side=side, half=half):
      return (px - 0.09 - 0.02 * math.sin(math.pi * s),
              side * (half * 0.85 + 0.04), -0.045 + 0.04 * s)

    def pec_weights(p, s, r, bone=bone):
      return {'Head': 1 - r, bone: r} if r < 1 else {bone: 1.0}
    fin(mb, pec_base, pec_tip, 3, 2, pec_weights, FIN_PEC)


# The rig

def build_armature(scene, name, members):
  """One armature for the whole shoal: per member a Root bone, at rest
  where the armature is with no turn, and under it the member's bones,
  scaled to it."""
  data = bpy.data.armatures.new(name)
  rig = link_object(scene, name, data, None)
  bpy.context.view_layer.objects.active = rig
  bpy.ops.object.mode_set(mode='EDIT')
  for res, sex in members:
    shape = shape_of(sex)
    scale = res.species.length * res.size
    prefix = res.name + ':'
    bones = {}

    def bone(bname, head, tail, parent, connect=False):
      eb = data.edit_bones.new(prefix + bname)
      eb.head = Vector(head) * scale
      eb.tail = Vector(tail) * scale
      eb.roll = 0.0
      eb.parent = bones[parent] if isinstance(parent, str) else parent
      eb.use_connect = connect
      bones[bname] = eb

    # Along +y with no roll, so the bone's rest frame is the armature's
    root = data.edit_bones.new(prefix + 'Root')
    root.head = Vector((0, 0, 0))
    root.tail = Vector((0, 0.3 * scale, 0))
    root.roll = 0.0
    xb = tail_base(shape)
    xs = (shape.snout_x,) + shape.joints + (xb,)
    for k, bname in enumerate(CHAIN):
      bone(bname, (xs[k], 0, 0), (xs[k + 1], 0, 0),
           CHAIN[k - 1] if k else root, connect=k > 0)
    bone('Caudal', (xb, 0, 0), (shape.tail_end, 0, 0), 'Tail', connect=True)
    _, _, half = scene_fish.profile(0.26, shape)
    px = scene_fish.body_x(0.26, shape)
    for side, bname in ((1, 'Pec.L'), (-1, 'Pec.R')):
      bone(bname, (px, side * half * 0.85, -0.015),
           (px - 0.09, side * (half * 0.85 + 0.03), -0.025), 'Head')
    top = scene_fish.profile(0.5, shape)[0]
    dx = scene_fish.body_x(0.5, shape)
    bone('Dorsal', (dx, 0, top), (dx - 0.15, 0, top + 0.08), 'Spine.0')
  bpy.ops.object.mode_set(mode='OBJECT')
  for pb in rig.pose.bones:
    pb.rotation_mode = 'QUATERNION' if pb.name.endswith(':Root') else 'XYZ'
  return rig


# Materials

def pattern(t):
  uv = t.add('ShaderNodeUVMap', {'uv_map': 'Pattern'})
  xyz = t.add('ShaderNodeSeparateXYZ')
  t.link(uv.outputs['UV'], xyz.inputs[0])
  return uv.outputs['UV'], xyz.outputs['X'], xyz.outputs['Y']


def plain_surface(t, out, color, glow=0.0, roughness=0.35, alpha=None):
  bsdf = t.add('ShaderNodeBsdfPrincipled', Roughness=roughness)
  t.link(color, bsdf.inputs['Base Color'])
  if glow:
    t.link(t.mix(glow, (0, 0, 0, 1), color), bsdf.inputs['Emission Color'])
    bsdf.inputs['Emission Strength'].default_value = 1.0
  if 'Specular IOR Level' in bsdf.inputs:
    bsdf.inputs['Specular IOR Level'].default_value = 0.6
  if alpha is not None:
    t.link(alpha, bsdf.inputs['Alpha'])
  t.link(bsdf.outputs[0], out.inputs['Surface'])
  return bsdf


def female_body_material():
  mat, t, out = new_material('GuppyFemale')
  uv, x, z = pattern(t)
  # Olive along the back, silver on the belly
  back = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
               Value=z, From_Min=-0.05, From_Max=0.06, To_Min=0.0,
               To_Max=1.0).outputs[0]
  color = t.mix(back, (0.66, 0.66, 0.62, 1.0), (0.28, 0.27, 0.16, 1.0))
  # Faint scale netting, coarse enough for the frame accumulation
  net = t.add('ShaderNodeTexVoronoi', {'feature': 'DISTANCE_TO_EDGE'},
              Vector=uv, Scale=38.0)
  edge = t.add('ShaderNodeMapRange', Value=net.outputs['Distance'],
               From_Min=0.0, From_Max=0.08, To_Min=0.25,
               To_Max=0.0).outputs[0]
  color = t.mix(edge, color, (0.18, 0.18, 0.12, 1.0))
  # The gravid spot, dark above the vent
  spot = t.math('MULTIPLY', band(t, x, z, -0.06, 0.0, 0.035, 0.03),
                band(t, z, x, -0.055, 0.0, 0.03, 0.025))
  color = t.mix(t.math('MULTIPLY', spot, 0.8), color,
                (0.05, 0.04, 0.03, 1.0))
  plain_surface(t, out, color, glow=0.04)
  return mat


def male_body_material():
  mat, t, out = new_material('GuppyMale')
  uv, x, z = pattern(t)
  back = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
               Value=z, From_Min=-0.04, From_Max=0.05, To_Min=0.0,
               To_Max=1.0).outputs[0]
  color = t.mix(back, (0.62, 0.64, 0.62, 1.0), (0.26, 0.28, 0.22, 1.0))
  # Flecks of color over the rear half: blue-green, orange and black
  # patches from a coarse noise, sharpened
  noise = t.add('ShaderNodeTexNoise', Vector=uv, Scale=14.0, Detail=1.0)
  rear = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
               Value=x, From_Min=0.12, From_Max=-0.02, To_Min=0.0,
               To_Max=1.0).outputs[0]
  flecks = t.ramp(noise.outputs['Fac'],
                  [(0.0, (0.02, 0.02, 0.02)), (0.36, (0.02, 0.02, 0.02)),
                   (0.40, (0.05, 0.45, 0.50)), (0.52, (0.05, 0.45, 0.50)),
                   (0.56, (0.90, 0.38, 0.06)), (0.66, (0.90, 0.38, 0.06)),
                   (0.70, (0.62, 0.64, 0.62)), (1.0, (0.62, 0.64, 0.62))])
  amount = t.math('MULTIPLY', rear, 0.85)
  color = t.mix(amount, color, flecks)
  # A shimmer that shifts as the fish turns, blue facing, green grazing
  facing = t.add('ShaderNodeLayerWeight', Blend=0.45).outputs['Facing']
  sheen = t.ramp(facing, [(0.0, (0.03, 0.08, 0.16)),
                          (1.0, (0.06, 0.14, 0.06))])
  bsdf = plain_surface(t, out, color, roughness=0.3)
  glow = t.mix(t.math('MULTIPLY', rear, 0.12), (0, 0, 0, 1), flecks)
  t.link(t.mix(1.0, glow, sheen, blend='ADD'), bsdf.inputs['Emission Color'])
  bsdf.inputs['Emission Strength'].default_value = 1.0
  return mat


def fin_rays(t):
  """The fin's (s, r) from its UVMap, and its faint rays."""
  uv = t.add('ShaderNodeUVMap', {'uv_map': 'UVMap'})
  sr = t.add('ShaderNodeSeparateXYZ')
  t.link(uv.outputs['UV'], sr.inputs[0])
  rays = t.math('MULTIPLY', t.math('ADD', t.math(
    'SINE', t.math('MULTIPLY', sr.outputs['X'], 2 * math.pi * 9)), 1.0), 0.5)
  return uv.outputs['UV'], sr.outputs['X'], sr.outputs['Y'], rays


def edge_fade(t, s, r):
  """1 inside the fin, fading out along its outer edge and side rays."""
  fade = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
               Value=r, From_Min=0.88, From_Max=1.0, To_Min=1.0,
               To_Max=0.0).outputs[0]
  side = t.math('ABSOLUTE', t.math('SUBTRACT', s, 0.5))
  return t.math('MULTIPLY', fade, t.add(
    'ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'}, Value=side,
    From_Min=0.44, From_Max=0.5, To_Min=1.0, To_Max=0.0).outputs[0])


def opaque_fin(name):
  mat, t, out = new_material(name)
  mat.surface_render_method = 'DITHERED'
  mat.use_backface_culling = False
  return mat, t, out


def female_fin_material():
  """Faintly tinted fins, mostly the water's color behind them."""
  mat, t, out = opaque_fin('GuppyFemaleFin')
  _, s, r, rays = fin_rays(t)
  tint = t.mix(t.math('MULTIPLY', rays, 0.3), (0.52, 0.50, 0.40, 1.0),
               (0.36, 0.35, 0.28, 1.0))
  color = t.mix(0.55, WATER_TINT, tint)
  plain_surface(t, out, color, roughness=0.4, alpha=edge_fade(t, s, r))
  return mat


def male_fin_material(index):
  """A male's fan and flag in his colors (MALE_COLORS[index]), spotted."""
  base, middle, edge, spot = MALE_COLORS[index]
  mat, t, out = opaque_fin('GuppyMaleFin.%d' % index)
  uv, s, r, rays = fin_rays(t)
  color = t.ramp(r, [(0.0, base), (0.45, middle), (1.0, edge)])
  color = t.mix(t.math('MULTIPLY', rays, 0.18), color,
                (0.05, 0.04, 0.04, 1.0))
  # Spots, coarse, scattered by a noise of the fin's own coordinates
  noise = t.add('ShaderNodeTexNoise', Vector=uv, Scale=7.0 + 2.0 * index,
                Detail=0.0)
  dots = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
               Value=noise.outputs['Fac'], From_Min=0.62, From_Max=0.68,
               To_Min=0.0, To_Max=0.85).outputs[0]
  color = t.mix(dots, color, spot + (1.0,))
  # A little of the water shows through near the base
  color = t.mix(t.add('ShaderNodeMapRange', Value=r, From_Min=0.0,
                      From_Max=0.25, To_Min=0.3, To_Max=0.0).outputs[0],
                color, WATER_TINT)
  plain_surface(t, out, color, glow=0.25, roughness=0.4,
                alpha=edge_fade(t, s, r))
  return mat


def pec_material():
  mat, t, out = new_material('GuppyPectoral', blended=True)
  _, s, r, _ = fin_rays(t)
  bsdf = t.add('ShaderNodeBsdfPrincipled', Roughness=0.4)
  bsdf.inputs['Base Color'].default_value = (0.70, 0.72, 0.72, 1.0)
  fade = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
               Value=r, From_Min=0.5, From_Max=1.0, To_Min=0.25,
               To_Max=0.0).outputs[0]
  t.link(fade, bsdf.inputs['Alpha'])
  t.link(bsdf.outputs[0], out.inputs['Surface'])
  return mat


# Building

def build(scene):
  body_mats = [female_body_material(), male_body_material(),
               scene_fish.eye_material('GuppyEye', GUPPY_EYE)]
  fin_mats = ([female_fin_material(), pec_material()]
              + [male_fin_material(i) for i in range(len(MALE_COLORS))])
  build_shoal(scene, sim_guppy.SHOAL, sim_guppy.residents(), body_mats,
              fin_mats)


def build_shoal(scene, name, members, body_mats, fin_mats):
  """The shoal as three objects: <shoal>.Rig, the armature, and <shoal>
  and <shoal>.Fins, every member's body and fins in one mesh each,
  skinned to it."""
  rig = build_armature(scene, name + '.Rig', members)
  body, fins = MeshBuilder(1.0), MeshBuilder(1.0)
  males = 0
  for res, sex in members:
    shape = shape_of(sex)
    male = sex == sim_guppy.MALE
    for mb in (body, fins):
      mb.scale = res.species.length * res.size
      mb.prefix = res.name + ':'
    scene_fish.add_body(body, rings=16, sides=12, shape=shape,
                        mat_index=BODY_MALE if male else BODY_FEMALE)
    for side in (1, -1):
      scene_fish.add_eye(body, side, EYE, segments=10, rings=6, shape=shape,
                         u=0.11, r=0.05, height=0.62)
    mat = FIN_MALE + males % len(MALE_COLORS) if male else FIN_FEMALE
    add_fins(fins, shape, sex, mat)
    males += male
  meshes = (body.finish(name, body_mats, scene, rig),
            fins.finish(name + '.Fins', fin_mats, scene, rig))
  # Small fish cast no shadows either (tools/species/angelfish.py)
  for obj in meshes:
    obj.visible_shadow = False
  return rig
