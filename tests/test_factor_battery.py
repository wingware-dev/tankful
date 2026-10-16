import os
import shutil
import tempfile
import unittest

from tankful.factors import base
from tankful.factors import battery
from tankful.factors import effects
from tankful.factors import registry
from tankful.factors.battery import BatteryState


PMSET_ON_BATTERY = """\
Now drawing from 'Battery Power'
 -InternalBattery-0 (id=21692515)\t42%; discharging; 3:10 remaining present: true
"""

PMSET_CHARGING = """\
Now drawing from 'AC Power'
 -InternalBattery-0 (id=21692515)\t67%; charging; 1:02 remaining present: true
"""

PMSET_NOT_CHARGING = """\
Now drawing from 'AC Power'
 -InternalBattery-0 (id=21692515)\t80%; AC attached; not charging present: true
"""

PMSET_DESKTOP = "Now drawing from 'AC Power'\n"

PMSET_DESKTOP_WITH_UPS = """\
Now drawing from 'AC Power'
 -CyberPower 1500 (id=123)\t100%; AC attached; not charging present: true
"""


class MacTests(unittest.TestCase):

  def test_on_battery(self):
    state = battery.read_macos(run=lambda: PMSET_ON_BATTERY)
    self.assertEqual(state, BatteryState(42.0, False, False))

  def test_charging(self):
    state = battery.read_macos(run=lambda: PMSET_CHARGING)
    self.assertEqual(state, BatteryState(67.0, True, True))

  def test_on_ac_not_charging(self):
    state = battery.read_macos(run=lambda: PMSET_NOT_CHARGING)
    self.assertEqual(state, BatteryState(80.0, True, False))

  def test_no_battery(self):
    state = battery.read_macos(run=lambda: PMSET_DESKTOP)
    self.assertEqual(state, battery.NO_BATTERY)

  def test_ups_is_not_the_battery(self):
    state = battery.read_macos(run=lambda: PMSET_DESKTOP_WITH_UPS)
    self.assertIsNone(state.percent)

  def test_pmset_failure_raises(self):
    def fail():
      raise FileNotFoundError('pmset')
    with self.assertRaises(FileNotFoundError):
      battery.read_macos(run=fail)


class LinuxTests(unittest.TestCase):

  def setUp(self):
    self.root = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, self.root)

  def supply(self, name, **files):
    path = os.path.join(self.root, name)
    os.mkdir(path)
    for key, text in files.items():
      with open(os.path.join(path, key), 'w') as f:
        f.write(text + '\n')

  def read(self):
    return battery.read_linux(root=self.root)

  def test_on_battery(self):
    self.supply('AC', type='Mains', online='0')
    self.supply('BAT0', type='Battery', capacity='35', status='Discharging')
    self.assertEqual(self.read(), BatteryState(35.0, False, False))

  def test_charging(self):
    self.supply('AC', type='Mains', online='1')
    self.supply('BAT0', type='Battery', capacity='60', status='Charging')
    self.assertEqual(self.read(), BatteryState(60.0, True, True))

  def test_two_batteries_average(self):
    self.supply('BAT0', type='Battery', capacity='20', status='Discharging')
    self.supply('BAT1', type='Battery', capacity='80', status='Discharging')
    self.assertEqual(self.read(), BatteryState(50.0, False, False))

  def test_energy_without_capacity(self):
    self.supply('BAT0', type='Battery', energy_now='25000',
                energy_full='50000', status='Full')
    self.assertEqual(self.read(), BatteryState(50.0, True, False))

  def test_peripheral_battery_skipped(self):
    self.supply('AC', type='Mains', online='1')
    self.supply('hidpp_battery_0', type='Battery', scope='Device',
                capacity='10', status='Discharging')
    self.assertEqual(self.read(), battery.NO_BATTERY)

  def test_absent_battery_skipped(self):
    self.supply('BAT0', type='Battery', present='0', capacity='0')
    self.assertIsNone(self.read().percent)

  def test_no_power_supplies(self):
    self.assertEqual(self.read(), battery.NO_BATTERY)

  def test_missing_root(self):
    state = battery.read_linux(root=os.path.join(self.root, 'nope'))
    self.assertEqual(state, battery.NO_BATTERY)


def power_status(ac=1, flag=1, percent=90):
  status = battery.SYSTEM_POWER_STATUS()
  status.ACLineStatus = ac
  status.BatteryFlag = flag
  status.BatteryLifePercent = percent
  return status


class WindowsTests(unittest.TestCase):

  def read(self, **kw):
    status = power_status(**kw)
    return battery.read_windows(get_status=lambda: status)

  def test_on_battery(self):
    self.assertEqual(self.read(ac=0, flag=2, percent=30),
                     BatteryState(30.0, False, False))

  def test_charging(self):
    self.assertEqual(self.read(ac=1, flag=8 | 1, percent=70),
                     BatteryState(70.0, True, True))

  def test_no_system_battery(self):
    self.assertEqual(self.read(ac=1, flag=128, percent=255),
                     battery.NO_BATTERY)

  def test_unknown_everything_is_no_battery(self):
    state = self.read(ac=255, flag=255, percent=255)
    self.assertIsNone(state.percent)
    self.assertIsNone(state.plugged)

  def test_unknown_charge_with_battery_raises(self):
    with self.assertRaises(ValueError):
      self.read(ac=0, flag=2, percent=255)

  def test_win_error_raises(self):
    def fail():
      raise OSError('GetSystemPowerStatus failed')
    with self.assertRaises(OSError):
      battery.read_windows(get_status=fail)


class ReaderForTests(unittest.TestCase):

  def test_platforms(self):
    self.assertIs(battery.reader_for('darwin'), battery.read_macos)
    self.assertIs(battery.reader_for('linux'), battery.read_linux)
    self.assertIs(battery.reader_for('win32'), battery.read_windows)
    self.assertIsNone(battery.reader_for('sunos5'))

  def test_make_source(self):
    source = battery.make_source({}, platform='linux')
    self.assertIsInstance(source, base.Source)
    self.assertEqual(source.name, 'battery')
    self.assertIsNone(battery.make_source({}, platform='sunos5'))


class EffectsTests(unittest.TestCase):

  def effects(self, state):
    return battery.effects_for(battery.BatterySource(lambda: state).fetch())

  def test_full_is_normal(self):
    self.assertEqual(self.effects(BatteryState(100.0, False)).speed_scale,
                     1.0)
    self.assertEqual(self.effects(BatteryState(battery.FULL_AT, False))
                     .speed_scale, 1.0)

  def test_low_is_sluggish(self):
    half = self.effects(BatteryState(40.0, False)).speed_scale
    low = self.effects(BatteryState(10.0, False)).speed_scale
    empty = self.effects(BatteryState(0.0, False)).speed_scale
    self.assertLess(low, half)
    self.assertLess(half, 1.0)
    self.assertAlmostEqual(empty, battery.SLOWEST)

  def test_only_speed_changes(self):
    result = self.effects(BatteryState(10.0, False))
    self.assertEqual(result.replace(speed_scale=1.0), effects.NEUTRAL)

  def test_inside_clamp_range(self):
    low, high = effects.RANGES['speed_scale']
    for percent in (-5, 0, 1, 50, 100, 150):
      scale = battery.speed_for(percent)
      self.assertTrue(low <= scale <= high, (percent, scale))

  def test_no_battery_is_neutral(self):
    self.assertEqual(self.effects(battery.NO_BATTERY), effects.NEUTRAL)

  def test_odd_value_is_neutral(self):
    self.assertEqual(battery.effects_for(base.Reading('junk')),
                     effects.NEUTRAL)


class LabelTests(unittest.TestCase):

  def test_labels(self):
    self.assertEqual(battery.label_for(BatteryState(42.4, False)), '42%')
    self.assertEqual(battery.label_for(BatteryState(67, True, True)),
                     '67%, charging')
    self.assertEqual(battery.label_for(BatteryState(100, True)),
                     '100%, on AC')
    self.assertEqual(battery.label_for(battery.NO_BATTERY),
                     battery.NO_BATTERY_LABEL)


class PollerTests(unittest.TestCase):
  """The source under the framework's Poller, with a fake clock."""

  def poller(self, reader):
    clock = base.FakeClock()
    return base.Poller(battery.BatterySource(reader), clock=clock), clock

  def test_reads_and_labels(self):
    poller, clock = self.poller(lambda: BatteryState(25.0, False))
    self.assertEqual(poller.poll(), battery.BatterySource.ttl)
    status = poller.status()
    self.assertEqual(status.label, '25%')
    self.assertLess(battery.effects_for(status.reading).speed_scale, 1.0)

  def test_no_battery_shows_and_is_neutral(self):
    poller, clock = self.poller(lambda: battery.NO_BATTERY)
    poller.poll()
    status = poller.status()
    self.assertFalse(status.offline)
    self.assertEqual(status.label, 'AC / no battery')
    self.assertEqual(battery.effects_for(status.reading), effects.NEUTRAL)

  def test_rereads_after_ttl(self):
    states = [BatteryState(90.0, False), BatteryState(20.0, False)]
    poller, clock = self.poller(lambda: states.pop(0))
    poller.poll()
    self.assertEqual(poller.status().label, '90%')
    clock.advance(battery.BatterySource.ttl)
    poller.poll()
    self.assertEqual(poller.status().label, '20%')

  def test_failing_reader_goes_offline(self):
    def fail():
      raise OSError('no pmset')
    poller, clock = self.poller(fail)
    with self.assertLogs('tankful.factors', 'WARNING'):
      self.assertEqual(poller.poll(), battery.BatterySource.retry)
    status = poller.status()
    self.assertTrue(status.offline)
    self.assertIsNone(status.reading)

  def test_registry_factor(self):
    factor = registry.get('battery')
    self.assertTrue(factor.available)
    reading = battery.BatterySource(lambda: BatteryState(0.0, False)).fetch()
    self.assertAlmostEqual(factor.effects_for(reading).speed_scale,
                           battery.SLOWEST)


if __name__ == '__main__':
  unittest.main()
