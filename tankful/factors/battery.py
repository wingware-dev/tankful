"""The Battery factor: the computer's charge sets how briskly the fish swim.

A full battery leaves them at normal speed; as it runs down they grow
sluggish.  Plugged in, the charge still counts (a nearly flat laptop on
its charger stays slow until it fills), and with no battery at all, as on
a desktop, the HUD says so and the tank stays neutral.

The battery is read with the standard library only:

  macOS:   pmset -g batt
  Linux:   /sys/class/power_supply/*/
  Windows: GetSystemPowerStatus, through ctypes

Each reader takes its OS access as arguments, so the tests run every
platform's reader on any machine with fakes.
"""

import ctypes
import dataclasses
import glob
import logging
import os
import re
import subprocess
import sys

from tankful.factors import base
from tankful.factors import effects

log = logging.getLogger('tankful.factors')

# At or above this percent the fish swim at normal speed.  Below full,
# since many laptops stop charging at 80% to spare the battery
FULL_AT = 80.0
# The speed_scale at 0%
SLOWEST = 0.3

NO_BATTERY_LABEL = 'AC / no battery'


@dataclasses.dataclass(frozen=True)
class BatteryState:
  """The battery as one reader saw it.

  percent: charge from 0 to 100, or None when there is no battery.
  plugged: on mains power (None when the OS doesn't say).
  charging: charging now.
  """
  percent: object = None
  plugged: object = None
  charging: bool = False


NO_BATTERY = BatteryState(None, True, False)


# macOS


_PMSET_SOURCE = re.compile(r"Now drawing from '([^']*)'")
_PMSET_BATTERY = re.compile(r'-InternalBattery-\d+.*?\t\s*(\d+)%;\s*([^;\n]*)')


def _run_pmset():
  return subprocess.run(['pmset', '-g', 'batt'], capture_output=True,
                        text=True, timeout=5, check=True).stdout


def parse_pmset(text):
  """A BatteryState from `pmset -g batt` output.

  Only the internal battery counts, not a UPS or a mouse.
  """
  source = _PMSET_SOURCE.search(text)
  plugged = None if source is None else source.group(1) == 'AC Power'
  battery = _PMSET_BATTERY.search(text)
  if battery is None:
    return dataclasses.replace(NO_BATTERY, plugged=True if plugged is None
                               else plugged)
  status = battery.group(2).strip().lower()
  if plugged is None:
    plugged = status != 'discharging'
  return BatteryState(float(battery.group(1)), plugged,
                      status in ('charging', 'finishing charge'))


def read_macos(run=_run_pmset):
  return parse_pmset(run())


# Linux


POWER_SUPPLY = '/sys/class/power_supply'


def _read_file(path):
  try:
    with open(path, encoding='ascii', errors='replace') as f:
      return f.read().strip()
  except OSError:
    return None


def _number(text):
  try:
    return float(text)
  except (TypeError, ValueError):
    return None


def _linux_percent(supply):
  percent = _number(_read_file(os.path.join(supply, 'capacity')))
  if percent is not None:
    return percent
  # Some batteries give only the charge or energy left and the full value
  for kind in ('energy', 'charge'):
    now = _number(_read_file(os.path.join(supply, kind + '_now')))
    full = _number(_read_file(os.path.join(supply, kind + '_full')))
    if now is not None and full:
      return 100.0 * now / full
  return None


def read_linux(root=POWER_SUPPLY):
  """A BatteryState from the kernel's power_supply class.

  The system batteries' charges are averaged; a battery whose scope is
  Device belongs to a peripheral (a mouse, a headset) and is skipped.
  """
  percents = []
  statuses = []
  mains = []
  for supply in sorted(glob.glob(os.path.join(root, '*'))):
    kind = _read_file(os.path.join(supply, 'type'))
    if kind == 'Battery':
      if _read_file(os.path.join(supply, 'scope')) == 'Device':
        continue
      if _read_file(os.path.join(supply, 'present')) == '0':
        continue
      percent = _linux_percent(supply)
      if percent is not None:
        percents.append(percent)
        statuses.append((_read_file(os.path.join(supply, 'status')) or '')
                        .lower())
    elif kind in ('Mains', 'USB', 'USB_C', 'USB_PD'):
      online = _read_file(os.path.join(supply, 'online'))
      if online is not None:
        mains.append(online == '1')
  if not percents:
    return NO_BATTERY
  charging = 'charging' in statuses
  if mains:
    plugged = any(mains)
  else:
    plugged = 'discharging' not in statuses
  return BatteryState(sum(percents) / len(percents), plugged, charging)


# Windows


class SYSTEM_POWER_STATUS(ctypes.Structure):
  _fields_ = [
    ('ACLineStatus', ctypes.c_ubyte),
    ('BatteryFlag', ctypes.c_ubyte),
    ('BatteryLifePercent', ctypes.c_ubyte),
    ('SystemStatusFlag', ctypes.c_ubyte),
    ('BatteryLifeTime', ctypes.c_uint32),
    ('BatteryFullLifeTime', ctypes.c_uint32),
  ]


_NO_SYSTEM_BATTERY = 128
_CHARGING = 8
_UNKNOWN = 255


def _get_power_status():
  status = SYSTEM_POWER_STATUS()
  if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
    raise ctypes.WinError()
  return status


def parse_power_status(status):
  """A BatteryState from a SYSTEM_POWER_STATUS."""
  plugged = {0: False, 1: True}.get(status.ACLineStatus)
  flag = status.BatteryFlag
  if flag != _UNKNOWN and flag & _NO_SYSTEM_BATTERY:
    return dataclasses.replace(NO_BATTERY, plugged=True if plugged is None
                               else plugged)
  if status.BatteryLifePercent == _UNKNOWN:
    if flag == _UNKNOWN:
      # Windows can't tell whether there is a battery at all
      return dataclasses.replace(NO_BATTERY, plugged=plugged)
    raise ValueError('battery present but its charge is unknown')
  charging = flag != _UNKNOWN and bool(flag & _CHARGING)
  return BatteryState(float(min(100, status.BatteryLifePercent)), plugged,
                      charging)


def read_windows(get_status=_get_power_status):
  return parse_power_status(get_status())


# The factor


def reader_for(platform=None):
  """This platform's battery reader, or None where there is none."""
  platform = sys.platform if platform is None else platform
  if platform == 'darwin':
    return read_macos
  if platform.startswith('linux'):
    return read_linux
  if platform in ('win32', 'cygwin'):
    return read_windows
  return None


def label_for(state):
  if state.percent is None:
    return NO_BATTERY_LABEL
  text = '%d%%' % round(state.percent)
  if state.charging:
    return text + ', charging'
  if state.plugged:
    return text + ', on AC'
  return text


class BatterySource(base.Source):
  name = 'battery'
  ttl = 60.0
  retry = 30.0

  def __init__(self, reader):
    self.reader = reader

  def fetch(self):
    state = self.reader()
    if state is None:
      return None
    return base.Reading(dataclasses.asdict(state), label_for(state))


def make_source(settings, platform=None):
  """The battery Source for this platform, or None where it can't read."""
  reader = reader_for(platform)
  if reader is None:
    log.info('Battery factor: no battery reader for %s',
             sys.platform if platform is None else platform)
    return None
  return BatterySource(reader)


def speed_for(percent):
  """speed_scale for a charge: 1 at FULL_AT and up, down to SLOWEST at 0."""
  percent = min(100.0, max(0.0, float(percent)))
  if percent >= FULL_AT:
    return 1.0
  return SLOWEST + (1.0 - SLOWEST) * percent / FULL_AT


def effects_for(reading):
  value = reading.value if isinstance(reading.value, dict) else {}
  percent = value.get('percent')
  if percent is None:
    return effects.NEUTRAL
  return effects.Effects(speed_scale=speed_for(percent))
