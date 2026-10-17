import json
import math
import unittest

from tankful.game.main import parse_size
from tankful.sim.species import angelfish
from tankful.sim.species import neon_tetra
from tankful.sim.tank import Tank, factor_species, shift_band


class TankTests(unittest.TestCase):

  def test_step_and_snapshot(self):
    tank = Tank()
    tank.step(0.5)
    tank.step(0.25)
    snap = tank.snapshot()
    self.assertEqual(snap['frame'], 2)
    self.assertAlmostEqual(snap['time'], 0.75)
    self.assertEqual(snap['fish'], [])
    json.dumps(snap)

  def test_negative_dt(self):
    with self.assertRaises(ValueError):
      Tank().step(-0.1)


class ShiftBandTests(unittest.TestCase):

  def test_none_keeps_the_band(self):
    self.assertEqual(shift_band((0.3, 0.6), 0.0), (0.3, 0.6))

  def test_full_shifts_reach_either_end(self):
    lo, hi = shift_band((0.3, 0.6), 1.0)
    self.assertAlmostEqual(lo, 0.7)
    self.assertAlmostEqual(hi, 1.0)
    lo, hi = shift_band((0.3, 0.6), -1.0)
    self.assertAlmostEqual(lo, 0.0)
    self.assertAlmostEqual(hi, 0.3)

  def test_half_shift_goes_half_way_and_keeps_width(self):
    lo, hi = shift_band((0.2, 0.5), -0.5)
    self.assertAlmostEqual(lo, 0.1)
    self.assertAlmostEqual(hi - lo, 0.3)

  def test_out_of_range_is_clamped(self):
    self.assertEqual(shift_band((0.3, 0.6), 3.0), shift_band((0.3, 0.6), 1.0))


class FactorSpeciesTests(unittest.TestCase):

  def test_speeds_scale_and_bands_shift(self):
    s = angelfish.SPECIES
    f = factor_species(s, 0.5, -1.0)
    self.assertAlmostEqual(f.cruise_speed, s.cruise_speed * 0.5)
    self.assertAlmostEqual(f.hover_speed, s.hover_speed * 0.5)
    self.assertAlmostEqual(f.max_speed, s.max_speed * 0.5)
    self.assertAlmostEqual(f.depth_band[0], 0.0)
    self.assertAlmostEqual(f.night.depth_band[0], 0.0)
    self.assertEqual(f.name, s.name)
    self.assertEqual(f.length, s.length)


class TankFactorTests(unittest.TestCase):

  def setUp(self):
    self.tank = Tank()
    angelfish.stock(self.tank)
    neon_tetra.stock(self.tank)
    self.own = {id(f): f.species for f in self.tank.fish + self.tank.schools}

  def test_neutral_changes_nothing(self):
    self.tank.set_factor()
    self.tank.step(0.1)
    for f in self.tank.fish + self.tank.schools:
      self.assertIs(f.species, self.own[id(f)])

  def test_factor_swaps_in_shared_species_and_back(self):
    self.tank.set_factor(0.5, 0.5)
    self.tank.step(0.1)
    by_name = {}
    for f in self.tank.fish + self.tank.schools:
      own = self.own[id(f)]
      self.assertIsNot(f.species, own)
      self.assertAlmostEqual(f.species.cruise_speed, own.cruise_speed * 0.5)
      # Fish of a kind share one species, as they tell each other apart
      # by it
      self.assertIs(by_name.setdefault(own.name, f.species), f.species)
    self.tank.set_factor()
    self.tank.step(0.1)
    for f in self.tank.fish + self.tank.schools:
      self.assertIs(f.species, self.own[id(f)])

  def test_small_changes_reuse_the_species(self):
    self.tank.set_factor(0.8, 0.0)
    self.tank.step(0.1)
    first = self.tank.fish[0].species
    self.tank.set_factor(0.8001, 0.0004)
    self.tank.step(0.1)
    self.assertIs(self.tank.fish[0].species, first)
    self.tank.set_factor(0.9, 0.0)
    self.tank.step(0.1)
    self.assertIsNot(self.tank.fish[0].species, first)
    self.assertAlmostEqual(self.tank.fish[0].species.cruise_speed,
                           self.own[id(self.tank.fish[0])].cruise_speed * 0.9)

  def test_snapshot_shows_the_factor(self):
    self.tank.set_factor(1.2, -0.3)
    self.assertEqual(self.tank.snapshot()['factor'],
                     {'speed_scale': 1.2, 'depth_shift': -0.3})

  def test_slower_fish_cover_less_ground(self):
    def travel(scale):
      tank = Tank()
      angelfish.stock(tank)
      tank.set_factor(scale, 0.0)
      start = [(f.x, f.y, f.z) for f in tank.fish]
      for _ in range(300):
        tank.step(1 / 60)
      return sum(math.dist(p, (f.x, f.y, f.z))
                 for p, f in zip(start, tank.fish))
    self.assertLess(travel(0.4), travel(1.0) * 0.8)


class ParseSizeTests(unittest.TestCase):

  def test_parse_size(self):
    self.assertEqual(parse_size('1280x720'), (1280, 720))
    self.assertEqual(parse_size('640X480'), (640, 480))
    for bad in ('', '1', 'x', '12xab', '-1x5'):
      self.assertIsNone(parse_size(bad), bad)


if __name__ == '__main__':
  unittest.main()
