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


class PopEventTests(unittest.TestCase):

  def test_each_pop_is_reported_once_at_the_surface(self):
    pool = BubblePool(SOURCE, SURFACE, seed=4)
    events = []
    for _ in range(int(20 / (1 / 60.0))):
      pool.step(1 / 60.0)
      events += pool.pop_events
      for x, y, radius in pool.pop_events:
        self.assertLess(abs(x - SOURCE[0]), 0.03)
        self.assertLess(abs(y - SOURCE[1]), 0.03)
        lo, hi = pool.radius_range
        self.assertTrue(lo <= radius <= hi, radius)
    # Every bubble that reached the surface, popped or still popping
    popping = sum(1 for b in pool.bubbles if b.state == bubbles.POPPING)
    self.assertEqual(len(events), pool.popped + popping)
    self.assertGreater(len(events), 200)

  def test_events_last_one_step(self):
    pool = BubblePool(SOURCE, SURFACE, seed=4)
    while not pool.pop_events:
      pool.step(1 / 60.0)
    pool.step(0.0)
    self.assertEqual(pool.pop_events, [])

  def test_no_events_before_the_first_pop(self):
    pool = BubblePool(SOURCE, SURFACE)
    self.assertEqual(pool.pop_events, [])
    run(pool, 0.5)
    self.assertEqual(pool.pop_events, [])


class RipplePoolTests(unittest.TestCase):

  def test_ripple_spreads_and_fades(self):
    ripples = bubbles.RipplePool(capacity=1)
    r = ripples.start(0.3, 0.16)
    self.assertEqual(r.progress, 0.0)
    self.assertAlmostEqual(r.spread, bubbles.RIPPLE_START)
    self.assertEqual(r.strength, 1.0)
    last = (r.radius, r.strength)
    for _ in range(int(bubbles.RIPPLE_TIME / 0.05) - 1):
      ripples.step(0.05)
      self.assertTrue(r.active)
      self.assertGreater(r.radius, last[0])
      self.assertLess(r.strength, last[1])
      self.assertLess(r.radius, bubbles.RIPPLE_RADIUS)
      last = (r.radius, r.strength)
    ripples.step(0.1)
    self.assertFalse(r.active)
    # A free slot reads as a spent ripple: spread out, and dark
    self.assertEqual(r.progress, 1.0)
    self.assertAlmostEqual(r.radius, bubbles.RIPPLE_RADIUS)
    self.assertEqual(r.strength, 0.0)

  def test_full_pool_skips_pops(self):
    ripples = bubbles.RipplePool(capacity=2)
    first = ripples.start(0.0, 0.0)
    ripples.step(0.1)
    second = ripples.start(0.0, 0.0)
    self.assertIsNone(ripples.start(0.0, 0.0))
    self.assertEqual(ripples.snapshot(), {'active': 2, 'capacity': 2,
                                          'started': 2, 'skipped': 1})
    # The oldest is not cut short
    self.assertAlmostEqual(first.age, 0.1)
    run(ripples, bubbles.RIPPLE_TIME - 0.05)
    self.assertFalse(first.active)
    self.assertTrue(second.active)
    self.assertIs(ripples.start(0.0, 0.0), first)

  def test_progresses_in_slot_order(self):
    ripples = bubbles.RipplePool(capacity=3)
    self.assertEqual(ripples.progresses(), (1.0, 1.0, 1.0))
    ripples.start(0.0, 0.0)
    ripples.step(bubbles.RIPPLE_TIME / 2)
    ripples.start(0.0, 0.0)
    p = ripples.progresses()
    self.assertAlmostEqual(p[0], 0.5)
    self.assertEqual(p[1:], (0.0, 1.0))

  def test_stream_keeps_the_pool_busy(self):
    pool = BubblePool(SOURCE, SURFACE, seed=2)
    ripples = bubbles.RipplePool()
    for _ in range(int(10 / (1 / 60.0))):
      pool.step(1 / 60.0)
      ripples.step(1 / 60.0)
      for x, y, _ in pool.pop_events:
        ripples.start(x, y)
    snap = ripples.snapshot()
    # Pops come many times a second: a ring starts soon after one ends
    self.assertGreater(snap['started'], 20)
    self.assertGreater(snap['skipped'], 0)
    json.dumps(snap)

  def test_bad_arguments(self):
    with self.assertRaises(ValueError):
      bubbles.RipplePool(capacity=0)
    with self.assertRaises(ValueError):
      bubbles.RipplePool().step(-0.1)


if __name__ == '__main__':
  unittest.main()
