import math
import unittest

from tankful.sim import environment as env
from tankful.sim import sway
from tankful.sim.tank import Tank


class SandTests(unittest.TestCase):

  def test_slopes_up_toward_the_back(self):
    for x in (-0.4, -0.1, 0.0, 0.2, 0.45):
      # The viewer is at -y
      front = env.sand_height(x, -env.INNER_Y)
      back = env.sand_height(x, env.INNER_Y)
      self.assertGreater(back - front, 0.03, x)

  def test_stays_in_a_sane_band(self):
    for i in range(41):
      for j in range(21):
        x = -env.INNER_X + 2 * env.INNER_X * i / 40
        y = -env.INNER_Y + 2 * env.INNER_Y * j / 20
        h = env.sand_height(x, y)
        self.assertGreater(h, env.GLASS + 0.01)
        self.assertLess(h, 0.12)

  def test_not_flat(self):
    # Dunes and ripples across the tank at one depth
    hs = [env.sand_height(-0.45 + 0.9 * i / 50, 0.0) for i in range(51)]
    self.assertGreater(max(hs) - min(hs), 0.005)


class LayoutTests(unittest.TestCase):

  def test_matches_the_tank(self):
    tank = Tank()
    self.assertEqual((tank.width, tank.depth, tank.height),
                     (env.TANK_W, env.TANK_D, env.TANK_H))
    self.assertLess(env.WATER_LEVEL, env.TANK_H)

  def test_everything_inside_the_glass(self):
    for item in env.rocks() + env.driftwood() + env.plants():
      self.assertTrue(env.inside(item.x, item.y, 0.02), item.name)
    self.assertTrue(env.inside(*env.AIRSTONE_XY, margin=0.02))

  def test_names_are_unique(self):
    names = [item.name for item in env.rocks() + env.driftwood() + env.plants()]
    self.assertEqual(len(names), len(set(names)))

  def test_plants(self):
    plants = env.plants()
    kinds = {p.kind for p in plants}
    self.assertEqual(kinds, {'vallisneria', 'sword', 'moss'})
    for p in plants:
      self.assertIn(p.kind, env.PLANT_BONES)
      self.assertGreater(p.count, 0)
      self.assertGreater(p.height, 0)
      self.assertLess(env.sand_height(p.x, p.y) + p.height, env.WATER_LEVEL)

  def test_deterministic(self):
    self.assertEqual(env.plants(), env.plants())

  def test_airstone_on_the_sand(self):
    x, y, z = env.airstone_position()
    self.assertEqual((x, y), env.AIRSTONE_XY)
    self.assertGreater(z, env.sand_height(x, y))
    self.assertLess(z, env.WATER_LEVEL - 0.2)


class SwayTests(unittest.TestCase):

  def test_current_range(self):
    for i in range(2000):
      c = sway.current(i * 0.37)
      self.assertGreaterEqual(c, 0.35 - 1e-9)
      self.assertLessEqual(c, 1.0 + 1e-9)

  def test_tip_lean_bounded(self):
    for bones in (1, 3, 4):
      for i in range(500):
        angles = sway.chain_angles(i * 0.1, bones, 0.7, 0.16, 0.3, leaf=i % 5)
        self.assertEqual(len(angles), bones)
        total_x = sum(a[0] for a in angles)
        total_y = sum(a[1] for a in angles)
        self.assertLessEqual(abs(total_x), 1.2 * 0.16 + 1e-9)
        self.assertLessEqual(abs(total_y), 1.2 * 0.16 + 1e-9)

  def test_tip_bends_most(self):
    peaks = [0.0] * 4
    for i in range(1000):
      for b, (ax, ay) in enumerate(sway.chain_angles(i * 0.05, 4, 0.0, 0.2,
                                                     0.3)):
        peaks[b] = max(peaks[b], math.hypot(ax, ay))
    self.assertEqual(peaks, sorted(peaks))
    self.assertGreater(peaks[-1], 2 * peaks[0])

  def test_moves_over_time(self):
    a = sway.chain_angles(1.0, 4, 0.3, 0.16, 0.3)
    b = sway.chain_angles(1.5, 4, 0.3, 0.16, 0.3)
    self.assertNotEqual(a, b)

  def test_leaves_differ(self):
    a = sway.chain_angles(2.0, 3, 0.3, 0.1, 0.3, leaf=0)
    b = sway.chain_angles(2.0, 3, 0.3, 0.1, 0.3, leaf=1)
    self.assertNotEqual(a, b)

  def test_still_without_amplitude(self):
    for bend in sway.chain_angles(3.0, 4, 0.3, 0.0, 0.3):
      self.assertEqual(bend, (0.0, 0.0))

  def test_no_bones(self):
    self.assertEqual(sway.chain_angles(1.0, 0, 0.0, 0.1, 0.3), [])


class ObstacleTests(unittest.TestCase):

  def test_wraps_all_the_decor(self):
    names = [o.name for o in env.obstacles()]
    self.assertEqual(len(names), len(set(names)))
    for item in env.rocks() + env.plants():
      self.assertIn(item.name, names)
    self.assertTrue(any(n.startswith('Driftwood.') for n in names))

  def test_inside_the_tank_from_the_sand_up(self):
    for o in env.obstacles():
      for x, y, z in (o.a, o.b):
        self.assertTrue(env.inside(x, y), o.name)
        self.assertGreater(z, 0.0, o.name)
        self.assertLess(z, env.WATER_LEVEL, o.name)
      self.assertGreater(o.radius, 0.0)
      # Only plants are soft
      self.assertEqual(o.soft, not o.name.startswith(('Rock', 'Driftwood')))


if __name__ == '__main__':
  unittest.main()
