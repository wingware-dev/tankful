import math
import unittest
from unittest import mock

from tankful.game import lighting
from tankful.game import scenery
from tankful.game.input import InputState
from tankful.sim import bubbles
from tankful.sim import daynight
from tankful.sim import environment as env
from tankful.sim.daynight import Light

from tests.test_scenery import CAUSTIC, FakeObject, FakeObjects

WINDOW = (1280, 720)


class FakeCamera:
  """Projects x and z straight onto the screen: x -1..1 m across, z 1..0
  m down."""

  def getScreenPosition(self, point):
    x, _, z = point
    return [(x + 1.0) / 2.0, 1.0 - z]


class FakeSocket:
  """A node socket that counts the writes to its value."""

  writes = 0
  _value = None

  @property
  def default_value(self):
    return self._value

  @default_value.setter
  def default_value(self, value):
    self.writes += 1
    self._value = value


class FakeWorld:
  """The world's Background node."""

  def __init__(self):
    self.inputs = {'Color': FakeSocket()}

  @property
  def writes(self):
    return self.inputs['Color'].writes


def make_lighting(light=None, world=None, objects=None):
  if objects is None:
    lamp = FakeObject(lighting.LAMP)
    lamp.blenderObject = mock.Mock(data=mock.Mock(energy=20.0))
    switch = FakeObject(lighting.SWITCH, position=env.SWITCH_CENTER)
    objects = [lamp, FakeObject(lighting.PANEL), FakeObject(lighting.GLASS),
               switch, FakeObject(lighting.ROCKER)]
  scene = mock.Mock(objects=FakeObjects(objects), active_camera=FakeCamera())
  with mock.patch.object(lighting.log, 'warning'):
    return lighting.Lighting(scene, light or Light(), world)


def switch_center_px():
  x, _, z = env.SWITCH_CENTER
  return (round((x + 1.0) / 2.0 * WINDOW[0]), round((1.0 - z) * WINDOW[1]))


class SwitchTests(unittest.TestCase):

  def setUp(self):
    self.light = Light()
    self.lighting = make_lighting(self.light)
    self.input = InputState()

  def frame(self):
    flipped = self.lighting.handle_input(self.input, WINDOW)
    self.input.end_frame()
    return flipped

  def test_l_key_flips(self):
    self.input.key_down('L')
    self.assertTrue(self.frame())
    self.assertFalse(self.light.on)
    # Held down, it does not flip again
    self.assertFalse(self.frame())
    self.input.key_up('l')
    self.input.key_down('l')
    self.assertTrue(self.frame())
    self.assertTrue(self.light.on)

  def test_click_on_the_plate_flips(self):
    x, y = switch_center_px()
    self.input.click(x, y)
    self.assertTrue(self.frame())
    self.assertFalse(self.light.on)
    # Just outside its edge, within the pad, still counts
    left, top, right, bottom = self.lighting.switch_rect(WINDOW)
    self.input.click(right + lighting.CLICK_PAD - 1, y)
    self.assertTrue(self.frame())
    self.assertTrue(self.light.on)

  def test_other_clicks_do_not(self):
    left, top, right, bottom = self.lighting.switch_rect(WINDOW)
    for x, y, button in ((right + 40, (top + bottom) / 2, 'left'),
                         ((left + right) / 2, bottom + 40, 'left'),
                         (640, 360, 'left'),
                         ((left + right) / 2, (top + bottom) / 2, 'right')):
      self.input.click(x, y, button)
      self.assertFalse(self.frame(), (x, y, button))
    self.assertTrue(self.light.on)

  def test_switch_rect_is_the_plate(self):
    left, top, right, bottom = self.lighting.switch_rect(WINDOW)
    w, h = env.SWITCH_SIZE
    self.assertAlmostEqual(right - left, w / 2.0 * WINDOW[0])
    self.assertAlmostEqual(bottom - top, h * WINDOW[1])
    x, y = switch_center_px()
    self.assertTrue(lighting.in_rect((left, top, right, bottom), x, y))

  def test_no_switch_in_the_scene(self):
    light = Light()
    lit = make_lighting(light, objects=[])
    state = InputState()
    state.click(*switch_center_px())
    self.assertIsNone(lit.switch_rect(WINDOW))
    self.assertFalse(lit.handle_input(state, WINDOW))
    lit.update()
    self.assertTrue(light.on)

  def test_rocker_tips_with_the_switch(self):
    rocker = self.lighting.rocker
    self.lighting.update()
    on = rocker.localOrientation
    self.assertAlmostEqual(on[2][1], math.sin(-env.SWITCH_TILT))
    self.light.toggle()
    self.lighting.update()
    self.assertAlmostEqual(rocker.localOrientation[2][1],
                           math.sin(env.SWITCH_TILT))
    # Only when it flips
    rocker.localOrientation = 'untouched'
    self.lighting.update()
    self.assertEqual(rocker.localOrientation, 'untouched')


class LookTests(unittest.TestCase):

  def test_day_then_night(self):
    light = Light(transition=2.0)
    world = FakeWorld()
    lit = make_lighting(light, world)
    lit.update()
    lamp = lit.lamp.blenderObject.data
    self.assertEqual(lamp.energy, daynight.DAY_LAMP)
    self.assertEqual(world.inputs['Color'].default_value,
                     daynight.DAY_ROOM + (1.0,))
    light.set(False)
    for _ in range(3 * 60):
      light.step(1 / 60.0)
      lit.update()
    night = daynight.look(0.0)
    self.assertAlmostEqual(lamp.energy, night.lamp)
    self.assertEqual(lamp.color, daynight.NIGHT_LAMP_COLOR)
    self.assertEqual(world.inputs['Color'].default_value,
                     daynight.NIGHT_ROOM + (1.0,))
    self.assertEqual(lit.panel.color, daynight.NIGHT_PANEL + (1.0,))
    self.assertEqual(lit.glass.color, daynight.NIGHT_SHEEN + (1.0,))
    # The room is written in steps, far fewer than the fade's frames
    self.assertLess(world.writes, 40)
    self.assertGreater(world.writes, 10)

  def test_nothing_written_once_the_fade_is_done(self):
    lit = make_lighting(Light())
    lit.update()
    lamp = lit.lamp.blenderObject.data
    lamp.energy = 'untouched'
    lit.panel.color = 'untouched'
    lit.update()
    self.assertEqual((lamp.energy, lit.panel.color),
                     ('untouched', 'untouched'))

  def test_moon_brightens_the_night_lamp(self):
    light = Light(on=False)
    lit = make_lighting(light)
    light.set_moon(0.0)
    lit.update()
    dark = lit.lamp.blenderObject.data.energy
    light.set_moon(1.0)
    lit.update()
    self.assertGreater(lit.lamp.blenderObject.data.energy, dark)

  def test_room_due(self):
    day = daynight.DAY_ROOM
    self.assertTrue(lighting.room_due(None, day))
    self.assertFalse(lighting.room_due(day, day))
    near = tuple(c - lighting.ROOM_STEP / 2 for c in day)
    self.assertFalse(lighting.room_due(day, near))
    self.assertTrue(lighting.room_due(near, daynight.NIGHT_ROOM))
    self.assertTrue(lighting.room_due(daynight.NIGHT_ROOM, day))
    far = tuple(c - lighting.ROOM_STEP for c in day)
    self.assertTrue(lighting.room_due(day, far))

  def test_snapshot(self):
    lit = make_lighting()
    lit.handle_input(InputState(), WINDOW)
    lit.update()
    snap = lit.snapshot()
    self.assertEqual(snap['lamp'], daynight.DAY_LAMP)
    self.assertEqual(snap['light']['on'], True)
    self.assertEqual(len(snap['switch_rect']), 4)


class SceneryLookTests(unittest.TestCase):

  def setUp(self):
    self.projector = FakeObject(scenery.PROJECTOR, position=(0, 0, 0.62))
    self.sand = FakeObject('Sand', groups=CAUSTIC)
    self.disc = FakeObject(scenery.RIPPLES)
    self.bubble = FakeObject('Bubble.00')
    self.pool = bubbles.BubblePool((0.3, 0.16, 0.05), 0.46, capacity=1)
    with mock.patch.object(scenery.log, 'warning'):
      self.scenery = scenery.Scenery(
        mock.Mock(objects=FakeObjects([self.projector, self.sand, self.disc,
                                       self.bubble])), self.pool)

  def test_day_as_before(self):
    self.scenery.set_look(daynight.look(1.0))
    self.scenery.update(1.0, 0.1)
    self.assertEqual(self.sand.color[3], 1.0)
    self.assertEqual(self.disc.color[3], 1.0)
    self.assertEqual(self.bubble.color, (1.0, 1.0, 1.0, 1.0))
    self.assertEqual(self.pool.rate, 18.0)

  def test_night_dims_caustics_bubbles_and_ripples(self):
    night = daynight.look(0.0)
    self.scenery.set_look(night)
    self.scenery.update(1.0, 0.1)
    self.assertEqual(self.sand.color[3], night.caustics)
    self.assertAlmostEqual(self.disc.color[3], sum(night.bubbles) / 3)
    self.assertEqual(self.bubble.color, night.bubbles + (1.0,))
    self.assertAlmostEqual(self.pool.rate, 18.0 * night.bubble_rate)
    self.assertEqual(self.scenery.snapshot()['caustics'],
                     round(night.caustics, 3))
    # The bubbles' tint is set only when it changes
    self.bubble.color = 'untouched'
    self.scenery.set_look(night)
    self.scenery.update(1.1, 0.1)
    self.assertEqual(self.bubble.color, 'untouched')


if __name__ == '__main__':
  unittest.main()
