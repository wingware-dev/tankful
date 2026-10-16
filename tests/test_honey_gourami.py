import ast
import math
import statistics
import unittest

from tankful.sim import environment as env
from tankful.sim import species
from tankful.sim import swim
from tankful.sim import vec
from tankful.sim.fish import Fish
from tankful.sim.species import angelfish, honey_gourami, neon_tetra, pleco
from tankful.sim.species.honey_gourami import SPECIES as GOURAMI
from tankful.sim.tank import Tank

DT = 1 / 60.0


def alone():
  """A tank with the gouramis and nothing else."""
  tank = Tank()
  return tank, honey_gourami.stock(tank)


def stocked():
  """The tank as the game stocks it, with the gouramis."""
  tank = Tank()
  angelfish.stock(tank)
  neon_tetra.stock(tank)
  pleco.stock(tank)
  return tank, honey_gourami.stock(tank)


def steps(tank, seconds):
  for _ in range(int(round(seconds / DT))):
    tank.step(DT)
    yield


def depth(g):
  """How high g is in its swim box, 0 at the bottom to 1 at the top."""
  _, _, (z0, z1) = g.bounds()
  return (g.z - z0) / (z1 - z0)


def ahead(g, distance, side=0.0, up=0.0):
  """A point distance ahead of g, turned side (radians) to its left, and
  up meters above it."""
  h = g.yaw + side
  return (g.x + distance * math.cos(h), g.y + distance * math.sin(h),
          g.z + up)


def visitor(g, point):
  """An angelfish at point, held still: something for g to probe."""
  other = Fish('Visitor', angelfish.SPECIES, 0.5, 9, point, 0.0)
  other.x, other.y, other.z = point
  other.step = lambda dt, others=(): None
  return other


def still(g):
  """Hold g where it is, so only its feelers move."""
  g._swim = lambda dt, want: setattr(g, 'speed', 0.0)
  g._turn = lambda dt, want: setattr(g, 'yaw_rate', 0.0)
  g._pitch = lambda dt, want: None


class GouramiStockTests(unittest.TestCase):

  def test_registered_and_present(self):
    self.assertIn('honey_gourami', species.NAMES)
    self.assertIn('honey_gourami', species.present())
    self.assertIs(species.of(GOURAMI), honey_gourami)

  def test_stock(self):
    tank, gs = alone()
    self.assertEqual(gs, tank.fish)
    self.assertEqual([g.name for g in gs],
                     ['HoneyGourami.0', 'HoneyGourami.1'])
    for g in gs:
      self.assertIsInstance(g, honey_gourami.Gourami)
      self.assertIs(g.species, GOURAMI)
      self.assertEqual([f.reach for f in g.feelers], [0.0, 0.0])
    # One male, who the model colors so
    self.assertEqual([g.name for g in gs if g.name in honey_gourami.MALES],
                     ['HoneyGourami.0'])
    # Each its own seed
    seeds = [r.seed for r in honey_gourami.residents()]
    self.assertEqual(len(set(seeds)), len(seeds))

  def test_starts_near_the_top(self):
    _, gs = alone()
    for g in gs:
      self.assertGreater(depth(g), 0.8, g.name)

  def test_stocks_after_the_others(self):
    tank = Tank()
    species.stock(tank)
    names = [f.name for f in tank.fish]
    self.assertEqual(tank.fish[17].name, 'Pleco')
    first = names.index('HoneyGourami.0')
    self.assertEqual(names[first:first + 2],
                     ['HoneyGourami.0', 'HoneyGourami.1'])


class GouramiSwimTests(unittest.TestCase):

  def test_stays_near_the_top(self):
    tank, gs = stocked()
    heights = []
    for _ in steps(tank, 180):
      heights.extend(depth(g) for g in gs)
    self.assertGreater(statistics.mean(heights), 0.82)
    self.assertGreater(min(heights), 0.65)
    # Under the surface
    for g in gs:
      self.assertLessEqual(g.z, g.bounds()[2][1] + 1e-9)

  def test_slow(self):
    tank, gs = stocked()
    angels, tetras = tank.fish[:2], tank.fish[2:17]
    mine, big, small = [], [], []
    for _ in steps(tank, 120):
      mine.extend(g.speed for g in gs)
      big.extend(a.speed for a in angels)
      small.extend(t.speed for t in tetras)
    self.assertLess(statistics.mean(mine), GOURAMI.cruise_speed)
    self.assertLessEqual(max(mine), GOURAMI.max_speed + 1e-9)
    # Slower than the angelfish, and for its size than the tetras
    self.assertLess(statistics.mean(mine), 0.6 * statistics.mean(big))
    self.assertLess(statistics.mean(mine) / GOURAMI.length,
                    0.6 * statistics.mean(small)
                    / neon_tetra.SPECIES.length)

  def test_same_run_same_tank(self):
    def run():
      tank, _ = stocked()
      for _ in steps(tank, 20):
        pass
      return tank.snapshot()
    self.assertEqual(run(), run())

  def test_zero_and_negative_steps(self):
    _, gs = alone()
    g = gs[0]
    before = g.snapshot()
    g.step(0.0)
    self.assertEqual(g.snapshot(), before)
    with self.assertRaises(ValueError):
      g.step(-DT)


class GouramiProbeTests(unittest.TestCase):

  def setUp(self):
    self.tank, gs = alone()
    self.g = gs[0]
    del self.tank.fish[1]
    still(self.g)
    # No probing at nothing, unless a test asks
    self.idle = honey_gourami.IDLE_CHANCE
    honey_gourami.IDLE_CHANCE = 0.0
    self.addCleanup(setattr, honey_gourami, 'IDLE_CHANCE', self.idle)

  def add(self, point):
    other = visitor(self.g, point)
    self.tank.fish.append(other)
    return other

  def test_reaches_toward_a_fish_on_its_left(self):
    g = self.g
    left, right = g.feelers
    other = self.add(ahead(g, 0.06, 0.6, -0.01))
    self.tank.step(DT)
    self.assertIs(left.target, other)
    self.assertIsNone(right.target)
    self.assertGreater(left.side, 0.3)
    self.assertGreater(left.dip, 0.0)
    for _ in steps(self.tank, 1.0):
      pass
    self.assertAlmostEqual(left.reach, 1.0)
    self.assertEqual(right.reach, 0.0)
    self.assertAlmostEqual(g.probing, 1.0)
    # The pose swings the left thread down and forward, toward its left
    rx, _, rz = honey_gourami.pose(g)['Feeler.L']
    self.assertAlmostEqual(rx, honey_gourami.FEELER_REST + left.dip
                           - math.pi)
    self.assertLess(rz, -0.3)

  def test_both_feelers_for_straight_ahead(self):
    other = self.add(ahead(self.g, 0.05))
    self.tank.step(DT)
    self.assertEqual([f.target for f in self.g.feelers], [other, other])

  def test_nothing_behind_or_out_of_range(self):
    self.add(ahead(self.g, 0.05, math.pi))
    self.add(ahead(self.g, honey_gourami.PROBE_RANGE + 0.02))
    for _ in steps(self.tank, 3.0):
      self.assertEqual([f.target for f in self.g.feelers], [None, None])
    self.assertEqual(self.g.probing, 0.0)

  def test_follows_and_lets_go(self):
    g = self.g
    left = g.feelers[0]
    other = self.add(ahead(g, 0.06, 0.4))
    for _ in steps(self.tank, 0.5):
      pass
    side = left.side
    # It moves further to the left: the aim follows
    other.x, other.y, other.z = ahead(g, 0.06, 0.65)
    self.tank.step(DT)
    self.assertGreater(left.side, side + 0.1)
    # It goes out of reach: the feeler draws back and rests
    other.x, other.y, other.z = ahead(g, 0.3)
    self.tank.step(DT)
    self.assertIsNone(left.target)
    self.assertFalse(left.probing)
    self.assertGreater(left.rest, 0.0)
    for _ in steps(self.tank, 1.0):
      pass
    self.assertEqual(left.reach, 0.0)

  def test_probe_times_out_then_comes_back(self):
    left = self.g.feelers[0]
    self.add(ahead(self.g, 0.06, 0.6))
    probes = []
    for _ in steps(self.tank, 20.0):
      probes.append(left.probing)
    # Out, then resting, then out again while the fish stays
    self.assertIn(False, probes[probes.index(True):])
    self.assertGreater(left.probes, 1)
    self.assertLessEqual(left.probes, 20.0 / (
      honey_gourami.PROBE_TIME[0] + honey_gourami.PROBE_REST[0]) + 1)

  def test_probes_decor(self):
    g = self.g
    # Just off a slim piece of decor, facing the middle of its axis
    obstacle = min(g._obstacles, key=lambda o: o.radius)
    mid = vec.lerp(obstacle.a, obstacle.b, 0.5)
    across = vec.normalized(vec.cross(vec.sub(obstacle.b, obstacle.a),
                                      (0.0, 0.0, 1.0)), (1.0, 0.0, 0.0))
    g.x, g.y, g.z = vec.add(mid, vec.scale(across, obstacle.radius + 0.03))
    g.yaw, g.pitch, g.roll = (math.atan2(-across[1], -across[0]), 0.0,
                              0.0)
    target, side, _ = g._find_target(self.tank.fish)
    self.assertIs(target, obstacle)
    self.assertAlmostEqual(side, 0.0, places=6)
    self.assertIn(obstacle.name, [o.name for o in env.obstacles()])

  def test_probing_slows_it(self):
    g = self.g
    want = g.forward()
    g.mode = 'cruise'
    free, _ = g._target_speed(want)
    g.feelers[0].reach = 1.0
    slowed, _ = g._target_speed(want)
    self.assertAlmostEqual(slowed, free * (1 - honey_gourami.PROBE_SLOW))

  def test_reaches_at_nothing_now_and_then(self):
    honey_gourami.IDLE_CHANCE = self.idle
    for _ in steps(self.tank, 120):
      pass
    probes = sum(f.probes for f in self.g.feelers)
    self.assertGreater(probes, 1)
    for f in self.g.feelers:
      self.assertIsNone(f.target)


class GouramiPoseTests(unittest.TestCase):

  def test_pose_covers_the_bones(self):
    tank, gs = stocked()
    for _ in steps(tank, 10):
      for g in gs:
        pose = honey_gourami.pose(g)
        self.assertEqual(set(pose), set(honey_gourami.BONES))
        for bone, angles in pose.items():
          self.assertEqual(len(angles), 3, bone)
          for a in angles:
            self.assertTrue(math.isfinite(a), bone)
        self.assertEqual(honey_gourami.scales(g), {})

  def test_bones(self):
    self.assertEqual(honey_gourami.BONES[:5], ('Head',) + swim.SPINE)
    self.assertEqual(len(set(honey_gourami.BONES)),
                     len(honey_gourami.BONES))

  def test_feelers_at_rest_trail(self):
    _, gs = alone()
    g = gs[0]
    for name in honey_gourami.FEELERS:
      rx, ry, rz = honey_gourami.pose(g)[name]
      # Near the rest pose: no more than the trail and sway
      self.assertLess(abs(rx), 0.35)
      self.assertLess(abs(rz), 0.05)

  def test_feelers_reach_mirrors(self):
    _, gs = alone()
    g = gs[0]
    for f in g.feelers:
      f.reach, f.side, f.dip = 1.0, 0.0, 0.3
    g.feeler_phase = 0.0
    left = honey_gourami.pose(g)['Feeler.L']
    right = honey_gourami.pose(g)['Feeler.R']
    self.assertAlmostEqual(left[0], right[0])
    # Straight ahead, each spreads to its own side
    self.assertLess(left[2], 0.0)
    self.assertGreater(right[2], 0.0)

  def test_model_makes_every_bone(self):
    # The model module runs only under Blender: read it for the names
    with open(species.model_path('honey_gourami'), encoding='utf-8') as f:
      tree = ast.parse(f.read())
    names = {node.value for node in ast.walk(tree)
             if isinstance(node, ast.Constant) and isinstance(node.value,
                                                              str)}
    for bone in honey_gourami.BONES[5:]:
      self.assertIn(bone, names)


if __name__ == '__main__':
  unittest.main()
