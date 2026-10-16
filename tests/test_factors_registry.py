import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

from tankful.factors import base
from tankful.factors import controller
from tankful.factors import effects
from tankful.factors import registry
from tankful.factors import settings as settings_mod
from tankful.factors.base import Reading, ScriptedSource

FAKE = 'tests._fake_factor'
BROKEN = 'tests._broken_factor'


def fake_module(source=None, effects_for=None):
  """A factor module in sys.modules (removed at test cleanup)."""
  module = types.ModuleType(FAKE)
  module.made = []

  def make_source(settings):
    module.made.append(settings)
    return source
  module.make_source = make_source
  module.effects_for = effects_for or (
    lambda reading: effects.Effects(speed_scale=reading.value))
  return module


class RegistryTests(unittest.TestCase):

  def test_factors_in_picker_order(self):
    self.assertEqual(registry.keys(),
                     ['none', 'weather', 'moon', 'battery', 'stock'])
    self.assertEqual([f.label for f in registry.FACTORS],
                     ['None', 'Weather', 'Time & Moon', 'Battery', 'Stock'])

  def test_modules_follow_keys(self):
    for f in registry.FACTORS[1:]:
      self.assertEqual(f.module, 'tankful.factors.' + f.key)

  def test_get(self):
    self.assertEqual(registry.get('stock').label, 'Stock')

  def test_unknown_gets_none(self):
    with self.assertLogs('tankful.factors', 'WARNING'):
      self.assertEqual(registry.get('tides').key, 'none')
    self.assertEqual(registry.get(None).key, 'none')

  def test_default_is_none(self):
    self.assertEqual(registry.get(registry.DEFAULT).key, 'none')


class NoneFactorTests(unittest.TestCase):

  def test_neutral_and_sourceless(self):
    none = registry.get('none')
    self.assertTrue(none.available)
    self.assertIsNone(none.load())
    self.assertIsNone(none.make_source({}))
    self.assertIs(none.effects_for(Reading(1)), effects.NEUTRAL)


class FactorTests(unittest.TestCase):

  def setUp(self):
    patcher = mock.patch.dict(sys.modules)
    patcher.start()
    self.addCleanup(patcher.stop)

  def factor(self, module=FAKE):
    return registry.Factor('fake', 'Fake', module)

  def test_imports_lazily_once(self):
    sys.modules[FAKE] = fake_module()
    with mock.patch('importlib.import_module',
                    side_effect=lambda name: sys.modules[name]) as imp:
      f = self.factor()
      imp.assert_not_called()
      f.load()
      f.load()
    imp.assert_called_once_with(FAKE)

  def test_missing_module_is_unavailable_and_neutral(self):
    f = self.factor('tests._no_such_factor')
    with self.assertLogs('tankful.factors', 'WARNING'):
      self.assertFalse(f.available)
    self.assertIsNone(f.make_source({}))
    self.assertIs(f.effects_for(Reading(1)), effects.NEUTRAL)

  def test_make_source_passes_settings(self):
    source = ScriptedSource([Reading(1)])
    sys.modules[FAKE] = module = fake_module(source)
    self.assertIs(self.factor().make_source({'factor': 'fake'}), source)
    self.assertEqual(module.made, [{'factor': 'fake'}])

  def test_make_source_error_is_logged(self):
    module = fake_module()
    module.make_source = mock.Mock(side_effect=RuntimeError('boom'))
    sys.modules[FAKE] = module
    with self.assertLogs('tankful.factors', 'ERROR'):
      self.assertIsNone(self.factor().make_source({}))

  def test_effects_are_clamped(self):
    sys.modules[FAKE] = fake_module()
    self.assertEqual(self.factor().effects_for(Reading(0.5)).speed_scale, 0.5)
    self.assertEqual(self.factor().effects_for(Reading(99)).speed_scale, 2.0)

  def test_no_reading_is_neutral(self):
    sys.modules[FAKE] = fake_module()
    self.assertIs(self.factor().effects_for(None), effects.NEUTRAL)

  def test_effects_error_is_neutral(self):
    sys.modules[FAKE] = fake_module(effects_for=lambda r: 1 / 0)
    with self.assertLogs('tankful.factors', 'ERROR'):
      self.assertIs(self.factor().effects_for(Reading(1)), effects.NEUTRAL)

  def test_effects_wrong_type_is_neutral(self):
    sys.modules[FAKE] = fake_module(effects_for=lambda r: {'speed': 2})
    with self.assertLogs('tankful.factors', 'ERROR'):
      self.assertIs(self.factor().effects_for(Reading(1)), effects.NEUTRAL)


class ControllerTests(unittest.TestCase):

  def setUp(self):
    patcher = mock.patch.dict(sys.modules)
    patcher.start()
    self.addCleanup(patcher.stop)
    self.dir = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, self.dir)
    self.path = os.path.join(self.dir, 'settings.json')
    self.source = ScriptedSource([Reading(0.5, 'slow')], name='fake')
    sys.modules[FAKE] = fake_module(self.source)
    sys.modules[BROKEN] = types.ModuleType(BROKEN)  # no make_source
    factors = registry.FACTORS + (registry.Factor('fake', 'Fake', FAKE),
                                  registry.Factor('broken', 'Broken', BROKEN))
    patcher = mock.patch.object(registry, 'FACTORS', factors)
    patcher.start()
    self.addCleanup(patcher.stop)
    for f in factors:
      f._loaded = None
    self.clock = base.FakeClock()

  def make(self, settings=None, **kw):
    # An unstarted thread: the test polls by hand with a fake clock
    thread = base.FetchThread(poller=base.Poller(clock=self.clock))
    return controller.FactorController(settings, settings_path=self.path,
                                       thread=thread, **kw)

  def test_starts_with_none(self):
    c = self.make()
    self.assertEqual(c.key, 'none')
    self.assertEqual(c.label, '')
    self.assertEqual(c.update(1.0), effects.NEUTRAL)

  def test_starts_with_saved_factor(self):
    settings_mod.save({'factor': 'fake'}, self.path)
    c = self.make()
    self.assertEqual(c.key, 'fake')
    self.assertIs(c.thread.poller.source, self.source)

  def test_select_saves_and_switches(self):
    c = self.make()
    c.select('fake')
    self.assertEqual(settings_mod.load(self.path)['factor'], 'fake')
    self.assertEqual(c.label, 'Fake: …')
    c.thread.poller.poll()
    self.assertEqual(c.label, 'Fake: slow')
    c.select('none')
    self.assertIsNone(c.thread.poller.source)
    self.assertEqual(settings_mod.load(self.path)['factor'], 'none')

  def test_select_unknown_falls_back(self):
    c = self.make()
    with self.assertLogs('tankful.factors', 'WARNING'):
      self.assertEqual(c.select('tides').key, 'none')
    self.assertEqual(c.settings['factor'], 'none')

  def test_no_save(self):
    c = self.make(save=False)
    c.select('fake')
    self.assertFalse(os.path.exists(self.path))

  def test_given_settings_are_used(self):
    c = self.make({'factor': 'fake', 'fake': {'x': 1}})
    self.assertEqual(sys.modules[FAKE].made[-1]['fake'], {'x': 1})
    self.assertEqual(c.key, 'fake')

  def test_effects_ease_in(self):
    c = self.make({'factor': 'fake'}, time_constant=1.0)
    c.thread.poller.poll()
    self.assertEqual(c.target().speed_scale, 0.5)
    first = c.update(1.0).speed_scale
    self.assertTrue(0.5 < first < 1.0)
    for _ in range(600):
      c.update(1 / 60.0)
    self.assertAlmostEqual(c.effects.speed_scale, 0.5, places=3)

  def test_back_to_none_eases_to_neutral(self):
    c = self.make({'factor': 'fake'}, time_constant=0)
    c.thread.poller.poll()
    self.assertEqual(c.update(0.1).speed_scale, 0.5)
    c.select('none')
    self.assertEqual(c.update(0.1), effects.NEUTRAL)

  def test_offline_label(self):
    self.source.script = [None]
    c = self.make({'factor': 'fake'})
    with self.assertLogs('tankful.factors', 'WARNING'):
      c.thread.poller.poll()
    self.assertEqual(c.label, 'Fake: offline')
    self.assertEqual(c.update(1.0), effects.NEUTRAL)

  def test_broken_factor(self):
    with self.assertLogs('tankful.factors', 'ERROR'):
      c = self.make({'factor': 'broken'})
    self.assertEqual(c.label, 'Broken')
    self.assertEqual(c.update(1.0), effects.NEUTRAL)

  def test_unavailable_label(self):
    c = self.make()
    registry.get('fake')._loaded = registry._MISSING
    c.select('fake')
    self.assertEqual(c.label, 'Fake: unavailable')
    self.assertEqual(c.update(1.0), effects.NEUTRAL)

  def test_stop(self):
    self.assertTrue(self.make().stop())


if __name__ == '__main__':
  unittest.main()
