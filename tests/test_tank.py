import json
import math
import unittest

from tankful.game.main import parse_size
from tankful.sim import fish as fish_mod
from tankful.sim.species import angelfish
from tankful.sim.species import guppy
from tankful.sim.species import neon_tetra
from tankful.sim.tank import (MIN_SURFACE_MARGIN, Tank, factor_species,
                               lift_margin, shift_band)


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
    self.assertAlmostEqual(lo, 0.85)
    self.assertAlmostEqual(hi, 1.0)
    lo, hi = shift_band((0.3, 0.6), -1.0)
    self.assertAlmostEqual(lo, 0.0)
    self.assertAlmostEqual(hi, 0.15)

  def test_half_shift_moves_the_center_half_way_and_keeps_width(self):
    lo, hi = shift_band((0.2, 0.5), -0.5)
    self.assertAlmostEqual((lo + hi) / 2, 0.175)
    self.assertAlmostEqual(hi - lo, 0.3)
    lo, hi = shift_band((0.2, 0.5), 0.5)
    self.assertAlmostEqual((lo + hi) / 2, 0.675)
    self.assertAlmostEqual(hi - lo, 0.3)

  def test_high_bands_rise_most_of_their_room(self):
    # The day bands of angelfish, guppies and tetras: a 0.8 up day lifts
    # each center by over half the room above it (shift * (1 - hi), all
    # an up day once had, left guppies 0.06 higher), as a down day sinks
    # it by over half the room below
    for band in ((0.4, 0.8), (0.55, 0.93), (0.3, 0.62)):
      center = sum(band) / 2
      up = sum(shift_band(band, 0.8)) / 2 - center
      down = center - sum(shift_band(band, -0.8)) / 2
      self.assertGreater(up, 0.5 * (1 - center), band)
      self.assertGreater(up, 0.12, band)
      self.assertGreater(down, 0.5 * center, band)
    # The gourami's band is at the surface already: it stays there,
    # squeezed only to the minimum width
    lo, hi = shift_band((0.86, 1.0), 0.8)
    self.assertEqual(hi, 1.0)
    self.assertAlmostEqual(lo, 0.88)

  def test_bands_stay_within_the_tank(self):
    for band in ((0.0, 0.1), (0.0, 0.2), (0.0, 1.0), (0.4, 0.8),
                 (0.86, 1.0), (0.9, 1.0)):
      for shift in (-1.0, -0.9, -0.4, 0.4, 0.8, 1.0):
        lo, hi = shift_band(band, shift)
        self.assertGreaterEqual(lo, 0.0, (band, shift))
        self.assertLessEqual(hi, 1.0, (band, shift))
        self.assertGreaterEqual(hi - lo, min(0.12, band[1] - band[0]) - 1e-9)
        self.assertLessEqual(hi - lo, band[1] - band[0] + 1e-9)

  def test_sand_bands_stay_on_the_sand_on_down_days(self):
    # Corydoras and cherry shrimp
    for band in ((0.0, 0.1), (0.0, 0.2)):
      for shift in (-0.2, -0.9, -1.0):
        lo, hi = shift_band(band, shift)
        self.assertAlmostEqual(lo, 0.0)
        self.assertLessEqual(hi, band[1])
        self.assertGreaterEqual(hi, min(0.12, band[1]))

  def test_squeezed_bands_keep_a_minimum_width(self):
    lo, hi = shift_band((0.55, 0.93), 1.0)
    self.assertAlmostEqual(hi, 1.0)
    self.assertAlmostEqual(hi - lo, 0.19)
    lo, hi = shift_band((0.4, 0.8), -0.95)
    self.assertAlmostEqual(lo, 0.0)
    self.assertGreaterEqual(hi - lo, 0.12)

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

  def test_up_shifts_let_fish_nearer_the_surface(self):
    s = guppy.SPECIES
    self.assertIsNone(s.surface_margin)
    up = factor_species(s, 1.0, 0.8)
    self.assertLess(up.surface_margin, fish_mod.MARGIN)
    self.assertGreaterEqual(up.surface_margin, MIN_SURFACE_MARGIN)
    self.assertLessEqual(up.night.surface_margin, s.night.surface_margin)
    down = factor_species(s, 1.0, -0.8)
    self.assertIsNone(down.surface_margin)
    self.assertEqual(down.night.surface_margin, s.night.surface_margin)

  def test_lift_margin(self):
    self.assertAlmostEqual(lift_margin(None, 0.0), fish_mod.MARGIN)
    self.assertAlmostEqual(lift_margin(None, 1.0), MIN_SURFACE_MARGIN)
    self.assertAlmostEqual(lift_margin(0.1, 0.5),
                           (0.1 + MIN_SURFACE_MARGIN) / 2)
    self.assertEqual(lift_margin(0.02, 1.0), 0.02)
    self.assertAlmostEqual(lift_margin(0.1, 3.0), MIN_SURFACE_MARGIN)


class DepthShiftSwimTests(unittest.TestCase):
  """Guppies, which swim near the surface, rise visibly on an up day,
  though they have only about 0.1 m above them to rise into (an up day
  once lifted them under 0.01 m), and sink on a down day."""

  def mean_height(self, shift):
    tank = Tank()
    guppy.stock(tank)
    tank.set_factor(1.0, shift)
    heights = []
    for i in range(30 * 60):
      tank.step(1 / 60)
      if i >= 10 * 60 and i % 30 == 0:
        heights.extend(f.z for f in tank.fish)
    return sum(heights) / len(heights)

  def test_up_lifts_and_down_sinks(self):
    neutral = self.mean_height(0.0)
    up = self.mean_height(0.8) - neutral
    down = neutral - self.mean_height(-0.8)
    self.assertGreater(up, 0.03)
    self.assertGreater(down, 0.1)


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
                     {'speed_scale': 1.2, 'depth_shift': -0.3,
                      'skittish': 0.0, 'flicker': 0.0, 'startles': 0})
    self.tank.set_factor(1.0, 0.0, skittish=0.8, flicker=1.0)
    factor = self.tank.snapshot()['factor']
    self.assertEqual((factor['skittish'], factor['flicker']), (0.8, 1.0))

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
