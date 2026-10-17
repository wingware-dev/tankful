"""Ties the factor framework together for the game.

The game makes one FactorController at start, calls select() when the
viewer picks a factor, and update(dt) each frame for the Effects to apply
(eased, so changes fade in) and label for the HUD.  The pick is saved to
the settings file at once.
"""

from tankful.factors import base
from tankful.factors import effects
from tankful.factors import registry
from tankful.factors import settings as settings_mod


class FactorController:

  def __init__(self, settings=None, settings_path=None, thread=None,
               save=True, time_constant=2.0, make_source=None):
    """settings: a dict, else loaded from settings_path (else the default
    path).  thread: a FetchThread, for the tests; made and started here
    when None.  save=False never writes the settings file.  make_source:
    make_source(factor, settings) gives the factor's Source in place of
    its own, for stand-ins (tankful.factors.standins).
    """
    self.settings_path = settings_path
    if settings is None:
      settings = settings_mod.load(settings_path)
    self.settings = settings
    self._save = save
    self.time_constant = time_constant
    self.thread = thread or base.FetchThread().start()
    self.effects = effects.NEUTRAL
    self._make_source = make_source
    self.factor = registry.get(settings.get('factor'))
    self.thread.set_source(self._source())

  @property
  def key(self):
    return self.factor.key

  def select(self, key):
    """Switch to the factor for key and remember the choice."""
    self.factor = registry.get(key)
    self.settings['factor'] = self.factor.key
    if self._save:
      settings_mod.save(self.settings, self.settings_path)
    self.thread.set_source(self._source())
    return self.factor

  def _source(self):
    if self._make_source is not None:
      return self._make_source(self.factor, self.settings)
    return self.factor.make_source(self.settings)

  def status(self):
    return self.thread.status()

  @property
  def label(self):
    """HUD text: the factor and its live value, or '' with no factor."""
    if self.factor.module is None:
      return ''
    if not self.factor.available:
      return '%s: unavailable' % self.factor.label
    text = self.status().label
    return '%s: %s' % (self.factor.label, text) if text else self.factor.label

  def target(self):
    """The Effects the current reading calls for, before easing."""
    return self.factor.effects_for(self.status().reading)

  def light_for(self):
    """Whether the current reading wants the tank's light on, for a
    factor that works the switch; None otherwise or with no reading."""
    return self.factor.light_for(self.status().reading)

  def update(self, dt):
    """Ease toward the target over dt seconds; returns the Effects to use."""
    self.effects = effects.approach(self.effects, self.target(), dt,
                                    self.time_constant)
    return self.effects

  def stop(self):
    return self.thread.stop()
