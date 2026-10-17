"""Collisions between fish (tankful.sim.fish.Fish._bump): bumped fish
dart apart, a fish the user steers doesn't, and schoolmates, the pleco on
the glass and the shrimp are handled as their own cases."""

import math
import unittest

from tankful.sim import fish as sim_fish
from tankful.sim import school as sim_school
from tankful.sim import steering
from tankful.sim import vec
from tankful.sim.fish import Fish
from tankful.sim.species import cherry_shrimp, corydoras, guppy, neon_tetra
from tankful.sim.species import pleco as sim_pleco
from tankful.sim.species.angelfish import SPECIES as ANGELFISH

DT = 1 / 60.0
# Open water, clear of the decor
HERE = (0.0, -0.05, 0.3)


def pos(f):
  return (f.x, f.y, f.z)


def beside(f, species, gap, school=None):
  """A fish of species alongside f, heading the same way, its center
  gap (in the two bodies' radii) to f's left: a member of school, if
  given."""
  if school is None:
    other = Fish('Other', species, 1.0, 2, HERE, f.yaw)
  else:
    other = sim_school.Member('Other', species, school, 1.0, 2, HERE, f.yaw)
  radii = sim_fish.BODY_RADIUS * (f.length + other.length)
  left = (-math.sin(f.yaw), math.cos(f.yaw), 0.0)
  other.x, other.y, other.z = vec.add(pos(f), vec.scale(left, gap * radii))
  return other


def step_all(fish, seconds=DT):
  for _ in range(max(1, int(round(seconds / DT)))):
    for f in fish:
      f.step(DT, fish)


def steer(target, weight=1.0, direction=(1.0, 0.0)):
  s = steering.Steer([target])
  s.attach()
  s.weight = weight
  s.direction = direction
  return s


class BumpTests(unittest.TestCase):
  """Two free fish whose bodies touch both dart away."""

  def setUp(self):
    self.a = Fish('A', ANGELFISH, 1.0, 1, HERE, 0.0)

  def test_touching_fish_both_startle(self):
    a = self.a
    b = beside(a, ANGELFISH, 0.5)
    speeds = a.speed, b.speed
    step_all([a, b])
    self.assertEqual((a.bumps, b.bumps), (1, 1))
    self.assertGreater(a.startled, 0.9)
    self.assertGreater(b.startled, 0.9)
    # Each darts away from the other: a was to the right of b
    self.assertLess(a._startle_away[1], -0.5)
    self.assertGreater(b._startle_away[1], 0.5)
    # with a kick of speed
    self.assertGreater(a.speed, speeds[0] + 0.5 * a.cruise_speed)
    self.assertGreater(b.speed, speeds[1] + 0.5 * b.cruise_speed)
    self.assertEqual(a.snapshot()['bumps'], 1)

  def test_fish_of_other_kinds_startle(self):
    a = self.a
    b = beside(a, guppy.SPECIES, 0.5)
    step_all([a, b])
    self.assertEqual((a.bumps, b.bumps), (1, 1))

  def test_near_but_not_touching(self):
    a = self.a
    b = beside(a, ANGELFISH, 1.3)
    step_all([a, b])
    self.assertEqual((a.bumps, b.bumps), (0, 0))

  def test_they_swim_apart(self):
    a = self.a
    b = beside(a, ANGELFISH, 0.5)
    d0 = math.dist(pos(a), pos(b))
    step_all([a, b], a.startle_time + DT)
    self.assertGreater(math.dist(pos(a), pos(b)), d0 + 0.5 * a.length)
    # The startle eases off
    self.assertEqual(a.startled, 0.0)

  def test_calm_between_startles(self):
    a = self.a
    b = beside(a, ANGELFISH, 0.5)
    a._mind_others([0.0, 0.0, 0.0], [a, b])
    self.assertEqual(a.bumps, 1)
    # Bumped again before STARTLE_CALM is out, it isn't startled again
    a._mind_others([0.0, 0.0, 0.0], [a, b])
    self.assertEqual(a.bumps, 1)
    a.time += sim_fish.STARTLE_CALM
    a._mind_others([0.0, 0.0, 0.0], [a, b])
    self.assertEqual(a.bumps, 2)

  def test_startle_ends_a_hover(self):
    a = self.a
    a.mode, a.hover_left = sim_fish.HOVER, 5.0
    b = beside(a, ANGELFISH, 0.5)
    a._mind_others([0.0, 0.0, 0.0], [a, b])
    self.assertEqual(a.mode, sim_fish.CRUISE)


class SteeredTests(unittest.TestCase):
  """A fish the user steers is never startled: only the fish it bumps
  into flees, and gives way to it."""

  def setUp(self):
    self.a = Fish('A', ANGELFISH, 1.0, 1, HERE, 0.0)

  def test_only_the_other_fish_flees(self):
    a = self.a
    b = beside(a, ANGELFISH, 0.5)
    steer(a)
    step_all([a, b])
    self.assertEqual((a.bumps, b.bumps), (0, 1))

  def test_blending_out_counts_as_steered(self):
    a = self.a
    b = beside(a, ANGELFISH, 0.5)
    steer(a, weight=0.0)
    self.assertTrue(a.user_steered)
    step_all([a, b])
    self.assertEqual((a.bumps, b.bumps), (0, 1))

  def test_steered_fish_holds_its_place(self):
    a = self.a
    b = beside(a, ANGELFISH, 0.1)
    steer(a)
    before_a, before_b = pos(a), pos(b)
    gap = sim_fish.MIN_GAP * a.length
    d = math.dist(before_a, before_b)
    a._keep_apart([a, b])
    self.assertEqual(pos(a), before_a)
    b._keep_apart([a, b])
    # The other takes the whole overlap
    self.assertAlmostEqual(math.dist(pos(a), pos(b)), gap)
    self.assertGreater(math.dist(pos(b), before_b), 0.9 * (gap - d))

  def test_steered_school_member(self):
    school = sim_school.School('Tetras', neon_tetra.SPECIES, 3,
                               HERE + (0.0,))
    m = sim_school.Member('Tetra.0', neon_tetra.SPECIES, school, 1.0, 4,
                          HERE, 0.0)
    g = beside(m, guppy.SPECIES, 0.5)
    steer(school)
    self.assertTrue(m.user_steered)
    m._mind_others([0.0, 0.0, 0.0], [m, g], skip=school)
    g._mind_others([0.0, 0.0, 0.0], [m, g])
    self.assertEqual((m.bumps, g.bumps), (0, 1))


class GroupTests(unittest.TestCase):
  """Fish of one group keep apart by separation, not startles."""

  def test_schoolmates(self):
    school = sim_school.School('Tetras', neon_tetra.SPECIES, 3,
                               HERE + (0.0,))
    a = sim_school.Member('Tetra.0', neon_tetra.SPECIES, school, 1.0, 4,
                          HERE, 0.0)
    b = beside(a, neon_tetra.SPECIES, 0.5, school)
    want = [0.0, 0.0, 0.0]
    a._mind_others(want, [a, b], skip=school)
    b._mind_others([0.0, 0.0, 0.0], [a, b], skip=school)
    self.assertEqual((a.bumps, b.bumps), (0, 0))

  def test_member_bumped_from_outside_darts_briefly(self):
    school = sim_school.School('Tetras', neon_tetra.SPECIES, 3,
                               HERE + (0.0,))
    m = sim_school.Member('Tetra.0', neon_tetra.SPECIES, school, 1.0, 4,
                          HERE, 0.0)
    a = beside(m, ANGELFISH, 0.5)
    m._mind_others([0.0, 0.0, 0.0], [m, a], skip=school)
    self.assertEqual(m.bumps, 1)
    m.time += sim_school.FLICK_TIME
    self.assertEqual(m.startled, 0.0)

  def test_one_group(self):
    group = corydoras.Group('Shoal')
    a = Fish('A', guppy.SPECIES, 1.0, 1, HERE, 0.0)
    b = beside(a, guppy.SPECIES, 0.5)
    group.add(a)
    group.add(b)
    want = [0.0, 0.0, 0.0]
    a._mind_others(want, [a, b])
    self.assertEqual(a.bumps, 0)
    # Separation still pushes them apart
    self.assertLess(want[1], 0.0)


class PlecoTests(unittest.TestCase):
  """The pleco on the glass holds on; the fish that bumps it darts off."""

  def setUp(self):
    r = sim_pleco.plecos()[0]
    self.pleco = sim_pleco.Pleco(r.name, r.species, r.size, r.seed, r.start)
    self.assertEqual(self.pleco.state, sim_pleco.ATTACHED)

  def bumping(self, species=guppy.SPECIES):
    p = self.pleco
    f = Fish('Fish', species, 1.0, 1, HERE, 0.0)
    # Nose to nose with it, just in from the glass
    f.yaw, f.pitch = p.yaw, p.pitch
    f.x, f.y, f.z = vec.add(pos(p), vec.scale(p.normal, 0.5 * (
      sim_fish.BODY_RADIUS * (p.length + f.length))))
    return f

  def test_attached_pleco_holds_on(self):
    p = self.pleco
    f = self.bumping()
    contact = p.contact
    p.step(DT, [p, f])
    f.step(DT, [p, f])
    self.assertEqual(f.bumps, 1)
    self.assertEqual(p.bumps, 0)
    self.assertEqual(p.state, sim_pleco.ATTACHED)
    self.assertTrue(p.anchored)
    # Still on its spot, inching along the glass as ever
    self.assertLess(math.dist(p.contact, contact), 0.01)

  def test_fish_takes_the_whole_overlap(self):
    p = self.pleco
    f = self.bumping(ANGELFISH)
    before = pos(p)
    f._keep_apart([p, f])
    gap = sim_fish.MIN_GAP * 0.5 * (p.length + f.length)
    self.assertAlmostEqual(math.dist(pos(f), pos(p)), gap)
    self.assertEqual(pos(p), before)

  def test_darting_pleco_startles(self):
    p = self.pleco
    p.release()
    for _ in range(int(sim_pleco.RELEASE_TIME / DT) + 2):
      p.step(DT, [p])
    self.assertEqual(p.state, sim_pleco.DARTING)
    self.assertFalse(p.anchored)
    f = beside(p, guppy.SPECIES, 0.5)
    p._mind_others([0.0, 0.0, 0.0], [p, f])
    self.assertEqual(p.bumps, 1)


class ShrimpTests(unittest.TestCase):
  """A shrimp startles no fish; swimming, it darts off itself."""

  def setUp(self):
    self.shrimp = cherry_shrimp.Shrimp('Shrimp', cherry_shrimp.SPECIES, 1.0,
                                       9, (0.0, -0.12, 0.04, 0.0))

  def test_fish_bumping_a_shrimp(self):
    s = self.shrimp
    f = beside(s, guppy.SPECIES, 0.5)
    f._mind_others([0.0, 0.0, 0.0], [s, f])
    self.assertEqual(f.bumps, 0)
    self.assertTrue(s.anchored)

  def test_swimming_shrimp_darts_off(self):
    s = self.shrimp
    s.lift([s])
    for _ in range(int(cherry_shrimp.LIFT_TIME / DT) + 2):
      s.step(DT, [s])
    self.assertEqual(s.state, cherry_shrimp.SWIMMING)
    self.assertFalse(s.anchored)
    f = beside(s, guppy.SPECIES, 0.5)
    s._mind_others([0.0, 0.0, 0.0], [s, f])
    f._mind_others([0.0, 0.0, 0.0], [s, f])
    self.assertEqual((s.bumps, f.bumps), (1, 0))


class ReachTests(unittest.TestCase):

  def test_bodies_touch_only_within_separation(self):
    # _mind_others passes over fish a separation apart before looking
    # for bumps
    self.assertLess(2 * sim_fish.BODY_REACH, sim_fish.SEPARATION)


if __name__ == '__main__':
  unittest.main()
