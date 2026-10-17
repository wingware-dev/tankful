"""Stand-in sources for every factor, for the harness: no network, no
battery, and the same readings every run.

With TANKFUL_FACTOR_STANDINS set, the game (tankful.game.factor_hud)
gives its FactorController make_source below, so each factor reads a
canned Reading its effects_for takes: 'offline' makes every stand-in
fail instead, to show the HUD's offline state.

TANKFUL_STANDIN_STOCK picks the Stock stand-in's day: 'down' (the
default) or 'up', for shots of the fish sinking or rising.

TANKFUL_STANDIN_WEATHER picks the Weather stand-in's sky: 'rain' (the
default), 'storm', 'snow', 'clear' or 'cloudy'.
"""

import os

from tankful.factors import base

ENV = 'TANKFUL_FACTOR_STANDINS'

# Per factor key: the reading's value and its HUD label
READINGS = {
  'weather': ({'condition': 'rain', 'cloud_cover': 90.0,
               'precipitation': 2.0, 'wind_speed': 14.0},
              '14°C, rain'),
  'moon': ({'sun_elevation': -24.0, 'moon_illumination': 0.82},
           'night, waxing gibbous'),
  'battery': ({'percent': 35, 'charging': False}, '35%'),
  'stock': (-1.8, 'S&P 500 -1.80%'),
}

STOCK_ENV = 'TANKFUL_STANDIN_STOCK'
STOCK_DAYS = {
  'down': READINGS['stock'],
  'up': (1.6, 'S&P 500 +1.60%'),
}

WEATHER_ENV = 'TANKFUL_STANDIN_WEATHER'
WEATHER_SKIES = {
  'rain': READINGS['weather'],
  'storm': ({'condition': 'storm', 'cloud_cover': 100.0,
             'precipitation': 9.0, 'wind_speed': 40.0}, '17°C, thunderstorm'),
  'snow': ({'condition': 'snow', 'cloud_cover': 95.0,
            'precipitation': 0.6, 'wind_speed': 8.0}, '-3°C, snow'),
  'clear': ({'condition': 'clear', 'cloud_cover': 5.0,
             'precipitation': 0.0, 'wind_speed': 6.0}, '22°C, clear'),
  'cloudy': ({'condition': 'cloudy', 'cloud_cover': 85.0,
              'precipitation': 0.0, 'wind_speed': 10.0}, '15°C, cloudy'),
}


def _choice(env, name, choices, default):
  value = env.get(name, '').strip().lower() or default
  if value not in choices:
    raise ValueError('%s must be one of %s, not %r'
                     % (name, ', '.join(sorted(choices)), value))
  return choices[value]


def reading(key, env=None):
  """The stand-in (value, label) for factor key, or None."""
  env = os.environ if env is None else env
  if key == 'stock':
    day = env.get(STOCK_ENV, '').strip().lower() or 'down'
    if day not in STOCK_DAYS:
      raise ValueError('%s must be one of %s, not %r'
                       % (STOCK_ENV, ', '.join(sorted(STOCK_DAYS)), day))
    return STOCK_DAYS[day]
  if key == 'weather':
    return _choice(env, WEATHER_ENV, WEATHER_SKIES, 'rain')
  return READINGS.get(key)


def mode(env=None):
  """'' with no stand-ins, else 'offline' or 'on'."""
  env = os.environ if env is None else env
  value = env.get(ENV, '').strip().lower()
  if not value or value in ('0', 'off', 'no'):
    return ''
  return 'offline' if value == 'offline' else 'on'


def make_source(factor, settings, offline=False):
  """The stand-in Source for factor (a registry.Factor), or None for the
  None factor."""
  if factor.module is None:
    return None
  name = 'standin-' + factor.key
  canned = None if offline else reading(factor.key)
  if canned is None:
    return base.ScriptedSource([None], name=name)
  value, label = canned
  return base.StaticSource(name, value, label)


def make_source_offline(factor, settings):
  return make_source(factor, settings, offline=True)


def for_env(env=None):
  """The make_source the environment asks for, or None for the real
  sources."""
  which = mode(env)
  if which == 'on':
    reading('stock', env)   # a bad TANKFUL_STANDIN_STOCK fails here, at start
    reading('weather', env)  # and a bad TANKFUL_STANDIN_WEATHER
  return {'': None, 'on': make_source,
          'offline': make_source_offline}[which]
