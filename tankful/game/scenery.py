"""Animates the tank's scenery each frame: caustics, plant sway, bubbles.

The objects come from tools/build_scene.py (and tools/scene_env.py),
named after tankful.sim.environment's layout:

- CausticProjector: an empty whose space every caustic, shimmer and
  god-ray shader reads; sinking it runs the pattern's time axis and
  drifting it moves the pattern across the tank.  The shaders read where
  it is from their object's color (PROJECTOR_SPACE), which is set on
  every such object as it moves: reading the moving empty itself would
  cost far more (docs/harness.md, "Frame budget").
- <plant>.Rig: an armature per plant with a chain of bones L<leaf>.<bone>
  per leaf, bent by tankful.sim.sway.
- Bubble.NN: one object per slot of the tankful.sim.bubbles pool, moved,
  scaled and hidden to match it.
"""

import logging
import math

from tankful.sim import bubbles as sim_bubbles
from tankful.sim import environment as env
from tankful.sim import sway

log = logging.getLogger('tankful.scenery')

PROJECTOR = 'CausticProjector'
# How far the projector sinks per second: the caustics' pace.  The player
# accumulates frames to clean up soft shadows (see setup_render in
# tools/build_scene.py), which smears shading that changes quickly: much
# faster than this and the caustics wash out to a flat glow
CAUSTIC_SPEED = 0.1
# The node group of the shaders that read the projector's place from
# their object's color, and what is added to its drift there to keep it
# positive (tools/scene_env.py, projector_space_group)
PROJECTOR_SPACE = 'ProjectorSpace'
CAUSTIC_BIAS = 1.0


class Scenery:

  def __init__(self, scene, pool=None):
    objects = scene.objects
    self.projector = objects.get(PROJECTOR)
    if self.projector is None:
      log.warning('no %s in the scene: caustics stay still', PROJECTOR)
    self._projector_home = (list(self.projector.worldPosition)
                            if self.projector is not None else None)
    self.caustic_followers = [obj for obj in objects
                              if reads_group(obj, PROJECTOR_SPACE)]
    self.plants = []
    for plant in env.plants():
      rig = objects.get(plant.name + '.Rig')
      if rig is None:
        log.warning('no rig for plant %s', plant.name)
        continue
      bones = env.PLANT_BONES[plant.kind]
      chains = [[rig.channels['L%d.%d' % (leaf, b)] for b in range(bones)]
                for leaf in range(plant.count)]
      self.plants.append((plant, rig, chains))
    self.pool = pool or sim_bubbles.BubblePool(env.airstone_position(),
                                               env.WATER_LEVEL)
    self.bubbles = []
    for i in range(self.pool.capacity):
      obj = objects.get('Bubble.%02d' % i)
      if obj is None:
        log.warning('the scene has %d bubble objects for a pool of %d', i,
                    self.pool.capacity)
        break
      obj.visible = False
      self.bubbles.append(obj)

  def update(self, t, dt):
    self._move_projector(t)
    self._sway(t)
    self.pool.step(dt)
    self._place_bubbles()

  def _move_projector(self, t):
    if self.projector is None:
      return
    x, y, z = self._projector_home
    # Sinking runs the pattern's time; a slow drift slides it along
    dx = 0.02 * math.sin(0.05 * t) + 0.003 * t
    dy = 0.015 * math.cos(0.04 * t)
    sunk = CAUSTIC_SPEED * t
    self.projector.worldPosition = (x + dx, y + dy, z - sunk)
    color = (dx + CAUSTIC_BIAS, dy + CAUSTIC_BIAS, sunk, 1.0)
    for obj in self.caustic_followers:
      obj.color = color

  def _sway(self, t):
    for plant, rig, chains in self.plants:
      for leaf, chain in enumerate(chains):
        angles = sway.chain_angles(t, len(chain), plant.phase,
                                   plant.amplitude, plant.frequency, leaf)
        for channel, (bend_x, bend_y) in zip(chain, angles):
          channel.rotation_euler = (bend_x, 0.0, bend_y)
      rig.update()

  def _place_bubbles(self):
    for bubble, obj in zip(self.pool.bubbles, self.bubbles):
      if not bubble.active:
        if obj.visible:
          obj.visible = False
        continue
      obj.worldPosition = (bubble.x, bubble.y, bubble.z)
      r = bubble.radius
      if bubble.state == sim_bubbles.POPPING:
        # Flatten into the surface as it bursts
        obj.worldScale = (r, r, r * (1 - 0.7 * bubble.pop_progress))
      else:
        obj.worldScale = (r, r, r * 0.92)
      if not obj.visible:
        obj.visible = True

  def snapshot(self):
    return {
      'bubbles': self.pool.snapshot(),
      'plants': len(self.plants),
      'caustic_followers': len(self.caustic_followers),
      'projector': [round(v, 3) for v in self.projector.worldPosition]
      if self.projector is not None else None,
    }


def reads_group(obj, group_name):
  """Whether a material of obj (a KX_GameObject) uses the node group
  group_name, in its node tree or in a group within it."""
  blender_obj = getattr(obj, 'blenderObject', None)
  if blender_obj is None:
    return False
  return any(slot.material is not None
             and tree_uses(slot.material.node_tree, group_name, set())
             for slot in blender_obj.material_slots)


def tree_uses(tree, group_name, seen):
  """Whether node tree uses the group group_name, at any depth; seen holds
  the names of the groups already looked through."""
  if tree is None:
    return False
  for node in tree.nodes:
    if node.bl_idname != 'ShaderNodeGroup' or node.node_tree is None:
      continue
    name = node.node_tree.name
    if name == group_name:
      return True
    if name not in seen:
      seen.add(name)
      if tree_uses(node.node_tree, group_name, seen):
        return True
  return False
