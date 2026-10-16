import math
import unittest

from tankful.sim import swim
from tankful.sim.fish import Fish
from tankful.sim.noise import SmoothNoise
from tankful.sim.species import ANGELFISH


class SpineTests(unittest.TestCase):

  def test_tail_swing_is_the_wave(self):
    for phase in (0.0, 0.7, 2.0, 4.4):
      angles = swim.spine_angles(0.4, phase)
      self.assertEqual(len(angles), len(swim.SPINE))
      # Relative rotations add up to the tail's absolute swing
      self.assertAlmostEqual(sum(angles), 0.4 * math.sin(
        phase - (len(swim.SPINE) - 1) * swim.LAG))

  def test_wave_travels_toward_the_tail(self):
    # The tail peaks later in the cycle than the bone ahead of it
    def absolute(phase, k):
      return sum(swim.spine_angles(1.0, phase)[:k + 1])
    steps = [i * 2 * math.pi / 400 for i in range(400)]
    peak = [max(steps, key=lambda p: absolute(p, k)) for k in (2, 3)]
    self.assertGreater(peak[1], peak[0])

  def test_turns_bend_the_body_into_them(self):
    left = swim.spine_angles(0.0, 0.0, yaw_rate=0.4)
    right = swim.spine_angles(0.0, 0.0, yaw_rate=-0.4)
    # A left turn swings the rear left: negative z on every bone
    self.assertTrue(all(a < 0 for a in left))
    self.assertEqual([round(a, 9) for a in left],
                     [round(-a, 9) for a in right])
    # and the bend is capped
    self.assertEqual(swim.spine_angles(0.0, 0.0, 9.0),
                     swim.spine_angles(0.0, 0.0, swim.MAX_BEND))

  def test_pose_names_every_bone(self):
    f = Fish('f', ANGELFISH)
    pose = swim.pose(f)
    self.assertEqual(set(pose), set(swim.BONES))
    for angles in pose.values():
      self.assertEqual(len(angles), 3)
      self.assertTrue(all(abs(a) < 1.5 for a in angles))

  def test_pectorals_fold_when_cruising(self):
    f = Fish('f', ANGELFISH)
    f.hovering, f.fin_amp = 0.0, 0.2 * ANGELFISH.fin_swing
    cruising = max(abs(swim.pose(f)['Pec.L'][2]) for f.fin_phase in
                   [i * 0.3 for i in range(21)])
    f.hovering, f.fin_amp = 1.0, ANGELFISH.fin_swing
    hovering = max(abs(swim.pose(f)['Pec.L'][2]) for f.fin_phase in
                   [i * 0.3 for i in range(21)])
    self.assertGreater(hovering, 2 * cruising)


class NoiseTests(unittest.TestCase):

  def test_smooth_bounded_and_repeatable(self):
    n = SmoothNoise(seed=4, frequency=0.5)
    values = [n(i * 0.01) for i in range(20000)]
    self.assertTrue(all(-1.0 <= v <= 1.0 for v in values))
    # It ranges widely, but never jumps
    self.assertGreater(max(values) - min(values), 1.0)
    jumps = max(abs(a - b) for a, b in zip(values, values[1:]))
    self.assertLess(jumps, 0.05)
    self.assertEqual(values[:50],
                     [SmoothNoise(seed=4, frequency=0.5)(i * 0.01)
                      for i in range(50)])
    self.assertNotEqual(values[:50], [SmoothNoise(seed=5, frequency=0.5)(
      i * 0.01) for i in range(50)])


if __name__ == '__main__':
  unittest.main()
