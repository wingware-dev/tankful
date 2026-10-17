import unittest

from tankful.factors import base
from tankful.factors import controller as controller_mod
from tankful.factors import effects
from tankful.factors import registry
from tankful.factors import standins


class ModeTests(unittest.TestCase):

  def test_mode(self):
    self.assertEqual(standins.mode({}), '')
    for off in ('', '0', 'off', 'No'):
      self.assertEqual(standins.mode({standins.ENV: off}), '', off)
    self.assertEqual(standins.mode({standins.ENV: '1'}), 'on')
    self.assertEqual(standins.mode({standins.ENV: 'Offline'}), 'offline')

  def test_for_env(self):
    self.assertIsNone(standins.for_env({}))
    self.assertIs(standins.for_env({standins.ENV: '1'}), standins.make_source)
    self.assertIs(standins.for_env({standins.ENV: 'offline'}),
                  standins.make_source_offline)


class StandInTests(unittest.TestCase):

  def test_none_has_no_source(self):
    self.assertIsNone(standins.make_source(registry.get('none'), {}))

  def test_every_factor_reads_and_takes_effect(self):
    for factor in registry.FACTORS[1:]:
      source = standins.make_source(factor, {})
      reading = source.fetch()
      self.assertEqual(reading.label, standins.READINGS[factor.key][1])
      e = factor.effects_for(reading)
      self.assertIsInstance(e, effects.Effects)
      self.assertNotEqual(e, effects.NEUTRAL, factor.key)

  def test_offline_fetches_nothing(self):
    for factor in registry.FACTORS[1:]:
      self.assertIsNone(standins.make_source_offline(factor, {}).fetch())


class StockDayTests(unittest.TestCase):

  def depth_shift(self, day):
    env = {} if day is None else {standins.STOCK_ENV: day}
    value, label = standins.reading('stock', env)
    return registry.get('stock').effects_for(
      base.Reading(value, label)).depth_shift

  def test_down_by_default(self):
    self.assertEqual(standins.reading('stock', {}), standins.READINGS['stock'])
    self.assertLess(self.depth_shift(None), 0)

  def test_up_lifts_and_down_sinks(self):
    self.assertGreater(self.depth_shift('Up'), 0)
    self.assertLess(self.depth_shift('down'), 0)
    self.assertEqual(standins.reading('stock', {standins.STOCK_ENV: 'up'})[1],
                     'S&P 500 +1.60%')

  def test_other_factors_ignore_it(self):
    self.assertEqual(standins.reading('battery', {standins.STOCK_ENV: 'up'}),
                     standins.READINGS['battery'])
    self.assertIsNone(standins.reading('none', {}))

  def test_bad_day_fails_at_start(self):
    with self.assertRaises(ValueError):
      standins.for_env({standins.ENV: '1', standins.STOCK_ENV: 'sideways'})
    self.assertIsNone(standins.for_env({standins.STOCK_ENV: 'sideways'}))


class ControllerMakeSourceTests(unittest.TestCase):

  def test_make_source_replaces_the_factors_own(self):
    calls = []

    def make_source(factor, settings):
      calls.append(factor.key)
      return standins.make_source(factor, settings)
    thread = base.FetchThread()
    c = controller_mod.FactorController(settings={'factor': 'battery'},
                                        thread=thread, save=False,
                                        make_source=make_source)
    self.assertEqual(thread.poller.source.name, 'standin-battery')
    c.select('stock')
    self.assertEqual(thread.poller.source.name, 'standin-stock')
    self.assertEqual(calls, ['battery', 'stock'])
    thread.poller.poll()
    self.assertEqual(c.label, 'Stock: S&P 500 -1.80%')


if __name__ == '__main__':
  unittest.main()
