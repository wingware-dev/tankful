"""Stand-in sources for every factor, for the harness: no network, no
battery, and the same readings every run.

With TANKFUL_FACTOR_STANDINS set, the game (tankful.game.factor_hud)
gives its FactorController make_source below, so each factor reads a
canned Reading its effects_for takes: 'offline' makes every stand-in
fail instead, to show the HUD's offline state.
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
  if offline or factor.key not in READINGS:
    return base.ScriptedSource([None], name=name)
  value, label = READINGS[factor.key]
  return base.StaticSource(name, value, label)


def make_source_offline(factor, settings):
  return make_source(factor, settings, offline=True)


def for_env(env=None):
  """The make_source the environment asks for, or None for the real
  sources."""
  return {'': None, 'on': make_source,
          'offline': make_source_offline}[mode(env)]
