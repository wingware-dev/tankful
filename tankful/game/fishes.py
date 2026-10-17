"""Puts each simulated fish's pose on its model every frame.

The model builder (tools/species/<name>.py) makes, per fish, <name>.Rig:
an armature that carries the body and fin meshes.  Each frame the rig
takes the fish's position and orientation (tankful.sim.fish), and its
bones the pose of its species' module (tankful.sim.species.<name>: BONES,
pose and scales; the pleco's mouth bones scale as well), so all the
animation is object and bone transforms:
no shader parameters are written per frame (docs/harness.md).

A school (tools/species/neon_tetra.py) is one armature, <school>.Rig,
for all its members: each member's bones are prefixed with its name, and
its Root bone takes its position and orientation instead of an object.
The player spends time on every object that moves, so a school moves one
object, not one per fish.

Each fish's shadow is two discs on the sand under it, a dark core and a
fainter halo, each on a bone of FishShadows.Rig (tools/scene_fish.py,
build_shadows): shadow_pose places and scales them each frame, the core
shrinking away and the halo spreading, then shrinking, as the fish
rises, so the shadow fades with the fish's height.  The whole tank's
shadows move one object.
"""

import logging
import math

from tankful.sim import environment as env
from tankful.sim import species
from tankful.sim import vec

log = logging.getLogger('tankful.fishes')

SHADOW_RIG = 'FishShadows.Rig'

# A fish's shadow from above, across the body, as a fraction of its length
SHADOW_WIDTH = {'angelfish': 0.22, 'pleco': 0.4, 'corydoras': 0.4,
                'honey_gourami': 0.32, 'cherry_shrimp': 0.3}
DEFAULT_SHADOW_WIDTH = 0.3
# How high above the sand (m) the core has shrunk away
CORE_GONE = 0.16
# How far the halo spreads beyond the footprint on each side: on the sand,
# in footprint widths, then per meter above the sand, to at most HALO_MAX
# (m).  Above HALO_HOLD (m) it shrinks, to nothing at HALO_GONE, so the
# shadows of fish near the surface fade away
HALO_BASE = 1.0
HALO_SPREAD = 0.3
HALO_MAX = 0.06
HALO_HOLD = 0.1
HALO_GONE = 0.4
# How far above the sand the discs float, so the sand doesn't cut into
# them, and the span the sand's slope is measured over (m): wider than
# its ripples, which the soft discs needn't follow
SHADOW_LIFT = 0.004
SLOPE_SPAN = 0.03


def shadow_pose(f):
  """Where f's shadow is: (position, rotation quaternion (w, x, y, z),
  {'Umbra': scale, 'Penumbra': scale}), each scale (x, y, z) of a disc of
  unit diameter turned to f's heading and laid on the sand under it."""
  m = f.orientation()
  length = f.length
  width = length * SHADOW_WIDTH.get(f.species.name, DEFAULT_SHADOW_WIDTH)
  # The footprint: shortened as the fish noses up or down
  fx, fy = m[0][0], m[1][0]
  along = math.hypot(fx, fy)
  if along > 1e-6:
    fx, fy = fx / along, fy / along
  else:
    fx, fy = 1.0, 0.0
  foot = max(length * along, width)
  floor = env.sand_height(f.x, f.y)
  rise = max(0.0, f.z - floor)
  # The sand's normal, over SLOPE_SPAN
  d = SLOPE_SPAN / 2
  gx = (env.sand_height(f.x + d, f.y) - env.sand_height(f.x - d, f.y)) / (2 * d)
  gy = (env.sand_height(f.x, f.y + d) - env.sand_height(f.x, f.y - d)) / (2 * d)
  n = vec.normalized((-gx, -gy, 1.0))
  # The disc's x along the heading, laid in the sand's plane
  ax = vec.normalized(vec.sub((fx, fy, 0.0),
                              vec.scale(n, fx * n[0] + fy * n[1])))
  ay = vec.cross(n, ax)
  rot = tuple((ax[i], ay[i], n[i]) for i in range(3))
  pos = vec.add((f.x, f.y, floor), vec.scale(n, SHADOW_LIFT))
  core = 1.0 - min(1.0, rise / CORE_GONE)
  halo = width * HALO_BASE + min(HALO_MAX, HALO_SPREAD * rise)
  fade = 1.0 - _smoothstep((rise - HALO_HOLD) / (HALO_GONE - HALO_HOLD))
  return pos, vec.quaternion(rot), {
    'Umbra': (foot * core, width * core, 1.0),
    'Penumbra': ((foot + 2 * halo) * fade, (width + 2 * halo) * fade, 1.0)}


def _smoothstep(t):
  t = min(1.0, max(0.0, t))
  return t * t * (3 - 2 * t)


class Fishes:

  def __init__(self, scene, fish):
    objects = scene.objects
    # (fish, rig object, {bone: channel}) for fish with rigs of their own,
    # and (fish, Root channel, {bone: channel}) for school members
    self.rigs = []
    self.members = []
    self.school_rigs = []
    # What scales each fish: its rig, or its Root bone (set_scale)
    self._scalers = {}
    present = set(species.present())
    for f in fish:
      if f.species.name not in present:
        # Its modules aren't all written yet: the registry logged it
        continue
      if f.school is not None:
        rig = objects.get(f.school.name + '.Rig')
        prefix = f.name + ':'
      else:
        rig = objects.get(f.name + '.Rig')
        prefix = ''
      if rig is None:
        log.warning('no rig for fish %s', f.name)
        continue
      channels = {}
      for bone in species.of(f.species).BONES:
        channel = rig.channels.get(prefix + bone)
        if channel is None:
          log.warning('fish %s has no bone %s', f.name, bone)
          continue
        channels[bone] = channel
      if f.school is None:
        self.rigs.append((f, rig, channels))
        self._scalers[f] = (rig, None)
        continue
      root = rig.channels.get(prefix + 'Root')
      if root is None:
        log.warning('fish %s has no Root bone in %s', f.name, rig.name)
        continue
      self.members.append((f, root, channels))
      self._scalers[f] = (None, root)
      if rig not in self.school_rigs:
        self.school_rigs.append(rig)
    # (fish, Umbra channel, Penumbra channel)
    self.shadows = []
    self.shadow_rig = objects.get(SHADOW_RIG)
    if self.shadow_rig is None:
      log.warning('no %s: the fish have no shadows', SHADOW_RIG)
      return
    for f, _, _ in self.rigs + self.members:
      parts = [self.shadow_rig.channels.get('%s:%s' % (f.name, part))
               for part in ('Umbra', 'Penumbra')]
      if None in parts:
        log.warning('fish %s has no shadow bones in %s', f.name, SHADOW_RIG)
        continue
      self.shadows.append((f,) + tuple(parts))

  def update(self):
    for f, rig, channels in self.rigs:
      rig.worldPosition = (f.x, f.y, f.z)
      rig.worldOrientation = f.orientation()
      self._pose(f, channels)
      rig.update()
    for f, root, channels in self.members:
      # The Root bone's rest frame is the rig's, and the rig sits at the
      # origin unturned, so its pose is the fish's place in the tank
      root.location = (f.x, f.y, f.z)
      root.rotation_quaternion = vec.quaternion(f.orientation())
      self._pose(f, channels)
    for rig in self.school_rigs:
      # The player re-evaluates a pose only for an armature whose object
      # was moved this frame: update() alone leaves the school frozen
      rig.worldPosition = (0.0, 0.0, 0.0)
      rig.update()
    if self.shadows:
      for f, umbra, penumbra in self.shadows:
        pos, rot, scales = shadow_pose(f)
        for channel, part in ((umbra, 'Umbra'), (penumbra, 'Penumbra')):
          channel.location = pos
          channel.rotation_quaternion = rot
          channel.scale = scales[part]
      # Re-evaluated only when moved, as the schools are
      self.shadow_rig.worldPosition = (0.0, 0.0, 0.0)
      self.shadow_rig.update()

  def drawn(self):
    """The fish with a rig to draw them."""
    return set(self._scalers)

  def set_scale(self, f, scale):
    """Draw f scale times its size (tankful.game.steering), leaving its
    shadow be: its rig scaled, or a school member's Root bone, both kept
    until set again."""
    rig, root = self._scalers.get(f, (None, None))
    if rig is not None:
      rig.localScale = (scale, scale, scale)
    elif root is not None:
      root.scale = (scale, scale, scale)

  @staticmethod
  def _pose(f, channels):
    mod = species.of(f.species)
    pose = mod.pose(f)
    for bone, channel in channels.items():
      channel.rotation_euler = pose[bone]
    for bone, scale in mod.scales(f).items():
      if bone in channels:
        channels[bone].scale = scale

  def snapshot(self):
    return {'rigs': [f.name for f, _, _ in self.rigs],
            'school_rigs': [rig.name for rig in self.school_rigs],
            'members': len(self.members),
            'shadows': len(self.shadows)}
