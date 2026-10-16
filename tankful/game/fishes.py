"""Puts each simulated fish's pose on its model every frame.

tools/scene_fish.py builds, per fish, <name>.Rig: an armature that
carries the body and fin meshes.  Each frame the rig takes the fish's
position and orientation (tankful.sim.fish), and its bones the swim pose
(tankful.sim.swim; the pleco's mouth bones scale as well), so all the
animation is object and bone transforms:
no shader parameters are written per frame (docs/harness.md).

A school (tools/scene_tetra.py) is one armature, <school>.Rig, for all
its members: each member's bones are prefixed with its name, and its
Root bone takes its position and orientation instead of an object.  The
player spends time on every object that moves, so a school moves one
object, not one per fish.
"""

import logging

from tankful.sim import swim
from tankful.sim import vec

log = logging.getLogger('tankful.fishes')


class Fishes:

  def __init__(self, scene, fish):
    objects = scene.objects
    # (fish, rig object, {bone: channel}) for fish with rigs of their own,
    # and (fish, Root channel, {bone: channel}) for school members
    self.rigs = []
    self.members = []
    self.school_rigs = []
    for f in fish:
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
      for bone in swim.bones(f.species):
        channel = rig.channels.get(prefix + bone)
        if channel is None:
          log.warning('fish %s has no bone %s', f.name, bone)
          continue
        channels[bone] = channel
      if f.school is None:
        self.rigs.append((f, rig, channels))
        continue
      root = rig.channels.get(prefix + 'Root')
      if root is None:
        log.warning('fish %s has no Root bone in %s', f.name, rig.name)
        continue
      self.members.append((f, root, channels))
      if rig not in self.school_rigs:
        self.school_rigs.append(rig)

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

  @staticmethod
  def _pose(f, channels):
    pose = swim.pose(f)
    for bone, channel in channels.items():
      channel.rotation_euler = pose[bone]
    for bone, scale in swim.scales(f).items():
      if bone in channels:
        channels[bone].scale = scale

  def snapshot(self):
    return {'rigs': [f.name for f, _, _ in self.rigs],
            'school_rigs': [rig.name for rig in self.school_rigs],
            'members': len(self.members)}
