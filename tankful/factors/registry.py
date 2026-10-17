"""The factors the viewer can pick, in picker order.

Each factor but None is a module tankful/factors/<key>.py exposing:

  make_source(settings) -> base.Source, or None when it can't run here
  effects_for(reading) -> effects.Effects for a base.Reading

and may expose light_for(reading) -> bool, whether the tank's light
should be on, for a factor that works the light switch (moon.py).

The modules import lazily, on first use, so one that is missing or fails
to import only makes its own factor unavailable (and neutral).
"""

import dataclasses
import importlib
import logging

from tankful.factors import effects

log = logging.getLogger('tankful.factors')

_MISSING = object()


@dataclasses.dataclass
class Factor:
  key: str            # settings value and module name
  label: str          # picker text
  module: str = None  # dotted module name; None for the None factor
  _loaded: object = dataclasses.field(default=None, repr=False,
                                      compare=False)

  def load(self):
    """The factor's module, or None when it has none or fails to import."""
    if self.module is None:
      return None
    if self._loaded is None:
      try:
        self._loaded = importlib.import_module(self.module)
      except ImportError:
        log.warning('Factor %s unavailable', self.key, exc_info=True)
        self._loaded = _MISSING
    return None if self._loaded is _MISSING else self._loaded

  @property
  def available(self):
    return self.module is None or self.load() is not None

  def make_source(self, settings):
    """The factor's Source for these settings, or None (logged on error)."""
    module = self.load()
    if module is None:
      return None
    try:
      return module.make_source(settings)
    except Exception:
      log.exception('Factor %s: make_source failed', self.key)
      return None

  def effects_for(self, reading):
    """The clamped Effects for a reading; NEUTRAL with none or on error."""
    module = self.load()
    if module is None or reading is None:
      return effects.NEUTRAL
    try:
      result = module.effects_for(reading)
    except Exception:
      log.exception('Factor %s: effects_for failed', self.key)
      return effects.NEUTRAL
    if not isinstance(result, effects.Effects):
      log.error('Factor %s: effects_for returned %r', self.key, result)
      return effects.NEUTRAL
    return result.clamped()

  def light_for(self, reading):
    """Whether the tank's light should be on for a reading, for a factor
    that works the light switch (its module's light_for); None for one
    that doesn't, with no reading, or on error."""
    module = self.load()
    light_for = getattr(module, 'light_for', None)
    if light_for is None or reading is None:
      return None
    try:
      return bool(light_for(reading))
    except Exception:
      log.exception('Factor %s: light_for failed', self.key)
      return None


def _factor(key, label):
  return Factor(key, label, 'tankful.factors.' + key)


FACTORS = (
  Factor('none', 'None'),
  _factor('weather', 'Weather'),
  _factor('moon', 'Time & Moon'),
  _factor('battery', 'Battery'),
  _factor('stock', 'Stock'),
)

DEFAULT = 'none'


def keys():
  return [f.key for f in FACTORS]


def get(key):
  """The factor for a key; the None factor for an unknown one."""
  for f in FACTORS:
    if f.key == key:
      return f
  if key != DEFAULT:
    log.warning('Unknown factor %r, using %r', key, DEFAULT)
  return FACTORS[0]
