"""The cherry shrimp for tools/build_scene.py: the colony as one object.

Runs inside UPBGE's Blender.  The colony
(tankful.sim.species.cherry_shrimp.shrimps) is built as the neon tetras'
school is (tools/species/neon_tetra.py): <colony>.Rig, one armature for
all the shrimp, and <colony>, every shrimp's body, eyes and limbs in one
mesh, skinned to it.  Each shrimp has its own bones in the rig, prefixed
with its name ("CherryShrimp.2:Claw.L"): a Root bone, which the game
places and turns as the shrimp moves (tankful.game.fishes), and under it
the bones of tankful.sim.species.cherry_shrimp.BONES.

Each shrimp is built standing: its legs reach down to
z = -tankful.sim.species.cherry_shrimp.STAND, the surface it stands on,
its claws ahead of it down toward that, and its antennae forward and
out.  It is built on the frame budget's rules (docs/harness.md): two
objects for the colony, plain opaque materials with no caustic
projection or thin film, and no shadows.

Built in each shrimp's space as tools/scene_fish.py: +x forward, +y its
left, +z its back, origin halfway along it, in units of its length,
scaled to its size.
"""

import math

import bpy
from mathutils import Vector

import scene_fish
from scene_env import link_object, new_material
from scene_fish import CHAIN, MeshBuilder, Shape, fin, spine_weights
from tankful.sim.species import cherry_shrimp as sim_shrimp

FOOT = -sim_shrimp.STAND

# Side profile, rostrum (u=0) to the tail fan's base (u=1): (u, top,
# bottom, half-width), in lengths.  A pointed rostrum, the carapace
# deepest over the legs, the hump of the abdomen behind it, and a narrow
# rear that bends down to the tail fan
SHRIMP_BODY = (
  (0.00, 0.040, 0.030, 0.004),
  (0.07, 0.046, 0.016, 0.010),
  (0.14, 0.060, -0.030, 0.035),
  (0.22, 0.080, -0.058, 0.058),
  (0.32, 0.094, -0.074, 0.066),
  (0.42, 0.100, -0.072, 0.064),
  (0.52, 0.108, -0.066, 0.058),
  (0.62, 0.100, -0.066, 0.052),
  (0.72, 0.070, -0.068, 0.044),
  (0.82, 0.036, -0.070, 0.036),
  (0.92, 0.006, -0.066, 0.028),
  (1.00, -0.012, -0.058, 0.022),
)
# The Head (the carapace) to u=0.45, then the abdomen's three bones and
# the tail fan
SHRIMP = Shape(SHRIMP_BODY, 0.5, 0.84, (0.122, -0.021, -0.164, -0.315),
               -0.5, 0.0)

# The eyes: glossy black
SHRIMP_EYE = ((0.0, (0.004, 0.004, 0.004)), (0.6, (0.01, 0.008, 0.006)),
              (1.0, (0.05, 0.02, 0.015)))

# The walking legs, front to back: where each joins the body (x), and
# where its foot is (x, y)
LEGS = ((0.20, (0.25, 0.15)), (0.15, (0.16, 0.17)), (0.10, (0.04, 0.16)))
# The bones' heads: the legs', the claws' and the antennae's (y on the
# left side)
LEGS_BONE = (0.15, 0.04, -0.07)
CLAW_BASE = (0.26, 0.03, -0.05)
ANTENNA_BASE = (0.40, 0.015, 0.035)
# The swimmerets: a pair under each abdomen bone's segment, at u
SWIMMERETS = (0.58, 0.70, 0.82)


def body_x(u):
  return scene_fish.body_x(u, SHRIMP)


def profile(u):
  return scene_fish.profile(u, SHRIMP)


def weights(x):
  return spine_weights(x, blend=0.03, joints=SHRIMP.joints)


def limb_weights(bone, base_bone='Head'):
  """{bone: weight} at r (0 at a limb's base, 1 at its tip): its own
  bone, blended in from base_bone over the first part of it."""
  def w(r):
    share = min(1.0, r / 0.3)
    out = {bone: share}
    if share < 1.0:
      out[base_bone] = 1.0 - share
    return out
  return w


# The limbs

def tube(mb, points, radius, weight, mat_index, sides=4):
  """A thin tube along points (a polyline, in lengths), radius(r) round
  at r of the way along it, weighted by weight(r); closed to a point at
  the tip."""
  pts = [Vector(p) for p in points]
  # r along the polyline by length
  lengths = [0.0]
  for a, b in zip(pts, pts[1:]):
    lengths.append(lengths[-1] + (b - a).length)
  total = lengths[-1]
  rows = []
  for i, p in enumerate(pts):
    r = lengths[i] / total
    d = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
    a = d.orthogonal().normalized()
    b = d.cross(a)
    row = []
    for k in range(sides + 1):
      phi = 2 * math.pi * k / sides
      q = p + (a * math.cos(phi) + b * math.sin(phi)) * radius(r)
      row.append(mb.vert(tuple(q), (k / sides, r), weight(r)))
    rows.append(row)
  mb.grid(rows, mat_index)
  tip = mb.vert(tuple(pts[-1] + (pts[-1] - pts[-2]).normalized() * 0.004),
                (0.5, 1.0), weight(1.0))
  last = rows[-1]
  for k in range(sides):
    mb.face([last[k], last[k + 1], tip], mat_index)


def add_legs(mb, mat_index):
  """The three pairs of walking legs, out and down from the carapace's
  underside to their feet, kneed above the body's widest line."""
  for side, bone in ((1, 'Legs.L'), (-1, 'Legs.R')):
    for x, (fx, fy) in LEGS:
      u = (SHRIMP.snout_x - x) / SHRIMP.body_len
      top, bot, half = profile(u)
      base = (x, side * half * 0.5, bot + 0.012)
      knee = ((x + fx) / 2, side * (half + 0.06), bot - 0.01)
      foot = (fx, side * fy, FOOT)
      tube(mb, (base, knee, foot), lambda r: 0.011 - 0.006 * r,
           limb_weights(bone), mat_index)


def add_claws(mb, mat_index):
  """The two small pairs of clawed legs that pick, reaching ahead and
  down from under the head, with a pincer at each tip."""
  for side, bone in ((1, 'Claw.L'), (-1, 'Claw.R')):
    for k, (reach, out) in enumerate(((0.16, 0.05), (0.12, 0.08))):
      bx, by, bz = CLAW_BASE
      base = (bx - 0.03 * k, side * by, bz)
      elbow = (bx + 0.05, side * (by + out), bz - 0.06)
      tip = (bx + reach, side * (by + out * 0.5), FOOT + 0.035)
      tube(mb, (base, elbow, tip), lambda r: 0.009 - 0.003 * r,
           limb_weights(bone), mat_index)
      # The pincer: two short fingers
      for spread in (0.6, -0.6):
        d = Vector(tip) - Vector(elbow)
        d = d.normalized()
        end = Vector(tip) + (d + Vector((0, 0, spread))).normalized() * 0.03
        tube(mb, (tip, tuple(end)), lambda r: 0.006 - 0.003 * r,
             lambda r, bone=bone: {bone: 1.0}, mat_index, sides=3)


def add_antennae(mb, mat_index):
  """The long antennae, forward, out and a little up, and the short
  antennules under them."""
  for side, bone in ((1, 'Antenna.L'), (-1, 'Antenna.R')):
    bx, by, bz = ANTENNA_BASE
    pts = ((bx, side * by, bz), (bx + 0.15, side * 0.05, bz + 0.04),
           (bx + 0.40, side * 0.14, bz + 0.05),
           (bx + 0.62, side * 0.26, bz + 0.02),
           (bx + 0.78, side * 0.38, bz - 0.03))
    tube(mb, pts, lambda r: 0.007 - 0.005 * r, limb_weights(bone), mat_index,
         sides=3)
    short = ((bx + 0.01, side * by * 0.6, bz - 0.01),
             (bx + 0.10, side * 0.035, bz + 0.01),
             (bx + 0.18, side * 0.06, bz - 0.01))
    tube(mb, short, lambda r: 0.006 - 0.003 * r, limb_weights(bone),
         mat_index, sides=3)


def add_swimmerets(mb, mat_index):
  """A pair of small paddles under each abdomen segment, hanging down
  and back."""
  for k, u in enumerate(SWIMMERETS):
    bone = 'Swim.%d' % k
    top, bot, half = profile(u)
    x = body_x(u)
    for side in (1, -1):
      def base(s, x=x, side=side):
        return (x + 0.025 - 0.05 * s, side * half * 0.5, bot + 0.006)

      def tip(s, x=x, side=side):
        return (x - 0.01 - 0.04 * s, side * half * 0.6, bot - 0.05)

      def w(p, s, r, bone=bone):
        out = {b: v * (1 - r) for b, v in weights(p[0]).items()}
        out[bone] = out.get(bone, 0.0) + r
        return out
      fin(mb, base, tip, 2, 2, w, mat_index)


def add_tail_fan(mb, mat_index):
  """The tail fan, the telson and uropods spread flat behind the
  abdomen."""
  tail = body_x(1.0)
  top, bot, half = profile(1.0)
  z = (top + bot) / 2

  def base(s):
    return (tail + 0.01, -half + 2 * half * s, z)

  def tip(s):
    e = 2 * s - 1
    return (tail - 0.15 - 0.02 * (1 - abs(e)), e * 0.085, z - 0.01)
  fin(mb, base, tip, 6, 3, lambda p, s, r: weights(p[0]), mat_index)


# The rig

def build_armature(scene, name, members):
  """One armature for the colony: per shrimp a Root bone, at rest where
  the armature is with no turn (the game puts the shrimp's place and
  heading on it), and under it the spine chain and the limbs' bones,
  scaled to the shrimp.  The limbs' bones point straight back with roll
  0, so bone x is the shrimp's left and z its back."""
  data = bpy.data.armatures.new(name)
  rig = link_object(scene, name, data, None)
  bpy.context.view_layer.objects.active = rig
  bpy.ops.object.mode_set(mode='EDIT')
  for res in members:
    scale = res.species.length * res.size
    prefix = res.name + ':'
    bones = {}

    def bone(bname, head, parent, tail=None, length=0.08):
      eb = data.edit_bones.new(prefix + bname)
      eb.head = Vector(head) * scale
      eb.tail = (Vector(tail) if tail else
                 Vector(head) - Vector((length, 0, 0))) * scale
      eb.roll = 0.0
      eb.parent = bones[parent]
      eb.use_connect = tail is not None and parent in CHAIN
      bones[bname] = eb

    # Along +y with no roll, so the bone's rest frame is the armature's
    root = data.edit_bones.new(prefix + 'Root')
    root.head = Vector((0, 0, 0))
    root.tail = Vector((0, 0.3 * scale, 0))
    root.roll = 0.0
    bones['Root'] = root
    xs = (SHRIMP.snout_x,) + SHRIMP.joints + (SHRIMP.tail_end,)
    for k, bname in enumerate(CHAIN):
      bone(bname, (xs[k], 0, 0), CHAIN[k - 1] if k else 'Root',
           tail=(xs[k + 1], 0, 0))
    for side, suffix in ((1, 'L'), (-1, 'R')):
      for bname, (x, y, z) in (('Legs', LEGS_BONE), ('Claw', CLAW_BASE),
                               ('Antenna', ANTENNA_BASE)):
        bone('%s.%s' % (bname, suffix), (x, side * y, z), 'Head')
    for k, u in enumerate(SWIMMERETS):
      bone('Swim.%d' % k, (body_x(u), 0, profile(u)[1] + 0.006),
           'Spine.%d' % k, length=0.05)
  bpy.ops.object.mode_set(mode='OBJECT')
  for pb in rig.pose.bones:
    pb.rotation_mode = 'QUATERNION' if pb.name.endswith(':Root') else 'XYZ'
  return rig


# Materials

# The lamp is above the tank and the viewer sees the shrimp from the
# side, low down among the decor: the materials glow faintly with their
# own color (FILL of it), as the pleco's do (tools/species/pleco.py)
FILL = 0.25


def fill(t, bsdf, color, amount=FILL):
  t.link(t.mix(amount, (0, 0, 0, 1), color), bsdf.inputs['Emission Color'])
  bsdf.inputs['Emission Strength'].default_value = 1.0


def body_material():
  """The body and tail fan: cherry red, glossy, mottled deeper and brighter in patches a few
  millimeters across (coarse, so the frame accumulation keeps them), and
  paler toward the belly."""
  mat, t, out = new_material('CherryShrimp')
  # The tail fan is a single sheet
  mat.use_backface_culling = False
  uv = t.add('ShaderNodeUVMap', {'uv_map': 'Pattern'})
  sep = t.add('ShaderNodeSeparateXYZ')
  t.link(uv.outputs['UV'], sep.inputs[0])
  z = sep.outputs['Y']
  mottle = t.add('ShaderNodeTexNoise', Vector=uv.outputs['UV'], Scale=7.0,
                 Detail=1.0)
  color = t.ramp(mottle.outputs['Fac'], [(0.3, (0.30, 0.012, 0.010)),
                                         (0.5, (0.52, 0.030, 0.020)),
                                         (0.7, (0.70, 0.080, 0.040))])
  belly = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
                Value=z, From_Min=-0.02, From_Max=-0.07, To_Min=0.0,
                To_Max=0.6).outputs[0]
  color = t.mix(belly, color, (0.66, 0.24, 0.17, 1.0))
  bsdf = t.add('ShaderNodeBsdfPrincipled', Roughness=0.28)
  t.link(color, bsdf.inputs['Base Color'])
  if 'Specular IOR Level' in bsdf.inputs:
    bsdf.inputs['Specular IOR Level'].default_value = 0.7
  fill(t, bsdf, color)
  t.link(bsdf.outputs[0], out.inputs['Surface'])
  return mat


def limb_material():
  """The legs, claws, antennae and swimmerets: a paler, pinker red,
  drawn from both sides."""
  mat, t, out = new_material('CherryShrimpLimb')
  mat.use_backface_culling = False
  color = (0.52, 0.07, 0.045, 1.0)
  bsdf = t.add('ShaderNodeBsdfPrincipled', Roughness=0.4)
  bsdf.inputs['Base Color'].default_value = color
  fill(t, bsdf, color)
  t.link(bsdf.outputs[0], out.inputs['Surface'])
  return mat


# Building

def build(scene):
  mats = [body_material(),
          scene_fish.eye_material('CherryShrimpEye', SHRIMP_EYE),
          limb_material()]
  return build_colony(scene, sim_shrimp.COLONY, sim_shrimp.shrimps(), mats)


def build_colony(scene, name, members, mats):
  """The colony as two objects: <name>.Rig, the armature, and <name>,
  every member's body, eyes and limbs in one mesh, skinned to it."""
  rig = build_armature(scene, name + '.Rig', members)
  mb = MeshBuilder(1.0)
  for res in members:
    mb.scale = res.species.length * res.size
    mb.prefix = res.name + ':'
    scene_fish.add_body(mb, SHRIMP, rings=18, sides=10)
    for side in (1, -1):
      scene_fish.add_eye(mb, side, 1, SHRIMP, segments=8, rings=5, u=0.13,
                         r=0.03, height=0.7)
    add_legs(mb, 2)
    add_claws(mb, 2)
    add_antennae(mb, 2)
    add_swimmerets(mb, 2)
    add_tail_fan(mb, 0)
  body = mb.finish(name, mats, scene, rig)
  # Small animals cast no shadows (tools/species/angelfish.py)
  body.visible_shadow = False
  return rig
