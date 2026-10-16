import unittest

from tankful.game import input as game_input
from tankful.game.input import InputState, normalize_key


class NormalizeKeyTests(unittest.TestCase):

  def test_names(self):
    cases = {'LEFTARROWKEY': 'left', 'left': 'left', 'Left': 'left',
             'AKEY': 'a', 'L': 'l', 'ESCKEY': 'escape', 'RETKEY': 'enter',
             'SPACEKEY': 'space', 'ONEKEY': 'one', 'key': 'key'}
    for name, want in cases.items():
      self.assertEqual(normalize_key(name), want, name)


class InputStateTests(unittest.TestCase):

  def test_key_lifecycle(self):
    s = InputState()
    s.key_down('LEFTARROWKEY')
    self.assertTrue(s.is_down('left'))
    self.assertTrue(s.was_pressed('left'))
    s.end_frame()
    self.assertTrue(s.is_down('left'))
    self.assertFalse(s.was_pressed('left'))
    s.key_down('left')
    self.assertFalse(s.was_pressed('left'), 'already down: no new press')
    s.key_up('left')
    self.assertFalse(s.is_down('left'))
    self.assertTrue(s.was_released('left'))
    s.end_frame()
    self.assertFalse(s.was_released('left'))

  def test_key_up_without_down_is_ignored(self):
    s = InputState()
    s.key_up('x')
    self.assertFalse(s.was_released('x'))

  def test_clicks_last_one_frame(self):
    s = InputState()
    s.click(10, 20)
    s.click(30, 40, 'right')
    self.assertEqual(s.clicks(), [(10, 20, 'left'), (30, 40, 'right')])
    self.assertEqual(s.mouse, (30, 40))
    s.end_frame()
    self.assertEqual(s.clicks(), [])
    self.assertEqual(s.mouse, (30, 40))

  def test_snapshot(self):
    s = InputState()
    s.key_down('b')
    s.key_down('a')
    self.assertEqual(s.snapshot(), {'keys_down': ['a', 'b'], 'mouse': [0, 0]})


class FakeInput:

  def __init__(self, activated=False, released=False):
    self.activated = activated
    self.released = released


class FakeDevice:

  def __init__(self, active, position=(0.0, 0.0)):
    self.activeInputs = active
    self.position = position


class FakeEvents:
  LEFTARROWKEY = 143
  AKEY = 97
  LEFTMOUSE = 116


class FakeLogic:

  def __init__(self, keys, buttons, position):
    self.keyboard = FakeDevice(keys)
    self.mouse = FakeDevice(buttons, position)


class FakeRender:

  @staticmethod
  def getWindowWidth():
    return 200

  @staticmethod
  def getWindowHeight():
    return 100


class FeedFromBgeTests(unittest.TestCase):

  def setUp(self):
    game_input._event_names = None
    self.addCleanup(setattr, game_input, '_event_names', None)

  def test_real_events_reach_the_state(self):
    s = InputState()
    s.key_down('a')
    logic = FakeLogic({143: FakeInput(activated=True),
                       97: FakeInput(released=True),
                       9999: FakeInput(activated=True)},
                      {116: FakeInput(activated=True)}, (0.5, 0.25))
    game_input.feed_from_bge(s, logic, FakeEvents, FakeRender)
    self.assertTrue(s.is_down('left'))
    self.assertFalse(s.is_down('a'))
    self.assertEqual(s.mouse, (100, 25))
    self.assertEqual(s.clicks(), [(100, 25, 'left')])


if __name__ == '__main__':
  unittest.main()
