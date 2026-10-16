import threading
import time
import unittest

from tankful.factors import base
from tankful.factors.base import FakeClock, Reading, ScriptedSource

GOOD = Reading(1.0, 'good')
LATER = Reading(2.0, 'later')


def poller(source):
  clock = FakeClock()
  return base.Poller(source, clock=clock), clock


class ReadingTests(unittest.TestCase):

  def test_fields(self):
    r = Reading({'temp': 12}, '12°C')
    self.assertEqual(r.value, {'temp': 12})
    self.assertEqual(r.label, '12°C')
    self.assertEqual(r.time, 0.0)


class SourceTests(unittest.TestCase):

  def test_fetch_is_abstract(self):
    with self.assertRaises(NotImplementedError):
      base.Source().fetch()

  def test_keep_for_defaults_to_three_ttls(self):
    s = base.Source()
    s.ttl = 100
    self.assertEqual(s.keep_for(), 300)
    s.max_stale = 50
    self.assertEqual(s.keep_for(), 50)

  def test_static_source(self):
    s = base.StaticSource('s', 3, 'three')
    self.assertEqual(s.fetch(), Reading(3, 'three'))
    self.assertEqual(s.calls, 1)

  def test_scripted_source_repeats_last(self):
    s = ScriptedSource([GOOD, None, ValueError('x')])
    self.assertEqual(s.fetch(), GOOD)
    self.assertIsNone(s.fetch())
    for _ in range(2):
      with self.assertRaises(ValueError):
        s.fetch()
    self.assertEqual(s.calls, 4)


class StatusTests(unittest.TestCase):

  def test_idle(self):
    self.assertEqual(base.IDLE.label, '')

  def test_labels(self):
    self.assertEqual(base.Status('w', GOOD, False).label, 'good')
    self.assertEqual(base.Status('w', GOOD, True).label, 'good (offline)')
    self.assertEqual(base.Status('w', None, True).label, 'offline')
    self.assertEqual(base.Status('w', None, False).label, '…')


class PollerTests(unittest.TestCase):

  def test_no_source_is_idle(self):
    p, _ = poller(None)
    self.assertIsNone(p.poll())
    self.assertEqual(p.status(), base.IDLE)

  def test_first_poll_fetches_and_stamps_time(self):
    source = ScriptedSource([GOOD], ttl=100)
    p, clock = poller(source)
    self.assertEqual(p.status(), base.Status('scripted', None, False))
    self.assertEqual(p.poll(), 100)
    status = p.status()
    self.assertEqual(status.reading.value, 1.0)
    self.assertEqual(status.reading.time, clock.now)
    self.assertFalse(status.offline)

  def test_keeps_fetched_time(self):
    p, _ = poller(ScriptedSource([Reading(1, 'x', time=5.0)]))
    p.poll()
    self.assertEqual(p.status().reading.time, 5.0)

  def test_ttl_cache(self):
    source = ScriptedSource([GOOD, LATER], ttl=100)
    p, clock = poller(source)
    p.poll()
    clock.advance(60)
    self.assertAlmostEqual(p.poll(), 40)
    self.assertEqual(source.calls, 1)
    clock.advance(40)
    p.poll()
    self.assertEqual(source.calls, 2)
    self.assertEqual(p.status().reading.label, 'later')

  def test_failure_keeps_last_reading_offline(self):
    source = ScriptedSource([GOOD, None], ttl=100, retry=10, max_stale=250)
    p, clock = poller(source)
    p.poll()
    clock.advance(100)
    self.assertEqual(p.poll(), 10)
    status = p.status()
    self.assertTrue(status.offline)
    self.assertEqual(status.reading.label, 'good')
    self.assertEqual(status.label, 'good (offline)')

  def test_failure_past_max_stale_drops_reading(self):
    source = ScriptedSource([GOOD, None], ttl=100, retry=10, max_stale=250)
    p, clock = poller(source)
    p.poll()
    clock.advance(100)
    p.poll()
    clock.advance(149)
    self.assertIsNotNone(p.status().reading)
    clock.advance(1)
    self.assertEqual(p.status(), base.Status('scripted', None, True))

  def test_reading_past_ttl_is_shown_until_refetch(self):
    # With no failure yet, an old reading stays up while a fetch is due
    p, clock = poller(ScriptedSource([GOOD], ttl=100))
    p.poll()
    clock.advance(1000)
    self.assertEqual(p.status().reading.label, 'good')
    self.assertFalse(p.status().offline)

  def test_exception_counts_as_failure(self):
    source = ScriptedSource([OSError('no network')], retry=30)
    p, _ = poller(source)
    with self.assertLogs('tankful.factors', 'WARNING') as logs:
      self.assertEqual(p.poll(), 30)
    self.assertIn('fetch failed', logs.output[0])
    self.assertEqual(p.status(), base.Status('scripted', None, True))

  def test_repeated_failures_warn_once(self):
    source = ScriptedSource([OSError('no network')], retry=30)
    p, clock = poller(source)
    with self.assertLogs('tankful.factors', 'WARNING') as logs:
      p.poll()
      clock.advance(30)
      p.poll()
      clock.advance(30)
      p.poll()
    self.assertEqual(source.calls, 3)
    self.assertEqual(len(logs.output), 2)  # 'fetch failed' + 'no data'

  def test_non_reading_is_failure(self):
    p, _ = poller(ScriptedSource([42]))
    with self.assertLogs('tankful.factors', 'ERROR'):
      p.poll()
    self.assertTrue(p.status().offline)

  def test_retry_capped_by_ttl(self):
    p, _ = poller(ScriptedSource([None], ttl=5, retry=60))
    with self.assertLogs('tankful.factors', 'WARNING'):
      self.assertEqual(p.poll(), 5)

  def test_recovers(self):
    source = ScriptedSource([None, GOOD], ttl=100, retry=10)
    p, clock = poller(source)
    with self.assertLogs('tankful.factors', 'INFO') as logs:
      p.poll()
      clock.advance(10)
      p.poll()
    self.assertIn('back online', logs.output[-1])
    self.assertFalse(p.status().offline)
    self.assertEqual(p.status().reading.label, 'good')

  def test_switch_uses_fresh_cache(self):
    a = ScriptedSource([GOOD], name='a', ttl=100)
    b = ScriptedSource([LATER], name='b', ttl=100)
    p, clock = poller(a)
    p.poll()
    p.set_source(b)
    p.poll()
    clock.advance(50)
    p.set_source(a)
    self.assertEqual(p.status().reading.label, 'good')
    self.assertAlmostEqual(p.poll(), 50)
    self.assertEqual(a.calls, 1)

  def test_switch_refetches_expired_cache(self):
    a = ScriptedSource([GOOD, LATER], name='a', ttl=100)
    p, clock = poller(a)
    p.poll()
    p.set_source(None)
    clock.advance(200)
    p.set_source(a)
    p.poll()
    self.assertEqual(a.calls, 2)

  def test_switch_clears_offline(self):
    a = ScriptedSource([None], name='a')
    b = ScriptedSource([GOOD], name='b')
    p, _ = poller(a)
    with self.assertLogs('tankful.factors', 'WARNING'):
      p.poll()
    p.set_source(b)
    self.assertFalse(p.status().offline)

  def test_result_for_replaced_source_is_dropped(self):
    gate = threading.Event()
    a = ScriptedSource([GOOD], name='a', gate=gate)
    b = ScriptedSource([LATER], name='b')
    p = base.Poller(a)
    results = []
    t = threading.Thread(target=lambda: results.append(p.poll()))
    t.start()
    # Swap while a's fetch is held in flight
    self.assertTrue(a.started.wait(5))
    p.set_source(b)
    gate.set()
    t.join(5)
    self.assertEqual(results, [0.0])
    self.assertEqual(p.status().reading, None)
    p.poll()
    self.assertEqual(p.status().reading.label, 'later')


class FetchThreadTests(unittest.TestCase):

  def wait_for(self, predicate, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
      if predicate():
        return True
      time.sleep(0.005)
    return False

  def test_fetches_in_background(self):
    thread = base.FetchThread(ScriptedSource([GOOD])).start()
    try:
      self.assertTrue(self.wait_for(lambda: thread.status().reading))
      self.assertEqual(thread.status().label, 'good')
    finally:
      self.assertTrue(thread.stop())

  def test_set_source_wakes_thread(self):
    thread = base.FetchThread(None).start()
    try:
      self.assertEqual(thread.status(), base.IDLE)
      thread.set_source(ScriptedSource([LATER], name='b'))
      self.assertTrue(self.wait_for(lambda: thread.status().reading))
      self.assertEqual(thread.status().source, 'b')
    finally:
      self.assertTrue(thread.stop())

  def test_status_never_waits_on_a_fetch(self):
    gate = threading.Event()
    source = ScriptedSource([GOOD], gate=gate)
    thread = base.FetchThread(source).start()
    try:
      start = time.monotonic()
      self.assertIsNone(thread.status().reading)
      self.assertLess(time.monotonic() - start, 0.5)
    finally:
      gate.set()
      self.assertTrue(thread.stop())

  def test_refresh_after_failure(self):
    source = ScriptedSource([None, GOOD], retry=3600)
    thread = base.FetchThread(source)
    with self.assertLogs('tankful.factors', 'WARNING'):
      thread.start()
      self.assertTrue(self.wait_for(lambda: thread.status().offline))
    try:
      # refresh() only wakes it: the retry wait still applies
      thread.refresh()
      time.sleep(0.05)
      self.assertEqual(source.calls, 1)
    finally:
      self.assertTrue(thread.stop())

  def test_stop_without_start(self):
    self.assertTrue(base.FetchThread(None).stop())

  def test_start_twice_is_one_thread(self):
    thread = base.FetchThread(None)
    self.assertIs(thread.start(), thread)
    first = thread._thread
    thread.start()
    self.assertIs(thread._thread, first)
    self.assertTrue(thread.stop())

  def test_daemon(self):
    thread = base.FetchThread(None).start()
    try:
      self.assertTrue(thread._thread.daemon)
    finally:
      thread.stop()


class FakeClockTests(unittest.TestCase):

  def test_advance(self):
    clock = FakeClock(10)
    clock.advance(2.5)
    self.assertEqual(clock(), 12.5)


if __name__ == '__main__':
  unittest.main()
