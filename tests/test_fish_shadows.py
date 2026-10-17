import ast
import math
import os
import unittest
from unittest import mock
from types import SimpleNamespace

from tankful.game import fishes
from tankful.sim import environment as env
from tankful.sim import vec
from tankful.sim.species import angelfish
from tankful.sim.tank import Tank


class FakeFish:

  def __init__(self, x, y, z, yaw=0.0, pitch=0.0, name='angelfish',
               length=0.12):
    self.x, self.y, self.z = x, y, z
    self.yaw, self.pitch = yaw, pitch
    self.length = length
    self.species = SimpleNamespace(name=name)

  def orientation(self):
    cy, sy = math.cos(self.yaw), math.sin(self.yaw)
    cp, sp = math.cos(self.pitch), math.sin(self.pitch)
    m = ((cp, 0.0, -sp), (0.0, 1.0, 0.0), (sp, 0.0, cp))
    return tuple(tuple(cy * m[0][j] - sy * m[1][j] if i == 0 else
                       sy * m[0][j] + cy * m[1][j] if i == 1 else m[2][j]
                       for j in range(3)) for i in range(3))


def area(scale):
  return scale[0] * scale[1]


def halo_scales(rise):
  floor = env.sand_height(0.0, 0.0)
  return fishes.shadow_pose(FakeFish(0.0, 0.0, floor + rise))[2]


def full_halo(rise):
  """The area of a halo disc at rise had none switched off yet."""
  with mock.patch.object(fishes, 'HALO_HOLD', 10.0), \
       mock.patch.object(fishes, 'HALO_GONE', 11.0):
    return area(halo_scales(rise)[fishes.SHADOW_ROOT])


class ShadowPoseTest(unittest.TestCase):

  def test_lies_on_the_sand_under_the_fish(self):
    f = FakeFish(0.1, 0.05, 0.3)
    pos, rot, _ = fishes.shadow_pose(f)
    self.assertAlmostEqual(pos[0], f.x, delta=0.002)
    self.assertAlmostEqual(pos[1], f.y, delta=0.002)
    floor = env.sand_height(f.x, f.y)
    self.assertGreater(pos[2], floor)
    self.assertLess(pos[2], floor + 2 * fishes.SHADOW_LIFT)
    # The disc's normal leans with the sand, but stays nearly upright
    up = vec.rotation(rot)[2][2]
    self.assertGreater(up, 0.95)

  def test_faces_the_fish_heading(self):
    f = FakeFish(0.0, 0.0, 0.2, yaw=math.pi / 2)
    _, rot, _ = fishes.shadow_pose(f)
    m = vec.rotation(rot)
    # The disc's x axis (its length) runs along +y with the fish, tilted
    # up the sand's slope toward the back
    self.assertAlmostEqual(m[0][0], 0.0, delta=0.05)
    self.assertGreater(m[1][0], 0.95)

  def test_fades_as_the_fish_rises(self):
    floor = env.sand_height(0.0, 0.0)
    low, mid, top = (fishes.shadow_pose(FakeFish(0.0, 0.0, floor + rise))[2]
                     for rise in (0.01, 0.1, 0.42))
    for part in fishes.HALO:
      self.assertGreater(area(low[part]), area(low['Umbra']))
    # The core shrinks away while the halo spreads...
    self.assertLess(area(mid['Umbra']), area(low['Umbra']) / 4)
    for part in fishes.HALO:
      self.assertGreater(area(mid[part]), area(low[part]))
    # ...and near the surface all of it is gone
    for part in fishes.SHADOW_PARTS:
      self.assertEqual(area(top[part]), 0.0)

  def test_halo_switches_off_one_by_one(self):
    # Below HALO_HOLD the discs lie one on another, the same size
    held = halo_scales(fishes.HALO_HOLD - 0.001)
    for part in fishes.HALO:
      self.assertEqual(held[part], held[fishes.HALO[0]])
    # Then each is gone when the next has shrunk by half, and the last one
    # held at full size until the first is half gone
    span = fishes.HALO_GONE - fishes.HALO_HOLD
    for i, (part, after) in enumerate(zip(fishes.HALO, fishes.HALO[1:])):
      gone = fishes.HALO_HOLD + span * (
        fishes.HALO_BAND + i * (1 - fishes.HALO_BAND) / (len(fishes.HALO) - 1))
      scales = halo_scales(gone + 1e-6)
      self.assertEqual(area(scales[part]), 0.0)
      self.assertAlmostEqual(area(scales[after]) / full_halo(gone), 0.25,
                             delta=0.01)
    rise = fishes.HALO_HOLD + span * fishes.HALO_BAND / 2
    self.assertEqual(area(halo_scales(rise)[fishes.SHADOW_ROOT]),
                     full_halo(rise))

  def test_halo_darkness_falls_steadily(self):
    # The share of the full halo's darkness its discs, each as faint as
    # the others, still cover falls at every step from HALO_HOLD to
    # HALO_GONE, no step by more than twice the average
    n = 60
    span = fishes.HALO_GONE - fishes.HALO_HOLD
    covered = []
    for k in range(n + 1):
      rise = fishes.HALO_HOLD + span * k / n
      scales = halo_scales(rise)
      covered.append(sum(area(scales[part]) for part in fishes.HALO)
                     / (len(fishes.HALO) * full_halo(rise)))
    drops = [a - b for a, b in zip(covered, covered[1:])]
    self.assertAlmostEqual(covered[0], 1.0)
    self.assertTrue(all(d > 0 for d in drops[1:-1]), drops)
    self.assertLess(max(drops), 2.0 / n)
    self.assertEqual(covered[-1], 0.0)

  def test_relative_scales(self):
    f = FakeFish(0.0, 0.0, env.sand_height(0.0, 0.0) + 0.05)
    scales = fishes.shadow_pose(f)[2]
    relative = fishes.relative_scales(scales)
    self.assertEqual(set(relative),
                     set(fishes.SHADOW_PARTS) - {fishes.SHADOW_ROOT})
    root = scales[fishes.SHADOW_ROOT]
    for part, scale in relative.items():
      for i in range(2):
        self.assertAlmostEqual(root[i] * scale[i], scales[part][i])
      self.assertEqual(scale[2], 1.0)

  def test_relative_scales_of_a_vanished_root(self):
    scales = {part: (0.0, 0.0, 1.0) for part in fishes.SHADOW_PARTS}
    self.assertEqual(set(fishes.relative_scales(scales).values()),
                     {(0.0, 0.0, 1.0)})

  def test_footprint_shortens_when_nosing_down(self):
    level = FakeFish(0.0, 0.0, 0.2)
    diving = FakeFish(0.0, 0.0, 0.2, pitch=1.2)
    self.assertLess(fishes.shadow_pose(diving)[2]['Umbra'][0],
                    fishes.shadow_pose(level)[2]['Umbra'][0] / 2)

  def test_straight_up_still_has_a_shadow(self):
    f = FakeFish(0.0, 0.0, 0.2, pitch=math.pi / 2)
    _, rot, scales = fishes.shadow_pose(f)
    self.assertTrue(all(v > 0 for v in scales['Umbra']))
    self.assertTrue(all(math.isfinite(v) for v in rot))


class Channel:

  def __init__(self):
    self.location = None
    self.rotation_quaternion = None
    self.rotation_euler = None
    self.scale = None


class FishesShadowTest(unittest.TestCase):

  def test_places_only_the_root_bone(self):
    tank = Tank()
    angels = angelfish.stock(tank)
    rigs = {}
    for f in angels:
      rigs[f.name + '.Rig'] = SimpleNamespace(
        name=f.name + '.Rig', update=lambda: None,
        channels={bone: Channel() for bone in angelfish.BONES})
    shadow_channels = {'%s:%s' % (f.name, part): Channel()
                       for f in angels for part in fishes.SHADOW_PARTS}
    updates = []
    rig = SimpleNamespace(name=fishes.SHADOW_RIG, channels=shadow_channels,
                          worldPosition=None,
                          update=lambda: updates.append(1))
    scene = SimpleNamespace(objects=dict(rigs, **{rig.name: rig}))
    driver = fishes.Fishes(scene, angels)
    self.assertEqual(driver.snapshot()['shadows'], len(angels))
    driver.update()
    self.assertEqual(updates, [1])
    for f in angels:
      pos, rot, scales = fishes.shadow_pose(f)
      root = shadow_channels['%s:%s' % (f.name, fishes.SHADOW_ROOT)]
      self.assertEqual(root.location, pos)
      self.assertEqual(root.rotation_quaternion, rot)
      self.assertEqual(root.scale, scales[fishes.SHADOW_ROOT])
      relative = fishes.relative_scales(scales)
      for part in relative:
        child = shadow_channels['%s:%s' % (f.name, part)]
        self.assertIsNone(child.location)
        self.assertIsNone(child.rotation_quaternion)
        self.assertEqual(child.scale, relative[part])

  def test_missing_bone_warns(self):
    tank = Tank()
    angels = angelfish.stock(tank)
    rigs = {f.name + '.Rig': SimpleNamespace(
              name=f.name + '.Rig', update=lambda: None,
              channels={bone: Channel() for bone in angelfish.BONES})
            for f in angels}
    # Built before the halo had more than one disc
    shadow_channels = {'%s:%s' % (f.name, part): Channel()
                       for f in angels for part in ('Umbra', 'Penumbra')}
    rig = SimpleNamespace(name=fishes.SHADOW_RIG, channels=shadow_channels)
    scene = SimpleNamespace(objects=dict(rigs, **{rig.name: rig}))
    with self.assertLogs('tankful.fishes', 'WARNING'):
      driver = fishes.Fishes(scene, angels)
    self.assertEqual(driver.snapshot()['shadows'], 0)


class BuilderAgreesTest(unittest.TestCase):
  """tools/scene_fish.py runs in Blender, so can't import the game's
  names: it repeats them, and they must agree."""

  def test_same_parts(self):
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        'tools', 'scene_fish.py')
    with open(path) as fh:
      tree = ast.parse(fh.read())
    values = {}
    for node in tree.body:
      if (isinstance(node, ast.Assign) and len(node.targets) == 1
          and isinstance(node.targets[0], ast.Name)):
        try:
          values[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
          pass
    self.assertEqual(values['SHADOW_RIG'], fishes.SHADOW_RIG)
    self.assertEqual(values['HALO'], fishes.HALO)


if __name__ == '__main__':
  unittest.main()
