"""The tank environment for tools/build_scene.py: sand, decor, plants,
bubbles and the light effects.

Runs inside UPBGE's Blender.  The layout (where the sand rises, where
each rock and plant stands) comes from tankful.sim.environment, which the
game reads too.

Moving light is done without per-frame shader parameters: every animated
shader reads its pattern through the CausticProjection node group, which
projects a caustic pattern down from the CausticProjector empty above the
tank.  The game moves that empty each frame (tankful.game.scenery), which
moves the caustics on the sand, rocks and plants, the shimmer on the
water surface and the flicker of the god rays together.
"""

import math
import random

import bpy
import bmesh
import mathutils
from mathutils import Vector

from tankful.sim import bubbles as sim_bubbles
from tankful.sim import environment as env

PROJECTOR = 'CausticProjector'
# How fast W, the caustic pattern's time axis, runs per unit the projector
# sinks (the game sinks it by CAUSTIC_SPEED per second)
CAUSTIC_W = 0.8


def build_environment(scene, tank, mats):
  projector = bpy.data.objects.new(PROJECTOR, None)
  projector.empty_display_type = 'SINGLE_ARROW'
  projector.location = (0, 0, env.TANK_H + 0.2)
  scene.collection.objects.link(projector)
  caustic = caustic_group(projector)

  build_back_panel(scene, tank)
  build_sand(scene, tank, caustic)
  build_rocks(scene, tank, caustic)
  build_driftwood(scene, tank, caustic)
  build_plants(scene, tank, caustic)
  build_airstone(scene, tank)
  build_bubbles(scene, tank)
  build_water_surface(scene, tank, caustic)
  build_god_rays(scene, tank, caustic)
  mats['glass_front'] = glass_front_material()
  return projector


# Node helpers

class Tree:
  """Adds and links shader nodes: n = t.add('ShaderNodeMath', Value=1)."""

  def __init__(self, tree):
    self.tree = tree

  def add(self, kind, _props=None, **inputs):
    node = self.tree.nodes.new(kind)
    for attr, value in (_props or {}).items():
      setattr(node, attr, value)
    for name, value in inputs.items():
      sock = socket(node.inputs, name.replace('_', ' '))
      if hasattr(value, 'bl_idname') or isinstance(value, bpy.types.NodeSocket):
        self.link(value, sock)
      else:
        sock.default_value = value
    return node

  def link(self, out, inp):
    if isinstance(out, bpy.types.Node):
      out = first_output(out)
    self.tree.links.new(out, inp)

  def math(self, op, a, b=None, clamp=False):
    node = self.add('ShaderNodeMath', {'operation': op, 'use_clamp': clamp})
    for sock, value in zip(node.inputs, (a, b)):
      if value is None:
        continue
      if isinstance(value, (int, float)):
        sock.default_value = value
      else:
        self.link(value, sock)
    return node.outputs[0]

  def mix(self, fac, a, b, blend='MIX'):
    node = self.add('ShaderNodeMix', {'data_type': 'RGBA',
                                      'blend_type': blend})
    for name, value in (('Factor', fac), ('A', a), ('B', b)):
      sock = socket(node.inputs, name)
      if isinstance(value, (int, float, tuple)):
        sock.default_value = value
      else:
        self.link(value, sock)
    return socket(node.outputs, 'Result')

  def ramp(self, fac, stops):
    node = self.add('ShaderNodeValToRGB')
    self.link(fac, node.inputs['Fac'])
    # The ramp keeps its stops sorted, so place the ends first and add the
    # rest between them (stops must be in order)
    elems = node.color_ramp.elements
    elems[0].position = stops[0][0]
    elems[1].position = stops[-1][0]
    for pos, _ in stops[1:-1]:
      elems.new(pos)
    for elem, (_, color) in zip(elems, stops):
      elem.color = color if len(color) == 4 else tuple(color) + (1.0,)
    return node.outputs['Color']


def socket(sockets, name):
  """The enabled socket called name (nodes like Mix have hidden twins)."""
  for sock in sockets:
    if sock.name == name and sock.enabled:
      return sock
  for sock in sockets:
    if sock.identifier == name:
      return sock
  raise KeyError(name)


def first_output(node):
  for sock in node.outputs:
    if sock.enabled:
      return sock
  return node.outputs[0]


def new_material(name, blended=False):
  mat = bpy.data.materials.new(name)
  mat.use_nodes = True
  nodes = mat.node_tree.nodes
  for node in list(nodes):
    if node.bl_idname != 'ShaderNodeOutputMaterial':
      nodes.remove(node)
  if blended:
    mat.surface_render_method = 'BLENDED'
    mat.use_backface_culling = False
    mat.use_transparent_shadow = True
  return mat, Tree(mat.node_tree), nodes['Material Output']


def caustic_group(projector):
  """A node group whose Caustic output is the moving caustic light.

  The pattern is two layers of Voronoi cell edges, wobbled by noise, in
  the projector's object space: x and y across the tank, and its z as the
  4D Voronoi's W, so sinking the projector evolves the pattern.  Light
  falls from above, so it fades on surfaces that face away from it.
  """
  group = bpy.data.node_groups.new('CausticProjection', 'ShaderNodeTree')
  group.interface.new_socket('Caustic', in_out='OUTPUT',
                             socket_type='NodeSocketFloat')
  # The pattern without the fade, for the water surface seen from below
  group.interface.new_socket('Pattern', in_out='OUTPUT',
                             socket_type='NodeSocketFloat')
  t = Tree(group)
  out = t.add('NodeGroupOutput')
  coords = t.add('ShaderNodeTexCoord', {'object': projector})
  xyz = t.add('ShaderNodeSeparateXYZ')
  t.link(coords.outputs['Object'], xyz.inputs[0])
  w = t.math('MULTIPLY', xyz.outputs['Z'], CAUSTIC_W)
  flat = t.add('ShaderNodeCombineXYZ', X=xyz.outputs['X'], Y=xyz.outputs['Y'])
  warp = t.add('ShaderNodeTexNoise', {'noise_dimensions': '4D'},
               Vector=flat.outputs[0], W=w, Scale=3.0, Detail=1.0)
  warp_vec = t.add('ShaderNodeVectorMath', {'operation': 'MULTIPLY_ADD'})
  t.link(warp.outputs['Color'], warp_vec.inputs[0])
  warp_vec.inputs[1].default_value = (0.06, 0.06, 0.0)
  t.link(flat.outputs[0], warp_vec.inputs[2])
  layers = []
  # A web of bright edges over dark cells, finer layer fainter.  Wider
  # edges blur into a flat glow
  for scale, offset, speed, width, weight in (
      (6.0, (0, 0, 0), 1.0, 0.05, 1.0),
      (10.0, (0.37, 0.71, 0), -1.3, 0.04, 0.45)):
    shifted = t.add('ShaderNodeVectorMath', {'operation': 'ADD'})
    t.link(warp_vec.outputs[0], shifted.inputs[0])
    shifted.inputs[1].default_value = offset
    vor = t.add('ShaderNodeTexVoronoi',
                {'voronoi_dimensions': '4D', 'feature': 'DISTANCE_TO_EDGE'},
                Vector=shifted.outputs[0], W=t.math('MULTIPLY', w, speed),
                Scale=scale)
    edge = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
                 Value=vor.outputs['Distance'], From_Min=0.0, From_Max=width,
                 To_Min=weight, To_Max=0.0)
    layers.append(edge.outputs[0])
  both = t.math('ADD', layers[0], layers[1], clamp=True)
  t.link(both, out.inputs['Pattern'])
  geom = t.add('ShaderNodeNewGeometry')
  nz = t.add('ShaderNodeSeparateXYZ')
  t.link(geom.outputs['Normal'], nz.inputs[0])
  facing = t.math('MULTIPLY_ADD', nz.outputs['Z'], 0.75)
  facing.node.inputs[2].default_value = 0.25
  lit = t.math('MULTIPLY', both, t.math('MAXIMUM', facing, 0.0))
  t.link(lit, out.inputs['Caustic'])
  return group


def caustic_node(t, group, output='Caustic'):
  node = t.add('ShaderNodeGroup')
  node.node_tree = group
  return node.outputs[output]


def lit_surface(t, out, color, caustic, roughness=0.6, strength=3.2,
                normal=None, bsdf_extra=None):
  """Principled with caustic light added as emission tinted by color."""
  bsdf = t.add('ShaderNodeBsdfPrincipled', Roughness=roughness)
  t.link(color, bsdf.inputs['Base Color'])
  glow = t.mix(t.math('MULTIPLY', caustic, strength), (0, 0, 0, 1), color)
  warm = t.mix(1.0, glow, (1.0, 0.96, 0.85, 1.0), blend='MULTIPLY')
  t.link(warm, bsdf.inputs['Emission Color'])
  bsdf.inputs['Emission Strength'].default_value = 1.0
  if normal is not None:
    t.link(normal, bsdf.inputs['Normal'])
  for name, value in (bsdf_extra or {}).items():
    bsdf.inputs[name].default_value = value
  t.link(bsdf.outputs[0], out.inputs['Surface'])
  return bsdf


def object_coords(t, scale=1.0):
  coords = t.add('ShaderNodeTexCoord')
  if scale == 1.0:
    return coords.outputs['Object']
  vec = t.add('ShaderNodeVectorMath', {'operation': 'SCALE'})
  t.link(coords.outputs['Object'], vec.inputs[0])
  socket(vec.inputs, 'Scale').default_value = scale
  return vec.outputs[0]


def bump(t, height, strength, distance=0.002):
  node = t.add('ShaderNodeBump', Strength=strength, Distance=distance)
  t.link(height, node.inputs['Height'])
  return node.outputs['Normal']


# Mesh helpers

def link_object(scene, name, data, parent, shadow=True):
  obj = bpy.data.objects.new(name, data)
  scene.collection.objects.link(obj)
  if parent is not None:
    obj.parent = parent
  if data is not None and getattr(obj, 'type', None) == 'MESH':
    obj.game.physics_type = 'NO_COLLISION'
  obj.visible_shadow = shadow
  return obj


def finish_mesh(bm, name, mat, smooth=True):
  mesh = bpy.data.meshes.new(name)
  bm.to_mesh(mesh)
  bm.free()
  mesh.materials.append(mat)
  for poly in mesh.polygons:
    poly.use_smooth = smooth
  return mesh


def tube(bm, points, radii, sides=8, noise_seed=None, noise_amp=0.0):
  """Rings of sides verts along points (Vectors), joined and capped."""
  rings = []
  n = len(points)
  up = Vector((0, 0, 1))
  for i, (p, r) in enumerate(zip(points, radii)):
    a = points[max(0, i - 1)]
    b = points[min(n - 1, i + 1)]
    axis = (b - a).normalized()
    side = axis.cross(up)
    if side.length < 1e-4:
      side = axis.cross(Vector((1, 0, 0)))
    side.normalize()
    other = axis.cross(side).normalized()
    ring = []
    for k in range(sides):
      ang = 2 * math.pi * k / sides
      offset = side * math.cos(ang) + other * math.sin(ang)
      rr = r
      if noise_seed is not None:
        q = p * 25 + offset * 0.6 + Vector((noise_seed, 0, 0))
        rr *= 1 + noise_amp * mathutils.noise.noise(q)
      ring.append(bm.verts.new(p + offset * rr))
    rings.append(ring)
  for r0, r1 in zip(rings, rings[1:]):
    for k in range(sides):
      bm.faces.new((r0[k], r0[(k + 1) % sides], r1[(k + 1) % sides], r1[k]))
  bm.faces.new(list(reversed(rings[0])))
  bm.faces.new(rings[-1])


# Background and sand

def build_back_panel(scene, tank):
  """A gradient panel just behind the back glass, lit from within."""
  mat, t, out = new_material('BackPanel')
  coords = t.add('ShaderNodeTexCoord')
  z = t.add('ShaderNodeSeparateXYZ')
  t.link(coords.outputs['Generated'], z.inputs[0])
  noise = t.add('ShaderNodeTexNoise', Vector=coords.outputs['Generated'],
                Scale=3.0, Detail=3.0)
  fac = t.math('ADD', z.outputs['Z'],
               t.math('MULTIPLY', t.math('SUBTRACT', noise.outputs['Fac'], 0.5),
                      0.12))
  color = t.ramp(fac, [(0.0, (0.004, 0.02, 0.02)),
                       (0.4, (0.015, 0.09, 0.10)),
                       (1.0, (0.06, 0.30, 0.42))])
  emit = t.add('ShaderNodeEmission', Strength=1.6)
  t.link(color, emit.inputs['Color'])
  t.link(emit.outputs[0], out.inputs['Surface'])

  bm = bmesh.new()
  w, h = env.TANK_W - 2 * env.GLASS, env.TANK_H
  y = env.TANK_D / 2 + 0.004
  verts = [bm.verts.new(v) for v in ((-w / 2, y, 0), (w / 2, y, 0),
                                     (w / 2, y, h), (-w / 2, y, h))]
  bm.faces.new(verts)
  link_object(scene, 'BackPanel', finish_mesh(bm, 'BackPanel', mat, False),
              tank, shadow=False)


def sand_material(caustic):
  mat, t, out = new_material('Sand')
  co = object_coords(t)
  # No grain finer than a pixel or so: the player's temporal reprojection
  # clamps its history to each pixel's neighborhood, and sub-pixel speckle
  # widens that range so far that the moving caustics smear to nothing
  broad = t.add('ShaderNodeTexNoise', Vector=co, Scale=14.0, Detail=4.0)
  grain = t.add('ShaderNodeTexNoise', Vector=co, Scale=110.0, Detail=1.0)
  pebbles = t.add('ShaderNodeTexVoronoi', Vector=co, Scale=55.0)
  base = t.ramp(broad.outputs['Fac'], [(0.3, (0.30, 0.23, 0.14)),
                                        (0.7, (0.46, 0.37, 0.24))])
  speck = t.ramp(grain.outputs['Fac'], [(0.3, (0.85, 0.82, 0.78)),
                                         (0.7, (1.08, 1.05, 1.0))])
  color = t.mix(1.0, base, speck, blend='MULTIPLY')
  dark = t.ramp(pebbles.outputs['Distance'], [(0.06, (0.55, 0.47, 0.40)),
                                               (0.12, (1, 1, 1))])
  color = t.mix(0.6, color, dark, blend='MULTIPLY')
  height = t.math('ADD', grain.outputs['Fac'],
                  t.math('MULTIPLY', pebbles.outputs['Distance'], 2.0))
  lit_surface(t, out, color, caustic_node(t, caustic), roughness=0.85,
              normal=bump(t, height, 0.2, 0.002))
  return mat


def build_sand(scene, tank, caustic):
  """The sand bed: a heightfield grid with skirts down to the glass floor."""
  nx, ny = 100, 40
  x0, y0 = -env.INNER_X + 0.001, -env.INNER_Y + 0.001
  dx, dy = -2 * x0 / nx, -2 * y0 / ny
  bm = bmesh.new()
  grid = []
  for j in range(ny + 1):
    row = []
    for i in range(nx + 1):
      x, y = x0 + i * dx, y0 + j * dy
      row.append(bm.verts.new((x, y, env.sand_height(x, y))))
    grid.append(row)
  for j in range(ny):
    for i in range(nx):
      bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1],
                    grid[j + 1][i]))
  edge = ([grid[0][i] for i in range(nx + 1)] +
          [grid[j][nx] for j in range(1, ny + 1)] +
          [grid[ny][i] for i in range(nx - 1, -1, -1)] +
          [grid[j][0] for j in range(ny - 1, 0, -1)])
  floor = env.GLASS
  bottom = [bm.verts.new((v.co.x, v.co.y, floor)) for v in edge]
  for k in range(len(edge)):
    k1 = (k + 1) % len(edge)
    bm.faces.new((edge[k1], edge[k], bottom[k], bottom[k1]))
  bm.normal_update()
  link_object(scene, 'Sand', finish_mesh(bm, 'Sand', sand_material(caustic)),
              tank)


# Decor

def rock_material(caustic):
  mat, t, out = new_material('Rock')
  co = object_coords(t)
  big = t.add('ShaderNodeTexNoise', Vector=co, Scale=6.0, Detail=6.0,
              Roughness=0.6)
  fine = t.add('ShaderNodeTexNoise', Vector=co, Scale=60.0, Detail=4.0)
  color = t.ramp(big.outputs['Fac'], [(0.35, (0.16, 0.15, 0.14)),
                                       (0.5, (0.32, 0.30, 0.27)),
                                       (0.65, (0.42, 0.38, 0.32))])
  # Algae on the upward faces
  geom = t.add('ShaderNodeNewGeometry')
  nz = t.add('ShaderNodeSeparateXYZ')
  t.link(geom.outputs['Normal'], nz.inputs[0])
  algae = t.add('ShaderNodeMapRange', Value=t.math(
                  'ADD', nz.outputs['Z'],
                  t.math('MULTIPLY', fine.outputs['Fac'], 0.5)),
                From_Min=0.85, From_Max=1.2, To_Min=0.0, To_Max=0.7)
  color = t.mix(algae.outputs[0], color, (0.13, 0.20, 0.07, 1.0))
  height = t.math('ADD', big.outputs['Fac'],
                  t.math('MULTIPLY', fine.outputs['Fac'], 0.4))
  lit_surface(t, out, color, caustic_node(t, caustic), roughness=0.8,
              normal=bump(t, height, 0.6, 0.004))
  return mat


def build_rocks(scene, tank, caustic):
  mat = rock_material(caustic)
  for rock in env.rocks():
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=4, radius=1.0)
    rng = random.Random(rock.seed)
    off = Vector((rng.uniform(-50, 50), rng.uniform(-50, 50),
                  rng.uniform(-50, 50)))
    for v in bm.verts:
      n = v.co.normalized()
      d = (0.28 * mathutils.noise.noise(n * 1.3 + off) +
           0.08 * mathutils.noise.noise(n * 4.0 + off) +
           0.03 * mathutils.noise.noise(n * 11.0 + off))
      co = n * (1 + d)
      # Flat-ish bottoms, sitting in the sand
      if co.z < -0.2:
        co.z = -0.2 + (co.z + 0.2) * 0.3
      v.co = co
    sx, sy, sz = rock.size
    bmesh.ops.scale(bm, vec=(sx / 2, sy / 2, sz / 2), verts=bm.verts)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0),
                     matrix=mathutils.Matrix.Rotation(rock.yaw, 3, 'Z'))
    obj = link_object(scene, rock.name, finish_mesh(bm, rock.name, mat), tank)
    obj.location = (rock.x, rock.y, env.sand_height(rock.x, rock.y) +
                    sz * 0.18)


def wood_material(caustic):
  mat, t, out = new_material('Driftwood')
  co = object_coords(t)
  grain = t.add('ShaderNodeTexWave', {'wave_type': 'BANDS',
                                      'bands_direction': 'X'},
                Vector=co, Scale=8.0, Distortion=6.0, Detail=4.0,
                Detail_Scale=2.0)
  knots = t.add('ShaderNodeTexNoise', Vector=co, Scale=18.0, Detail=5.0)
  color = t.ramp(grain.outputs['Fac'], [(0.2, (0.11, 0.06, 0.035)),
                                         (0.6, (0.30, 0.19, 0.11)),
                                         (0.9, (0.42, 0.30, 0.19))])
  color = t.mix(t.math('MULTIPLY', knots.outputs['Fac'], 0.5), color,
                (0.08, 0.05, 0.03, 1.0))
  height = t.math('ADD', grain.outputs['Fac'], knots.outputs['Fac'])
  lit_surface(t, out, color, caustic_node(t, caustic), roughness=0.75,
              normal=bump(t, height, 0.7, 0.003))
  return mat


def build_driftwood(scene, tank, caustic):
  """A trunk lying across the sand with two branches reaching up."""
  mat = wood_material(caustic)
  for wood in env.driftwood():
    rng = random.Random(wood.seed)
    bm = bmesh.new()

    def wiggle(points, amount):
      return [p + Vector((rng.uniform(-amount, amount),
                          rng.uniform(-amount, amount),
                          rng.uniform(-amount, amount) * 0.5))
              for p in points]

    def span(a, b, steps):
      return [a.lerp(b, i / steps) for i in range(steps + 1)]

    trunk = wiggle(span(Vector((-0.18, -0.02, 0.016)),
                        Vector((0.17, 0.03, 0.035)), 16), 0.006)
    tube(bm, trunk, [0.032 - 0.016 * i / 16 for i in range(17)], sides=12,
         noise_seed=wood.seed, noise_amp=0.3)
    # Branches reach up and toward the back (+y)
    for start, end, r0 in ((trunk[5], Vector((-0.11, 0.05, 0.25)), 0.018),
                           (trunk[10], Vector((0.11, -0.02, 0.18)), 0.014),
                           (trunk[13], Vector((0.23, 0.06, 0.09)), 0.010)):
      pts = span(start, end, 8)
      # Bow the branch out a little
      mid = Vector(((rng.random() - 0.5) * 0.04, (rng.random() - 0.5) * 0.04,
                    0))
      pts = [p + mid * math.sin(math.pi * i / 8) for i, p in enumerate(pts)]
      tube(bm, wiggle(pts, 0.003), [r0 * (1 - 0.75 * i / 8) for i in range(9)],
           sides=10, noise_seed=wood.seed + 1, noise_amp=0.25)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0),
                     matrix=mathutils.Matrix.Rotation(wood.yaw, 3, 'Z'))
    obj = link_object(scene, wood.name, finish_mesh(bm, wood.name, mat), tank)
    obj.location = (wood.x, wood.y, env.sand_height(wood.x, wood.y) - 0.008)


# Plants

def plant_material(name, caustic, base, tip, roughness, translucency,
                   vein=None, fuzz=0.0):
  mat, t, out = new_material(name)
  mat.use_backface_culling = False
  uv = t.add('ShaderNodeUVMap')
  uvs = t.add('ShaderNodeSeparateXYZ')
  t.link(uv.outputs['UV'], uvs.inputs[0])
  color = t.ramp(uvs.outputs['Y'], [(0.0, base), (1.0, tip)])
  streak = t.add('ShaderNodeTexNoise', Vector=object_coords(t),
                 Scale=40.0, Detail=3.0)
  color = t.mix(t.math('MULTIPLY', streak.outputs['Fac'], 0.35), color,
                (0.05, 0.12, 0.03, 1.0))
  if vein is not None:
    mid = t.math('ABSOLUTE', t.math('SUBTRACT', uvs.outputs['X'], 0.5))
    v = t.add('ShaderNodeMapRange', Value=mid, From_Min=0.02, From_Max=0.07,
              To_Min=0.6, To_Max=0.0)
    color = t.mix(v.outputs[0], color, vein)
  normal = None
  if fuzz:
    # Moss: a fine, deep bump of tiny fronds, darker in the hollows
    fronds = t.add('ShaderNodeTexNoise', Vector=object_coords(t),
                   Scale=160.0, Detail=2.0, Roughness=0.6)
    color = t.mix(t.math('MULTIPLY', fronds.outputs['Fac'], 0.8),
                  (0.01, 0.03, 0.01, 1.0), color)
    normal = bump(t, fronds.outputs['Fac'], fuzz, 0.002)
  bsdf = lit_surface(t, out, color, caustic_node(t, caustic),
                     roughness=roughness, strength=1.6, normal=normal)
  # Light through the leaf: mix in a translucent layer
  through = t.add('ShaderNodeBsdfTranslucent')
  t.link(color, through.inputs['Color'])
  both = t.add('ShaderNodeMixShader')
  both.inputs[0].default_value = translucency
  t.link(bsdf.outputs[0], both.inputs[1])
  t.link(through.outputs[0], both.inputs[2])
  t.link(both.outputs[0], out.inputs['Surface'])
  return mat


def leaf_bones(plant):
  return env.PLANT_BONES[plant.kind]


def bone_name(leaf, bone):
  return 'L%d.%d' % (leaf, bone)


def build_plants(scene, tank, caustic):
  mats = {
    'vallisneria': plant_material(
      'Vallisneria', caustic, (0.10, 0.22, 0.04), (0.30, 0.52, 0.12),
      0.5, 0.3),
    'sword': plant_material(
      'Sword', caustic, (0.04, 0.16, 0.03), (0.12, 0.36, 0.06), 0.35, 0.2,
      vein=(0.30, 0.48, 0.14, 1.0)),
    'moss': plant_material(
      'Moss', caustic, (0.03, 0.09, 0.02), (0.10, 0.26, 0.05), 0.9, 0.1,
      fuzz=0.9),
  }
  for plant in env.plants():
    build_plant(scene, tank, plant, mats[plant.kind])


def build_plant(scene, tank, plant, mat):
  """An armature with a bone chain per leaf, and the leaves skinned to it.

  Every leaf is a centerline from its base to its tip, with a profile
  across it; the leaf's bones run along the centerline, and each vertex
  is weighted to the bones near its distance along the leaf, with the
  static Root bone at the base, so the base stays planted.
  """
  rng = random.Random(plant.seed)
  x, y = plant.x, plant.y
  base_z = env.sand_height(x, y) - 0.004
  leaves = make_leaves(plant, rng)

  arm_data = bpy.data.armatures.new(plant.name + '.Rig')
  rig = link_object(scene, plant.name + '.Rig', arm_data, tank)
  rig.location = (x, y, base_z)
  # Bones can only be made in edit mode, with the rig active
  bpy.context.view_layer.objects.active = rig
  bpy.ops.object.mode_set(mode='EDIT')
  root = arm_data.edit_bones.new('Root')
  root.head, root.tail = (0, 0, -0.02), (0, 0, 0)
  bones = leaf_bones(plant)
  for li, leaf in enumerate(leaves):
    parent = root
    for b in range(bones):
      eb = arm_data.edit_bones.new(bone_name(li, b))
      eb.head = leaf['center'](b / bones)
      eb.tail = leaf['center']((b + 1) / bones)
      eb.roll = 0.0
      eb.parent = parent
      eb.use_connect = b > 0
      parent = eb
  bpy.ops.object.mode_set(mode='OBJECT')
  for pb in rig.pose.bones:
    pb.rotation_mode = 'XYZ'

  bm = bmesh.new()
  uv_layer = bm.loops.layers.uv.new('UVMap')
  deform = bm.verts.layers.deform.verify()
  groups = {'Root': 0}
  for li in range(len(leaves)):
    for b in range(bones):
      groups[bone_name(li, b)] = len(groups)
  for li, leaf in enumerate(leaves):
    add_leaf(bm, uv_layer, deform, groups, li, bones, leaf)
  mesh = finish_mesh(bm, plant.name, mat)
  obj = link_object(scene, plant.name, mesh, rig)
  for name in groups:
    obj.vertex_groups.new(name=name)
  mod = obj.modifiers.new('Rig', 'ARMATURE')
  mod.object = rig


def make_leaves(plant, rng):
  """Each leaf: its centerline function, width function and cross profile."""
  leaves = []
  h = plant.height
  for i in range(plant.count):
    yaw = 2 * math.pi * i / plant.count + rng.uniform(-0.4, 0.4)
    out = Vector((math.cos(yaw), math.sin(yaw), 0))
    side = Vector((-math.sin(yaw), math.cos(yaw), 0))
    spot = out * rng.uniform(0.0, 0.025)
    if plant.kind == 'vallisneria':
      # Long ribbons that lean out a little and arc over toward the tip,
      # the longest the most
      # (capped so that even the straightest stays under the surface)
      length = min(0.36, h * rng.uniform(0.75, 1.15))
      lean = rng.uniform(0.03, 0.2)
      arc = rng.uniform(0.2, 1.1) * length / h
      twist = rng.uniform(-1.5, 1.5)
      width = rng.uniform(0.005, 0.008)
      spot = out * rng.uniform(0.0, 0.04)
      wave = rng.uniform(0.01, 0.025)
      pts = [Vector(spot)]
      steps = 32
      for k in range(steps):
        s = (k + 0.5) / steps
        ang = lean + arc * s ** 1.6
        step = (out * math.sin(ang) + Vector((0, 0, math.cos(ang)))
                + side * (wave * math.cos(5 * s + yaw)))
        pts.append(pts[-1] + step.normalized() * (length / steps))

      def center(s, pts=pts, steps=steps):
        f = min(max(s, 0.0), 1.0) * steps
        k = min(int(f), steps - 1)
        return pts[k].lerp(pts[k + 1], f - k)

      def across(s, side=side, out=out, twist=twist, yaw=yaw):
        a = twist * s
        return side * math.cos(a) + out * math.sin(a)

      def wid(s, width=width):
        return width * (1.0 if s < 0.85 else (1 - s) / 0.15 * 0.9 + 0.1)
      segments = 16
    elif plant.kind == 'sword':
      length = h * rng.uniform(0.75, 1.1)
      tilt = rng.uniform(0.25, 0.75)
      width = rng.uniform(0.022, 0.03)

      def center(s, spot=spot, out=out, length=length, tilt=tilt):
        ang = tilt + 0.9 * tilt * s * s
        r = length * (s * math.sin(tilt) + 0.35 * s * s * math.sin(ang))
        z = length * (s * math.cos(tilt) - 0.25 * s * s * (1 - math.cos(ang)))
        return spot + out * r + Vector((0, 0, max(0.0, z)))

      def across(s, side=side):
        return side

      def wid(s, width=width):
        if s < 0.3:
          return 0.0025
        u = (s - 0.3) / 0.7
        return 0.0025 + width * math.sin(math.pi * min(1.0, u * 0.95)) ** 0.8
      segments = 14
    else:
      # A low cushion of small tufts, leaning out from the middle
      spread = rng.uniform(0.0, 1.0) ** 0.7
      length = h * rng.uniform(0.5, 1.0) * (1.1 - 0.5 * spread)
      spot = out * (0.045 * spread)
      width = rng.uniform(0.007, 0.013)

      def center(s, spot=spot, out=out, length=length, spread=spread):
        return spot + out * (0.4 * spread * length * s) + Vector(
          (0, 0, length * s))

      def across(s, side=side):
        return side

      def wid(s, width=width):
        return width * math.sin(math.pi * (0.15 + 0.7 * s))
      segments = 6
    leaves.append({'center': center, 'across': across, 'width': wid,
                   'segments': segments, 'fat': plant.kind == 'moss',
                   'seed': rng.random() * 100})
  return leaves


def add_leaf(bm, uv_layer, deform, groups, li, bones, leaf):
  """One leaf as a strip (or a lumpy tuft for moss), weighted to bones."""
  segs = leaf['segments']
  cols = 3 if not leaf['fat'] else 6
  rows = []
  for k in range(segs + 1):
    s = k / segs
    c = leaf['center'](s)
    a = leaf['across'](s)
    w = leaf['width'](s)
    row = []
    if leaf['fat']:
      # A lumpy ring around the centerline
      for j in range(cols):
        ang = 2 * math.pi * j / cols
        n = mathutils.noise.noise(c * 60 + Vector((leaf['seed'], j, 0)))
        off = (a * math.cos(ang) + a.cross(Vector((0, 0, 1))) *
               math.sin(ang)) * w * (1 + 0.4 * n)
        row.append((bm.verts.new(c + off), j / cols, s))
    else:
      # Left edge, raised midrib, right edge
      normal = a.cross((leaf['center'](min(1, s + 0.01)) -
                        leaf['center'](max(0, s - 0.01))).normalized())
      for j, (f, lift) in enumerate(((-1, 0), (0, 0.15), (1, 0))):
        row.append((bm.verts.new(c + a * (w * f) + normal * (w * lift)),
                    j / 2.0, s))
    for v, _, _ in row:
      set_weights(v[deform], groups, li, bones, s)
    rows.append(row)
  for r0, r1 in zip(rows, rows[1:]):
    n = len(r0) if leaf['fat'] else len(r0) - 1
    for j in range(n):
      j1 = (j + 1) % len(r0)
      quad = (r0[j], r0[j1], r1[j1], r1[j])
      face = bm.faces.new([q[0] for q in quad])
      for loop, (_, u, v) in zip(face.loops, quad):
        loop[uv_layer].uv = (u, v)
  if leaf['fat']:
    tip = bm.verts.new(leaf['center'](1.0) + Vector((0, 0, 0.002)))
    set_weights(tip[deform], groups, li, bones, 1.0)
    last = rows[-1]
    for j in range(len(last)):
      face = bm.faces.new((last[j][0], last[(j + 1) % len(last)][0], tip))
      for loop in face.loops:
        loop[uv_layer].uv = (0.5, 1.0)


def set_weights(dvert, groups, li, bones, s):
  """Blend between the bones around s along the leaf; Root at the base."""
  f = s * bones
  weights = {}
  for b in range(-1, bones):
    w = max(0.0, 1.0 - abs(f - (b + 0.5)))
    if w > 0:
      name = 'Root' if b < 0 else bone_name(li, b)
      weights[name] = w
  if s >= 1.0 - 1e-6:
    weights = {bone_name(li, bones - 1): 1.0}
  total = sum(weights.values())
  for name, w in weights.items():
    dvert[groups[name]] = w / total


# Airstone and bubbles

def build_airstone(scene, tank):
  mat, t, out = new_material('Airstone')
  co = object_coords(t)
  pores = t.add('ShaderNodeTexVoronoi', Vector=co, Scale=600.0)
  color = t.ramp(pores.outputs['Distance'], [(0.05, (0.12, 0.12, 0.13)),
                                              (0.3, (0.55, 0.55, 0.55))])
  bsdf = t.add('ShaderNodeBsdfPrincipled', Roughness=0.95,
               Normal=bump(t, pores.outputs['Distance'], 0.8, 0.0005))
  t.link(color, bsdf.inputs['Base Color'])
  t.link(bsdf.outputs[0], out.inputs['Surface'])

  bm = bmesh.new()
  bmesh.ops.create_cube(bm, size=1.0)
  sx, sy, sz = env.AIRSTONE_SIZE
  bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
  bmesh.ops.bevel(bm, geom=list(bm.edges), offset=sz * 0.35, segments=3,
                  affect='EDGES', profile=0.5)
  x, y = env.AIRSTONE_XY
  stone = link_object(scene, 'Airstone', finish_mesh(bm, 'Airstone', mat),
                      tank)
  stone.location = (x, y, env.sand_height(x, y) + sz * 0.3)

  # The air line, from the stone up the back corner and over the rim
  tube_mat, t, out = new_material('AirLine', blended=True)
  bsdf = t.add('ShaderNodeBsdfPrincipled', Roughness=0.25, Alpha=0.45,
               Base_Color=(0.75, 0.85, 0.8, 1.0))
  t.link(bsdf.outputs[0], out.inputs['Surface'])
  bm = bmesh.new()
  sxz = env.sand_height(x, y) + sz * 0.3
  pts = [Vector(p) for p in ((x + sx / 2, y, sxz), (x + 0.04, y + 0.01, sxz),
                             (0.475, 0.18, sxz + 0.04),
                             (0.478, 0.185, 0.3), (0.478, 0.185, env.TANK_H),
                             (0.47, 0.185, env.TANK_H + 0.03),
                             (0.50, 0.20, env.TANK_H + 0.05))]
  tube(bm, pts, [0.0025] * len(pts), sides=8)
  link_object(scene, 'AirLine', finish_mesh(bm, 'AirLine', tube_mat), tank,
              shadow=False)


def build_bubbles(scene, tank):
  """One unit-radius bubble per pool slot; the game scales and moves them."""
  mat, t, out = new_material('Bubble', blended=True)
  lw = t.add('ShaderNodeLayerWeight', Blend=0.35)
  rim = t.math('POWER', lw.outputs['Facing'], 2.0)
  clear = t.add('ShaderNodeBsdfTransparent')
  shell = t.add('ShaderNodeBsdfGlossy', Roughness=0.05,
                Color=(0.95, 1.0, 1.0, 1.0))
  glow = t.add('ShaderNodeEmission', Color=(0.8, 0.95, 1.0, 1.0),
               Strength=2.2)
  lit = t.add('ShaderNodeAddShader')
  t.link(shell.outputs[0], lit.inputs[0])
  t.link(glow.outputs[0], lit.inputs[1])
  # Mostly clear in the middle, a bright rim; fairly opaque overall, since
  # the player's frame accumulation fades small things that move fast
  mix = t.add('ShaderNodeMixShader')
  t.link(t.math('ADD', t.math('MULTIPLY', rim, 0.6), 0.4, clamp=True),
         mix.inputs[0])
  t.link(clear.outputs[0], mix.inputs[1])
  t.link(lit.outputs[0], mix.inputs[2])
  t.link(mix.outputs[0], out.inputs['Surface'])

  bm = bmesh.new()
  bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
  mesh = finish_mesh(bm, 'Bubble', mat)
  src = env.airstone_position()
  for i in range(sim_bubbles.CAPACITY):
    obj = link_object(scene, 'Bubble.%02d' % i, mesh, tank, shadow=False)
    obj.location = src
    obj.scale = (0.002,) * 3


# Light effects

def build_water_surface(scene, tank, caustic):
  """The surface seen from below: rippling, with bright caustic shimmer."""
  mat, t, out = new_material('WaterSurface', blended=True)
  # The same moving pattern as the caustics below, unfaded: seen from
  # below, the surface faces away from the light
  shimmer = caustic_node(t, caustic, 'Pattern')
  ripples = t.add('ShaderNodeTexNoise', Vector=object_coords(t, 1.0),
                  Scale=12.0, Detail=2.0)
  bsdf = t.add('ShaderNodeBsdfPrincipled', Roughness=0.05,
               Base_Color=(0.6, 0.85, 0.9, 1.0),
               Normal=bump(t, t.math('ADD', ripples.outputs['Fac'], shimmer),
                           0.5, 0.004))
  t.link(t.math('ADD', t.math('MULTIPLY', shimmer, 0.5), 0.3, clamp=True),
         bsdf.inputs['Alpha'])
  bsdf.inputs['Emission Color'].default_value = (0.75, 0.95, 1.0, 1.0)
  glow = t.math('MULTIPLY_ADD', shimmer, 1.2)
  glow.node.inputs[2].default_value = 0.1
  t.link(glow, bsdf.inputs['Emission Strength'])
  t.link(bsdf.outputs[0], out.inputs['Surface'])

  w = env.TANK_W - 2 * env.GLASS - 0.002
  d = env.TANK_D - 2 * env.GLASS - 0.002
  bm = bmesh.new()
  bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
  bmesh.ops.scale(bm, vec=(w, d, 1), verts=bm.verts)
  obj = link_object(scene, 'WaterSurface',
                    finish_mesh(bm, 'WaterSurface', mat), tank, shadow=False)
  obj.location = (0, 0, env.WATER_LEVEL + 0.0005)


def build_god_rays(scene, tank, caustic):
  """Soft slanted shafts of light under the surface, flickering slowly."""
  mat, t, out = new_material('GodRay', blended=True)
  mat.use_transparent_shadow = False
  uv = t.add('ShaderNodeUVMap')
  uvs = t.add('ShaderNodeSeparateXYZ')
  t.link(uv.outputs['UV'], uvs.inputs[0])
  across = t.math('SINE', t.math('MULTIPLY', uvs.outputs['X'], math.pi))
  across = t.math('POWER', across, 2.0)
  # Bright under the surface, gone well above the sand
  down = t.add('ShaderNodeMapRange', {'interpolation_type': 'SMOOTHSTEP'},
               Value=uvs.outputs['Y'], From_Min=0.0, From_Max=0.85,
               To_Min=0.0, To_Max=1.0)
  top = t.add('ShaderNodeMapRange', Value=uvs.outputs['Y'], From_Min=0.94,
              From_Max=1.0, To_Min=1.0, To_Max=0.0)
  # The flicker runs on the projector's time axis, like the caustics
  proj = t.add('ShaderNodeTexCoord', {'object': bpy.data.objects[PROJECTOR]})
  pxyz = t.add('ShaderNodeSeparateXYZ')
  t.link(proj.outputs['Object'], pxyz.inputs[0])
  flicker = t.add('ShaderNodeTexNoise', {'noise_dimensions': '4D'},
                  Vector=proj.outputs['Object'], Scale=2.0, Detail=1.0,
                  W=t.math('MULTIPLY', pxyz.outputs['Z'], CAUSTIC_W * 0.5))
  strength = t.math('MULTIPLY', t.math('MULTIPLY', across, down.outputs[0]),
                    top.outputs[0])
  strength = t.math('MULTIPLY', strength, t.math(
    'MULTIPLY_ADD', flicker.outputs['Fac'], 1.6))
  strength.node.inputs[2].default_value = -0.35
  strength = t.math('MULTIPLY', strength, 0.16, clamp=True)
  clear = t.add('ShaderNodeBsdfTransparent')
  glow = t.add('ShaderNodeEmission', Color=(1.0, 0.97, 0.85, 1.0),
               Strength=1.0)
  mix = t.add('ShaderNodeMixShader')
  t.link(strength, mix.inputs[0])
  t.link(clear.outputs[0], mix.inputs[1])
  t.link(glow.outputs[0], mix.inputs[2])
  t.link(mix.outputs[0], out.inputs['Surface'])

  top_z = env.WATER_LEVEL
  for i, (x, y, width, lean) in enumerate(((-0.30, 0.08, 0.10, 0.10),
                                           (-0.05, 0.02, 0.07, 0.12),
                                           (0.16, 0.10, 0.12, 0.09),
                                           (0.34, -0.02, 0.06, 0.11))):
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new('UVMap')
    length = top_z - 0.06
    corners = ((x - width / 2, top_z, 0, 1), (x + width / 2, top_z, 1, 1),
               (x + width / 2 + lean * 1.4, top_z - length, 1, 0),
               (x - width / 2 + lean, top_z - length, 0, 0))
    verts = [bm.verts.new((cx, y, cz)) for cx, cz, _, _ in corners]
    face = bm.faces.new(verts)
    for loop, (_, _, u, v) in zip(face.loops, corners):
      loop[uv_layer].uv = (u, v)
    link_object(scene, 'GodRay.%d' % i, finish_mesh(bm, 'GodRay.%d' % i, mat,
                                                    False), tank, shadow=False)


def glass_front_material():
  """Clear glass with faint diagonal sheens, the room reflected in it."""
  mat, t, out = new_material('GlassFront', blended=True)
  coords = t.add('ShaderNodeTexCoord')
  g = t.add('ShaderNodeSeparateXYZ')
  t.link(coords.outputs['Generated'], g.inputs[0])
  diag = t.math('ADD', t.math('MULTIPLY', g.outputs['X'], 0.55), g.outputs['Z'])
  bands = t.ramp(diag, [(0.38, (0, 0, 0)), (0.47, (1, 1, 1)),
                        (0.52, (0.25, 0.25, 0.25)), (0.56, (0, 0, 0)),
                        (0.86, (0, 0, 0)), (0.9, (0.6, 0.6, 0.6)),
                        (0.93, (0, 0, 0))])
  noise = t.add('ShaderNodeTexNoise', Vector=coords.outputs['Generated'],
                Scale=2.0)
  sheen = t.math('MULTIPLY', t.add('ShaderNodeRGBToBW', Color=bands),
                 t.math('ADD', noise.outputs['Fac'], 0.3))
  clear = t.add('ShaderNodeBsdfTransparent', Color=(0.93, 0.98, 0.97, 1.0))
  glossy = t.add('ShaderNodeBsdfGlossy', Roughness=0.02)
  glow = t.add('ShaderNodeEmission', Color=(0.85, 0.9, 1.0, 1.0),
               Strength=1.0)
  shine = t.add('ShaderNodeAddShader')
  t.link(glossy.outputs[0], shine.inputs[0])
  t.link(glow.outputs[0], shine.inputs[1])
  lw = t.add('ShaderNodeLayerWeight', Blend=0.2)
  fac = t.math('ADD', t.math('MULTIPLY', sheen, 0.07),
               t.math('MULTIPLY', lw.outputs['Fresnel'], 0.12))
  mix = t.add('ShaderNodeMixShader')
  t.link(fac, mix.inputs[0])
  t.link(clear.outputs[0], mix.inputs[1])
  t.link(shine.outputs[0], mix.inputs[2])
  t.link(mix.outputs[0], out.inputs['Surface'])
  return mat
