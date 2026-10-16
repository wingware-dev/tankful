import json
import unittest

from tankful.game.main import parse_size
from tankful.sim.tank import Tank


class TankTests(unittest.TestCase):

  def test_step_and_snapshot(self):
    tank = Tank()
    tank.step(0.5)
    tank.step(0.25)
    snap = tank.snapshot()
    self.assertEqual(snap['frame'], 2)
    self.assertAlmostEqual(snap['time'], 0.75)
    self.assertEqual(snap['fish'], [])
    json.dumps(snap)

  def test_negative_dt(self):
    with self.assertRaises(ValueError):
      Tank().step(-0.1)


class ParseSizeTests(unittest.TestCase):

  def test_parse_size(self):
    self.assertEqual(parse_size('1280x720'), (1280, 720))
    self.assertEqual(parse_size('640X480'), (640, 480))
    for bad in ('', '1', 'x', '12xab', '-1x5'):
      self.assertIsNone(parse_size(bad), bad)


if __name__ == '__main__':
  unittest.main()
