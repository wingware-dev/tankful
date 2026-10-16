import json
import unittest

from tankful.sim import bubbles
from tankful.sim.bubbles import BubblePool

SOURCE = (0.3, -0.15, 0.09)
SURFACE = 0.46


def run(pool, seconds, dt=1 / 60.0):
  for _ in range(int(round(seconds / dt))):
    pool.step(dt)


class BubblePoolTests(unittest.TestCase):

  def test_starts_empty(self):
    pool = BubblePool(SOURCE, SURFACE)
    self.assertEqual(pool.capacity, bubbles.CAPACITY)
    self.assertEqual(pool.active(), [])
    self.assertEqual(pool.snapshot()['emitted'], 0)

  def test_steady_stream_reuses_slots(self):
    pool = BubblePool(SOURCE, SURFACE, capacity=48, rate=18.0)
    run(pool, 30.0)
    snap = pool.snapshot()
    # Far more bubbles than slots have come and gone
    self.assertGreater(snap['emitted'], 400)
    self.assertGreater(snap['popped'], 380)
    self.assertLessEqual(snap['active'], 48)
    self.assertEqual(snap['emitted'], snap['popped'] + snap['active'])
    # The rate is about what was asked for
    self.assertAlmostEqual(snap['emitted'] / 30.0, 18.0, delta=2.5)
    json.dumps(snap)

  def test_bubbles_rise_within_the_water(self):
    pool = BubblePool(SOURCE, SURFACE, seed=3)
    sx, sy, sz = SOURCE
    last_z = {}
    for _ in range(600):
      pool.step(1 / 60.0)
      for i, b in enumerate(pool.bubbles):
        if b.state == bubbles.RISING:
          self.assertGreaterEqual(b.z, sz)
          self.assertLess(b.z + b.radius, SURFACE + 1e-9)
          # The wobble stays a narrow column around the source
          self.assertLess(abs(b.x - sx), 0.02)
          self.assertLess(abs(b.y - sy), 0.015)
          if i in last_z and last_z[i] is not None:
            self.assertGreater(b.z, last_z[i])
          last_z[i] = b.z
        else:
          last_z[i] = None

  def test_wobble_moves_sideways(self):
    pool = BubblePool(SOURCE, SURFACE, rate=0.0)
    pool._emit()
    b = pool.bubbles[0]
    xs = set()
    for _ in range(60):
      pool.step(1 / 60.0)
      xs.add(round(b.x, 5))
    self.assertGreater(len(xs), 30)

  def test_size_variation(self):
    pool = BubblePool(SOURCE, SURFACE, seed=5)
    lo, hi = pool.radius_range
    radii = set()
    for _ in range(200):
      pool._emit()
      b = pool.active()[-1]
      self.assertTrue(lo <= b.base_radius <= hi)
      radii.add(round(b.base_radius, 6))
      b.state = bubbles.FREE
    self.assertGreater(len(radii), 100)

  def test_pop_at_surface(self):
    pool = BubblePool(SOURCE, SURFACE, rate=0.0)
    pool._emit()
    b = pool.bubbles[0]
    base = b.base_radius
    states = []
    for _ in range(int(3.0 * 60)):
      pool.step(1 / 60.0)
      states.append(b.state)
      if b.state == bubbles.POPPING:
        # It swells at the surface as it bursts
        self.assertGreaterEqual(b.radius, base)
        self.assertLessEqual(b.radius, base * (1 + bubbles.POP_SWELL) + 1e-9)
        self.assertAlmostEqual(b.z, SURFACE - 0.4 * base, delta=0.4 * base)
    self.assertIn(bubbles.POPPING, states)
    self.assertEqual(states[-1], bubbles.FREE)
    first_pop = states.index(bubbles.POPPING)
    self.assertNotIn(bubbles.RISING, states[first_pop:])
    self.assertEqual(pool.popped, 1)

  def test_full_pool_stalls_emission(self):
    pool = BubblePool(SOURCE, SURFACE, capacity=4, rate=200.0)
    run(pool, 0.5)
    self.assertEqual(len(pool.active()), 4)
    self.assertGreater(pool.stalled, 0)
    # Slots free up as bubbles pop, and the stream carries on
    run(pool, 5.0)
    self.assertGreater(pool.popped, 4)

  def test_long_step_does_not_burst(self):
    # The scene load before the first frame can be seconds of dt
    pool = BubblePool(SOURCE, SURFACE, rate=18.0)
    pool.step(8.0)
    self.assertLessEqual(pool.emitted, 3)
    self.assertAlmostEqual(pool.time, bubbles.MAX_STEP)

  def test_zero_rate(self):
    pool = BubblePool(SOURCE, SURFACE, rate=0.0)
    run(pool, 2.0)
    self.assertEqual(pool.emitted, 0)

  def test_repeatable(self):
    a = BubblePool(SOURCE, SURFACE, seed=9)
    b = BubblePool(SOURCE, SURFACE, seed=9)
    run(a, 3.0)
    run(b, 3.0)
    self.assertEqual([(x.x, x.z, x.radius) for x in a.bubbles],
                     [(x.x, x.z, x.radius) for x in b.bubbles])

  def test_bad_arguments(self):
    with self.assertRaises(ValueError):
      BubblePool(SOURCE, SURFACE, capacity=0)
    with self.assertRaises(ValueError):
      BubblePool(SOURCE, SURFACE, rate=-1)
    with self.assertRaises(ValueError):
      BubblePool(SOURCE, SOURCE[2])
    with self.assertRaises(ValueError):
      BubblePool(SOURCE, SURFACE).step(-0.1)

  def test_zero_dt(self):
    pool = BubblePool(SOURCE, SURFACE)
    pool.step(0.0)
    self.assertEqual(pool.time, 0.0)


if __name__ == '__main__':
  unittest.main()
