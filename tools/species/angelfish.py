"""The angelfish for tools/build_scene.py: rigged models built from
profiles.

Runs inside UPBGE's Blender.  Each angelfish
(tankful.sim.species.angelfish.residents) gets:

- <name>.Rig: an armature with the bones tankful.sim.species.angelfish
  poses, which the game moves and turns as the fish swims
  (tankful.game.fishes);
- <name>: the body, lofted from side and top profiles, with the eyes,
  skinned to the spine;
- <name>.Fins: the dorsal, anal, caudal, pectoral and pelvic fins as thin
  sheets, skinned to the spine and to their own bones.

Built in the fish's space as tools/scene_fish.py says.  Both meshes
carry the Pattern UV map, so the bars painted from it line up across
body and fins and stay put on the skin as the body bends.
"""

import math

import bpy
from mathutils import Vector

import scene_env
import scene_fish
from scene_env import caustic_node, link_object, new_material
from scene_fish import (CHAIN, WATER_TINT, MeshBuilder, Shape, band, bezier,
                        fin, lerp, spine_weights, swept)
from tankful.sim.species import angelfish as sim_angelfish

# Side profile of an angelfish's body, snout (u=0) to the tail's base
# (u=1): (u, top, bottom, half-width), in lengths.  A disc: a steep
# forehead, a deep body, and a short, narrow tail base
ANGEL_BODY = (
  (0.00, 0.010, -0.014, 0.008),
  (0.04, 0.038, -0.036, 0.022),
  (0.10, 0.088, -0.078, 0.038),
  (0.18, 0.158, -0.138, 0.050),
  (0.28, 0.226, -0.198, 0.056),
  (0.40, 0.262, -0.242, 0.054),
  (0.52, 0.254, -0.250, 0.048),
  (0.64, 0.204, -0.214, 0.039),
  (0.76, 0.128, -0.138, 0.029),
  (0.88, 0.062, -0.068, 0.019),
  (1.00, 0.040, -0.044, 0.013),
)
SNOUT_X = 0.5
BODY_LEN = 0.66

# The spine's joints along x, head to tail (tankful.sim.swim.SPINE)
JOINTS = (0.25, 0.10, -0.03, -0.16)
TAIL_END = -0.47
ANGEL = Shape(ANGEL_BODY, SNOUT_X, BODY_LEN, JOINTS, TAIL_END, 0.22)


def body_x(u):
  return scene_fish.body_x(u, ANGEL)


def profile(u):
  return scene_fish.profile(u, ANGEL)


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
  # Dorsal: from the top of the disc, the leading edge sweeps steeply up
  # and back to a long point; the trailing edge curves down to the tail
  def dorsal_base(s):
    u = 0.30 + 0.68 * s
    return (body_x(u), 0.0, profile(u)[0] - 0.012)

  def dorsal_tip(s):
    return swept((0.06, 0, 0.44), (-0.24, 0, 0.75), (-0.10, 0, 0.40),
                 (-0.15, 0, 0.06), s)
  fin(mb, dorsal_base, dorsal_tip, 16, 8, fin_weights('Dorsal'))

  # Anal: the same below, a little longer
  def anal_base(s):
    u = 0.40 + 0.58 * s
    return (body_x(u), 0.0, profile(u)[1] + 0.012)

  def anal_tip(s):
    return swept((0.02, 0, -0.46), (-0.25, 0, -0.80), (-0.10, 0, -0.42),
                 (-0.15, 0, -0.065), s)
  fin(mb, anal_base, anal_tip, 16, 8, fin_weights('Anal'))

  # Caudal: a fan from the tail's base, its outer rays drawn out into
  # filaments
  def caudal_base(s):
    return (-0.145, 0.0, -0.036 + 0.072 * s)

  def caudal_tip(s):
    e = abs(2 * s - 1)
    return (TAIL_END + 0.06 - 0.09 * e ** 6 - 0.012 * (1 - e),
            0.0, (2 * s - 1) * (0.25 + 0.05 * e ** 4))

  fin(mb, caudal_base, caudal_tip, 12, 8,
      lambda p, s, r: spine_weights(p[0], JOINTS))

  # Pectorals: small clear fans behind the gill cover, angled out
  for side, bone in ((1, 'Pec.L'), (-1, 'Pec.R')):
    top, bot, half = profile(0.27)
    x0 = body_x(0.27)

    def pec_base(s, x0=x0, side=side, half=half):
      return (x0, side * half * 0.85, -0.06 + 0.055 * s)

    def pec_tip(s, x0=x0, side=side, half=half):
      return (x0 - 0.10 - 0.035 * math.sin(math.pi * s),
              side * (half * 0.85 + 0.045), -0.085 + 0.07 * s)

    def pec_weights(p, s, r, bone=bone):
      return {'Head': 1 - r, bone: r} if r < 1 else {bone: 1.0}
    fin(mb, pec_base, pec_tip, 5, 4, pec_weights, mat_index=1)

  # Pelvic threads: long, narrow, hanging down and back from the chest
  for side, bone in ((1, 'Pelvic.L'), (-1, 'Pelvic.R')):
    x0 = body_x(0.30)
    _, bot, _ = profile(0.30)

    def thread(s, r, x0=x0, bot=bot, side=side):
      along = bezier(((x0, 0, bot + 0.01), (x0 - 0.05, 0, bot - 0.25),
                      (x0 - 0.20, 0, -0.66), (x0 - 0.30, 0, -0.74)), r)
      w = 0.036 * (1 - r) ** 1.5 + 0.006
      return (along[0] + (s - 0.5) * w, side * 0.012, along[2])

    def pelvic_weights(p, s, r, bone=bone):
      return {'Head': max(0.0, 1 - 4 * r), bone: min(1.0, 4 * r)}
    fin(mb, lambda s: thread(s, 0.0), lambda s: thread(s, 1.0), 2, 12,
        pelvic_weights,
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

  def bone(bname, head, tail, parent=None, connect=False):
    eb = data.edit_bones.new(bname)
    eb.head = Vector(head) * scale
    eb.tail = Vector(tail) * scale
    eb.roll = 0.0
    if parent is not None:
      eb.parent = bones[parent]
      eb.use_connect = connect
    bones[bname] = eb

  xs = (SNOUT_X,) + JOINTS + (TAIL_END + 0.1,)
  for k, bname in enumerate(CHAIN):
    bone(bname, (xs[k], 0, 0), (xs[k + 1], 0, 0),
         CHAIN[k - 1] if k else None, connect=k > 0)
  pec_x = body_x(0.27)
  _, _, half = profile(0.27)
  for side, bname in ((1, 'Pec.L'), (-1, 'Pec.R')):
    bone(bname, (pec_x, side * half * 0.85, -0.035),
         (pec_x - 0.11, side * (half * 0.85 + 0.03), -0.05), 'Head')
  pel_x = body_x(0.30)
  _, bot, _ = profile(0.30)
  for side, bname in ((1, 'Pelvic.L'), (-1, 'Pelvic.R')):
    bone(bname, (pel_x, side * 0.012, bot + 0.01),
         (pel_x - 0.25, side * 0.012, -0.70), 'Head')
  bone('Dorsal', (0.0, 0, 0.24), (-0.30, 0, 0.72), 'Spine.0')
  bone('Anal', (0.0, 0, -0.24), (-0.30, 0, -0.76), 'Spine.0')
  bpy.ops.object.mode_set(mode='OBJECT')
  for pb in rig.pose.bones:
    pb.rotation_mode = 'XYZ'
  return rig


# Materials

def angel_bars(t):
  """The wild angelfish's bars, from the Pattern map: (x, z, darkness)."""
  uv = t.add('ShaderNodeUVMap', {'uv_map': 'Pattern'})
  xyz = t.add('ShaderNodeSeparateXYZ')
  t.link(uv.outputs['UV'], xyz.inputs[0])
  x, z = xyz.outputs['X'], xyz.outputs['Y']
  dark = None
  # Through the eye; from the top of the disc down through the middle;
  # from the dorsal fin's rear down to the anal fin's; a faint one across
  # the tail's base
  for center, slant, half, soft, weight in (
      (0.405, 0.05, 0.022, 0.012, 0.9),
      (0.165, -0.10, 0.034, 0.016, 0.95),
      (-0.075, -0.14, 0.03, 0.016, 0.9),
      (-0.165, 0.0, 0.008, 0.012, 0.45)):
    b = t.math('MULTIPLY', band(t, x, z, center, slant, half, soft), weight)
    dark = b if dark is None else t.math('MAXIMUM', dark, b)
  return x, z, dark


def body_material(caustic):
  mat, t, out = new_material('Angelfish')
  x, z, dark = angel_bars(t)
  # Silver, warmer along the back, pale on the belly
  back = t.add('ShaderNodeMapRange', Value=z, From_Min=-0.2, From_Max=0.25,
               To_Min=0.0, To_Max=1.0).outputs[0]
  color = t.ramp(back, [(0.0, (0.80, 0.80, 0.78)), (0.55, (0.66, 0.66, 0.63)),
                        (1.0, (0.52, 0.47, 0.36))])
  # A soft speckle of scales, coarse enough for the player's frame
  # accumulation (docs/harness.md)
  uv = t.add('ShaderNodeUVMap', {'uv_map': 'Pattern'})
  scales = t.add('ShaderNodeTexNoise', Vector=uv.outputs['UV'], Scale=60.0,
                 Detail=1.0)
  color = t.mix(t.math('MULTIPLY', scales.outputs['Fac'], 0.25), color,
                (0.45, 0.45, 0.44, 1.0))
  # The gill cover's edge, a faint arc behind the eye
  gill = band(t, x, t.math('MULTIPLY', z, z), 0.335, -1.6, 0.004, 0.006)
  near = t.add('ShaderNodeMapRange', Value=t.math('ABSOLUTE', z),
               From_Min=0.12, From_Max=0.17, To_Min=1.0, To_Max=0.0)
  color = t.mix(t.math('MULTIPLY', t.math('MULTIPLY', gill,
                                          near.outputs[0]), 0.3),
                color, (0.25, 0.25, 0.25, 1.0))
  color = t.mix(dark, color, (0.025, 0.025, 0.03, 1.0))
  bsdf = scene_env.lit_surface(t, out, color, caustic_node(t, caustic),
                               roughness=0.3, strength=0.9)
  # Iridescence: a thin film over the silver catches violet and green
  # as the fish turns, fading on the dark bars
  for name, value in (('Metallic', 0.35), ('Specular IOR Level', 0.75),
                      ('Thin Film IOR', 1.45)):
    if name in bsdf.inputs:
      bsdf.inputs[name].default_value = value
  if 'Thin Film Thickness' in bsdf.inputs:
    film = t.math('MULTIPLY', t.math('SUBTRACT', 1.0, dark), 380.0)
    t.link(film, bsdf.inputs['Thin Film Thickness'])
  # The player's EEVEE shows little of the film, so a sheen that shifts
  # from blue-violet facing the viewer to green-gold at grazing angles
  # glows faintly on the silver: it changes as the fish turns, at no
  # per-frame cost
  facing = t.add('ShaderNodeLayerWeight', Blend=0.4).outputs['Facing']
  sheen = t.ramp(facing, [(0.0, (0.045, 0.04, 0.085)),
                          (0.5, (0.03, 0.075, 0.08)),
                          (1.0, (0.11, 0.095, 0.035))])
  sheen = t.mix(t.math('SUBTRACT', 1.0, dark), (0, 0, 0, 1), sheen)
  emission = bsdf.inputs['Emission Color']
  glow = emission.links[0].from_socket
  t.link(t.mix(1.0, glow, sheen, blend='ADD'), emission)
  return mat


# The angelfish's eye, pupil (0) to the back (1): black, then a red iris
# ringed with orange, then silver
ANGEL_EYE = ((0.0, (0.005, 0.005, 0.005)), (0.17, (0.01, 0.008, 0.008)),
             (0.21, (0.45, 0.06, 0.03)), (0.30, (0.72, 0.22, 0.06)),
             (0.36, (0.55, 0.52, 0.45)), (1.0, (0.40, 0.40, 0.38)))


def fin_material(name, alpha, clear, ray_alpha=0.12, opaque=False):
  """Fins, the bars running on into them, rays faintly darker.

  Fins have no caustics: the moving pattern on a moving sheet cost about
  3 fps for the two angelfish and showed only as shimmer.  opaque fins
  are drawn solid, with their color blended toward WATER_TINT where they
  would be clear, and only their outer edge faded out (dithered): the
  player's frame accumulation (TAA) has no motion for blended surfaces,
  so a moving blended fin with dark bars breaks up into blocks and
  speckle (docs/harness.md).  Blended fins suit only nearly clear ones,
  such as the pectorals, with no detail to break up.
  """
  mat, t, out = new_material(name, blended=not opaque)
  if opaque:
    mat.surface_render_method = 'DITHERED'
    mat.use_backface_culling = False
  else:
    mat.use_transparency_overlap = True
  x, z, dark = angel_bars(t)
  uv = t.add('ShaderNodeUVMap', {'uv_map': 'UVMap'})
  sr = t.add('ShaderNodeSeparateXYZ')
  t.link(uv.outputs['UV'], sr.inputs[0])
  rays = t.math('MULTIPLY', t.math('ADD', t.math(
    'SINE', t.math('MULTIPLY', sr.outputs['X'], 2 * math.pi * 11)), 1.0), 0.5)
  color = t.mix(t.math('MULTIPLY', rays, 0.25), (0.78, 0.80, 0.80, 1.0),
                (0.45, 0.47, 0.48, 1.0))
  # A faint dark margin along the outer edge
  rim = t.add('ShaderNodeMapRange', Value=sr.outputs['Y'], From_Min=0.82,
              From_Max=0.93, To_Min=0.0, To_Max=0.45 * clear).outputs[0]
  dark = t.math('MAXIMUM', t.math('MULTIPLY', dark, clear), rim)
  color = t.mix(dark, color, (0.02, 0.02, 0.025, 1.0))
  a = t.math('ADD', alpha, t.math('ADD', t.math('MULTIPLY', dark, 0.5),
                                  t.math('MULTIPLY', rays, ray_alpha)),
             clamp=True)
  if opaque:
    color = t.mix(a, WATER_TINT, color)
  bsdf = scene_env.lit_surface(t, out, color, 0.0, roughness=0.35,
                               strength=0.7)
  # Fade out at the very edge: the player's frame accumulation leaves a
  # hard edge on a moving sheet stair-stepped
  fade = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
               Value=sr.outputs['Y'], From_Min=0.93, From_Max=1.0,
               To_Min=1.0, To_Max=0.0).outputs[0]
  # and along the first and last rays
  side = t.math('ABSOLUTE', t.math('SUBTRACT', sr.outputs['X'], 0.5))
  fade = t.math('MULTIPLY', fade, t.add(
    'ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'}, Value=side,
    From_Min=0.45, From_Max=0.5, To_Min=1.0, To_Max=0.0).outputs[0])
  t.link(fade if opaque else t.math('MULTIPLY', a, fade),
         bsdf.inputs['Alpha'])
  return mat


# Building

def build(scene, caustic=None):
  if caustic is None:
    caustic = bpy.data.node_groups[scene_env.FISH_CAUSTIC]
  mats = {
    'body': body_material(caustic),
    'eye': scene_fish.eye_material('AngelfishEye', ANGEL_EYE),
    'fin': fin_material('AngelfishFin', 0.62, 1.0, opaque=True),
    'pec': fin_material('AngelfishPectoral', 0.04, 0.0, 0.05),
  }
  for res in sim_angelfish.residents():
    build_one(scene, res, mats)


def build_one(scene, res, mats):
  scale = res.species.length * res.size
  rig = build_rig(scene, res.name, scale)
  x, y, z, heading = res.start
  rig.location = (x, y, z)
  rig.rotation_euler = (0.0, 0.0, heading)

  mb = MeshBuilder(scale)
  scene_fish.add_body(mb, ANGEL)
  scene_fish.add_eye(mb, 1, 1, ANGEL)
  scene_fish.add_eye(mb, -1, 1, ANGEL)
  mb.finish(res.name, [mats['body'], mats['eye']], scene, rig)

  fins = MeshBuilder(scale)
  add_fins(fins)
  fins.finish(res.name + '.Fins', [mats['fin'], mats['pec']], scene, rig)
  # Fish cast no shadows: moving casters cost the player 3-4 fps each for
  # body and fins (docs/harness.md), too much for a tank of fish
  for obj in rig.children:
    obj.visible_shadow = False
  return rig
