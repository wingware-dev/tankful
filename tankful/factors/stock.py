"""The Stock factor: today's S&P 500 move sets how high the fish swim.

Up days lift the depth band toward the surface and down days sink it
toward the sand, in proportion to the day's change up to FULL_SCALE.

The data is Yahoo's chart endpoint, which needs no key but is unofficial
and rate limited, so everything here fails soft: a failed fetch or an
unexpected response is no reading, and the tank stays neutral.  It is
refetched every 10 minutes while the US market is open; otherwise the
last reading is kept until the next open.

Market hours are computed here (9:30 to 16:00 New York time, weekdays,
with US daylight saving), without zoneinfo, which may lack its tz data
under UPBGE's Python.  Holidays are not known, so on one the source just
refetches the unchanged close every 10 minutes.
"""

import datetime
import time
import urllib.parse

from tankful.factors import base
from tankful.factors import effects
from tankful.factors import net
from tankful.factors import settings as settings_mod


KEY = 'stock'

SYMBOL = '^GSPC'
NAMES = {'^GSPC': 'S&P 500'}
URL = ('https://query1.finance.yahoo.com/v8/finance/chart/%s'
       '?range=2d&interval=1d')

OPEN_TTL = 600.0       # seconds between fetches while the market is open
MIN_TTL = 60.0
CLOSE_MARGIN = 300.0   # one more fetch this long after the close, for it

# A day's change in percent that moves the band all the way
FULL_SCALE = 2.0

_OPEN = datetime.time(9, 30)
_CLOSE = datetime.time(16, 0)


def make_source(settings):
  """A StockSource for the settings' 'stock' section.

  The section may name another Yahoo symbol, such as {'symbol': '^IXIC'}.
  """
  section = settings_mod.section(settings, KEY)
  symbol = section.get('symbol')
  if not isinstance(symbol, str) or not symbol.strip():
    symbol = SYMBOL
  return StockSource(symbol.strip())


def effects_for(reading):
  """Effects for a reading whose value is the day's change in percent."""
  try:
    change = float(reading.value)
  except (TypeError, ValueError):
    return effects.NEUTRAL
  if change != change:   # NaN
    return effects.NEUTRAL
  shift = max(-1.0, min(1.0, change / FULL_SCALE))
  return effects.Effects(depth_shift=shift)


class StockSource(base.Source):
  """Fetches the day's percent change for one symbol.

  ttl depends on when the last good reading was fetched: OPEN_TTL while
  the market is open, else until the next open.  opener and clock are for
  the tests: opener(request, timeout) returns a file-like response.
  """
  name = KEY
  retry = 120.0

  def __init__(self, symbol=SYMBOL, opener=None, clock=None):
    self.symbol = symbol
    self._opener = opener or net.urlopen
    self._clock = clock or time.time
    self._fetched = None

  @property
  def ttl(self):
    if self._fetched is None:
      return OPEN_TTL
    return ttl_after(self._fetched)

  def url(self):
    return URL % urllib.parse.quote(self.symbol, safe='')

  def fetch(self):
    data = net.fetch_json(self.url(), opener=self._opener)
    change = parse_change(data)
    if change is None:
      return None
    self._fetched = self._clock()
    name = NAMES.get(self.symbol, self.symbol)
    return base.Reading(change, '%s %+.2f%%' % (name, change))


def parse_change(data):
  """The day's change in percent from a chart response, or None.

  Uses Yahoo's own regularMarketChangePercent when given, else the price
  against the previous close: meta's previousClose, or the session before
  the last in the daily closes.  chartPreviousClose is the close before
  the whole range, so it is only right when the range holds one session.
  """
  try:
    result = data['chart']['result'][0]
    meta = result['meta']
  except (KeyError, IndexError, TypeError):
    return None
  if not isinstance(meta, dict):
    return None
  percent = _number(meta.get('regularMarketChangePercent'))
  if percent is not None:
    return percent
  closes = _closes(result)
  price = _number(meta.get('regularMarketPrice'))
  if price is None and closes:
    price = closes[-1]
  previous = _number(meta.get('previousClose'))
  if previous is None and len(closes) >= 2:
    previous = closes[-2]
  if previous is None and len(closes) <= 1:
    previous = _number(meta.get('chartPreviousClose'))
  if price is None or not previous or previous <= 0:
    return None
  return (price / previous - 1.0) * 100.0


def _closes(result):
  try:
    closes = result['indicators']['quote'][0]['close']
  except (KeyError, IndexError, TypeError):
    return []
  if not isinstance(closes, list):
    return []
  return [c for c in (_number(c) for c in closes) if c is not None]


def _number(value):
  if isinstance(value, bool) or not isinstance(value, (int, float)):
    return None
  value = float(value)
  if value != value or value in (float('inf'), float('-inf')):
    return None
  return value


# Market hours, in New York time


def _first_sunday(year, month):
  day = datetime.date(year, month, 1)
  return day + datetime.timedelta(days=(6 - day.weekday()) % 7)


def _utc_offset(when):
  """New York's UTC offset at a UTC datetime: EDT from the second Sunday
  of March to the first Sunday of November, both at 2:00 local."""
  year = when.year
  start = datetime.datetime.combine(
    _first_sunday(year, 3) + datetime.timedelta(days=7),
    datetime.time(7, 0))              # 2:00 EST
  end = datetime.datetime.combine(_first_sunday(year, 11),
                                  datetime.time(6, 0))   # 2:00 EDT
  naive = when.replace(tzinfo=None)
  hours = -4 if start <= naive < end else -5
  return datetime.timedelta(hours=hours)


def _utc(timestamp):
  return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)


def new_york_time(timestamp):
  """The naive New York wall time at a time.time() timestamp."""
  when = _utc(timestamp)
  return (when + _utc_offset(when)).replace(tzinfo=None)


def _timestamp(local):
  """time.time() for a naive New York wall time (not in a DST gap)."""
  guess = local.replace(tzinfo=datetime.timezone.utc)
  offset = _utc_offset(guess + datetime.timedelta(hours=5))
  return (guess - offset).timestamp()


def market_open(timestamp):
  """Whether the US market is in regular hours (holidays aside)."""
  local = new_york_time(timestamp)
  return local.weekday() < 5 and _OPEN <= local.time() < _CLOSE


def next_open(timestamp):
  """The timestamp of the next regular open after this time."""
  local = new_york_time(timestamp)
  day = local.date()
  if local.time() >= _OPEN:
    day += datetime.timedelta(days=1)
  while day.weekday() >= 5:
    day += datetime.timedelta(days=1)
  return _timestamp(datetime.datetime.combine(day, _OPEN))


def ttl_after(timestamp):
  """How long a reading fetched at this time stays fresh."""
  if market_open(timestamp):
    local = new_york_time(timestamp)
    close = datetime.datetime.combine(local.date(), _CLOSE)
    until_close = _timestamp(close) - timestamp
    # Refetch every OPEN_TTL, and once shortly after the close
    return max(MIN_TTL, min(OPEN_TTL, until_close + CLOSE_MARGIN))
  return max(MIN_TTL, next_open(timestamp) - timestamp)
