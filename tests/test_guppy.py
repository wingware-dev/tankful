import math
import unittest

from tankful.sim import species
from tankful.sim import steering
from tankful.sim import swim
from tankful.sim import vec
from tankful.sim.school import group_of
from tankful.sim.species import angelfish, guppy, neon_tetra, pleco
from tankful.sim.species.guppy import SPECIES as GUPPY
from tankful.sim.tank import Tank

DT = 1 / 60.0


def alone():
  """A tank with the guppies and nothing else."""
  tank = Tank()
  return tank, guppy.stock(tank)


def stocked():
  """The whole tank as the registry stocks it, the guppies after the
  angelfish, the school and the pleco."""
  tank = Tank()
  angelfish.stock(tank)
  neon_tetra.stock(tank)
  pleco.stock(tank)
  return tank, guppy.stock(tank)


def run(tank, seconds):
  for _ in range(int(round(seconds / DT))):
    tank.step(DT)
    yield tank.time


def depth_fraction(f):
  """Where f is between the bottom (0) and top (1) of its swim box."""
  _, _, (z0, z1) = f.bounds()
  return (f.z - z0) / (z1 - z0)


class GuppyStockTests(unittest.TestCase):

  def test_shoal(self):
    tank, gs = alone()
    self.assertEqual(len(gs), 6)
    self.assertEqual(tank.fish, gs)
    shoal = tank.schools[0]
    self.assertEqual(shoal.name, guppy.SHOAL)
    self.assertEqual(shoal.members, gs)
    for g in gs:
      # The fish driver finds the shoal's one rig through its school
      self.assertIs(g.school, shoal)
      self.assertIs(group_of(g), shoal)
      self.assertIn(g, shoal)
    self.assertEqual(len(shoal.males()), 3)
    self.assertEqual(len(shoal.females()), 3)
    self.assertEqual(len({g.name for g in gs}), 6)
    self.assertEqual(len({g.rng.random() for g in gs}), 6)

  def test_males_are_smaller(self):
    _, gs = alone()
    males = [g.length for g in gs if g.male]
    females = [g.length for g in gs if not g.male]
    self.assertLess(max(males), min(females))

  def test_residents_match_stock(self):
    tank, gs = alone()
    for (res, sex), g in zip(guppy.residents(), gs):
      self.assertEqual((res.name, sex, res.size), (g.name, g.sex, g.size))
      self.assertEqual(res.start[:3], (g.x, g.y, g.z))
      self.assertIs(res.species, GUPPY)

  def test_bad_sex(self):
    with self.assertRaises(ValueError):
      guppy.Guppy('G', GUPPY, 'neither')

  def test_shoal_steps_as_a_school_does(self):
    tank, _ = alone()
    shoal = tank.schools[0]
    shoal.step(DT)
    shoal.settle()
    snap = tank.snapshot()
    self.assertEqual(snap['schools'][0]['name'], guppy.SHOAL)
    self.assertEqual(snap['fish'][0]['sex'], guppy.MALE)
    self.assertIn('chasing', snap['fish'][0])

  def test_the_others_stock_as_before(self):
    # Stocked after the others, the guppies leave their fish as they were
    tank, gs = stocked()
    self.assertEqual(len(tank.fish), 24)
    self.assertEqual(tank.fish[18:], gs)
    self.assertEqual(tank.fish[17].name, 'Pleco')
    self.assertEqual([s.name for s in tank.schools],
                     ['NeonTetras', guppy.SHOAL])


class GuppySwimTests(unittest.TestCase):

  def test_quick(self):
    # In body lengths per second they cruise faster than the angelfish
    rel = GUPPY.cruise_speed / GUPPY.length
    self.assertGreater(rel, angelfish.SPECIES.cruise_speed
                       / angelfish.SPECIES.length * 2)
    self.assertGreater(GUPPY.max_turn_rate, angelfish.SPECIES.max_turn_rate)

  def test_stay_mid_to_top(self):
    tank, gs = stocked()
    fracs = []
    for t in run(tank, 120):
      if t > 10:
        fracs.extend(depth_fraction(g) for g in gs)
    fracs.sort()
    self.assertGreater(fracs[len(fracs) // 2], 0.6)
    self.assertGreater(fracs[len(fracs) // 10], 0.45)

  def test_in_bounds_and_apart(self):
    tank, gs = stocked()
    for _ in run(tank, 60):
      for g in gs:
        (x0, x1), (y0, y1), (z0, z1) = g.bounds()
        self.assertTrue(x0 - 1e-9 <= g.x <= x1 + 1e-9, g.name)
        self.assertTrue(y0 - 1e-9 <= g.y <= y1 + 1e-9, g.name)
        self.assertTrue(z0 - 1e-9 <= g.z <= z1 + 1e-9, g.name)
        self.assertLessEqual(g.speed, g.max_speed)

  def test_flicks(self):
    tank, gs = alone()
    seen = set()
    for _ in run(tank, 60):
      for g in gs:
        if g.flicking:
          seen.add(g.name)
    self.assertEqual(len(seen), 6)

  def test_flick_turns_and_speeds(self):
    tank, gs = alone()
    g = gs[3]
    for _ in run(tank, 2):
      pass
    g.flick_left = guppy.FLICK_TIME
    g.flick_turn = 1.0
    yaw = g.yaw
    for _ in range(int(guppy.FLICK_TIME / DT)):
      tank.step(DT)
    # Turned the flick's way, a good part of it in its short time
    self.assertGreater(vec.wrap_angle(g.yaw - yaw), 0.2)
    self.assertGreater(g.speed, g.cruise_speed)

  def test_no_hover_while_busy(self):
    tank, gs = alone()
    g = gs[0]
    g.mode = guppy.HOVER
    g.chase = gs[3]
    g.chase_left = 5.0
    tank.step(DT)
    self.assertEqual(g.mode, guppy.CRUISE)


class GuppyChaseTests(unittest.TestCase):

  def test_males_chase_females(self):
    tank, gs = stocked()
    chased = {}
    displayed = set()
    for _ in run(tank, 120):
      for g in gs:
        if g.chase is not None:
          self.assertTrue(g.male)
          self.assertFalse(g.chase.male)
          chased.setdefault(g.name, 0)
          chased[g.name] += 1
        if g.display > 0.5:
          displayed.add(g.name)
        if not g.male:
          self.assertEqual(g.display, 0.0)
    # Every male chases, for a good while but not all the time
    self.assertEqual(sorted(chased), ['Guppy.M0', 'Guppy.M1', 'Guppy.M2'])
    for n in chased.values():
      self.assertGreater(n * DT, 8)
      self.assertLess(n * DT, 80)
    self.assertTrue(displayed)

  def test_chaser_closes_in(self):
    tank, gs = alone()
    m, f = gs[0], gs[3]
    m.rest_left = 1e9
    m.chase, m.chase_left = f, 30.0
    first = vec.length(vec.sub(m.chase_spot(), (m.x, m.y, m.z)))
    near = []
    for _ in run(tank, 6):
      if m.chase is None:
        break
      near.append(vec.length(vec.sub(m.chase_spot(), (m.x, m.y, m.z))))
    self.assertGreater(first, min(near))
    self.assertLess(min(near), guppy.DISPLAY_RANGE * f.length)

  def test_chase_spot_behind_and_below(self):
    _, gs = alone()
    m, f = gs[0], gs[3]
    m.chase = f
    spot = m.chase_spot()
    off = vec.sub(spot, (f.x, f.y, f.z))
    self.assertLess(vec.dot(off, f.forward()), 0)
    self.assertLess(spot[2], f.z)

  def test_female_flees_a_close_chaser(self):
    tank, gs = alone()
    m, f = gs[0], gs[3]
    m.chase, m.chase_left = f, 30.0
    m.x, m.y, m.z = f.x - f.length, f.y, f.z
    tank.step(DT)
    self.assertGreater(f.fleeing, 0)
    plain = guppy.Guppy('Plain', GUPPY, guppy.FEMALE, f.size, 1,
                        (f.x, f.y, f.z), f.yaw)
    plain.speed = f.speed
    want = plain.forward()
    self.assertGreater(f._target_speed(want)[0],
                       plain._target_speed(want)[0])

  def test_gives_up_when_time_is_out(self):
    tank, gs = alone()
    m = gs[0]
    m.chase, m.chase_left = gs[3], DT / 2
    tank.step(DT)
    self.assertIsNone(m.chase)
    self.assertGreaterEqual(m.rest_left, guppy.CHASE_REST[0] - DT)

  def test_gives_up_when_she_gets_away(self):
    tank, gs = alone()
    m, f = gs[0], gs[3]
    m.chase, m.chase_left = f, 30.0
    f.x, f.y, f.z = -m.x, -m.y, m.z
    if math.dist((m.x, m.y, m.z), (f.x, f.y, f.z)) < 1.5 * guppy.CHASE_RANGE:
      f.x = math.copysign(0.4, -m.x)
    tank.step(DT)
    self.assertIsNone(m.chase)

  def test_picks_the_nearest_female_in_range(self):
    _, gs = alone()
    m = gs[0]
    for f in gs[3:]:
      f.x, f.y, f.z = m.x + 1.0, m.y, m.z
    self.assertIsNone(m._nearest_female())
    gs[4].x = m.x + 0.1
    gs[5].x = m.x + 0.05
    self.assertIs(m._nearest_female(), gs[5])


class GuppyStuckTests(unittest.TestCase):
  """A guppy caught where the right sword plant's and vallisneria's
  clearances meet the glass, on a down day, rises out (Fish._rise)."""

  POCKET = (0.419, 0.087, 0.17)

  def caught(self):
    tank, gs = alone()
    tank.set_factor(depth_shift=-0.9)
    f = next(g for g in gs if g.name == 'Guppy.F1')
    # The rest well off, so none chases or flees her
    for k, g in enumerate(g for g in gs if g is not f):
      g.x, g.y, g.z = -0.3 + 0.08 * k, -0.05, 0.25
    f.x, f.y, f.z = self.POCKET
    f.yaw = math.pi
    return tank, f

  def away(self, f):
    return math.hypot(f.x - self.POCKET[0], f.y - self.POCKET[1])

  def test_rises_out_of_a_pocket(self):
    tank, f = self.caught()
    rose = False
    for t in run(tank, 6.0):
      rose = rose or f._rise_left > 0
      if self.away(f) > 0.08:
        break
    self.assertTrue(rose)
    self.assertGreater(self.away(f), 0.08, t)
    # And it keeps off the pocket for a while after
    for _ in run(tank, 4.0):
      self.assertGreater(self.away(f), 0.04)

  def test_stays_without_rising(self):
    # Without the rise it stays caught, as it did before
    tank, f = self.caught()
    f._track_headway = lambda dt, start: None
    for _ in run(tank, 6.0):
      pass
    self.assertLess(self.away(f), 0.01)

  def test_not_while_steered(self):
    # The user asking it into the pocket is not its being stuck
    tank, f = self.caught()
    f.steer = steering.Steer([f])
    f.steer.direction, f.steer.weight = (1.0, 0.0), 1.0
    for _ in run(tank, 3.0):
      self.assertEqual(f._rise_left, 0.0)


class GuppyPoseTests(unittest.TestCase):

  def test_bones(self):
    self.assertEqual(guppy.BONES[:5], ('Head',) + swim.SPINE)
    self.assertEqual(len(set(guppy.BONES)), len(guppy.BONES))
    self.assertIs(species.of(GUPPY), guppy)

  def test_pose_covers_the_bones(self):
    tank, gs = alone()
    for _ in run(tank, 1):
      pass
    for g in gs:
      pose = guppy.pose(g)
      self.assertEqual(set(pose), set(guppy.BONES))
      for bone, angles in pose.items():
        self.assertEqual(len(angles), 3)
        self.assertTrue(all(math.isfinite(a) for a in angles), bone)
      self.assertLessEqual(set(guppy.scales(g)), set(guppy.BONES))

  def test_display_quivers_spreads_and_raises(self):
    _, gs = alone()
    m = gs[0]
    plain = guppy.pose(m)
    m.display = 1.0
    m.quiver_phase = math.pi / 2
    shown = guppy.pose(m)
    self.assertNotAlmostEqual(shown['Spine.1'][2], plain['Spine.1'][2])
    self.assertGreater(shown['Dorsal'][0], plain['Dorsal'][0])
    self.assertGreater(guppy.scales(m)['Caudal'][2], 1.2)
    m.display = 0.0
    self.assertEqual(guppy.scales(m)['Caudal'], (1.0, 1.0, 1.0))

  def test_flick_snaps_the_tail(self):
    tank, gs = alone()
    g = gs[3]
    for _ in run(tank, 1):
      pass
    phase = g.beat_phase
    g.flick_left = guppy.FLICK_TIME
    g.flick_turn = 0.5
    tank.step(DT)
    normal = g.beat_freq * 2 * math.pi * DT
    self.assertGreater((g.beat_phase - phase) % (2 * math.pi), normal * 1.5)
    self.assertGreater(guppy.scales(g)['Caudal'][2], 1.0)


if __name__ == '__main__':
  unittest.main()
