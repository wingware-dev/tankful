"""Animates the tank's scenery each frame: caustics, plant sway, bubbles.

The objects come from tools/build_scene.py (and tools/scene_env.py),
named after tankful.sim.environment's layout:

- CausticProjector: an empty whose space every caustic, shimmer and
  god-ray shader reads; sinking it runs the pattern's time axis and
  drifting it moves the pattern across the tank.  The shaders read where
  it is from their object's color (PROJECTOR_SPACE), which is set on
  every such object as it moves: reading the moving empty itself would
  cost far more (docs/harness.md, "Frame budget").  The color's alpha is
  the caustics' strength, dimmed at night (set_look).
- <plant>.Rig: an armature per plant with a chain of bones L<leaf>.<bone>
  per leaf, bent by tankful.sim.sway.
- Bubble.NN: one object per slot of the tankful.sim.bubbles pool, moved,
  scaled and hidden to match it.
- Ripples: a disc under the surface over the bubble stream, which draws
  the ripple pool's rings, spreading and fading as its color says.
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
# The object that draws the ripples (tools/scene_env.py, build_ripples)
RIPPLES = 'Ripples'


class Scenery:

  def __init__(self, scene, pool=None, ripples=None):
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
    self.ripple_pool = ripples or sim_bubbles.RipplePool()
    self.ripple_obj = objects.get(RIPPLES)
    if self.ripple_obj is None:
      log.warning('no %s in the scene: bubbles pop without ripples', RIPPLES)
    elif len(self.ripple_pool.ripples) > 3:
      raise ValueError('the %s object draws 3 ripples, not %d' % (
        RIPPLES, len(self.ripple_pool.ripples)))
    self._ripple_color = None
    # The day's look until set_look says otherwise
    self._day_rate = self.pool.rate
    self.caustics = 1.0
    self.glow = 1.0
    self._bubble_color = (1.0, 1.0, 1.0, 1.0)
    self._bubbles_tinted = self._bubble_color

  def set_look(self, look):
    """Show the caustics, god rays, bubbles and ripples as look (a
    tankful.sim.daynight.Look) says: dimmer at night, and fewer
    bubbles."""
    self.caustics = look.caustics
    self.glow = sum(look.bubbles) / 3.0
    self._bubble_color = tuple(look.bubbles) + (1.0,)
    self.pool.rate = self._day_rate * look.bubble_rate

  def update(self, t, dt):
    self._move_projector(t)
    self._sway(t)
    self.pool.step(dt)
    self._place_bubbles()
    self.ripple_pool.step(dt)
    for x, y, size in self.pool.pop_events:
      self.ripple_pool.start(x, y)
    self._place_ripples()

  def _move_projector(self, t):
    if self.projector is None:
      return
    x, y, z = self._projector_home
    # Sinking runs the pattern's time; a slow drift slides it along
    dx = 0.02 * math.sin(0.05 * t) + 0.003 * t
    dy = 0.015 * math.cos(0.04 * t)
    sunk = CAUSTIC_SPEED * t
    self.projector.worldPosition = (x + dx, y + dy, z - sunk)
    # Its alpha is the caustics' strength (tools/scene_env.py,
    # projector_space_group)
    color = (dx + CAUSTIC_BIAS, dy + CAUSTIC_BIAS, sunk, self.caustics)
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
    if self._bubble_color != self._bubbles_tinted:
      # Their glow's tint (tools/scene_env.py, build_bubbles): only while
      # the light fades
      for obj in self.bubbles:
        obj.color = self._bubble_color
      self._bubbles_tinted = self._bubble_color
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

  def _place_ripples(self):
    # One object draws every ripple, each slot's progress in a channel of
    # its color (tools/scene_env.py, build_ripples): a ring object of its
    # own per ripple, moved and faded each frame, cost about 0.13 ms of
    # Depsgraph apiece (docs/harness.md, "Frame budget")
    if self.ripple_obj is None:
      return
    progress = self.ripple_pool.progresses()
    # Alpha is the rings' brightness
    color = progress + (1.0,) * (3 - len(progress)) + (self.glow,)
    if color != self._ripple_color:
      self.ripple_obj.color = color
      self._ripple_color = color

  def snapshot(self):
    return {
      'bubbles': self.pool.snapshot(),
      'ripples': self.ripple_pool.snapshot(),
      'plants': len(self.plants),
      'caustic_followers': len(self.caustic_followers),
      'caustics': round(self.caustics, 3),
      'bubble_rate': round(self.pool.rate, 3),
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
