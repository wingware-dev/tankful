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

def add_body(mb, shape, rings=30, sides=26):
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
  mb.grid(rows, flip=True)
  # Close the snout to a point, and the tail's base flat
  top, bot, _ = profile(0.0, shape)
  tip = mb.vert((body_x(0.0, shape) + 0.006, 0.0, (top + bot) / 2),
                (0.0, 0.5), weights(shape.snout_x))
  for j in range(sides):
    mb.face([tip, rows[0][j + 1], rows[0][j]][::-1])
  last = rows[-1]
  top, bot, _ = profile(1.0, shape)
  end = mb.vert((body_x(1.0, shape) - 0.004, 0.0, (top + bot) / 2),
                (1.0, 0.5), weights(body_x(1.0, shape)))
  for j in range(sides):
    mb.face([end, last[j], last[j + 1]][::-1])


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
  """Every species' fish (tools/species/<name>.py), in the registry's
  order (tankful.sim.species.NAMES)."""
  for name in sim_species.NAMES:
    importlib.import_module('species.' + name).build(scene)
