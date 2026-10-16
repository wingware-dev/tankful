"""Puts each simulated fish's pose on its model every frame.

tools/scene_fish.py builds, per fish, <name>.Rig: an armature that
carries the body and fin meshes.  Each frame the rig takes the fish's
position and orientation (tankful.sim.fish), and its bones the swim pose
(tankful.sim.swim), so all the animation is object and bone transforms:
no shader parameters are written per frame (docs/harness.md).
"""

import logging

from tankful.sim import swim

log = logging.getLogger('tankful.fishes')


class Fishes:

  def __init__(self, scene, fish):
    objects = scene.objects
    self.rigs = []
    for f in fish:
      rig = objects.get(f.name + '.Rig')
      if rig is None:
        log.warning('no rig for fish %s', f.name)
        continue
      channels = {}
      for bone in swim.BONES:
        channel = rig.channels.get(bone)
        if channel is None:
          log.warning('fish %s has no bone %s', f.name, bone)
          continue
        channels[bone] = channel
      self.rigs.append((f, rig, channels))

  def update(self):
    for f, rig, channels in self.rigs:
      rig.worldPosition = (f.x, f.y, f.z)
      rig.worldOrientation = f.orientation()
      for bone, angles in swim.pose(f).items():
        channel = channels.get(bone)
        if channel is not None:
          channel.rotation_euler = angles
      rig.update()

  def snapshot(self):
    return {'rigs': [f.name for f, _, _ in self.rigs]}
