import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tankful.factors import settings


class ConfigDirTests(unittest.TestCase):

  def test_macos(self):
    self.assertEqual(
      settings.config_dir({}, 'darwin', '/Users/me'),
      '/Users/me/Library/Application Support/Tankful')

  def test_windows_appdata(self):
    path = settings.config_dir({'APPDATA': r'C:\Users\me\AppData\Roaming'},
                               'win32', r'C:\Users\me')
    self.assertTrue(path.startswith(r'C:\Users\me\AppData\Roaming'))
    self.assertTrue(path.endswith('Tankful'))

  def test_windows_without_appdata(self):
    path = settings.config_dir({}, 'win32', 'C:/Users/me')
    self.assertIn('AppData', path)

  def test_linux_xdg(self):
    self.assertEqual(
      settings.config_dir({'XDG_CONFIG_HOME': '/cfg'}, 'linux', '/home/me'),
      '/cfg/tankful')

  def test_linux_default(self):
    self.assertEqual(settings.config_dir({}, 'linux', '/home/me'),
                     '/home/me/.config/tankful')

  def test_override(self):
    self.assertEqual(
      settings.config_dir({'TANKFUL_CONFIG_DIR': '/x'}, 'darwin', '/h'), '/x')

  def test_settings_path(self):
    self.assertEqual(settings.settings_path({}, 'linux', '/home/me'),
                     '/home/me/.config/tankful/settings.json')


class LoadSaveTests(unittest.TestCase):

  def setUp(self):
    self.dir = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, self.dir)
    self.path = os.path.join(self.dir, 'sub', 'settings.json')

  def write(self, text):
    os.makedirs(os.path.dirname(self.path), exist_ok=True)
    with open(self.path, 'w', encoding='utf-8') as f:
      f.write(text)

  def test_missing_file_gives_defaults(self):
    self.assertEqual(settings.load(self.path), settings.DEFAULTS)

  def test_defaults_are_a_copy(self):
    s = settings.load(self.path)
    s['factor'] = 'stock'
    self.assertEqual(settings.DEFAULTS['factor'], 'none')

  def test_round_trip(self):
    s = settings.load(self.path)
    s['factor'] = 'weather'
    s['weather'] = {'lat': 47.6, 'lon': -122.3}
    self.assertTrue(settings.save(s, self.path))
    loaded = settings.load(self.path)
    self.assertEqual(loaded['factor'], 'weather')
    self.assertEqual(loaded['weather'], {'lat': 47.6, 'lon': -122.3})
    self.assertEqual(loaded['version'], settings.VERSION)

  def test_save_leaves_no_temp_files(self):
    settings.save({'factor': 'moon'}, self.path)
    self.assertEqual(os.listdir(os.path.dirname(self.path)),
                     ['settings.json'])

  def test_keeps_unknown_keys(self):
    self.write('{"factor": "battery", "future": [1, 2]}')
    self.assertEqual(settings.load(self.path)['future'], [1, 2])

  def test_corrupt_file_gives_defaults(self):
    self.write('{not json')
    with self.assertLogs('tankful.settings', 'WARNING'):
      self.assertEqual(settings.load(self.path), settings.DEFAULTS)

  def test_non_object_gives_defaults(self):
    self.write('[1, 2]')
    with self.assertLogs('tankful.settings', 'WARNING'):
      self.assertEqual(settings.load(self.path), settings.DEFAULTS)

  def test_bad_factor_value_gives_default(self):
    self.write('{"factor": 3}')
    self.assertEqual(settings.load(self.path)['factor'], 'none')

  def test_unwritable_dir_fails_soft(self):
    blocker = os.path.join(self.dir, 'file')
    with open(blocker, 'w') as f:
      f.write('x')
    with self.assertLogs('tankful.settings', 'WARNING'):
      self.assertFalse(settings.save({'factor': 'none'},
                                     os.path.join(blocker, 'settings.json')))

  def test_unserializable_fails_soft_and_cleans_up(self):
    with self.assertLogs('tankful.settings', 'WARNING'):
      self.assertFalse(settings.save({'bad': object()}, self.path))
    self.assertEqual(os.listdir(os.path.dirname(self.path)), [])

  def test_failed_save_keeps_old_file(self):
    settings.save({'factor': 'stock'}, self.path)
    with self.assertLogs('tankful.settings', 'WARNING'):
      settings.save({'factor': 'moon', 'bad': object()}, self.path)
    self.assertEqual(settings.load(self.path)['factor'], 'stock')

  def test_default_path_uses_env(self):
    with mock.patch.dict(os.environ, {'TANKFUL_CONFIG_DIR': self.dir}):
      settings.save({'factor': 'battery'})
      self.assertEqual(settings.load()['factor'], 'battery')
    with open(os.path.join(self.dir, 'settings.json')) as f:
      self.assertEqual(json.load(f)['factor'], 'battery')


class SectionTests(unittest.TestCase):

  def test_section(self):
    s = {'weather': {'lat': 1}, 'stock': 'junk'}
    self.assertEqual(settings.section(s, 'weather'), {'lat': 1})
    self.assertEqual(settings.section(s, 'stock'), {})
    self.assertEqual(settings.section(s, 'moon'), {})


if __name__ == '__main__':
  unittest.main()
