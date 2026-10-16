import collections
import math
import unittest
from unittest import mock

from tankful.sim import environment as env
from tankful.sim import species
from tankful.sim import swim
from tankful.sim import vec
from tankful.sim.species import angelfish, neon_tetra, pleco
from tankful.sim.species.pleco import SPECIES as PLECO
from tankful.sim.tank import Tank

DT = 1 / 60.0


def alone():
  """A tank with the pleco and nothing else."""
  tank = Tank()
  return tank, pleco.stock(tank)[0]


def stocked():
  """The whole tank: the angelfish, the school and the pleco."""
  tank = Tank()
  angelfish.stock(tank)
  neon_tetra.stock(tank)
  return tank, pleco.stock(tank)[0]


def steps(tank, seconds):
  for _ in range(int(round(seconds / DT))):
    tank.step(DT)
    yield


def column(m, j):
  return (m[0][j], m[1][j], m[2][j])


def up(p):
  return column(p.orientation(), 2)


class PlecoClingTests(unittest.TestCase):

  def assert_on_surface(self, p):
    """Its center BELLY lengths off the contact, along the normal, and
    the contact on its surface."""
    center = vec.add(p.contact, vec.scale(p.normal, pleco.BELLY * p.length))
    self.assertLess(math.dist(center, (p.x, p.y, p.z)), 1e-9)
    for a, b in zip(up(p), p.normal):
      self.assertAlmostEqual(a, b, places=6)
    on, _ = p.surface.contact(p.contact)
    self.assertLess(math.dist(on, p.contact), 1e-9)
    self.assertAlmostEqual(vec.dot(p.heading, p.normal), 0.0, places=6)

  def test_starts_on_the_front_glass_belly_to_the_viewer(self):
    _, p = alone()
    self.assertEqual(p.state, pleco.ATTACHED)
    self.assertEqual(p.surface.name, 'GlassFront')
    # Its back is away from the viewer (+y): its belly faces them
    self.assertEqual(p.normal, (0.0, 1.0, 0.0))
    self.assert_on_surface(p)
    self.assertAlmostEqual(p.y, -env.INNER_Y + pleco.GLASS_GAP
                           + pleco.BELLY * p.length)

  def test_clings_inching_within_the_glass(self):
    tank, p = alone()
    p.attach_left = 1e9
    surface = p.surface
    start = p.contact
    path = 0.0
    top = pleco.INCH_SPEED * p.length * 2.0
    before = p.contact
    for _ in steps(tank, 120):
      self.assertEqual(p.state, pleco.ATTACHED)
      self.assertIs(p.surface, surface)
      self.assert_on_surface(p)
      for depth, _ in surface.edges(p.contact):
        self.assertGreaterEqual(depth, -1e-9)
      self.assertLessEqual(p.speed, top + 1e-9)
      path += math.dist(before, p.contact)
      before = p.contact
    # It gets somewhere, slowly
    self.assertGreater(path, 0.02)
    self.assertLess(path, 120 * pleco.INCH_SPEED * p.length * 1.01)
    self.assertGreater(math.dist(start, p.contact), 0.0)

  def test_inches_in_pulses_with_the_rasps(self):
    tank, p = alone()
    p.attach_left = 1e9
    phases, speeds = [], []
    for _ in steps(tank, 6):
      phases.append(p.rasp_phase)
      speeds.append(p.speed)
    # Still for the half of each rasp when the disc grips, which is when
    # sin(rasp_phase) < 0
    for phase, speed in zip(phases, speeds):
      if math.sin(phase) < 0:
        self.assertEqual(speed, 0.0)
    self.assertGreater(max(speeds), 0.0)

  def test_turns_back_from_the_edges(self):
    tank, p = alone()
    p.attach_left = 1e9
    # Heading straight down, just above the sand line
    surface = p.surface
    p.contact = surface.clamp((p.contact[0], p.contact[1], 0.0))
    p.heading = (0.0, 0.0, -1.0)
    for _ in steps(tank, 30):
      pass
    self.assertGreater(p.heading[2], 0.0)
    self.assertGreater(min(d for d, _ in surface.edges(p.contact)), 0.0)


class PlecoStateMachineTests(unittest.TestCase):

  def test_the_states_run_round_in_order(self):
    tank, p = alone()
    seen = [p.state]
    while p.darts < 3 or p.state != pleco.ATTACHED:
      tank.step(DT)
      if p.state != seen[-1]:
        seen.append(p.state)
      self.assertLess(tank.time, 400)
    cycle = [pleco.ATTACHED, pleco.RELEASING, pleco.DARTING,
             pleco.ATTACHING]
    self.assertEqual(seen, cycle * 3 + [pleco.ATTACHED])

  def test_lets_go_when_its_time_is_up(self):
    tank, p = alone()
    p.attach_left = 1.0
    for _ in steps(tank, 0.9):
      pass
    self.assertEqual(p.state, pleco.ATTACHED)
    for _ in steps(tank, 0.2):
      pass
    self.assertEqual(p.state, pleco.RELEASING)
    self.assertIsNone(p.surface)
    self.assertIsNotNone(p.target)

  def test_release_only_from_a_surface(self):
    _, p = alone()
    self.assertTrue(p.release())
    self.assertEqual(p.state, pleco.RELEASING)
    self.assertFalse(p.release())

  def test_pushes_off_then_swims(self):
    tank, p = alone()
    start = (p.x, p.y, p.z)
    normal = p.normal
    p.release()
    for _ in steps(tank, pleco.RELEASE_TIME - DT / 2):
      pass
    self.assertEqual(p.state, pleco.RELEASING)
    off = vec.sub((p.x, p.y, p.z), start)
    self.assertAlmostEqual(vec.dot(off, normal), pleco.PUSH_OFF, places=3)
    tank.step(DT)
    self.assertEqual(p.state, pleco.DARTING)
    self.assertEqual(p.swimming, 1.0)
    # Swimming as a fish now: facing along its yaw and pitch
    self.assertIsNone(p._frame)

  def test_settles_exactly_on_the_spot(self):
    tank, p = alone()
    p.release()
    target = p.target
    while p.state != pleco.ATTACHED:
      tank.step(DT)
      self.assertLess(tank.time, 60)
    self.assertIs(p.surface, target.surface)
    self.assertEqual(p.contact, target.point)
    self.assertEqual(p.normal, target.normal)
    PlecoClingTests.assert_on_surface(self, p)
    self.assertIsNone(p.target)
    self.assertEqual(p.swimming, 0.0)

  def test_gives_up_on_a_spot_it_cannot_reach(self):
    tank, p = alone()
    p.release()
    for _ in steps(tank, pleco.RELEASE_TIME + 0.1):
      pass
    self.assertEqual(p.state, pleco.DARTING)
    first = p.target
    with mock.patch.object(pleco, 'ARRIVE', -1.0):
      for _ in steps(tank, pleco.DART_TIMEOUT + 0.5):
        pass
    self.assertEqual(p.state, pleco.DARTING)
    self.assertIsNot(p.target, first)
    self.assertLess(p.state_time, 1.0)

  def test_visits_glass_sand_and_decor_and_stays_in_the_tank(self):
    tank, p = alone()
    kinds = collections.Counter()
    prev = p.state
    darting = 0.0
    for _ in steps(tank, 900):
      for v in (p.x, p.y, p.z):
        self.assertTrue(math.isfinite(v))
      self.assertLessEqual(abs(p.x), env.INNER_X)
      self.assertLessEqual(abs(p.y), env.INNER_Y)
      self.assertGreater(p.z, env.sand_height(p.x, p.y))
      self.assertLess(p.z, env.WATER_LEVEL)
      if p.state == pleco.DARTING:
        darting = max(darting, p.state_time)
      if p.state == pleco.ATTACHED and prev != pleco.ATTACHED:
        kinds[p.surface.kind] += 1
      prev = p.state
    self.assertEqual(set(kinds), {'glass', 'sand', 'perch'})
    # Most time is spent clinging; darts are quick
    self.assertGreaterEqual(sum(kinds.values()), 12)
    self.assertLess(darting, pleco.DART_TIMEOUT)

  def test_repeatable(self):
    a, pa = stocked()
    b, pb = stocked()
    for _ in steps(a, 90):
      pass
    for _ in steps(b, 90):
      pass
    self.assertGreater(pa.darts, 0)
    self.assertEqual(a.snapshot(), b.snapshot())

  def test_frame_is_a_rotation_in_every_state(self):
    tank, p = alone()
    states = set()
    for _ in steps(tank, 120):
      m = p.orientation()
      states.add(p.state)
      for i in range(3):
        for j in range(3):
          d = vec.dot(column(m, i), column(m, j))
          self.assertAlmostEqual(d, 1.0 if i == j else 0.0, places=6)
      self.assertAlmostEqual(vec.dot(vec.cross(column(m, 0), column(m, 1)),
                                     column(m, 2)), 1.0, places=6)
      f = p.forward()
      for a, b in zip(f, column(m, 0)):
        self.assertAlmostEqual(a, b, places=9)
    self.assertEqual(states, {pleco.ATTACHED, pleco.RELEASING,
                              pleco.DARTING, pleco.ATTACHING})

  def test_snapshot(self):
    tank, p = alone()
    snap = tank.snapshot()['fish'][0]
    self.assertEqual(snap['state'], pleco.ATTACHED)
    self.assertEqual(snap['surface'], 'GlassFront')
    self.assertEqual(snap['normal'], [0.0, 1.0, 0.0])
    self.assertIsNone(snap['target'])


class SpotTests(unittest.TestCase):

  def setUp(self):
    self.surfaces = pleco.surfaces(PLECO.length)
    self.rng = __import__('random').Random(3)

  def test_spots_are_on_their_surfaces_and_away_from_the_last(self):
    last = (0.0, -0.19, 0.25)
    kinds = collections.Counter()
    for _ in range(400):
      spot = pleco.choose_spot(self.rng, self.surfaces, None, last)
      kinds[spot.surface.kind] += 1
      self.assertGreaterEqual(math.dist(spot.point, last), pleco.MIN_HOP)
      on, normal = spot.surface.contact(spot.point)
      self.assertLess(math.dist(on, spot.point), 1e-9)
      self.assertEqual(normal, spot.normal)
      self.assertAlmostEqual(vec.dot(spot.heading, spot.normal), 0.0)
      for depth, _ in spot.surface.edges(spot.point):
        self.assertGreaterEqual(depth, -1e-9)
      last = spot.point
    self.assertEqual(set(kinds), {'glass', 'sand', 'perch'})

  def test_never_the_perch_it_is_on(self):
    perch = self.surfaces['perch'][0]
    for _ in range(200):
      spot = pleco.choose_spot(self.rng, self.surfaces, perch, perch.point)
      self.assertIsNot(spot.surface, perch)

  def test_sand_spots_keep_off_the_decor(self):
    sand = self.surfaces['sand'][0]
    for _ in range(200):
      x, y, z = sand.random_point(self.rng)
      self.assertAlmostEqual(z, env.sand_height(x, y))
      self.assertLessEqual(y, pleco.SAND_BACK)
      for o in env.obstacles():
        a, b = (o.a[0], o.a[1], 0.0), (o.b[0], o.b[1], 0.0)
        c = vec.closest_on_segment((x, y, 0.0), a, b)
        self.assertGreater(math.dist(c, (x, y, 0.0)), o.radius)

  def test_perches_sit_on_their_rocks(self):
    obstacles = {o.name: o for o in env.obstacles()}
    for perch in env.perches():
      rock = obstacles[perch.obstacle]
      x, y, z = perch.point
      self.assertLess(math.hypot(x - rock.a[0], y - rock.a[1]), rock.radius)
      # On top: above the rock's middle, facing up
      self.assertGreater(z, rock.a[2])
      self.assertGreater(vec.normalized(perch.normal)[2], 0.9)


class PlecoPoseTests(unittest.TestCase):

  def test_bones(self):
    self.assertIs(species.of(PLECO), pleco)
    self.assertEqual(pleco.BONES[:5], ('Head',) + swim.SPINE)
    _, p = alone()
    self.assertEqual(set(pleco.pose(p)), set(pleco.BONES))
    self.assertEqual(set(pleco.scales(p)), {'Mouth', 'Jaw'})

  def test_clinging_the_fins_spread_and_the_mouth_works(self):
    tank, p = alone()
    p.attach_left = 1e9
    discs = []
    for _ in steps(tank, 1.5):
      pose = pleco.pose(p)
      self.assertEqual(pose['Pec.L'][2], 0.0)
      self.assertEqual(pose['Dorsal'][0], -pleco.DORSAL_FOLD)
      discs.append(pleco.scales(p)['Jaw'][0])
    # The jaws open and close with the rasps
    self.assertLess(min(discs), 0.6)
    self.assertGreater(max(discs), 0.95)

  def test_swimming_the_fins_fold_and_the_mouth_rests(self):
    tank, p = alone()
    p.release()
    for _ in steps(tank, pleco.RELEASE_TIME + 0.2):
      pass
    self.assertEqual(p.state, pleco.DARTING)
    pose = pleco.pose(p)
    # The left fins swing in toward the right, the right ones the other way
    self.assertGreater(pose['Pec.L'][2], 0.5)
    self.assertLess(pose['Pec.R'][2], -0.5)
    self.assertEqual(pose['Dorsal'][0], 0.0)
    self.assertEqual(pleco.scales(p), {'Mouth': (1.0, 1.0, 1.0),
                                      'Jaw': (1.0, 1.0, 1.0)})

  def test_other_fish_have_no_scales(self):
    tank = Tank()
    angelfish.stock(tank)
    neon_tetra.stock(tank)
    for f in tank.fish:
      self.assertEqual(species.of(f.species).scales(f), {})


if __name__ == '__main__':
  unittest.main()
