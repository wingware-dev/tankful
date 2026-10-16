import random
import unittest

from tankful.sim import environment as env
from tankful.sim import surfaces
from tankful.sim import vec


class SandTest(unittest.TestCase):

  def test_back_bounds_the_sand(self):
    rng = random.Random(3)
    for back in (-0.05, 0.0, 0.05):
      sand = surfaces.Sand(0.02, back)
      for _ in range(100):
        x, y, z = sand.random_point(rng)
        self.assertLessEqual(y, back)
        self.assertAlmostEqual(z, env.sand_height(x, y))

  def test_clamp_pulls_points_in_front_of_back(self):
    sand = surfaces.Sand(0.02, -0.05)
    x, y, z = sand.clamp((0.0, env.INNER_Y, 0.0))
    self.assertLessEqual(y, -0.05)

  def test_edges_measure_to_back(self):
    sand = surfaces.Sand(0.02, 0.01)
    gap, way_in = sand.edges((0.0, -0.04, 0.0))[3]
    self.assertAlmostEqual(gap, 0.05)
    self.assertEqual(way_in, (0.0, -1.0, 0.0))


class GeometryTest(unittest.TestCase):

  def test_ease_is_clamped_and_smooth(self):
    self.assertEqual(surfaces.ease(-1.0), 0.0)
    self.assertEqual(surfaces.ease(2.0), 1.0)
    self.assertAlmostEqual(surfaces.ease(0.5), 0.5)

  def test_tangent(self):
    up = (0.0, 0.0, 1.0)
    t = surfaces.tangent((2.0, 0.0, 3.0), up)
    for a, b in zip(t, (1.0, 0.0, 0.0)):
      self.assertAlmostEqual(a, b)
    self.assertIsNone(surfaces.tangent((0.0, 0.0, 2.0), up))

  def test_turned_and_signed_angle_agree(self):
    up = (0.0, 0.0, 1.0)
    h = (1.0, 0.0, 0.0)
    for angle in (-2.0, -0.3, 0.0, 0.7, 3.0):
      t = surfaces.turned(h, up, angle)
      self.assertAlmostEqual(vec.length(t), 1.0)
      self.assertAlmostEqual(surfaces.signed_angle(h, t, up), angle)

  def test_spot_fields(self):
    self.assertEqual(surfaces.Spot._fields,
                     ('surface', 'point', 'normal', 'heading'))


if __name__ == '__main__':
  unittest.main()
