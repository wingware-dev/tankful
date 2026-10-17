import math
import unittest
from types import SimpleNamespace

from tankful.game import fishes
from tankful.sim import environment as env
from tankful.sim import vec


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
    self.assertGreater(area(low['Penumbra']), area(low['Umbra']))
    # The core shrinks away while the halo spreads...
    self.assertLess(area(mid['Umbra']), area(low['Umbra']) / 4)
    self.assertGreater(area(mid['Penumbra']), area(low['Penumbra']))
    # ...and near the surface both are gone
    self.assertEqual(area(top['Umbra']), 0.0)
    self.assertEqual(area(top['Penumbra']), 0.0)

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


if __name__ == '__main__':
  unittest.main()
