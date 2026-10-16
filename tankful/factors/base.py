"""Sources of external data, and the background thread that polls them.

A Source fetches one Reading (the weather, the battery level, ...) and says
how long it stays good (ttl).  The Poller keeps a TTL cache of readings per
source and decides when to fetch, and it fails soft: when a fetch fails it
keeps the last good reading for a while (shown as offline on the HUD), and
past that drops to no reading, so the factor's effects go neutral.
FetchThread runs a Poller in the background so a slow network never stalls
a frame; the game only ever reads status().

Stand-in sources for the tests are at the end.  Nothing here imports bge.
"""

import collections
import dataclasses
import logging
import threading
import time

log = logging.getLogger('tankful.factors')


@dataclasses.dataclass(frozen=True)
class Reading:
  """One fetched value.

  value: the factor's own data (a number or a dict), for its effects_for.
  label: short text for the HUD, such as '12°C, rain' or '84%'.
  time: when it was fetched, as time.time(); the Poller stamps it when 0.
  """
  value: object
  label: str = ''
  time: float = 0.0


class Source:
  """Fetches readings for one factor.

  Subclasses set name and ttl and define fetch().  fetch() runs on the
  fetch thread, may block on the network, and returns a Reading, or None
  when there is no data; raising counts the same as None, and is logged.
  """
  name = 'source'
  ttl = 600.0          # seconds a reading stays fresh
  retry = 60.0         # seconds to wait after a failed fetch
  max_stale = None     # seconds a failed source keeps its last reading;
                       # None is 3 * ttl

  def fetch(self):
    raise NotImplementedError

  def keep_for(self):
    """How long the last good reading is kept once fetches fail."""
    return 3 * self.ttl if self.max_stale is None else self.max_stale


class Status(collections.namedtuple('Status', 'source reading offline')):
  """What the HUD and the effects layer see.

  source: the active source's name, or None with no factor.
  reading: the reading to use (maybe an old one while offline), or None.
  offline: the last fetch failed.
  """
  __slots__ = ()

  @property
  def label(self):
    """HUD text: the reading's label, marked when offline."""
    if self.source is None:
      return ''
    if self.reading is None:
      return 'offline' if self.offline else '…'
    if self.offline:
      return '%s (offline)' % self.reading.label
    return self.reading.label


IDLE = Status(None, None, False)


class Poller:
  """The TTL cache and fetch schedule for the active source.

  Not a thread: poll() fetches when due and says how long to wait, so the
  tests drive it with a fake clock.  Safe to use from two threads: the
  game thread calls set_source() and status() while FetchThread polls.
  """

  def __init__(self, source=None, clock=time.time):
    self._clock = clock
    self._lock = threading.Lock()
    self._source = None
    self._generation = 0
    # Per source name: the last good reading, and when it was fetched
    self._cache = {}
    # For the active source: when to fetch next, and whether the last
    # fetch failed
    self._next = 0.0
    self._offline = False
    self.set_source(source)

  @property
  def source(self):
    return self._source

  def set_source(self, source):
    """Make source the active one (None for no factor).

    A cached reading still inside its ttl is used at once, without a
    fetch; otherwise the next poll() fetches.
    """
    now = self._clock()
    with self._lock:
      self._source = source
      self._generation += 1
      self._offline = False
      self._next = now
      if source is not None:
        cached = self._cache.get(source.name)
        if cached is not None and now - cached[1] < source.ttl:
          self._next = cached[1] + source.ttl

  def poll(self):
    """Fetch if due; returns seconds until the next poll is wanted.

    With no source it returns None: nothing to do until set_source().
    """
    with self._lock:
      source, generation = self._source, self._generation
      if source is None:
        return None
      wait = self._next - self._clock()
    if wait > 0:
      return wait
    reading = self._fetch(source)
    now = self._clock()
    with self._lock:
      if generation != self._generation:
        # The source changed while fetching: drop the result, poll again
        return 0.0
      if reading is None:
        if not self._offline:
          log.warning('%s: no data, using fallback', source.name)
        self._offline = True
        self._next = now + min(source.retry, source.ttl)
      else:
        if not reading.time:
          reading = dataclasses.replace(reading, time=now)
        if self._offline:
          log.info('%s: back online', source.name)
        self._offline = False
        self._cache[source.name] = (reading, now)
        self._next = now + source.ttl
      return max(0.0, self._next - now)

  def _fetch(self, source):
    try:
      reading = source.fetch()
    except Exception:
      # Warn when a source first fails; while offline, retries only debug
      level = logging.DEBUG if self._offline else logging.WARNING
      log.log(level, '%s: fetch failed', source.name, exc_info=True)
      return None
    if reading is not None and not isinstance(reading, Reading):
      log.error('%s: fetch returned %r, not a Reading', source.name, reading)
      return None
    return reading

  def status(self):
    """The Status to show now: never blocks on a fetch."""
    now = self._clock()
    with self._lock:
      source = self._source
      if source is None:
        return IDLE
      cached = self._cache.get(source.name)
      reading = None
      if cached is not None:
        # A reading past its ttl is still shown until the refetch lands,
        # but once fetches fail it is only kept for keep_for()
        age = now - cached[1]
        if not self._offline or age < max(source.ttl, source.keep_for()):
          reading = cached[0]
      return Status(source.name, reading, self._offline)


class FetchThread:
  """Runs a Poller on a daemon thread.

  start() once; set_source() from the game when the viewer picks a factor;
  status() each frame; stop() on exit.
  """

  def __init__(self, source=None, clock=time.time, poller=None):
    self.poller = poller or Poller(source, clock=clock)
    self._wake = threading.Event()
    self._stopping = False
    self._thread = None

  def start(self):
    if self._thread is None:
      self._thread = threading.Thread(target=self._run, name='tankful-fetch',
                                      daemon=True)
      self._thread.start()
    return self

  def set_source(self, source):
    self.poller.set_source(source)
    self._wake.set()

  def refresh(self):
    """Wake the thread to poll now (for instance after a settings change)."""
    self._wake.set()

  def status(self):
    return self.poller.status()

  def stop(self, timeout=2.0):
    """Ask the thread to end, and wait up to timeout for it.

    A fetch blocked on the network may outlast the wait; the thread is a
    daemon, so it never holds up exit.
    """
    self._stopping = True
    self._wake.set()
    if self._thread is not None:
      self._thread.join(timeout)
    return self._thread is None or not self._thread.is_alive()

  def _run(self):
    while not self._stopping:
      try:
        wait = self.poller.poll()
      except Exception:
        log.exception('fetch thread: poll failed')
        wait = 60.0
      if self._stopping:
        break
      if wait is None or wait > 0:
        self._wake.wait(wait)
      self._wake.clear()


# Stand-in sources, for the tests and the harness: never touch the network


class StaticSource(Source):
  """Always returns the same reading."""

  def __init__(self, name='static', value=0.0, label='', ttl=600.0):
    self.name = name
    self.ttl = ttl
    self.reading = Reading(value, label)
    self.calls = 0

  def fetch(self):
    self.calls += 1
    return self.reading


class ScriptedSource(Source):
  """Returns a scripted sequence, then repeats its last entry.

  Each entry is a Reading, None (no data) or an exception to raise.  With
  a gate (a threading.Event), each fetch first waits for it, so a test can
  hold a fetch in flight.
  """

  def __init__(self, script, name='scripted', ttl=600.0, retry=60.0,
               max_stale=None, gate=None):
    self.name = name
    self.ttl = ttl
    self.retry = retry
    self.max_stale = max_stale
    self.script = list(script)
    self.gate = gate
    self.calls = 0
    self.started = threading.Event()
    self.fetched = threading.Event()

  def fetch(self):
    self.started.set()
    if self.gate is not None:
      self.gate.wait(5.0)
    entry = self.script[min(self.calls, len(self.script) - 1)]
    self.calls += 1
    self.fetched.set()
    if isinstance(entry, BaseException):
      raise entry
    return entry


class FakeClock:
  """A settable clock for Poller(clock=...)."""

  def __init__(self, now=1000.0):
    self.now = now

  def __call__(self):
    return self.now

  def advance(self, seconds):
    self.now += seconds
