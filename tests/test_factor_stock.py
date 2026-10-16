import datetime
import io
import json
import os
import sys
import unittest
import urllib.error
from unittest import mock

from tankful.factors import base
from tankful.factors import effects
from tankful.factors import registry
from tankful.factors import stock


def utc(*args):
  """time.time() for a UTC date and time."""
  return datetime.datetime(*args, tzinfo=datetime.timezone.utc).timestamp()


# 2026-10-16 is a Friday, in EDT (UTC-4)
FRIDAY_10AM = utc(2026, 10, 16, 14, 0)
FRIDAY_3_58PM = utc(2026, 10, 16, 19, 58)
FRIDAY_5PM = utc(2026, 10, 16, 21, 0)
MONDAY_930AM = utc(2026, 10, 19, 13, 30)


LIVE_FIXTURE = os.path.join(os.path.dirname(__file__), 'fixtures',
                            'yahoo_chart_gspc.json')
LIVE_URL = ('https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC'
            '?range=2d&interval=1d')


def live_bytes():
  """A real chart reply for LIVE_URL (re-indented, data unchanged)."""
  with open(LIVE_FIXTURE, 'rb') as f:
    return f.read()


def live():
  return json.loads(live_bytes())


def chart(price=5050.0, previous=5000.0, closes=(5000.0, 5050.0),
          chart_previous=4900.0, **meta):
  """A chart response shaped like Yahoo's, range=2d&interval=1d."""
  base_meta = {'symbol': '^GSPC', 'currency': 'USD',
               'regularMarketPrice': price,
               'chartPreviousClose': chart_previous}
  if previous is not None:
    base_meta['previousClose'] = previous
  base_meta.update(meta)
  return {'chart': {'result': [{
    'meta': base_meta,
    'timestamp': [1760621400, 1760707800][:len(closes)],
    'indicators': {'quote': [{'close': list(closes)}]},
  }], 'error': None}}


class FakeOpener:
  """Stands in for urlopen: returns canned bodies, or raises."""

  def __init__(self, *bodies):
    self.bodies = list(bodies)
    self.requests = []

  def __call__(self, request, timeout=None):
    self.requests.append(request)
    body = self.bodies[min(len(self.requests), len(self.bodies)) - 1]
    if isinstance(body, BaseException):
      raise body
    if not isinstance(body, bytes):
      body = json.dumps(body).encode('utf-8')
    return io.BytesIO(body)


class LiveResponseTests(unittest.TestCase):
  """A real reply, fetched from LIVE_URL after the close on 2026-10-16."""

  def test_parses(self):
    self.assertAlmostEqual(stock.parse_change(live()), -1.093)

  def test_without_yahoo_percent_uses_closes(self):
    # The day before's close, from the closes: chartPreviousClose
    # (7718.94) is the close before the two-day range, and would give
    # about -0.77%
    data = live()
    del data['chart']['result'][0]['meta']['regularMarketChangePercent']
    self.assertAlmostEqual(stock.parse_change(data),
                           (7659.44 / 7744.06005859375 - 1) * 100)
    self.assertAlmostEqual(stock.parse_change(data), -1.093, places=3)

  def test_effects(self):
    reading = base.Reading(stock.parse_change(live()), '')
    self.assertAlmostEqual(stock.effects_for(reading).depth_shift,
                           -1.093 / stock.FULL_SCALE)


class ParseChangeTests(unittest.TestCase):

  def test_price_against_previous_close(self):
    self.assertAlmostEqual(stock.parse_change(chart()), 1.0)

  def test_down_day(self):
    self.assertAlmostEqual(stock.parse_change(chart(price=4900.0)), -2.0)

  def test_prefers_yahoo_percent(self):
    data = chart(regularMarketChangePercent=0.42)
    self.assertAlmostEqual(stock.parse_change(data), 0.42)

  def test_previous_session_from_closes(self):
    # Without previousClose, the session before the last; not
    # chartPreviousClose, which is before the two-day range
    data = chart(previous=None, closes=(5000.0, 5050.0), price=5100.0)
    self.assertAlmostEqual(stock.parse_change(data), 2.0)

  def test_chart_previous_close_with_one_session(self):
    data = chart(previous=None, closes=(5050.0,), chart_previous=5000.0)
    self.assertAlmostEqual(stock.parse_change(data), 1.0)

  def test_null_closes_skipped(self):
    data = chart(previous=None, closes=(5000.0, None, 5050.0), price=None)
    self.assertAlmostEqual(stock.parse_change(data), 1.0)

  def test_bad_responses(self):
    for data in ({}, [], None, {'chart': {'result': None}},
                 {'chart': {'result': []}},
                 {'chart': {'result': [{'meta': 'x'}]}},
                 {'chart': {'result': None,
                            'error': {'code': 'Not Found'}}},
                 chart(price=None, closes=()),
                 chart(previous=0.0, closes=()),
                 chart(price='5050', closes=()),
                 chart(regularMarketChangePercent=float('nan'), closes=(),
                       price=None)):
      with self.subTest(data=data):
        self.assertIsNone(stock.parse_change(data))


class EffectsTests(unittest.TestCase):

  def reading(self, value):
    return base.Reading(value, '')

  def test_flat_is_neutral(self):
    self.assertEqual(stock.effects_for(self.reading(0.0)), effects.NEUTRAL)

  def test_up_lifts(self):
    e = stock.effects_for(self.reading(1.0))
    self.assertAlmostEqual(e.depth_shift, 0.5)
    self.assertEqual(e.replace(depth_shift=0.0), effects.NEUTRAL)

  def test_down_sinks(self):
    self.assertAlmostEqual(
      stock.effects_for(self.reading(-0.5)).depth_shift, -0.25)

  def test_clamped(self):
    self.assertEqual(stock.effects_for(self.reading(7.5)).depth_shift, 1.0)
    self.assertEqual(stock.effects_for(self.reading(-12)).depth_shift, -1.0)

  def test_bad_values_neutral(self):
    for value in (None, 'up', float('nan'), {'change': 1}):
      with self.subTest(value=value):
        self.assertEqual(stock.effects_for(self.reading(value)),
                         effects.NEUTRAL)

  def test_through_registry(self):
    factor = registry.get('stock')
    self.assertTrue(factor.available)
    self.assertAlmostEqual(
      factor.effects_for(self.reading(-1.0)).depth_shift, -0.5)
    self.assertEqual(factor.effects_for(None), effects.NEUTRAL)


class MarketHoursTests(unittest.TestCase):

  def test_new_york_time_edt_and_est(self):
    self.assertEqual(stock.new_york_time(FRIDAY_10AM),
                     datetime.datetime(2026, 10, 16, 10, 0))
    self.assertEqual(stock.new_york_time(utc(2026, 1, 5, 15, 0)),
                     datetime.datetime(2026, 1, 5, 10, 0))

  def test_dst_boundaries(self):
    # 2026: DST from Sunday March 8 to Sunday November 1, 2:00 local
    self.assertEqual(stock.new_york_time(utc(2026, 3, 8, 6, 59)).hour, 1)
    self.assertEqual(stock.new_york_time(utc(2026, 3, 8, 7, 0)).hour, 3)
    self.assertEqual(stock.new_york_time(utc(2026, 11, 1, 5, 59)).hour, 1)
    self.assertEqual(stock.new_york_time(utc(2026, 11, 1, 6, 0)).hour, 1)

  def test_open(self):
    self.assertTrue(stock.market_open(FRIDAY_10AM))
    self.assertTrue(stock.market_open(utc(2026, 10, 16, 13, 30)))

  def test_closed(self):
    for when in (utc(2026, 10, 16, 13, 29),     # 9:29
                 utc(2026, 10, 16, 20, 0),      # 16:00
                 FRIDAY_5PM,
                 utc(2026, 10, 17, 15, 0),      # Saturday
                 utc(2026, 10, 18, 15, 0)):     # Sunday
      with self.subTest(when=when):
        self.assertFalse(stock.market_open(when))

  def test_open_in_winter(self):
    # 9:30 EST is 14:30 UTC
    self.assertFalse(stock.market_open(utc(2026, 12, 1, 14, 29)))
    self.assertTrue(stock.market_open(utc(2026, 12, 1, 14, 30)))

  def test_next_open(self):
    self.assertEqual(stock.next_open(FRIDAY_5PM), MONDAY_930AM)
    self.assertEqual(stock.next_open(FRIDAY_10AM), MONDAY_930AM)
    self.assertEqual(stock.next_open(utc(2026, 10, 15, 2, 0)),
                     utc(2026, 10, 15, 13, 30))   # Wed 22:00 -> Thu 9:30

  def test_next_open_across_dst_end(self):
    # Friday Oct 30 (EDT) to Monday Nov 2 (EST): 9:30 is 14:30 UTC
    self.assertEqual(stock.next_open(utc(2026, 10, 30, 21, 0)),
                     utc(2026, 11, 2, 14, 30))

  def test_ttl_while_open(self):
    self.assertEqual(stock.ttl_after(FRIDAY_10AM), stock.OPEN_TTL)

  def test_ttl_near_close_fetches_once_after(self):
    # 15:58: 2 minutes to the close plus the margin
    self.assertEqual(stock.ttl_after(FRIDAY_3_58PM),
                     120 + stock.CLOSE_MARGIN)

  def test_ttl_when_closed_lasts_to_open(self):
    self.assertEqual(stock.ttl_after(FRIDAY_5PM), MONDAY_930AM - FRIDAY_5PM)


class SourceTests(unittest.TestCase):

  def test_make_source_default(self):
    source = stock.make_source({'factor': 'stock'})
    self.assertIsInstance(source, base.Source)
    self.assertEqual(source.name, 'stock')
    self.assertEqual(source.symbol, '^GSPC')

  def test_make_source_symbol_setting(self):
    self.assertEqual(
      stock.make_source({'stock': {'symbol': ' ^IXIC '}}).symbol, '^IXIC')
    for section in ({'symbol': ''}, {'symbol': 5}, 'junk'):
      with self.subTest(section=section):
        self.assertEqual(stock.make_source({'stock': section}).symbol,
                         '^GSPC')

  def test_fetch(self):
    opener = FakeOpener(live_bytes())
    source = stock.StockSource(opener=opener, clock=lambda: FRIDAY_5PM)
    reading = source.fetch()
    self.assertAlmostEqual(reading.value, -1.093)
    self.assertEqual(reading.label, 'S&P 500 -1.09%')
    request = opener.requests[0]
    self.assertEqual(request.full_url, LIVE_URL)
    # Yahoo answers 429 to a spoofed browser User-Agent
    self.assertEqual(request.get_header('User-agent'),
                     'tankful/0.1 (+desktop aquarium)')

  def test_label_for_other_symbol(self):
    source = stock.StockSource('^IXIC',
                               opener=FakeOpener(chart(price=4950.0)),
                               clock=lambda: FRIDAY_10AM)
    self.assertEqual(source.fetch().label, '^IXIC -1.00%')

  def test_unexpected_json_is_none(self):
    for body in (b'{}', b'[]', {'chart': {'result': []}}):
      with self.subTest(body=body):
        source = stock.StockSource(opener=FakeOpener(body))
        self.assertIsNone(source.fetch())

  def test_not_json_raises(self):
    # The Poller logs it and treats it as no data
    source = stock.StockSource(opener=FakeOpener(b'Too Many Requests'))
    self.assertRaises(ValueError, source.fetch)

  def test_ttl_follows_last_good_fetch(self):
    clock = base.FakeClock(FRIDAY_5PM)
    source = stock.StockSource(opener=FakeOpener(chart()), clock=clock)
    self.assertEqual(source.ttl, stock.OPEN_TTL)
    source.fetch()
    self.assertEqual(source.ttl, MONDAY_930AM - FRIDAY_5PM)


class FakeContext:

  def __init__(self, cas):
    self.cas = cas
    self.loaded = []

  def cert_store_stats(self):
    return {'crl': 0, 'x509': self.cas, 'x509_ca': self.cas}

  def load_verify_locations(self, cafile=None):
    self.loaded.append(cafile)


class SslTests(unittest.TestCase):

  def setUp(self):
    patcher = mock.patch.object(stock, '_context', None)
    patcher.start()
    self.addCleanup(patcher.stop)
    # Without certifi, as in python.org's Python
    patcher = mock.patch.dict(sys.modules, {'certifi': None})
    patcher.start()
    self.addCleanup(patcher.stop)

  def test_bundle_is_first_that_exists(self):
    self.assertEqual(stock.ca_bundle(lambda p: p.startswith('/etc/pki')),
                     '/etc/pki/tls/certs/ca-bundle.crt')
    self.assertIsNone(stock.ca_bundle(lambda p: False))

  def test_certifi_preferred(self):
    certifi = mock.Mock(where=lambda: '/x/cacert.pem')
    with mock.patch.dict(sys.modules, {'certifi': certifi}):
      self.assertEqual(stock.ca_bundle(lambda p: True), '/x/cacert.pem')

  def test_defaults_kept_when_they_have_cas(self):
    context = FakeContext(cas=140)
    with mock.patch('ssl.create_default_context', return_value=context):
      self.assertIs(stock.ssl_context(), context)
    self.assertEqual(context.loaded, [])

  def test_bundle_loaded_when_defaults_empty(self):
    context = FakeContext(cas=0)
    with mock.patch('ssl.create_default_context', return_value=context), \
         mock.patch.object(stock, 'ca_bundle', return_value='/b.pem'), \
         self.assertLogs('tankful.factors', 'INFO'):
      self.assertIs(stock.ssl_context(), context)
      self.assertIs(stock.ssl_context(), context)
    self.assertEqual(context.loaded, ['/b.pem'])

  def test_warns_with_no_bundle(self):
    context = FakeContext(cas=0)
    with mock.patch('ssl.create_default_context', return_value=context), \
         mock.patch.object(stock, 'ca_bundle', return_value=None), \
         self.assertLogs('tankful.factors', 'WARNING'):
      stock.ssl_context()
    self.assertEqual(context.loaded, [])

  def test_urlopen_uses_context(self):
    context = FakeContext(cas=1)
    with mock.patch.object(stock, '_context', context), \
         mock.patch('urllib.request.urlopen') as urlopen:
      stock._urlopen('request', timeout=3)
    urlopen.assert_called_once_with('request', timeout=3, context=context)


class PollerTests(unittest.TestCase):

  def poller(self, now, *bodies):
    clock = base.FakeClock(now)
    opener = FakeOpener(*bodies)
    source = stock.StockSource(opener=opener, clock=clock)
    return base.Poller(source, clock=clock), clock, opener

  def test_refreshes_every_ten_minutes_while_open(self):
    poller, clock, opener = self.poller(FRIDAY_10AM, chart(price=5050.0),
                                        chart(price=4950.0))
    self.assertEqual(poller.poll(), stock.OPEN_TTL)
    self.assertEqual(poller.status().label, 'S&P 500 +1.00%')
    clock.advance(599)
    self.assertAlmostEqual(poller.poll(), 1.0)
    self.assertEqual(len(opener.requests), 1)
    clock.advance(1)
    poller.poll()
    self.assertEqual(len(opener.requests), 2)
    self.assertEqual(poller.status().label, 'S&P 500 -1.00%')

  def test_cached_until_open_when_closed(self):
    poller, clock, opener = self.poller(FRIDAY_5PM, live_bytes())
    self.assertEqual(poller.poll(), MONDAY_930AM - FRIDAY_5PM)
    clock.now = utc(2026, 10, 18, 12, 0)   # Sunday
    self.assertGreater(poller.poll(), 0)
    self.assertEqual(len(opener.requests), 1)
    self.assertFalse(poller.status().offline)
    clock.now = MONDAY_930AM
    poller.poll()
    self.assertEqual(len(opener.requests), 2)

  def test_fetches_the_close(self):
    poller, clock, opener = self.poller(FRIDAY_3_58PM, chart(), chart())
    poller.poll()
    clock.advance(120 + stock.CLOSE_MARGIN)
    poller.poll()
    self.assertEqual(len(opener.requests), 2)
    # That after-close reading lasts until Monday
    self.assertEqual(poller.poll(), MONDAY_930AM - clock.now)

  def test_failure_is_neutral(self):
    error = urllib.error.HTTPError('u', 429, 'Too Many Requests', {}, None)
    poller, clock, opener = self.poller(FRIDAY_10AM, error)
    with self.assertLogs('tankful.factors', 'WARNING'):
      self.assertEqual(poller.poll(), stock.StockSource.retry)
    status = poller.status()
    self.assertTrue(status.offline)
    self.assertIsNone(status.reading)
    self.assertEqual(registry.get('stock').effects_for(status.reading),
                     effects.NEUTRAL)

  def test_failure_keeps_last_reading_then_drops_it(self):
    poller, clock, opener = self.poller(
      FRIDAY_10AM, chart(price=5100.0), urllib.error.URLError('down'))
    poller.poll()
    clock.advance(stock.OPEN_TTL)
    with self.assertLogs('tankful.factors', 'WARNING'):
      poller.poll()
    status = poller.status()
    self.assertTrue(status.offline)
    self.assertEqual(status.label, 'S&P 500 +2.00% (offline)')
    clock.advance(3 * stock.OPEN_TTL)
    self.assertIsNone(poller.status().reading)


if __name__ == '__main__':
  unittest.main()
