import json
import math
import statistics
import unittest

from tankful.sim import daynight
from tankful.sim import environment as env
from tankful.sim import vec
from tankful.sim.daynight import Light, Night
from tankful.sim.species import (angelfish, cherry_shrimp, corydoras, guppy,
                                 honey_gourami, neon_tetra, pleco)
from tankful.sim.tank import Tank

DT = 1 / 60.0


def run(tank, seconds, each=None):
  for i in range(int(round(seconds / DT))):
    tank.step(DT)
    if each is not None and i % 10 == 0:
      each(tank)


def plant_gap(f):
  """How far f is from the leaves of the nearest plant clump (m)."""
  p = (f.x, f.y, f.z)
  return min(math.dist(p, vec.closest_on_segment(p, o.a, o.b))
             - f.clearance(o) for o in env.obstacles() if o.soft)


def height(f):
  """f's height in the open water, 0 on the sand to 1 at the surface."""
  floor = env.sand_height(f.x, f.y)
  return (f.z - floor) / (env.WATER_LEVEL - floor)


class Watch:
  """A tank of one species, run by day or into the night, and what its
  fish did: their mean height, speed, plant gap and time hovering, the
  school's spread, and how many moves (darts or hops) they made."""

  WARM, SETTLE, SPAN = 20.0, 30.0, 60.0

  def __init__(self, module, night):
    tank = Tank()
    module.stock(tank)
    run(tank, self.WARM)
    if night:
      tank.light.set(False)
    run(tank, self.SETTLE)
    self.tank = tank
    moves0 = self.moves()
    self.heights, self.speeds, self.gaps, self.hover, self.spread = (
      [], [], [], [], [])

    def each(tank):
      for f in tank.fish:
        self.heights.append(height(f))
        self.speeds.append(f.speed)
        self.gaps.append(plant_gap(f))
        self.hover.append(f.mode == 'hover')
      for s in tank.schools:
        if hasattr(s, 'spread'):
          self.spread.append(s.spread())
    run(tank, self.SPAN, each)
    self.moved = self.moves() - moves0

  def moves(self):
    return sum(getattr(f, 'darts', 0) + getattr(f, 'hops', 0)
               for f in self.tank.fish)

  def mean(self, name):
    return statistics.mean(getattr(self, name))


class DayAndNight:
  """Each species' tank watched by day and by night, once per run."""

  _watches = {}

  @classmethod
  def get(cls, module):
    if module not in cls._watches:
      cls._watches[module] = (Watch(module, False), Watch(module, True))
    return cls._watches[module]


class LightTests(unittest.TestCase):

  def test_starts_as_day(self):
    light = Light()
    self.assertTrue(light.on)
    self.assertEqual((light.level, light.night), (1.0, 0.0))
    self.assertFalse(light.fading)
    self.assertEqual(Light(on=False).level, 0.0)

  def test_fades_to_night_over_the_transition(self):
    light = Light(transition=4.0)
    self.assertTrue(light.set(False))
    self.assertFalse(light.set(False))
    self.assertEqual(light.switches, 1)
    levels = []
    for _ in range(4 * 60):
      light.step(DT)
      levels.append(light.level)
    self.assertAlmostEqual(levels[0], 1.0, places=3)
    self.assertAlmostEqual(levels[len(levels) // 2 - 1], 0.5, places=6)
    self.assertAlmostEqual(levels[-1], 0.0, places=9)
    # Down all the way, and eased: slowest at both ends
    self.assertTrue(all(b <= a for a, b in zip(levels, levels[1:])))
    steps = [a - b for a, b in zip(levels, levels[1:])]
    self.assertLess(steps[0], steps[len(steps) // 2] / 10)
    self.assertLess(steps[-1], steps[len(steps) // 2] / 10)
    light.step(10.0)
    self.assertEqual(light.night, 1.0)
    self.assertFalse(light.fading)

  def test_toggling_midway_turns_back_from_where_it_is(self):
    light = Light(transition=6.0)
    light.toggle()
    light.step(2.0)
    self.assertTrue(light.fading)
    mid = light.level
    self.assertTrue(light.toggle())
    light.step(DT)
    self.assertGreater(light.level, mid)
    light.step(2.0 - DT)
    self.assertAlmostEqual(light.level, 1.0)

  def test_moon_hook(self):
    light = Light()
    self.assertEqual(light.moon, daynight.MOON_DEFAULT)
    light.set_moon(0.8)
    self.assertEqual(light.moon, 0.8)
    light.set_moon(3)
    self.assertEqual(light.moon, 1.0)
    light.set_moon(-1)
    self.assertEqual(light.moon, 0.0)

  def test_bad_values(self):
    with self.assertRaises(ValueError):
      Light(transition=0)
    with self.assertRaises(ValueError):
      Light().step(-0.1)

  def test_snapshot(self):
    light = Light()
    light.toggle()
    light.step(1.0)
    snap = light.snapshot()
    self.assertEqual(snap['on'], False)
    self.assertTrue(snap['fading'])
    self.assertAlmostEqual(snap['level'] + snap['night'], 1.0)
    json.dumps(snap)


class LookTests(unittest.TestCase):

  def test_day(self):
    day = daynight.look(1.0)
    self.assertEqual(day.lamp, daynight.DAY_LAMP)
    self.assertEqual(day.lamp_color, daynight.DAY_LAMP_COLOR)
    self.assertEqual(day.caustics, 1.0)
    self.assertEqual(day.bubble_rate, 1.0)
    self.assertEqual(day.panel, (1.0, 1.0, 1.0))
    # The moon makes no difference by day
    self.assertEqual(daynight.look(1.0, 0.0), daynight.look(1.0, 1.0))

  def test_night_is_dim_blue_moonlight(self):
    night = daynight.look(0.0)
    self.assertLess(night.lamp, daynight.DAY_LAMP / 4)
    r, g, b = night.lamp_color
    self.assertGreater(b, g)
    self.assertGreater(g, r)
    self.assertLess(night.caustics, 0.25)
    self.assertLess(night.bubble_rate, 0.5)
    self.assertLess(max(night.bubbles), 0.5)
    self.assertLess(max(night.panel), 0.25)
    self.assertTrue(all(n < d for n, d in zip(night.room, daynight.DAY_ROOM)))

  def test_moon_brightens_the_night(self):
    new, full = daynight.look(0.0, 0.0), daynight.look(0.0, 1.0)
    self.assertLess(new.lamp, full.lamp)
    self.assertLess(new.caustics, full.caustics)
    self.assertLess(full.lamp, daynight.DAY_LAMP / 4)

  def test_between(self):
    mid = daynight.look(0.5)
    night, day = daynight.look(0.0), daynight.look(1.0)
    self.assertLess(night.lamp, mid.lamp)
    self.assertLess(mid.lamp, day.lamp)
    self.assertEqual(daynight.look(-1), night)
    self.assertEqual(daynight.look(2), day)


class FactorTests(unittest.TestCase):

  def test_no_night_changes_nothing(self):
    for name in ('speed', 'hover', 'activity', 'loosen'):
      self.assertEqual(daynight.factor(pleco.SPECIES._replace(night=None),
                                       name, 1.0), 1.0)
    self.assertEqual(daynight.depth_band(angelfish.SPECIES, 0.0),
                     angelfish.SPECIES.depth_band)

  def test_blended_by_how_far_into_the_night(self):
    species = angelfish.SPECIES._replace(
      night=Night(speed=0.5, depth_band=(0.0, 0.2)))
    self.assertEqual(daynight.factor(species, 'speed', 0.0), 1.0)
    self.assertAlmostEqual(daynight.factor(species, 'speed', 0.5), 0.75)
    self.assertAlmostEqual(daynight.factor(species, 'speed', 1.0), 0.5)
    lo, hi = daynight.depth_band(species, 0.5)
    self.assertAlmostEqual(lo, 0.2)
    self.assertAlmostEqual(hi, 0.5)

  def test_every_species_has_a_night(self):
    for module in (angelfish, neon_tetra, guppy, honey_gourami, corydoras,
                   pleco, cherry_shrimp):
      self.assertIsInstance(module.SPECIES.night, Night, module.__name__)

  def test_the_tank_tells_the_fish(self):
    tank = Tank()
    angelfish.stock(tank)
    neon_tetra.stock(tank)
    tank.step(DT)
    self.assertTrue(all(f.night == 0.0 for f in tank.fish))
    self.assertEqual(tank.fish[0].by_night('speed'), 1.0)
    tank.light.set(False)
    self.assertFalse(tank.light_on)
    run(tank, tank.light.transition / 2)
    self.assertAlmostEqual(tank.fish[0].night, 0.5, places=2)
    self.assertEqual(tank.schools[0].night, tank.fish[0].night)
    run(tank, tank.light.transition)
    self.assertEqual(tank.fish[0].night, 1.0)
    self.assertAlmostEqual(tank.fish[0].by_night('speed'),
                           angelfish.SPECIES.night.speed)
    snap = tank.snapshot()
    self.assertEqual(snap['light']['night'], 1.0)
    self.assertFalse(snap['light_on'])


class NightBehaviorTests(unittest.TestCase):
  """Each species by day and at night, the same fish from the same seeds."""

  def test_tetras_slow_loosen_and_rest_low(self):
    day, night = DayAndNight.get(neon_tetra)
    self.assertLess(night.mean('speeds'), 0.6 * day.mean('speeds'))
    self.assertLess(night.mean('heights'), day.mean('heights') - 0.08)
    self.assertLess(night.mean('heights'), 0.33)
    self.assertGreater(night.mean('spread'), 1.25 * day.mean('spread'))

  def test_angelfish_hover_near_the_plants(self):
    day, night = DayAndNight.get(angelfish)
    self.assertLess(night.mean('speeds'), 0.6 * day.mean('speeds'))
    self.assertGreater(night.mean('hover'), 2 * day.mean('hover'))
    self.assertLessEqual(night.mean('gaps'), day.mean('gaps') + 0.005)
    self.assertLess(night.mean('gaps'), 0.09)

  def test_gourami_hover_near_the_plants(self):
    day, night = DayAndNight.get(honey_gourami)
    self.assertLess(night.mean('speeds'), 0.6 * day.mean('speeds'))
    self.assertGreater(night.mean('hover'), 1.5 * day.mean('hover'))
    self.assertLess(night.mean('gaps'), 0.75 * day.mean('gaps'))

  def test_guppies_rest_near_the_surface(self):
    day, night = DayAndNight.get(guppy)
    self.assertLess(night.mean('speeds'), 0.5 * day.mean('speeds'))
    self.assertGreater(night.mean('heights'), day.mean('heights') + 0.08)
    self.assertGreater(night.mean('heights'), 0.85)
    self.assertGreater(night.mean('hover'), 5 * max(day.mean('hover'), 0.01))

  def test_nocturnal_species_are_busier(self):
    for module in (corydoras, pleco, cherry_shrimp):
      day, night = DayAndNight.get(module)
      self.assertGreater(night.moved, 1.3 * day.moved, module.__name__)
      self.assertGreater(night.mean('speeds'), 1.2 * day.mean('speeds'),
                         module.__name__)


if __name__ == '__main__':
  unittest.main()
