import math
import unittest

from tankful.factors import effects
from tankful.factors.effects import Effects, NEUTRAL


class NeutralTests(unittest.TestCase):

  def test_defaults_are_neutral(self):
    self.assertEqual(NEUTRAL.speed_scale, 1.0)
    self.assertEqual(NEUTRAL.depth_shift, 0.0)
    self.assertEqual(NEUTRAL.light_level, 1.0)
    self.assertEqual(NEUTRAL.caustic_sharpness, 1.0)
    self.assertEqual(NEUTRAL.tint, (1.0, 1.0, 1.0))
    self.assertEqual(NEUTRAL.surface_agitation, 0.0)
    self.assertEqual(NEUTRAL.skittish, 0.0)
    self.assertEqual(NEUTRAL.night_light, 0.0)
    self.assertEqual(NEUTRAL.flicker, 0.0)

  def test_neutral_is_inside_its_ranges(self):
    self.assertEqual(NEUTRAL.clamped(), NEUTRAL)

  def test_frozen(self):
    with self.assertRaises(AttributeError):
      NEUTRAL.speed_scale = 2.0

  def test_replace(self):
    e = NEUTRAL.replace(skittish=0.5)
    self.assertEqual(e.skittish, 0.5)
    self.assertEqual(NEUTRAL.skittish, 0.0)


class ClampTests(unittest.TestCase):

  def test_clamps_each_field_to_its_range(self):
    e = Effects(speed_scale=10, depth_shift=-5, light_level=-1,
                caustic_sharpness=9, tint=(2, -1, 0.5),
                surface_agitation=3, skittish=-2, night_light=7).clamped()
    self.assertEqual(e.speed_scale, effects.RANGES['speed_scale'][1])
    self.assertEqual(e.depth_shift, -1.0)
    self.assertEqual(e.light_level, 0.0)
    self.assertEqual(e.caustic_sharpness, 2.0)
    self.assertEqual(e.tint, (1.0, 0.0, 0.5))
    self.assertEqual(e.surface_agitation, 1.0)
    self.assertEqual(e.skittish, 0.0)
    self.assertEqual(e.night_light, 1.0)

  def test_flicker_range_and_blend(self):
    self.assertEqual(Effects(flicker=3).clamped().flicker, 1.0)
    self.assertEqual(Effects(flicker=-1).clamped().flicker, 0.0)
    e = effects.blend(NEUTRAL, Effects(flicker=1.0), 0.25)
    self.assertAlmostEqual(e.flicker, 0.25)

  def test_low_speed_floor(self):
    self.assertEqual(Effects(speed_scale=0).clamped().speed_scale, 0.25)

  def test_nan_and_junk_become_neutral(self):
    e = Effects(speed_scale=float('nan'), depth_shift='x',
                tint=(float('nan'), 0.5, 0.5)).clamped()
    self.assertEqual(e.speed_scale, 1.0)
    self.assertEqual(e.depth_shift, 0.0)
    self.assertEqual(e.tint, (1.0, 0.5, 0.5))

  def test_bad_tint_becomes_white(self):
    self.assertEqual(Effects(tint=None).clamped().tint, (1.0, 1.0, 1.0))
    self.assertEqual(Effects(tint=(0.5,)).clamped().tint, (1.0, 1.0, 1.0))

  def test_tint_list_becomes_tuple(self):
    self.assertEqual(Effects(tint=[0.2, 0.4, 0.6, 1.0]).clamped().tint,
                     (0.2, 0.4, 0.6))

  def test_infinity_clamps(self):
    self.assertEqual(Effects(depth_shift=math.inf).clamped().depth_shift, 1.0)


class BlendTests(unittest.TestCase):

  DARK = Effects(speed_scale=0.5, depth_shift=-1, light_level=0.2,
                 caustic_sharpness=0, tint=(0.6, 0.8, 1.0),
                 surface_agitation=1, skittish=1, night_light=1)

  def test_ends(self):
    self.assertEqual(effects.blend(NEUTRAL, self.DARK, 0), NEUTRAL)
    self.assertEqual(effects.blend(NEUTRAL, self.DARK, 1), self.DARK)

  def test_halfway(self):
    e = effects.blend(NEUTRAL, self.DARK, 0.5)
    self.assertAlmostEqual(e.speed_scale, 0.75)
    self.assertAlmostEqual(e.depth_shift, -0.5)
    self.assertAlmostEqual(e.light_level, 0.6)
    self.assertEqual(e.tint, (0.8, 0.9, 1.0))
    self.assertAlmostEqual(e.night_light, 0.5)

  def test_t_is_clamped(self):
    self.assertEqual(effects.blend(NEUTRAL, self.DARK, 3), self.DARK)
    self.assertEqual(effects.blend(NEUTRAL, self.DARK, -1), NEUTRAL)


class ApproachTests(unittest.TestCase):

  TARGET = Effects(light_level=0.0)

  def test_moves_part_way(self):
    e = effects.approach(NEUTRAL, self.TARGET, 1.0, time_constant=1.0)
    self.assertAlmostEqual(e.light_level, math.exp(-1))

  def test_frame_rate_independent(self):
    one = effects.approach(NEUTRAL, self.TARGET, 1.0, 2.0)
    many = NEUTRAL
    for _ in range(60):
      many = effects.approach(many, self.TARGET, 1 / 60.0, 2.0)
    self.assertAlmostEqual(one.light_level, many.light_level)

  def test_converges(self):
    e = NEUTRAL
    for _ in range(600):
      e = effects.approach(e, self.TARGET, 1 / 60.0, 1.0)
    self.assertAlmostEqual(e.light_level, 0.0, places=3)

  def test_zero_time_constant_snaps(self):
    self.assertIs(effects.approach(NEUTRAL, self.TARGET, 0.01, 0),
                  self.TARGET)

  def test_zero_and_negative_dt_stay(self):
    self.assertEqual(effects.approach(NEUTRAL, self.TARGET, 0), NEUTRAL)
    self.assertEqual(effects.approach(NEUTRAL, self.TARGET, -1), NEUTRAL)


class MixTests(unittest.TestCase):

  def test_weighted_average(self):
    a = Effects(speed_scale=0.5, tint=(0.0, 0.0, 0.0))
    b = Effects(speed_scale=2.0, tint=(1.0, 1.0, 1.0))
    e = effects.mix((a, 2), (b, 1))
    self.assertAlmostEqual(e.speed_scale, 1.0)
    for c in e.tint:
      self.assertAlmostEqual(c, 1 / 3.0)

  def test_no_weight_is_neutral(self):
    self.assertEqual(effects.mix(), NEUTRAL)
    self.assertEqual(effects.mix((Effects(skittish=1), 0)), NEUTRAL)

  def test_negative_weights_ignored(self):
    e = effects.mix((Effects(skittish=1), 1), (NEUTRAL, -5))
    self.assertEqual(e.skittish, 1)


if __name__ == '__main__':
  unittest.main()
