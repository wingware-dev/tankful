"""The fish for tools/build_scene.py, and what their models share.

Runs inside UPBGE's Blender.  build_fish adds every species' fish, each
species from its own builder (tools/species/<name>.py), in the order of
the registry (tankful.sim.species.NAMES).  A fish is typically:

- <name>.Rig: an armature with the bones its species' sim module poses
  (tankful.sim.species.<name>.BONES), which the game moves and turns as
  the fish swims (tankful.game.fishes);
- <name>: the body, lofted from side and top profiles (add_body), with
  the eyes (add_eye), skinned to the spine;
- <name>.Fins: the fins as thin sheets (fin), skinned to the spine and
  to their own bones.

Models are built in the fish's space: +x forward, +y its left, +z its
back, with the origin halfway along it.  The profiles are in units of the
fish's length and scaled to it.

Meshes carry a Pattern UV map holding each vertex's rest x and z (in
lengths), so a pattern painted from it lines up across body and fins and
stays put on the skin as the body bends.
"""

import collections
import importlib
import math

import bpy
import bmesh
from mathutils import Vector

from scene_env import link_object, new_material
from tankful.sim import species as sim_species

# The spine chain, head to tail (tankful.sim.swim.SPINE)
CHAIN = ('Head', 'Spine.0', 'Spine.1', 'Spine.2', 'Tail')

# A body's build: its side profile, snout (u=0) to the tail's base (u=1),
# as (u, top, bottom, half-width) rows; where the snout is and how long
# the body is to the tail's base, the spine's joints along x, head to
# tail, and the tail fin's end (all in lengths); and how much flatter
# than an ellipse its cross-section is along the back and belly
Shape = collections.namedtuple('Shape',
                               'body snout_x body_len joints tail_end lens')


def body_x(u, shape):
  return shape.snout_x - shape.body_len * u


def profile(u, shape):
  """(top, bottom, half-width) at u, by Catmull-Rom through the shape's
  body profile."""
  pts = shape.body
  u = min(1.0, max(0.0, u))
  for i in range(len(pts) - 1):
    if pts[i + 1][0] >= u:
      break
  p0, p1, p2, p3 = (pts[max(0, i - 1)], pts[i], pts[i + 1],
                    pts[min(len(pts) - 1, i + 2)])
  span = p2[0] - p1[0]
  t = (u - p1[0]) / span if span else 0.0
  out = []
  for k in (1, 2, 3):
    a, b, c, d = p0[k], p1[k], p2[k], p3[k]
    # Tangents scaled to this span's width, for uneven sample spacing
    m1 = (c - a) / max(p2[0] - p0[0], 1e-6) * span
    m2 = (d - b) / max(p3[0] - p1[0], 1e-6) * span
    t2, t3 = t * t, t * t * t
    out.append((2 * t3 - 3 * t2 + 1) * b + (t3 - 2 * t2 + t) * m1
               + (-2 * t3 + 3 * t2) * c + (t3 - t2) * m2)
  return tuple(out)


def spine_weights(x, joints, blend=0.05):
  """{bone: weight} for a point at x: the spine bone over it, blended
  across each of joints (a Shape's)."""
  # Bone k spans joints[k-1] .. joints[k] (Head ahead of the first joint)
  edges = (math.inf,) + tuple(joints) + (-math.inf,)
  weights = {}
  for k, bone in enumerate(CHAIN):
    hi, lo = edges[k], edges[k + 1]
    w = 1.0
    if hi != math.inf:
      w *= min(1.0, max(0.0, (hi - x) / (2 * blend) + 0.5))
    if lo != -math.inf:
      w *= min(1.0, max(0.0, (x - lo) / (2 * blend) + 0.5))
    if w > 0:
      weights[bone] = w
  total = sum(weights.values())
  return {b: w / total for b, w in weights.items()}


class MeshBuilder:
  """A bmesh with a UVMap, a Pattern map and bone weights.

  Vertices are scaled by scale, and their bones' names prefixed with
  prefix: change them to add several fish to one mesh."""

  def __init__(self, scale, prefix=''):
    self.scale = scale
    self.prefix = prefix
    self.bm = bmesh.new()
    self.uv = self.bm.loops.layers.uv.new('UVMap')
    self.pattern = self.bm.loops.layers.uv.new('Pattern')
    self.deform = self.bm.verts.layers.deform.verify()
    self.groups = {}
    self.info = {}

  def vert(self, p, uv, weights):
    """A vertex at p (in lengths), with its UV and {bone: weight}."""
    v = self.bm.verts.new(Vector(p) * self.scale)
    dv = v[self.deform]
    for bone, w in weights.items():
      dv[self.groups.setdefault(self.prefix + bone, len(self.groups))] = w
    self.info[v] = (uv, (p[0], p[2]))
    return v

  def face(self, verts, mat_index=0):
    face = self.bm.faces.new(verts)
    face.material_index = mat_index
    for loop in face.loops:
      uv, pat = self.info[loop.vert]
      loop[self.uv].uv = uv
      loop[self.pattern].uv = pat
    return face

  def grid(self, rows, mat_index=0, flip=False):
    for r0, r1 in zip(rows, rows[1:]):
      for j in range(len(r0) - 1):
        quad = [r0[j], r0[j + 1], r1[j + 1], r1[j]]
        self.face(quad[::-1] if flip else quad, mat_index)

  def finish(self, name, mats, scene, parent):
    mesh = bpy.data.meshes.new(name)
    self.bm.normal_update()
    self.bm.to_mesh(mesh)
    self.bm.free()
    for mat in mats:
      mesh.materials.append(mat)
    for poly in mesh.polygons:
      poly.use_smooth = True
    obj = link_object(scene, name, mesh, parent)
    for bone, _ in sorted(self.groups.items(), key=lambda kv: kv[1]):
      obj.vertex_groups.new(name=bone)
    skin(obj, parent)
    return obj


def skin(obj, rig):
  """Deform obj by rig, on the GPU."""
  mod = obj.modifiers.new('Rig', 'ARMATURE')
  mod.object = rig
  # UPBGE's GPU skinning
  if hasattr(mod, 'use_gpu_deform'):
    mod.use_gpu_deform = True
  return mod


# The body

def add_body(mb, shape, rings=30, sides=26, mat_index=0):
  def weights(x):
    return spine_weights(x, shape.joints)

  rows = []
  for i in range(rings):
    u = 0.012 + (1.0 - 0.012) * (i / (rings - 1)) ** 1.1
    top, bot, half = profile(u, shape)
    x = body_x(u, shape)
    mid, hh = (top + bot) / 2, (top - bot) / 2
    row = []
    for j in range(sides + 1):
      phi = 2 * math.pi * j / sides
      c, s = math.cos(phi), math.sin(phi)
      # A lens more than an ellipse: thin along the back and belly
      p = (x, half * s * (1 - shape.lens * c * c), mid + hh * c)
      row.append(mb.vert(p, (u, j / sides), weights(x)))
    rows.append(row)
  mb.grid(rows, mat_index, flip=True)
  # Close the snout to a point, and the tail's base flat
  top, bot, _ = profile(0.0, shape)
  tip = mb.vert((body_x(0.0, shape) + 0.006, 0.0, (top + bot) / 2),
                (0.0, 0.5), weights(shape.snout_x))
  for j in range(sides):
    mb.face([tip, rows[0][j + 1], rows[0][j]][::-1], mat_index)
  last = rows[-1]
  top, bot, _ = profile(1.0, shape)
  end = mb.vert((body_x(1.0, shape) - 0.004, 0.0, (top + bot) / 2),
                (1.0, 0.5), weights(body_x(1.0, shape)))
  for j in range(sides):
    mb.face([end, last[j], last[j + 1]][::-1], mat_index)


def add_eye(mb, side, mat_index, shape, segments=16, rings=10, u=0.13,
            r=0.036, height=0.6):
  """An eye on side (+1 left, -1 right) at u along the body, height of the
  way from belly to back: a squashed sphere whose UV V runs from the
  pupil (0) out to the back (1)."""
  top, bot, half = profile(u, shape)
  center = Vector((body_x(u, shape), side * half * 0.78,
                   bot + (top - bot) * height))
  axis = Vector((0, side, 0))
  a = Vector((1, 0, 0))
  b = axis.cross(a)
  weights = {'Head': 1.0}
  pupil = mb.vert(center + axis * r * 0.62, (0.5, 0.0), weights)
  prev = None
  for i in range(1, rings + 1):
    theta = math.pi * i / rings
    row = []
    for j in range(segments + 1):
      phi = 2 * math.pi * j / segments
      d = (axis * (math.cos(theta) * 0.62) +
           (a * math.cos(phi) + b * math.sin(phi)) * math.sin(theta))
      row.append(mb.vert(center + d * r, (j / segments, i / rings), weights))
    if prev is None:
      for j in range(segments):
        f = [pupil, row[j], row[j + 1]]
        mb.face(f if side < 0 else f[::-1], mat_index)
    else:
      for j in range(segments):
        q = [prev[j], prev[j + 1], row[j + 1], row[j]]
        mb.face(q[::-1] if side < 0 else q, mat_index)
    prev = row


# The fins

def lerp(a, b, t):
  return tuple(x + (y - x) * t for x, y in zip(a, b))


def fin(mb, base, tip, cols, rows, weights, mat_index=0, curl=None):
  """A sheet from base(s) to tip(s), s and r in 0..1: its rays run from
  base to tip.  curl(s, r) may add an offset."""
  grid = []
  for i in range(rows + 1):
    r = i / rows
    row = []
    for j in range(cols + 1):
      s = j / cols
      p = lerp(base(s), tip(s), r)
      if curl is not None:
        p = tuple(a + b for a, b in zip(p, curl(s, r)))
      row.append(mb.vert(p, (s, r), weights(p, s, r)))
    grid.append(row)
  mb.grid(grid, mat_index)


def bezier(points, t):
  pts = [tuple(p) for p in points]
  while len(pts) > 1:
    pts = [lerp(a, b, t) for a, b in zip(pts, pts[1:])]
  return pts[0]


def swept(lead, tip, bow, end, s, split=0.3):
  """The outer edge of a swept-back fin: up the leading edge from lead to
  the tip (s up to split), then down a trailing edge bowed toward bow,
  to end."""
  if s < split:
    return lerp(lead, tip, (s / split) ** 0.8)
  return bezier((tip, bow, end), (s - split) / (1 - split))


# Materials

def band(t, x, z, center, slant, half, soft):
  """1 within half (lengths) of the bar x = center + slant z, fading
  over soft."""
  d = t.math('ABSOLUTE', t.math('SUBTRACT', t.math('SUBTRACT', x, center),
                                t.math('MULTIPLY', z, slant)))
  edge = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
               Value=d, From_Min=half, From_Max=half + soft, To_Min=1.0,
               To_Max=0.0)
  return edge.outputs[0]


def eye_material(name, stops):
  """A glossy eye colored by stops, a ramp from the pupil (0) to the back
  (1) as add_eye's UV V runs."""
  mat, t, out = new_material(name)
  uv = t.add('ShaderNodeUVMap', {'uv_map': 'UVMap'})
  v = t.add('ShaderNodeSeparateXYZ')
  t.link(uv.outputs['UV'], v.inputs[0])
  color = t.ramp(v.outputs['Y'], list(stops))
  bsdf = t.add('ShaderNodeBsdfPrincipled', Roughness=0.12)
  t.link(color, bsdf.inputs['Base Color'])
  for key, value in (('Coat Weight', 1.0), ('Specular IOR Level', 0.8)):
    if key in bsdf.inputs:
      bsdf.inputs[key].default_value = value
  t.link(bsdf.outputs[0], out.inputs['Surface'])
  return mat


# What a translucent fin lets through, for the opaque fins to blend
# toward: the water as it looks behind a fish
WATER_TINT = (0.30, 0.42, 0.45, 1.0)


# Building

def build_fish(scene):
  """Every present species' fish (tools/species/<name>.py), in the
  registry's order (tankful.sim.species.present)."""
  present = sim_species.present()
  for name in sim_species.NAMES:
    if name in present:
      importlib.import_module('species.' + name).build(scene)
    else:
      # Blender's Python has no logging set up, so say it here
      print('scene_fish: skipping species %s, its modules not all written'
            % name)
  build_shadows(scene)
  build_outlines(scene)


# The shadows

# The fish cast no real shadows, which cost too much of the frame
# (docs/harness.md), so each has a blob on the sand under it: a dark core
# (Umbra) inside a fainter halo of three faint discs stacked (HALO), each
# a disc on a bone of its own in one armature, FishShadows.Rig, and all of
# them in one mesh, FishShadows.  The game (tankful.game.fishes) puts the
# discs on the sand under their fish and scales them: as the fish rises
# the core shrinks away and the halo spreads, then its discs switch off
# one by one, so the shadow fades.  The fish's other bones are children of
# its last halo disc's (SHADOW_ROOT), so only that one is placed.  Nothing
# is read per frame but the bones, and the whole lot moves one object.
SHADOW_RIG = 'FishShadows.Rig'
HALO = ('Penumbra3', 'Penumbra2', 'Penumbra')
SHADOW_ROOT = HALO[-1]
SHADOW_PARTS = HALO + ('Umbra',)

# The darkness at the center of the core and of the whole halo (each
# disc fades to nothing at its edge), for fish SMALL_FISH long (m) or
# more, and less for smaller ones, which block less light and come in
# schools whose shadows overlap
SHADOW_ALPHA = {'Umbra': 0.7, 'Penumbra': 0.32}
SMALL_SHADOW_ALPHA = {'Umbra': 0.5, 'Penumbra': 0.1}
SMALL_FISH = 0.045


def layer_alpha(alpha, layers):
  """The darkness of each of layers blended discs stacked that together
  are alpha dark."""
  return 1.0 - (1.0 - alpha) ** (1.0 / layers)


def build_shadows(scene, sides=20):
  """FishShadows.Rig and FishShadows: per fish in the tank, a disc of unit
  diameter for each of SHADOW_PARTS, on its bone <fish>:<part>, all but
  SHADOW_ROOT's parented to it."""
  from tankful.sim import tank as sim_tank
  tank = sim_tank.Tank()
  fish = sim_species.stock(tank)
  data = bpy.data.armatures.new(SHADOW_RIG)
  rig = link_object(scene, SHADOW_RIG, data, None, shadow=False)
  bpy.context.view_layer.objects.active = rig
  bpy.ops.object.mode_set(mode='EDIT')
  for f in fish:
    root = None
    for part in (SHADOW_ROOT,) + tuple(p for p in SHADOW_PARTS
                                       if p != SHADOW_ROOT):
      # Along +y with no roll, so the bone's rest frame is the armature's,
      # and a child's pose is its own scale in its parent's
      eb = data.edit_bones.new('%s:%s' % (f.name, part))
      eb.head = Vector((0, 0, 0))
      eb.tail = Vector((0, 0.05, 0))
      eb.roll = 0.0
      if root is None:
        root = eb
      else:
        eb.parent = root
        eb.use_connect = False
  bpy.ops.object.mode_set(mode='OBJECT')
  for pb in rig.pose.bones:
    pb.rotation_mode = 'QUATERNION'
  # Umbra, Penumbra, then the same for small fish
  kinds = ('Umbra', 'Penumbra')
  mats = [shadow_material('FishShadow.%s%s' % (kind, suffix),
                          layer_alpha(alpha[kind],
                                      len(HALO) if kind == 'Penumbra' else 1))
          for suffix, alpha in (('', SHADOW_ALPHA),
                                ('.Small', SMALL_SHADOW_ALPHA))
          for kind in kinds]
  mb = MeshBuilder(1.0)
  for f in fish:
    mb.prefix = f.name + ':'
    first = len(kinds) if f.length < SMALL_FISH else 0
    for part in SHADOW_PARTS:
      index = first + (0 if part == 'Umbra' else 1)
      # UV is the point's place on the disc, 1 at its edge
      weights = {part: 1.0}
      center = mb.vert((0, 0, 0), (0.0, 0.0), weights)
      ring = []
      for j in range(sides):
        a = 2 * math.pi * j / sides
        c, s = math.cos(a), math.sin(a)
        ring.append(mb.vert((0.5 * c, 0.5 * s, 0), (c, s), weights))
      for j in range(sides):
        mb.face([center, ring[j], ring[(j + 1) % sides]], index)
  obj = mb.finish('FishShadows', mats, scene, rig)
  obj.visible_shadow = False
  return rig


def shadow_material(name, alpha):
  """A blended black, alpha dark at the center of a build_shadows disc and
  fading smoothly from a quarter of the way out to nothing at its edge."""
  mat, t, out = new_material(name, blended=True)
  uv = t.add('ShaderNodeUVMap', {'uv_map': 'UVMap'})
  r = t.add('ShaderNodeVectorMath', {'operation': 'LENGTH'})
  t.link(uv.outputs['UV'], r.inputs[0])
  fade = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
               Value=r.outputs['Value'], From_Min=0.25, From_Max=0.95,
               To_Min=alpha, To_Max=0.0).outputs[0]
  black = t.add('ShaderNodeEmission', Strength=0.0)
  black.inputs['Color'].default_value = (0.0, 0.0, 0.0, 1.0)
  clear = t.add('ShaderNodeBsdfTransparent')
  mix = t.add('ShaderNodeMixShader', Fac=fade)
  t.link(clear.outputs[0], mix.inputs[1])
  t.link(black.outputs[0], mix.inputs[2])
  t.link(mix.outputs[0], out.inputs['Surface'])
  return mat


# The outlines

# A selected fish (tankful.game.steering) shows a faint yellow outline:
# an inverted hull, <group>.Outline, a copy of its body pushed out along
# the normals by OUTLINE_WIDTH of its length (at least OUTLINE_MIN, m),
# turned inside out and culled from the front, so only its rim round the
# body's silhouette shows.  Each is skinned to its body's rig with the
# same weights, so it bends and scales with the fish, and one per rig
# covers a whole school.  The game hides them until their group is
# selected.
OUTLINE_SUFFIX = '.Outline'
OUTLINE_WIDTH = 0.035
OUTLINE_MIN = 0.0025
OUTLINE_COLOR = (1.0, 0.86, 0.25, 1.0)
OUTLINE_ALPHA = 0.55
OUTLINE_GLOW = 1.0


def build_outlines(scene):
  """<key>.Outline for each fish's or group's body <key> on <key>.Rig."""
  from tankful.sim import school as sim_school
  from tankful.sim import tank as sim_tank
  tank = sim_tank.Tank()
  lengths = {}
  for f in sim_species.stock(tank):
    key = sim_school.group_of(f).name
    lengths[key] = max(lengths.get(key, 0.0), f.length)
  mat = outline_material('FishOutline')
  for key, length in lengths.items():
    body = bpy.data.objects.get(key)
    rig = bpy.data.objects.get(key + '.Rig')
    if body is None or rig is None or body.type != 'MESH':
      print('scene_fish: no body or rig for %s, so no outline' % key)
      continue
    build_outline(scene, body, rig, max(OUTLINE_MIN, OUTLINE_WIDTH * length),
                  mat)


def build_outline(scene, body, rig, width, mat):
  bm = bmesh.new()
  bm.from_mesh(body.data)
  # Outward, whichever way the builder wound the faces
  bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
  bm.normal_update()
  for v in bm.verts:
    v.co += v.normal * width
  bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
  for face in bm.faces:
    face.material_index = 0
  name = body.name + OUTLINE_SUFFIX
  mesh = bpy.data.meshes.new(name)
  bm.to_mesh(mesh)
  bm.free()
  mesh.materials.append(mat)
  for poly in mesh.polygons:
    poly.use_smooth = True
  obj = link_object(scene, name, mesh, rig, shadow=False)
  obj.matrix_parent_inverse = body.matrix_parent_inverse.copy()
  obj.matrix_basis = body.matrix_basis.copy()
  for group in body.vertex_groups:
    obj.vertex_groups.new(name=group.name)
  skin(obj, rig)
  return obj


def outline_material(name):
  """A glowing yellow, OUTLINE_ALPHA opaque, culled from the front: on an
  inverted hull it shows only past the body's edge."""
  mat, t, out = new_material(name, blended=True)
  mat.use_backface_culling = True
  glow = t.add('ShaderNodeEmission', Strength=OUTLINE_GLOW)
  glow.inputs['Color'].default_value = OUTLINE_COLOR
  clear = t.add('ShaderNodeBsdfTransparent')
  mix = t.add('ShaderNodeMixShader', Fac=OUTLINE_ALPHA)
  t.link(clear.outputs[0], mix.inputs[1])
  t.link(glow.outputs[0], mix.inputs[2])
  t.link(mix.outputs[0], out.inputs['Surface'])
  return mat
