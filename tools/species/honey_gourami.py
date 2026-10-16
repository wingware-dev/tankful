"""The honey gouramis for tools/build_scene.py: rigged models built from
profiles.

Runs inside UPBGE's Blender.  Each gourami
(tankful.sim.species.honey_gourami.residents) gets:

- <name>.Rig: an armature with the bones
  tankful.sim.species.honey_gourami poses, the fin bones all pointing
  straight back at rest, which the game moves and turns as the fish swims
  (tankful.game.fishes);
- <name>: the body, lofted from side and top profiles, with the eyes,
  skinned to the spine;
- <name>.Fins: the dorsal, anal, caudal and pectoral fins as thin sheets,
  and the two feelers as long threads, skinned to the spine and to their
  own bones.

Built in the fish's space as tools/scene_fish.py says.  The male
(honey_gourami.MALES) is honey-gold with a dark throat and belly and a
gold-edged dorsal fin; the female is a paler buff with a brown stripe
along her side.
"""

import math

import bpy
from mathutils import Vector

import scene_env
import scene_fish
from scene_env import caustic_node, link_object, new_material
from scene_fish import (CHAIN, WATER_TINT, MeshBuilder, Shape, band, bezier,
                        fin, lerp, spine_weights)
from tankful.sim.species import honey_gourami as sim_gourami

# Side profile of a honey gourami's body, snout (u=0) to the tail's base
# (u=1): (u, top, bottom, half-width), in lengths.  An oval, flattened
# from side to side, with a small pointed snout
GOURAMI_BODY = (
  (0.00, 0.014, -0.006, 0.010),
  (0.05, 0.044, -0.036, 0.026),
  (0.12, 0.086, -0.076, 0.041),
  (0.22, 0.128, -0.118, 0.051),
  (0.34, 0.152, -0.146, 0.054),
  (0.48, 0.150, -0.150, 0.049),
  (0.62, 0.126, -0.130, 0.040),
  (0.76, 0.090, -0.094, 0.030),
  (0.88, 0.060, -0.062, 0.020),
  (1.00, 0.046, -0.048, 0.014),
)
SNOUT_X = 0.5
BODY_LEN = 0.74

# The spine's joints along x, head to tail (tankful.sim.swim.SPINE)
JOINTS = (0.24, 0.08, -0.08, -0.22)
TAIL_END = -0.50
GOURAMI = Shape(GOURAMI_BODY, SNOUT_X, BODY_LEN, JOINTS, TAIL_END, 0.22)

# Where the feelers leave the chest, along the body
FEELER_U = 0.22
# A feeler's length, in lengths
FEELER_LEN = 0.78
# Where the pectorals sit along the body
PEC_U = 0.25


def body_x(u):
  return scene_fish.body_x(u, GOURAMI)


def profile(u):
  return scene_fish.profile(u, GOURAMI)


def feeler_root(side):
  _, bot, half = profile(FEELER_U)
  return (body_x(FEELER_U), side * half * 0.35, bot + 0.008)


# The fins

def fin_weights(bone, share=0.75):
  """Spine weights at the base, giving way to bone toward the tip."""
  def weights(p, s, r):
    w = {b: v * (1 - share * r)
         for b, v in spine_weights(p[0], JOINTS).items()}
    w[bone] = w.get(bone, 0.0) + share * r
    return w
  return weights


def add_fins(mb):
  # Dorsal: set back, from mid-back almost to the tail, low in front and
  # rising to a rounded rear
  def dorsal_base(s):
    u = 0.40 + 0.56 * s
    return (body_x(u), 0.0, profile(u)[0] - 0.01)

  def dorsal_tip(s):
    u = 0.40 + 0.56 * s
    top = profile(u)[0]
    lift = 0.03 + 0.09 * math.sin(math.pi * min(1.0, 0.25 + 0.85 * s))
    return (body_x(u) - 0.05 - 0.07 * s * s, 0.0, top + lift)
  fin(mb, dorsal_base, dorsal_tip, 14, 6, fin_weights('Dorsal'))

  # Anal: long, from just behind the feelers to the tail, deepening to a
  # pointed rear lobe
  def anal_base(s):
    u = 0.30 + 0.66 * s
    return (body_x(u), 0.0, profile(u)[1] + 0.01)

  def anal_tip(s):
    u = 0.30 + 0.66 * s
    bot = profile(u)[1]
    drop = 0.035 + 0.075 * s ** 1.4 * (1.0 - 0.5 * max(0.0, s - 0.85) / 0.15)
    return (body_x(u) - 0.05 - 0.08 * s * s, 0.0, bot - drop)
  fin(mb, anal_base, anal_tip, 16, 6, fin_weights('Anal'))

  # Caudal: a broad fan, its trailing edge a shallow notch
  base_x = body_x(1.0)

  def caudal_base(s):
    return (base_x + 0.005, 0.0, -0.04 + 0.08 * s)

  def caudal_tip(s):
    e = abs(2 * s - 1)
    return (TAIL_END + 0.025 * (1 - e) - 0.01 * e, 0.0,
            (2 * s - 1) * 0.14)

  fin(mb, caudal_base, caudal_tip, 12, 7,
      lambda p, s, r: spine_weights(p[0], JOINTS))

  # Pectorals: small clear rounded fans behind the gill cover
  for side, bone in ((1, 'Pec.L'), (-1, 'Pec.R')):
    top, bot, half = profile(PEC_U)
    x0 = body_x(PEC_U)

    def pec_base(s, x0=x0, side=side, half=half):
      return (x0, side * half * 0.85, -0.045 + 0.04 * s)

    def pec_tip(s, x0=x0, side=side, half=half):
      return (x0 - 0.08 - 0.03 * math.sin(math.pi * s),
              side * (half * 0.85 + 0.035), -0.065 + 0.055 * s)

    def pec_weights(p, s, r, bone=bone):
      return {'Head': 1 - r, bone: r} if r < 1 else {bone: 1.0}
    fin(mb, pec_base, pec_tip, 5, 4, pec_weights, mat_index=1)


def add_feelers(mb, mat_index):
  """The two feelers: threads from the chest, hanging FEELER_REST below
  straight back and curving a little further down, on their own bones
  but for the root."""
  rest = sim_gourami.FEELER_REST
  for side, bone in ((1, 'Feeler.L'), (-1, 'Feeler.R')):
    root = feeler_root(side)
    dx, dz = -math.cos(rest), -math.sin(rest)
    L = FEELER_LEN

    def thread(s, r, root=root, dx=dx, dz=dz, L=L):
      along = bezier((root, (root[0] + dx * L * 0.4, root[1],
                             root[2] + dz * L * 0.4),
                      (root[0] + dx * L * 0.75, root[1],
                       root[2] + dz * L * 0.85),
                      (root[0] + dx * L * 0.95, root[1],
                       root[2] + dz * L * 1.15)), r)
      w = 0.03 * (1 - r) ** 1.2 + 0.012
      return (along[0] + (s - 0.5) * w * 0.4, along[1],
              along[2] + (s - 0.5) * w)

    def feeler_weights(p, s, r, bone=bone):
      return {'Head': max(0.0, 1 - 8 * r), bone: min(1.0, 8 * r)}
    fin(mb, lambda s: thread(s, 0.0), lambda s: thread(s, 1.0), 1, 14,
        feeler_weights, mat_index=mat_index,
        curl=lambda s, r, thread=thread: tuple(
          a - b for a, b in zip(thread(s, r),
                                lerp(thread(s, 0.0), thread(s, 1.0), r))))


# The rig

def build_rig(scene, name, scale):
  data = bpy.data.armatures.new(name + '.Rig')
  rig = link_object(scene, name + '.Rig', data, None)
  bpy.context.view_layer.objects.active = rig
  bpy.ops.object.mode_set(mode='EDIT')
  bones = {}

  def bone(bname, head, length, parent=None, connect=False, tail=None):
    eb = data.edit_bones.new(bname)
    eb.head = Vector(head) * scale
    eb.tail = (Vector(tail) if tail is not None
               else Vector(head) - Vector((length, 0, 0))) * scale
    eb.roll = 0.0
    if parent is not None:
      eb.parent = bones[parent]
      eb.use_connect = connect
    bones[bname] = eb

  xs = (SNOUT_X,) + JOINTS + (TAIL_END + 0.1,)
  for k, bname in enumerate(CHAIN):
    bone(bname, (xs[k], 0, 0), None, CHAIN[k - 1] if k else None,
         connect=k > 0, tail=(xs[k + 1], 0, 0))
  # The fins' bones all point straight back from their roots, so each
  # one's x is the fish's left and z its back (the sim's pose says so)
  pec_x = body_x(PEC_U)
  _, _, half = profile(PEC_U)
  for side, bname in ((1, 'Pec.L'), (-1, 'Pec.R')):
    bone(bname, (pec_x, side * half * 0.85, -0.025), 0.08, 'Head')
  for side, bname in ((1, 'Feeler.L'), (-1, 'Feeler.R')):
    bone(bname, feeler_root(side), 0.2, 'Head')
  bone('Dorsal', (body_x(0.40), 0, profile(0.40)[0]), 0.3, 'Spine.0')
  bone('Anal', (body_x(0.30), 0, profile(0.30)[1]), 0.3, 'Spine.0')
  bpy.ops.object.mode_set(mode='OBJECT')
  for pb in rig.pose.bones:
    pb.rotation_mode = 'XYZ'
  return rig


# Materials

# Each sex's colors: the body along the back, the flank and the belly; the
# throat's shading (the male's dark breeding colors); the stripe along
# the side; the fins
MALE = {
  'back': (0.60, 0.30, 0.05), 'flank': (0.88, 0.48, 0.08),
  'belly': (0.92, 0.70, 0.30), 'throat': (0.03, 0.04, 0.07),
  'throat_amount': 0.9, 'stripe': 0.0, 'fin': (0.90, 0.52, 0.10),
  'edge': (1.0, 0.85, 0.25),
}
FEMALE = {
  'back': (0.48, 0.38, 0.24), 'flank': (0.70, 0.58, 0.40),
  'belly': (0.86, 0.82, 0.72), 'throat': (0.0, 0.0, 0.0),
  'throat_amount': 0.0, 'stripe': 0.8, 'fin': (0.72, 0.64, 0.50),
  'edge': (0.80, 0.72, 0.55),
}


def pattern(t):
  """The Pattern map's rest x and z, in lengths."""
  uv = t.add('ShaderNodeUVMap', {'uv_map': 'Pattern'})
  xyz = t.add('ShaderNodeSeparateXYZ')
  t.link(uv.outputs['UV'], xyz.inputs[0])
  return xyz.outputs['X'], xyz.outputs['Y']


def throat(t, x, z):
  """1 over the throat and the belly's front half, under a line running
  from below the eye back and down to the anal fin."""
  line = t.math('SUBTRACT', z, t.math('ADD', t.math('MULTIPLY', x, 0.22),
                                      -0.075))
  below = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
                Value=line, From_Min=0.0, From_Max=-0.03, To_Min=0.0,
                To_Max=1.0).outputs[0]
  front = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
                Value=x, From_Min=-0.16, From_Max=-0.04, To_Min=0.0,
                To_Max=1.0).outputs[0]
  return t.math('MULTIPLY', below, front)


def body_material(name, colors, caustic):
  mat, t, out = new_material(name)
  x, z = pattern(t)
  shade = t.add('ShaderNodeMapRange', Value=z, From_Min=-0.14, From_Max=0.15,
                To_Min=0.0, To_Max=1.0).outputs[0]
  color = t.ramp(shade, [(0.0, colors['belly']), (0.5, colors['flank']),
                         (1.0, colors['back'])])
  # Fine scales, coarse enough for the player's frame accumulation
  uv = t.add('ShaderNodeUVMap', {'uv_map': 'Pattern'})
  scales = t.add('ShaderNodeTexNoise', Vector=uv.outputs['UV'], Scale=70.0,
                 Detail=1.0)
  color = t.mix(t.math('MULTIPLY', scales.outputs['Fac'], 0.2), color,
                tuple(c * 0.7 for c in colors['flank']) + (1.0,))
  # The female's stripe: brown, from behind the eye to the tail's base
  if colors['stripe']:
    stripe = band(t, z, x, 0.005, 0.02, 0.026, 0.016)
    color = t.mix(t.math('MULTIPLY', stripe, colors['stripe']), color,
                  (0.30, 0.20, 0.10, 1.0))
  # The male's dark throat and belly
  if colors['throat_amount']:
    color = t.mix(t.math('MULTIPLY', throat(t, x, z),
                         colors['throat_amount']),
                  color, colors['throat'] + (1.0,))
  bsdf = scene_env.lit_surface(t, out, color, caustic_node(t, caustic),
                               roughness=0.35, strength=0.9)
  for key, value in (('Metallic', 0.2), ('Specular IOR Level', 0.65)):
    if key in bsdf.inputs:
      bsdf.inputs[key].default_value = value
  return mat


# The gourami's eye, pupil (0) to the back (1): black, then a gold ring,
# then the body's color
GOURAMI_EYE = ((0.0, (0.004, 0.004, 0.004)), (0.2, (0.01, 0.008, 0.006)),
               (0.25, (0.55, 0.40, 0.12)), (0.36, (0.45, 0.30, 0.10)),
               (1.0, (0.40, 0.30, 0.15)))


def fin_material(name, colors, alpha, opaque=False, dark_front=0.0):
  """Fins, rays faintly darker, the outer edge in colors['edge'], and for
  the male's anal fin its front dark as his belly (dark_front).  Drawn
  as the angelfish's fins are (tools/species/angelfish.py), opaque and
  dithered or, for the nearly clear pectorals, blended."""
  mat, t, out = new_material(name, blended=not opaque)
  if opaque:
    mat.surface_render_method = 'DITHERED'
    mat.use_backface_culling = False
  else:
    mat.use_transparency_overlap = True
  x, z = pattern(t)
  uv = t.add('ShaderNodeUVMap', {'uv_map': 'UVMap'})
  sr = t.add('ShaderNodeSeparateXYZ')
  t.link(uv.outputs['UV'], sr.inputs[0])
  rays = t.math('MULTIPLY', t.math('ADD', t.math(
    'SINE', t.math('MULTIPLY', sr.outputs['X'], 2 * math.pi * 10)), 1.0), 0.5)
  base = colors['fin'] + (1.0,)
  color = t.mix(t.math('MULTIPLY', rays, 0.2), base,
                tuple(c * 0.6 for c in colors['fin']) + (1.0,))
  edge = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
               Value=sr.outputs['Y'], From_Min=0.7, From_Max=0.9,
               To_Min=0.0, To_Max=1.0).outputs[0]
  color = t.mix(edge, color, colors['edge'] + (1.0,))
  if dark_front:
    front = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
                  Value=x, From_Min=-0.12, From_Max=0.0, To_Min=0.0,
                  To_Max=dark_front).outputs[0]
    # the anal fin's only, below the body
    below = t.add('ShaderNodeMapRange', Value=z, From_Min=0.0,
                  From_Max=-0.05, To_Min=0.0, To_Max=1.0).outputs[0]
    front = t.math('MULTIPLY', front, below)
    color = t.mix(front, color, colors['throat'] + (1.0,))
  a = t.math('ADD', alpha, t.math('MULTIPLY', rays, 0.1), clamp=True)
  if opaque:
    color = t.mix(a, WATER_TINT, color)
  bsdf = scene_env.lit_surface(t, out, color, 0.0, roughness=0.35,
                               strength=0.7)
  fade = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
               Value=sr.outputs['Y'], From_Min=0.93, From_Max=1.0,
               To_Min=1.0, To_Max=0.0).outputs[0]
  t.link(fade if opaque else t.math('MULTIPLY', a, fade),
         bsdf.inputs['Alpha'])
  return mat


def feeler_material(name, colors):
  """The feelers: the fin color, paling to the tip (the thread's UV V)."""
  mat, t, out = new_material(name)
  uv = t.add('ShaderNodeUVMap', {'uv_map': 'UVMap'})
  sr = t.add('ShaderNodeSeparateXYZ')
  t.link(uv.outputs['UV'], sr.inputs[0])
  color = t.ramp(sr.outputs['Y'], [(0.0, colors['fin']),
                                   (0.7, colors['fin']),
                                   (1.0, colors['edge'])])
  scene_env.lit_surface(t, out, color, 0.0, roughness=0.4, strength=0.8)
  mat.use_backface_culling = False
  return mat


# Building

def materials(prefix, colors, caustic):
  male = colors is MALE
  return {
    'body': body_material(prefix, colors, caustic),
    'eye': scene_fish.eye_material(prefix + 'Eye', GOURAMI_EYE),
    'fin': fin_material(prefix + 'Fin', colors, 0.55, opaque=True,
                        dark_front=0.85 if male else 0.0),
    'pec': fin_material(prefix + 'Pectoral', colors, 0.05),
    'feeler': feeler_material(prefix + 'Feeler', colors),
  }


def build(scene, caustic=None):
  if caustic is None:
    caustic = bpy.data.node_groups[scene_env.FISH_CAUSTIC]
  mats = {'male': materials('HoneyGouramiMale', MALE, caustic),
          'female': materials('HoneyGouramiFemale', FEMALE, caustic)}
  for res in sim_gourami.residents():
    build_one(scene, res, mats['male' if res.name in sim_gourami.MALES
                               else 'female'])


def build_one(scene, res, mats):
  scale = res.species.length * res.size
  rig = build_rig(scene, res.name, scale)
  x, y, z, heading = res.start
  rig.location = (x, y, z)
  rig.rotation_euler = (0.0, 0.0, heading)

  mb = MeshBuilder(scale)
  scene_fish.add_body(mb, GOURAMI)
  scene_fish.add_eye(mb, 1, 1, GOURAMI, u=0.12, r=0.04, height=0.62)
  scene_fish.add_eye(mb, -1, 1, GOURAMI, u=0.12, r=0.04, height=0.62)
  mb.finish(res.name, [mats['body'], mats['eye']], scene, rig)

  fins = MeshBuilder(scale)
  add_fins(fins)
  add_feelers(fins, 2)
  fins.finish(res.name + '.Fins', [mats['fin'], mats['pec'],
                                   mats['feeler']], scene, rig)
  # Fish cast no shadows: moving casters cost too much (docs/harness.md)
  for obj in rig.children:
    obj.visible_shadow = False
  return rig
