"""The pleco for tools/build_scene.py: a flat-bellied sucker catfish.

Runs inside UPBGE's Blender.  Each pleco (tankful.sim.species.plecos)
gets, as the angelfish do (tools/scene_fish.py):

- <name>.Rig: an armature with the bones tankful.sim.pleco animates;
- <name>: the body, flat below and arched above, with the sucker disc
  on the belly under the head, the eyes high on the head and the
  bristles round the snout;
- <name>.Fins: the pectoral, pelvic, dorsal and caudal fins.

The model rests as the fish clings to the glass: the paired fins spread
flat in the plane of the belly, so on the front glass the viewer sees
the belly, the disc and the fins splayed round them.  The rig is placed
where the sim starts the fish.

It is built on the frame budget's rules (docs/harness.md): one rig of
its own, plain materials with no caustic projection or thin film, and no
shadows.  build_plecos also checks the decor perches
(tankful.sim.environment.perches) against the rock meshes.

Built in the fish's space as scene_fish: +x forward, +y its left, +z its
back, origin at its center, in units of its length.  The belly is flat
at z = -tankful.sim.pleco.BELLY.
"""

import collections
import math

import bpy
from mathutils import Vector

import scene_fish
from scene_env import link_object, new_material
from scene_fish import MeshBuilder, fin, lerp, spine_weights
from tankful.sim import environment as env
from tankful.sim import pleco as sim_pleco
from tankful.sim import species as sim_species
from tankful.sim import vec

B = -sim_pleco.BELLY

# Side and top profile, snout (u=0) to the tail's base (u=1): (u, top,
# bottom, half-width), in lengths.  A broad, flat head that rounds off at
# the snout, the back highest at the dorsal fin, and a narrow tail base
PLECO_BODY = (
  (0.00, -0.012, B + 0.008, 0.050),
  (0.03, 0.008, B + 0.001, 0.110),
  (0.08, 0.034, B, 0.150),
  (0.16, 0.068, B, 0.172),
  (0.26, 0.098, B, 0.176),
  (0.36, 0.110, B + 0.001, 0.156),
  (0.48, 0.100, B + 0.005, 0.122),
  (0.62, 0.080, B + 0.011, 0.088),
  (0.76, 0.060, B + 0.017, 0.060),
  (0.90, 0.046, B + 0.021, 0.042),
  (1.00, 0.040, B + 0.023, 0.034),
)
# The head is long and stiff (armored); the bend is behind it
PLECO = scene_fish.Shape(PLECO_BODY, 0.5, 0.76, (0.22, 0.05, -0.10, -0.22),
                         -0.5, 0.0)
CHAIN = scene_fish.CHAIN
# The sucker disc: its center on the belly, its radius, and the radius
# of the jaws within it
DISC_X, DISC_R, JAW_R = 0.38, 0.09, 0.034
DISC_Z = B - 0.002

# The eye, pupil (0) to the back (1): black, a gold-brown ring, then the
# dark skin round it
PLECO_EYE = ((0.0, (0.004, 0.004, 0.004)), (0.30, (0.006, 0.006, 0.006)),
             (0.36, (0.30, 0.22, 0.10)), (0.48, (0.08, 0.065, 0.045)),
             (1.0, (0.07, 0.06, 0.045)))


def body_x(u):
  return scene_fish.body_x(u, PLECO)


def profile(u):
  return scene_fish.profile(u, PLECO)


def weights(x):
  return spine_weights(x, blend=0.04, joints=PLECO.joints)


class PlecoMesh(MeshBuilder):
  """A MeshBuilder whose UVMap is each vertex's rest x and y (in
  lengths), for spots seen from above; Pattern is x and z as usual."""

  def vert(self, p, uv, w):
    return super().vert(p, (p[0], p[1]), w)


class FinMesh(MeshBuilder):
  """Fins keep the usual UVMap: along the fin's base (x) and out to its
  edge (y)."""


# The body

def section(top, bot, half, phi):
  """The cross-section at angle phi (0 at the back): an arch above the
  widest line, which is low, and flat below with rounded edges."""
  c, s = math.cos(phi), math.sin(phi)
  mid = bot + (top - bot) * 0.3
  if c >= 0:
    return half * s, mid + (top - mid) * c
  return (half * math.copysign(abs(s) ** 0.5, s),
          mid - (mid - bot) * abs(c) ** 0.35)


def add_body(mb, rings=34, sides=28):
  rows = []
  for i in range(rings):
    u = 0.01 + 0.99 * (i / (rings - 1)) ** 1.15
    top, bot, half = profile(u)
    x = body_x(u)
    row = []
    for j in range(sides + 1):
      y, z = section(top, bot, half, 2 * math.pi * j / sides)
      row.append(mb.vert((x, y, z), None, weights(x)))
    rows.append(row)
  mb.grid(rows, flip=True)
  top, bot, _ = profile(0.0)
  tip = mb.vert((body_x(0.0) + 0.004, 0.0, (top + bot) / 2), None,
                weights(PLECO.snout_x))
  for j in range(sides):
    mb.face([tip, rows[0][j + 1], rows[0][j]][::-1])
  top, bot, _ = profile(1.0)
  end = mb.vert((body_x(1.0) - 0.004, 0.0, (top + bot) / 2), None,
                weights(body_x(1.0)))
  last = rows[-1]
  for j in range(sides):
    mb.face([end, last[j], last[j + 1]][::-1])


def add_disc(mb, mat_index, segments=24):
  """The sucker disc, under the head and facing down: lips round the
  jaws.  The jaws scale with the Jaw bone, the lips with Mouth."""
  radii = (0.0, 0.016, JAW_R, JAW_R + 0.01, 0.07, DISC_R)
  # Each ring's stretch along and across the fish: the jaws are a band
  # across the disc, the lips a round that is a little wider than long
  stretch = ((0.5, 1.5), (0.5, 1.5), (0.6, 1.4), (0.85, 1.05),
             (0.9, 1.0))
  # How far each ring stands below the belly: the lips' rim is raised
  drop = (0.0015, 0.0015, 0.001, 0.003, 0.0035, 0.0)
  center = mb.vert((DISC_X, 0.0, DISC_Z - drop[0]), None, {'Jaw': 1.0})
  # UVMap: round the disc and out from its middle; Pattern: x and y
  mb.info[center] = ((0.5, 0.0), (DISC_X, 0.0))
  prev = None
  for r, d, (sx, sy) in zip(radii[1:], drop[1:], stretch):
    bone = 'Jaw' if r <= JAW_R + 1e-9 else 'Mouth'
    row = []
    for k in range(segments + 1):
      a = 2 * math.pi * k / segments
      p = (DISC_X + r * sx * math.cos(a), r * sy * math.sin(a), DISC_Z - d)
      v = mb.bm.verts.new(Vector(p) * mb.scale)
      v[mb.deform][mb.groups.setdefault(mb.prefix + bone, len(mb.groups))] = 1.0
      mb.info[v] = ((k / segments, r / DISC_R), (p[0], p[1]))
      row.append(v)
    if prev is None:
      for k in range(segments):
        mb.face([center, row[k + 1], row[k]], mat_index)
    else:
      for k in range(segments):
        mb.face([prev[k], prev[k + 1], row[k + 1], row[k]][::-1], mat_index)
    prev = row


def add_eye(mb, side, mat_index, u=0.2, r=0.024, segments=14, rings=8):
  """An eye high on the head, looking up and out."""
  top, bot, half = profile(u)
  y, z = section(top, bot, half, side * 0.75)
  center = Vector((body_x(u), y * 0.92, z - r * 0.25))
  axis = Vector((0.0, side * 0.55, 0.85)).normalized()
  a = Vector((1, 0, 0))
  b = axis.cross(a)
  w = {'Head': 1.0}
  pupil = mb.vert(tuple(center + axis * r * 0.7), None, w)
  mb.info[pupil] = ((0.5, 0.0), (0, 0))
  prev = None
  for i in range(1, rings + 1):
    theta = math.pi * 0.6 * i / rings
    row = []
    for j in range(segments + 1):
      phi = 2 * math.pi * j / segments
      d = (axis * (math.cos(theta) * 0.7) +
           (a * math.cos(phi) + b * math.sin(phi)) * math.sin(theta))
      v = mb.vert(tuple(center + d * r), None, w)
      mb.info[v] = ((j / segments, i / rings), (0, 0))
      row.append(v)
    if prev is None:
      for j in range(segments):
        f = [pupil, row[j], row[j + 1]]
        mb.face(f if side < 0 else f[::-1], mat_index)
    else:
      for j in range(segments):
        q = [prev[j], prev[j + 1], row[j + 1], row[j]]
        mb.face(q[::-1] if side < 0 else q, mat_index)
    prev = row


def add_bristles(mb, count=7):
  """The bristles: short fleshy tentacles along the snout's rim, on each
  side, longer toward the front."""
  for side in (1, -1):
    for i in range(count):
      u = 0.01 + 0.13 * i / (count - 1)
      top, bot, half = profile(u)
      y, z = section(top, bot, half, side * 1.2)
      base = Vector((body_x(u), y * 0.97, z))
      out = Vector((0.35 - 1.2 * u, side * 0.8, 0.55)).normalized()
      length = 0.045 - 0.12 * u
      tip = base + out * length
      ring = []
      for k in range(4):
        a = 2 * math.pi * k / 4
        o = out.orthogonal().normalized()
        o2 = out.cross(o)
        p = base + (o * math.cos(a) + o2 * math.sin(a)) * 0.006
        ring.append(mb.vert(tuple(p), None, {'Head': 1.0}))
      end = mb.vert(tuple(tip), None, {'Head': 1.0})
      for k in range(4):
        f = [ring[k], ring[(k + 1) % 4], end]
        mb.face(f if side > 0 else f[::-1])


# The fins

def fin_weights(bone, share=0.8):
  def w(p, s, r):
    out = {b: v * (1 - share * r) for b, v in weights(p[0]).items()}
    out[bone] = out.get(bone, 0.0) + share * r
    return out
  return w


def add_fins(mb):
  # Pectorals: big fans spread flat out to the sides behind the head,
  # the thick first ray reaching furthest
  for side, bone in ((1, 'Pec.L'), (-1, 'Pec.R')):
    def pec_base(s, side=side):
      u = 0.17 + 0.10 * s
      return (body_x(u), side * profile(u)[2] * 0.9, B + 0.006)

    def pec_tip(s, side=side):
      lead, trail = (0.25, side * 0.40), (0.13, side * 0.25)
      bow = (0.13, side * 0.38)
      x, y, _ = scene_fish.bezier(((lead[0], lead[1], 0), (bow[0], bow[1], 0),
                                   (trail[0], trail[1], 0)), s)
      return (x, y, B + 0.004)
    fin(mb, pec_base, pec_tip, 8, 6, fin_weights(bone))

  # Pelvics: smaller fans further back, also flat
  for side, bone in ((1, 'Pelvic.L'), (-1, 'Pelvic.R')):
    def pel_base(s, side=side):
      u = 0.50 + 0.08 * s
      return (body_x(u), side * profile(u)[2] * 0.85, B + 0.008)

    def pel_tip(s, side=side):
      x, y, _ = scene_fish.bezier(((-0.02, side * 0.24, 0),
                                   (-0.10, side * 0.23, 0),
                                   (-0.10, side * 0.13, 0)), s)
      return (x, y, B + 0.007)
    fin(mb, pel_base, pel_tip, 6, 4, fin_weights(bone))

  # Dorsal: a tall sail on the back, raised as it rests
  def dorsal_base(s):
    u = 0.30 + 0.24 * s
    return (body_x(u), 0.0, profile(u)[0] - 0.008)

  def dorsal_tip(s):
    return scene_fish.swept((0.25, 0, 0.13), (0.10, 0, 0.30),
                            (-0.02, 0, 0.22), (-0.08, 0, 0.11), s, 0.25)
  fin(mb, dorsal_base, dorsal_tip, 10, 6, fin_weights('Dorsal', 0.9))

  # Caudal: a broad, square-cut fan, its lower lobe a little longer
  tail = body_x(1.0)

  def caudal_base(s):
    return (tail + 0.01, 0.0, -0.022 + 0.06 * s)

  def caudal_tip(s):
    e = 2 * s - 1
    return (tail - 0.21 - 0.03 * abs(e) - (0.02 if e < 0 else 0.0) * abs(e),
            0.0, 0.008 + e * 0.11)
  fin(mb, caudal_base, caudal_tip, 8, 5, lambda p, s, r: weights(p[0]))


# The rig

def build_rig(scene, name, scale):
  data = bpy.data.armatures.new(name + '.Rig')
  rig = link_object(scene, name + '.Rig', data, None)
  bpy.context.view_layer.objects.active = rig
  bpy.ops.object.mode_set(mode='EDIT')
  bones = {}

  def bone(bname, head, length, parent, connect=False, tail=None):
    eb = data.edit_bones.new(bname)
    eb.head = Vector(head) * scale
    # Pointing straight back, so bone x is the fish's left and z its back
    eb.tail = (Vector(tail) if tail else
               Vector(head) - Vector((length, 0, 0))) * scale
    eb.roll = 0.0
    if parent is not None:
      eb.parent = bones[parent]
      eb.use_connect = connect
    bones[bname] = eb

  xs = (PLECO.snout_x,) + PLECO.joints + (PLECO.tail_end + 0.1,)
  for k, bname in enumerate(CHAIN):
    bone(bname, (xs[k], 0, 0), None, CHAIN[k - 1] if k else None,
         connect=k > 0, tail=(xs[k + 1], 0, 0))
  bone('Mouth', (DISC_X, 0, DISC_Z), 0.08, 'Head')
  bone('Jaw', (DISC_X, 0, DISC_Z), 0.04, 'Mouth')
  for side, bname in ((1, 'Pec.L'), (-1, 'Pec.R')):
    u = 0.17
    bone(bname, (body_x(u), side * profile(u)[2] * 0.9, B + 0.006), 0.12,
         'Head')
  for side, bname in ((1, 'Pelvic.L'), (-1, 'Pelvic.R')):
    u = 0.50
    bone(bname, (body_x(u), side * profile(u)[2] * 0.85, B + 0.008), 0.08,
         'Spine.0')
  u = 0.30
  bone('Dorsal', (body_x(u), 0, profile(u)[0] - 0.008), 0.2, 'Head')
  bpy.ops.object.mode_set(mode='OBJECT')
  for pb in rig.pose.bones:
    pb.rotation_mode = 'XYZ'
  return rig


# Materials

# The lamp is above the tank, so a pleco on the front glass shows the
# viewer its unlit belly: each material glows faintly with its own color
# (FILL of it), as if lit by the water around it
FILL = 0.3


def fill(t, bsdf, color, amount=FILL):
  t.link(t.mix(amount, (0, 0, 0, 1), color), bsdf.inputs['Emission Color'])
  bsdf.inputs['Emission Strength'].default_value = 1.0


def body_material():
  """Dark olive-brown with pale spots above, a pale gray-tan belly: no
  caustics, no thin film."""
  mat, t, out = new_material('Pleco')
  xy = t.add('ShaderNodeUVMap', {'uv_map': 'UVMap'}).outputs['UV']
  xz = t.add('ShaderNodeUVMap', {'uv_map': 'Pattern'})
  sep = t.add('ShaderNodeSeparateXYZ')
  t.link(xz.outputs['UV'], sep.inputs[0])
  z = sep.outputs['Y']
  spots = t.add('ShaderNodeTexVoronoi', {'feature': 'F1'}, Vector=xy,
                Scale=34.0, Randomness=0.9)
  dot = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
              Value=spots.outputs['Distance'], From_Min=0.16, From_Max=0.26,
              To_Min=1.0, To_Max=0.0).outputs[0]
  mottle = t.add('ShaderNodeTexNoise', Vector=xy, Scale=9.0, Detail=2.0)
  back = t.mix(t.math('MULTIPLY', mottle.outputs['Fac'], 0.6),
               (0.085, 0.075, 0.05, 1.0), (0.16, 0.13, 0.08, 1.0))
  back = t.mix(t.math('MULTIPLY', dot, 0.75), back, (0.55, 0.52, 0.42, 1.0))
  belly = t.mix(t.math('MULTIPLY', mottle.outputs['Fac'], 0.6),
                (0.26, 0.21, 0.14, 1.0), (0.15, 0.12, 0.075, 1.0))
  # Belly color below the widest line, the back's above it
  up = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
             Value=z, From_Min=B + 0.012, From_Max=B + 0.03, To_Min=0.0,
             To_Max=1.0).outputs[0]
  color = t.mix(up, belly, back)
  bsdf = t.add('ShaderNodeBsdfPrincipled', Roughness=0.55)
  t.link(color, bsdf.inputs['Base Color'])
  if 'Specular IOR Level' in bsdf.inputs:
    bsdf.inputs['Specular IOR Level'].default_value = 0.45
  fill(t, bsdf, color)
  t.link(bsdf.outputs[0], out.inputs['Surface'])
  return mat


def disc_material():
  """The sucker disc: pale lips speckled with papillae round dark
  jaws."""
  mat, t, out = new_material('PlecoDisc')
  uv = t.add('ShaderNodeUVMap', {'uv_map': 'UVMap'})
  sep = t.add('ShaderNodeSeparateXYZ')
  t.link(uv.outputs['UV'], sep.inputs[0])
  r = sep.outputs['Y']
  color = t.ramp(r, [(0.0, (0.03, 0.025, 0.02)), (0.36, (0.07, 0.05, 0.035)),
                     (0.46, (0.20, 0.15, 0.11)), (0.56, (0.50, 0.44, 0.36)),
                     (0.92, (0.42, 0.37, 0.30)), (1.0, (0.30, 0.26, 0.20))])
  pos = t.add('ShaderNodeUVMap', {'uv_map': 'Pattern'}).outputs['UV']
  papillae = t.add('ShaderNodeTexNoise', Vector=pos, Scale=220.0, Detail=0.0)
  color = t.mix(t.math('MULTIPLY', papillae.outputs['Fac'], 0.35), color,
                (0.18, 0.14, 0.10, 1.0))
  bsdf = t.add('ShaderNodeBsdfPrincipled', Roughness=0.5)
  t.link(color, bsdf.inputs['Base Color'])
  fill(t, bsdf, color)
  t.link(bsdf.outputs[0], out.inputs['Surface'])
  return mat


def fin_material():
  """Brown fins with rows of dark spots and darker rays, drawn opaque
  and faded only at the very edge (dithered), as the angelfish's are
  (tools/scene_fish.py, fin_material)."""
  mat, t, out = new_material('PlecoFin')
  mat.surface_render_method = 'DITHERED'
  mat.use_backface_culling = False
  uv = t.add('ShaderNodeUVMap', {'uv_map': 'UVMap'})
  sr = t.add('ShaderNodeSeparateXYZ')
  t.link(uv.outputs['UV'], sr.inputs[0])
  rays = t.math('MULTIPLY', t.math('ADD', t.math(
    'SINE', t.math('MULTIPLY', sr.outputs['X'], 2 * math.pi * 7)), 1.0), 0.5)
  spots = t.add('ShaderNodeTexVoronoi', Vector=uv.outputs['UV'], Scale=7.0,
                Randomness=0.7)
  dot = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
              Value=spots.outputs['Distance'], From_Min=0.12, From_Max=0.25,
              To_Min=1.0, To_Max=0.0).outputs[0]
  color = t.mix(t.math('MULTIPLY', rays, 0.5), (0.20, 0.15, 0.09, 1.0),
                (0.09, 0.065, 0.04, 1.0))
  color = t.mix(dot, color, (0.03, 0.025, 0.02, 1.0))
  # The membrane between rays thins toward the edge: toward the water
  thin = t.add('ShaderNodeMapRange', Value=sr.outputs['Y'], From_Min=0.5,
               From_Max=1.0, To_Min=0.0, To_Max=0.25).outputs[0]
  color = t.mix(thin, color, scene_fish.WATER_TINT)
  bsdf = t.add('ShaderNodeBsdfPrincipled', Roughness=0.5)
  t.link(color, bsdf.inputs['Base Color'])
  fill(t, bsdf, color)
  fade = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
               Value=sr.outputs['Y'], From_Min=0.9, From_Max=1.0,
               To_Min=1.0, To_Max=0.0).outputs[0]
  t.link(fade, bsdf.inputs['Alpha'])
  t.link(bsdf.outputs[0], out.inputs['Surface'])
  return mat


# Building

def build_plecos(scene):
  check_perches()
  mats = {
    'body': body_material(),
    'eye': scene_fish.eye_material('PlecoEye', PLECO_EYE),
    'disc': disc_material(),
    'fin': fin_material(),
  }
  for res in sim_species.plecos():
    build_one(scene, res, mats)


def build_one(scene, res, mats):
  scale = res.species.length * res.size
  rig = build_rig(scene, res.name, scale)
  # Where the sim starts it: clinging to the surface nearest its start
  fish = sim_pleco.Pleco(res.name, res.species, res.size, res.seed, res.start)
  rig.location = (fish.x, fish.y, fish.z)
  rig.rotation_mode = 'QUATERNION'
  rig.rotation_quaternion = vec.quaternion(fish.orientation())

  body = PlecoMesh(scale)
  add_body(body)
  add_bristles(body)
  add_eye(body, 1, 1)
  add_eye(body, -1, 1)
  add_disc(body, 2)
  fins = FinMesh(scale)
  add_fins(fins)
  meshes = (body.finish(res.name, [mats['body'], mats['eye'], mats['disc']],
                        scene, rig),
            fins.finish(res.name + '.Fins', [mats['fin']], scene, rig))
  for obj in meshes:
    obj.visible_shadow = False
  return rig


Miss = collections.namedtuple('Miss', 'perch mesh_z')


def check_perches(tolerance=0.012):
  """Warn about any perch more than tolerance (m) off its rock's mesh: a
  pleco there would float or sink."""
  misses = []
  for perch in env.perches():
    obj = bpy.data.objects.get(perch.obstacle)
    if obj is None:
      print('scene_pleco: no object %s for perch %s' % (perch.obstacle,
                                                        perch.name))
      continue
    inv = obj.matrix_world.inverted()
    x, y, z = perch.point
    origin = inv @ Vector((x, y, z + 0.2))
    down = (inv.to_3x3() @ Vector((0, 0, -1))).normalized()
    hit, loc, _, _ = obj.ray_cast(origin, down)
    mesh_z = (obj.matrix_world @ loc).z if hit else None
    if mesh_z is None or abs(mesh_z - z) > tolerance:
      misses.append(Miss(perch, mesh_z))
  for miss in misses:
    print('scene_pleco: WARNING perch %s at z %.4f, but its mesh is at %s'
          % (miss.perch.name, miss.perch.point[2], miss.mesh_z))
  return misses
