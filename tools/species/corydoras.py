"""The corydoras for tools/build_scene.py: a group of panda corydoras as
one object, with their sand puffs.

Runs inside UPBGE's Blender.  The group
(tankful.sim.species.corydoras.residents) is built as a school is
(tools/species/neon_tetra.py), since five fish with rigs of their own
would cost about 2 fps (docs/harness.md, "Frame budget"):

- Corydoras.Rig: one armature for all of them, each member's bones
  prefixed with its name ("Corydoras.3:Tail"): a Root bone, which the
  game places and turns as the fish moves (tankful.game.fishes), and
  under it the bones tankful.sim.species.corydoras poses;
- Corydoras: every member's body, eyes and barbels;
- Corydoras.Fins: their fins;
- Corydoras.Puffs: each member's sand puffs, one dome of grains per
  Puff bone, which the bone scales from nothing as the puff rises,
  spreads and settles (tankful.sim.species.corydoras.puff_scale).

A panda corydoras: short and deep, a rounded back over a flat belly, a
blunt snout with barbels under it; ivory with a black mask over the
eyes, a black dorsal fin and a black spot on the tail's base.  Plain
materials, no caustics, and no shadows.

Each member is built in its own space as tools/scene_fish.py: +x
forward, +y its left, +z its back, origin halfway along it, in units of
its length, scaled to its size.  The belly is flat at z =
-tankful.sim.species.corydoras.BELLY.
"""

import math
import random

import bpy
from mathutils import Vector

import scene_fish
from scene_env import link_object, new_material
from scene_fish import CHAIN, MeshBuilder, Shape, band, fin, spine_weights
from tankful.sim.species import corydoras as sim_cory

B = -sim_cory.BELLY

# Side and top profile, snout (u=0) to the tail's base (u=1): (u, top,
# bottom, half-width), in lengths.  The back rises steeply from a blunt
# snout to the dorsal fin; the belly is flat back to the anal fin
CORY_BODY = (
  (0.00, -0.040, -0.100, 0.030),
  (0.05, 0.020, B + 0.005, 0.070),
  (0.12, 0.090, B, 0.100),
  (0.22, 0.150, B, 0.115),
  (0.32, 0.185, B, 0.115),
  (0.45, 0.165, B + 0.004, 0.100),
  (0.60, 0.120, B + 0.030, 0.075),
  (0.75, 0.085, -0.075, 0.050),
  (0.88, 0.065, -0.058, 0.035),
  (1.00, 0.058, -0.052, 0.028),
)
# A stiff, armored front; the bend is behind the dorsal fin
CORY = Shape(CORY_BODY, 0.5, 0.78, (0.24, 0.06, -0.10, -0.24), -0.5, 0.0)
# The pectoral fins' base, under the gill cover, and the eye
PEC_U = 0.17
EYE_U = 0.14

# The eye, pupil (0) to the back (1): black, a thin gold ring, then the
# black of the mask
CORY_EYE = ((0.0, (0.004, 0.004, 0.004)), (0.30, (0.006, 0.006, 0.006)),
            (0.36, (0.36, 0.28, 0.12)), (0.46, (0.03, 0.025, 0.02)),
            (1.0, (0.02, 0.018, 0.015)))

# The puffs: grains per puff and their radius (lengths), and the dome
# they fill at full size: its radius and height
GRAINS = 40
GRAIN_R = (0.022, 0.045)
DOME_R = 0.34
DOME_H = 0.42
# The dome's middle, ahead of the mouth: the snout throws the sand
# forward and up
DOME_AHEAD = 0.08


def body_x(u):
  return scene_fish.body_x(u, CORY)


def profile(u):
  return scene_fish.profile(u, CORY)


def weights(x):
  return spine_weights(x, blend=0.04, joints=CORY.joints)


# The body

def section(top, bot, half, phi):
  """The cross-section at angle phi (0 at the back): a rounded arch
  above the widest line, which is low, and a broad flat belly below."""
  c, s = math.cos(phi), math.sin(phi)
  mid = bot + (top - bot) * 0.35
  if c >= 0:
    return half * s, mid + (top - mid) * c
  return (half * math.copysign(abs(s) ** 0.6, s),
          mid - (mid - bot) * abs(c) ** 0.5)


def add_body(mb, rings=22, sides=16):
  rows = []
  for i in range(rings):
    u = 0.01 + 0.99 * (i / (rings - 1)) ** 1.1
    top, bot, half = profile(u)
    x = body_x(u)
    row = []
    for j in range(sides + 1):
      y, z = section(top, bot, half, 2 * math.pi * j / sides)
      row.append(mb.vert((x, y, z), (u, j / sides), weights(x)))
    rows.append(row)
  mb.grid(rows, flip=True)
  top, bot, _ = profile(0.0)
  tip = mb.vert((body_x(0.0) + 0.006, 0.0, (top + bot) / 2), (0.0, 0.5),
                weights(CORY.snout_x))
  for j in range(sides):
    mb.face([tip, rows[0][j + 1], rows[0][j]][::-1])
  top, bot, _ = profile(1.0)
  end = mb.vert((body_x(1.0) - 0.004, 0.0, (top + bot) / 2), (1.0, 0.5),
                weights(body_x(1.0)))
  last = rows[-1]
  for j in range(sides):
    mb.face([end, last[j], last[j + 1]][::-1])


def add_eye(mb, side, mat_index, r=0.045, segments=10, rings=6):
  """An eye high on the head, looking out and a little up."""
  top, bot, half = profile(EYE_U)
  y, z = section(top, bot, half, side * 0.95)
  center = Vector((body_x(EYE_U), y * 0.9, z))
  axis = Vector((0.0, side * 0.85, 0.5)).normalized()
  a = Vector((1, 0, 0))
  b = axis.cross(a)
  w = {'Head': 1.0}
  pupil = mb.vert(tuple(center + axis * r * 0.62), (0.5, 0.0), w)
  prev = None
  for i in range(1, rings + 1):
    theta = math.pi * 0.7 * i / rings
    row = []
    for j in range(segments + 1):
      phi = 2 * math.pi * j / segments
      d = (axis * (math.cos(theta) * 0.62) +
           (a * math.cos(phi) + b * math.sin(phi)) * math.sin(theta))
      row.append(mb.vert(tuple(center + d * r), (j / segments, i / rings), w))
    if prev is None:
      for j in range(segments):
        f = [pupil, row[j], row[j + 1]]
        mb.face(f if side < 0 else f[::-1], mat_index)
    else:
      for j in range(segments):
        q = [prev[j], prev[j + 1], row[j + 1], row[j]]
        mb.face(q[::-1] if side < 0 else q, mat_index)
    prev = row


def add_barbels(mb):
  """Two pairs of short barbels under the snout, hanging forward and
  down to feel the sand."""
  for side in (1, -1):
    for out, length in ((0.35, 0.07), (0.8, 0.06)):
      base = Vector((sim_cory.MOUTH[0] + 0.01, side * 0.02 * (1 + out),
                     sim_cory.MOUTH[1] + 0.005))
      d = Vector((0.45, side * out, -0.8)).normalized()
      tip = base + d * length
      o = d.orthogonal().normalized()
      o2 = d.cross(o)
      ring = [mb.vert(tuple(base + (o * math.cos(a) + o2 * math.sin(a))
                            * 0.007), (0.0, 0.0), {'Head': 1.0})
              for a in (0.0, 2.1, 4.2)]
      end = mb.vert(tuple(tip), (0.0, 0.0), {'Head': 1.0})
      for k in range(3):
        f = [ring[k], ring[(k + 1) % 3], end]
        mb.face(f if side > 0 else f[::-1])


# The fins

def fin_weights(bone, share=0.85):
  def w(p, s, r):
    out = {b: v * (1 - share * r) for b, v in weights(p[0]).items()}
    out[bone] = out.get(bone, 0.0) + share * r
    return out
  return w


def body_weights(p, s=0.0, r=0.0):
  return weights(p[0])


def add_fins(mb, pale, black):
  # Dorsal: a tall sail on the back, its stiff first ray leaning back
  def dorsal_base(s):
    u = 0.27 + 0.17 * s
    return (body_x(u), 0.0, profile(u)[0] - 0.008)

  def dorsal_tip(s):
    return scene_fish.swept((0.27, 0, 0.21), (0.14, 0, 0.42),
                            (0.06, 0, 0.30), (-0.02, 0, 0.18), s, 0.3)
  fin(mb, dorsal_base, dorsal_tip, 7, 4, body_weights, black)

  # Adipose: a small spined flap far back on the back
  def adipose_base(s):
    u = 0.78 + 0.08 * s
    return (body_x(u), 0.0, profile(u)[0] - 0.005)

  def adipose_tip(s):
    u = 0.78 + 0.08 * s
    return (body_x(u) - 0.02, 0.0, profile(u)[0] + 0.05 * (1 - s) + 0.01)
  fin(mb, adipose_base, adipose_tip, 3, 2, body_weights, pale)

  # Caudal: a forked fan from the tail's base
  tail = body_x(1.0)

  def caudal_base(s):
    return (tail + 0.01, 0.0, -0.035 + 0.075 * s)

  def caudal_tip(s):
    e = 2 * s - 1
    reach = 0.12 + 0.11 * abs(e) ** 1.3
    return (tail - reach, 0.0, 0.003 + e * (0.10 + 0.05 * abs(e)))
  fin(mb, caudal_base, caudal_tip, 8, 4, body_weights, pale)

  # Pectorals: stiff fans low behind the gills, spread out and down to
  # prop the fish on the sand
  for side, bone in ((1, 'Pec.L'), (-1, 'Pec.R')):
    def pec_base(s, side=side):
      u = PEC_U + 0.06 * s
      return (body_x(u), side * profile(u)[2] * 0.85, B + 0.025)

    def pec_tip(s, side=side):
      x, y, z = scene_fish.bezier(((0.25, side * 0.30, B - 0.005),
                                   (0.16, side * 0.33, B),
                                   (0.10, side * 0.20, B + 0.01)), s)
      return (x, y, z)
    fin(mb, pec_base, pec_tip, 5, 4, fin_weights(bone), pale)

  # Pelvics and anal: small fins under the rear of the belly
  for side in (1, -1):
    def pel_base(s, side=side):
      u = 0.46 + 0.07 * s
      return (body_x(u), side * profile(u)[2] * 0.6, profile(u)[1] + 0.01)

    def pel_tip(s, side=side):
      u = 0.46 + 0.07 * s
      return (body_x(u) - 0.08, side * (profile(u)[2] * 0.6 + 0.06),
              profile(u)[1] - 0.02)
    fin(mb, pel_base, pel_tip, 3, 2, body_weights, pale)

  def anal_base(s):
    u = 0.66 + 0.12 * s
    return (body_x(u), 0.0, profile(u)[1] + 0.006)

  def anal_tip(s):
    u = 0.66 + 0.12 * s
    return (body_x(u) - 0.05, 0.0, profile(u)[1] - 0.07 * (1 - 0.5 * s))
  fin(mb, anal_base, anal_tip, 4, 2, body_weights, pale)


# The puffs

def add_grain(mb, center, r, bone, sides=6, rings=4):
  """A small round grain of sand, all on bone."""
  w = {bone: 1.0}
  top = mb.vert(tuple(center + Vector((0, 0, r))), (0.5, 1.0), w)
  bottom = mb.vert(tuple(center - Vector((0, 0, r))), (0.5, 0.0), w)
  rows = []
  for i in range(1, rings):
    theta = math.pi * i / rings
    row = []
    for j in range(sides):
      phi = 2 * math.pi * j / sides
      d = Vector((math.cos(phi) * math.sin(theta),
                  math.sin(phi) * math.sin(theta), math.cos(theta)))
      row.append(mb.vert(tuple(center + d * r), (j / sides, 1 - i / rings), w))
    rows.append(row)
  for j in range(sides):
    k = (j + 1) % sides
    mb.face([top, rows[0][j], rows[0][k]])
    mb.face([bottom, rows[-1][k], rows[-1][j]])
    for r0, r1 in zip(rows, rows[1:]):
      mb.face([r0[j], r1[j], r1[k], r0[k]])


def add_puffs(mb, rng):
  """A dome of grains on the sand at the mouth for each Puff bone, at
  full size: the higher grains nearer the middle, as a puff rises in a
  plume."""
  mouth = Vector((sim_cory.MOUTH[0] + DOME_AHEAD, 0.0, sim_cory.MOUTH[1]))
  for bone in sim_cory.PUFF_BONES:
    for _ in range(GRAINS):
      h = rng.random() ** 1.3
      reach = DOME_R * (1.0 - 0.6 * h) * math.sqrt(rng.random())
      a = rng.uniform(0, 2 * math.pi)
      p = mouth + Vector((math.cos(a) * reach, math.sin(a) * reach,
                          DOME_H * h))
      add_grain(mb, p, rng.uniform(*GRAIN_R), bone)


# The rig

def build_armature(scene, name, members):
  """One armature for the group: per member a Root bone, at rest where
  the armature is with no turn (the game puts the fish's place and
  heading on it), and under it the member's bones, scaled to it."""
  data = bpy.data.armatures.new(name)
  rig = link_object(scene, name, data, None)
  bpy.context.view_layer.objects.active = rig
  bpy.ops.object.mode_set(mode='EDIT')
  for res in members:
    scale = res.species.length * res.size
    prefix = res.name + ':'
    bones = {}

    def bone(bname, head, tail, parent, connect=False):
      eb = data.edit_bones.new(prefix + bname)
      eb.head = Vector(head) * scale
      eb.tail = Vector(tail) * scale
      # Roll 0: a bone pointing straight back has x the fish's left and
      # z its back
      eb.roll = 0.0
      if parent is not None:
        eb.parent = bones[parent]
        eb.use_connect = connect
      bones[bname] = eb

    # Along +y with no roll, so the bone's rest frame is the armature's
    bone('Root', (0, 0, 0), (0, 0.3, 0), None)
    xs = (CORY.snout_x,) + CORY.joints + (CORY.tail_end + 0.1,)
    for k, bname in enumerate(CHAIN):
      bone(bname, (xs[k], 0, 0), (xs[k + 1], 0, 0),
           CHAIN[k - 1] if k else 'Root', connect=k > 0)
    for side, bname in ((1, 'Pec.L'), (-1, 'Pec.R')):
      head = (body_x(PEC_U), side * profile(PEC_U)[2] * 0.85, B + 0.025)
      bone(bname, head, (head[0] - 0.12, head[1], head[2]), 'Head')
    # The puffs turn and scale about the mouth, pointing straight back
    mx, mz = sim_cory.MOUTH
    for bname in sim_cory.PUFF_BONES:
      bone(bname, (mx, 0, mz), (mx - 0.1, 0, mz), 'Root')
  bpy.ops.object.mode_set(mode='OBJECT')
  for pb in rig.pose.bones:
    pb.rotation_mode = 'QUATERNION' if pb.name.endswith(':Root') else 'XYZ'
  return rig


# Materials

def body_material():
  """Ivory, pinker below, with the black mask over the eyes and the
  black spot on the tail's base: no caustics, no thin film."""
  mat, t, out = new_material('Corydoras')
  uv = t.add('ShaderNodeUVMap', {'uv_map': 'Pattern'})
  xyz = t.add('ShaderNodeSeparateXYZ')
  t.link(uv.outputs['UV'], xyz.inputs[0])
  x, z = xyz.outputs['X'], xyz.outputs['Y']

  def step(value, lo, hi):
    return t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
                 Value=value, From_Min=lo, From_Max=hi, To_Min=0.0,
                 To_Max=1.0).outputs[0]

  # Pale gray-ivory on the back, warm ivory on the flanks, pinkish below
  color = t.mix(step(z, -0.10, 0.02), (0.86, 0.68, 0.58, 1.0),
                (0.84, 0.76, 0.62, 1.0))
  color = t.mix(step(z, 0.06, 0.16), color, (0.62, 0.58, 0.50, 1.0))
  # The mask: a black band over the eyes from the top of the head down
  # past them, leaning back a little
  eye_x = body_x(EYE_U)
  mask = t.math('MULTIPLY', band(t, x, z, eye_x - 0.005, -0.25, 0.05, 0.02),
                step(z, -0.07, -0.03))
  color = t.mix(mask, color, (0.02, 0.018, 0.016, 1.0))
  # The tail spot: a black blotch on the tail's base, above the middle
  spot = t.math('MULTIPLY', band(t, x, z, body_x(0.9), 0.0, 0.05, 0.02),
                t.math('MULTIPLY', step(z, -0.035, -0.01),
                       t.math('SUBTRACT', 1.0, step(z, 0.05, 0.07))))
  color = t.mix(spot, color, (0.02, 0.018, 0.016, 1.0))
  bsdf = t.add('ShaderNodeBsdfPrincipled', Roughness=0.4)
  t.link(color, bsdf.inputs['Base Color'])
  if 'Specular IOR Level' in bsdf.inputs:
    bsdf.inputs['Specular IOR Level'].default_value = 0.55
  # A faint glow of its own color, so the flanks in the dimmer water near
  # the sand don't go gray
  t.link(t.mix(0.12, (0, 0, 0, 1), color), bsdf.inputs['Emission Color'])
  bsdf.inputs['Emission Strength'].default_value = 1.0
  t.link(bsdf.outputs[0], out.inputs['Surface'])
  return mat


def fin_material(name, base, clear=(0.6, 0.5)):
  """Fins of color base, drawn opaque and dithered only at their edge,
  as the angelfish's are (tools/species/angelfish.py): toward the edge,
  from clear[0] of the way out, the color blends up to clear[1] of the
  way toward the water's, where the membrane would let it through."""
  mat, t, out = new_material(name)
  mat.surface_render_method = 'DITHERED'
  mat.use_backface_culling = False
  uv = t.add('ShaderNodeUVMap', {'uv_map': 'UVMap'})
  sr = t.add('ShaderNodeSeparateXYZ')
  t.link(uv.outputs['UV'], sr.inputs[0])
  color = t.mix(t.add('ShaderNodeMapRange', Value=sr.outputs['Y'],
                      From_Min=clear[0], From_Max=1.0, To_Min=0.0,
                      To_Max=clear[1]).outputs[0],
                base, scene_fish.WATER_TINT)
  bsdf = t.add('ShaderNodeBsdfPrincipled', Roughness=0.45)
  t.link(color, bsdf.inputs['Base Color'])
  fade = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
               Value=sr.outputs['Y'], From_Min=0.85, From_Max=1.0,
               To_Min=1.0, To_Max=0.0).outputs[0]
  t.link(fade, bsdf.inputs['Alpha'])
  t.link(bsdf.outputs[0], out.inputs['Surface'])
  return mat


def puff_material():
  """The sand's colors (tools/scene_env.py, sand_material), paler, as
  grains in the water catch the light from above, so a puff shows
  against the sand behind it; opaque, as small fast things fade in the
  player's frame accumulation (docs/harness.md)."""
  mat, t, out = new_material('CorydorasPuff')
  uv = t.add('ShaderNodeUVMap', {'uv_map': 'Pattern'})
  noise = t.add('ShaderNodeTexNoise', Vector=uv.outputs['UV'], Scale=30.0,
                Detail=0.0)
  color = t.ramp(noise.outputs['Fac'], [(0.3, (0.52, 0.44, 0.31)),
                                        (0.7, (0.72, 0.64, 0.50))])
  bsdf = t.add('ShaderNodeBsdfPrincipled', Roughness=0.85)
  t.link(color, bsdf.inputs['Base Color'])
  t.link(bsdf.outputs[0], out.inputs['Surface'])
  return mat


# Building

def build(scene):
  mats = {
    'body': body_material(),
    'eye': scene_fish.eye_material('CorydorasEye', CORY_EYE),
    'fin': fin_material('CorydorasFin', (0.82, 0.78, 0.70, 1.0), (0.2, 0.6)),
    'dorsal': fin_material('CorydorasDorsal', (0.025, 0.022, 0.02, 1.0)),
    'puff': puff_material(),
  }
  build_group(scene, sim_cory.GROUP_NAME, sim_cory.residents(), mats)


def build_group(scene, name, members, mats):
  """The group as four objects: <name>.Rig, the armature, and <name>,
  <name>.Fins and <name>.Puffs, every member's body, fins and puffs in
  one mesh each, skinned to it."""
  rig = build_armature(scene, name + '.Rig', members)
  body, fins, puffs = MeshBuilder(1.0), MeshBuilder(1.0), MeshBuilder(1.0)
  rng = random.Random(61)
  for res in members:
    for mb in (body, fins, puffs):
      mb.scale = res.species.length * res.size
      mb.prefix = res.name + ':'
    add_body(body)
    for side in (1, -1):
      add_eye(body, side, 1)
    add_barbels(body)
    add_fins(fins, 0, 1)
    add_puffs(puffs, rng)
  meshes = (body.finish(name, [mats['body'], mats['eye']], scene, rig),
            fins.finish(name + '.Fins', [mats['fin'], mats['dorsal']], scene,
                        rig),
            puffs.finish(name + '.Puffs', [mats['puff']], scene, rig))
  for obj in meshes:
    obj.visible_shadow = False
  # The puffs start hidden, as the game scales each from nothing
  for pb in rig.pose.bones:
    if ':Puff.' in pb.name:
      pb.scale = (sim_cory.HIDDEN,) * 3
  return rig
