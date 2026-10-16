"""The viewer's settings: which factor drives the tank, and each factor's own.

Stored as JSON in a per-user config directory:

  macOS:   ~/Library/Application Support/Tankful/settings.json
  Windows: %APPDATA%\\Tankful\\settings.json
  Linux:   $XDG_CONFIG_HOME/tankful/settings.json (~/.config/tankful)

TANKFUL_CONFIG_DIR overrides the directory, for the harness.  The
settings are a plain dict: 'factor' names the picked factor (a registry
key), and each factor may keep a dict of its own under its key, for
instance {'weather': {'lat': 47.6, 'lon': -122.3}}.  A missing or broken
file gives the defaults, so a bad file never stops the tank.
"""

import json
import logging
import os
import sys
import tempfile

log = logging.getLogger('tankful.settings')

FILENAME = 'settings.json'
VERSION = 1

DEFAULTS = {
  'version': VERSION,
  'factor': 'none',
}


def config_dir(env=None, platform=None, home=None):
  """The per-user directory for tankful's settings on this OS."""
  env = os.environ if env is None else env
  platform = sys.platform if platform is None else platform
  home = os.path.expanduser('~') if home is None else home
  if env.get('TANKFUL_CONFIG_DIR'):
    return env['TANKFUL_CONFIG_DIR']
  if platform == 'darwin':
    return os.path.join(home, 'Library', 'Application Support', 'Tankful')
  if platform.startswith('win'):
    base = env.get('APPDATA') or os.path.join(home, 'AppData', 'Roaming')
    return os.path.join(base, 'Tankful')
  base = env.get('XDG_CONFIG_HOME') or os.path.join(home, '.config')
  return os.path.join(base, 'tankful')


def settings_path(env=None, platform=None, home=None):
  return os.path.join(config_dir(env, platform, home), FILENAME)


def defaults():
  return dict(DEFAULTS)


def load(path=None):
  """The settings from path (default: settings_path()), over the defaults."""
  path = settings_path() if path is None else path
  settings = defaults()
  try:
    with open(path, encoding='utf-8') as f:
      stored = json.load(f)
  except FileNotFoundError:
    return settings
  except (OSError, ValueError) as e:
    log.warning('Ignoring unreadable settings %s: %s', path, e)
    return settings
  if not isinstance(stored, dict):
    log.warning('Ignoring settings %s: not a JSON object', path)
    return settings
  settings.update(stored)
  if not isinstance(settings.get('factor'), str):
    settings['factor'] = DEFAULTS['factor']
  return settings


def save(settings, path=None):
  """Write settings to path atomically; returns False (logged) on failure."""
  path = settings_path() if path is None else path
  data = dict(settings)
  data['version'] = VERSION
  tmp = None
  try:
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.settings-', suffix='.json',
                               dir=os.path.dirname(path) or '.')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
      json.dump(data, f, indent=2, sort_keys=True)
      f.write('\n')
    os.replace(tmp, path)
    tmp = None
    return True
  except (OSError, TypeError, ValueError) as e:
    log.warning('Could not save settings to %s: %s', path, e)
    return False
  finally:
    if tmp is not None:
      try:
        os.remove(tmp)
      except OSError:
        log.debug('Could not remove %s', tmp, exc_info=True)


def section(settings, key):
  """A factor's own settings dict (empty when it has none)."""
  value = settings.get(key)
  return value if isinstance(value, dict) else {}
