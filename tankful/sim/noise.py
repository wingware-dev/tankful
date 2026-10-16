"""Smooth, repeatable 1D noise, for wandering that never jerks."""

import math
import random


class SmoothNoise:
  """Gradient noise over t: smooth (C2), repeatable for a seed, in [-1, 1].

  Two octaves, the second at 2.3 times the frequency and a third of the
  weight, so the result meanders without settling into a visible period.
  frequency is in cycles per unit of t, roughly.
  """

  SIZE = 256

  def __init__(self, seed=0, frequency=1.0):
    rng = random.Random(seed)
    self.frequency = frequency
    self._grad = [rng.uniform(-1.0, 1.0) for _ in range(self.SIZE)]
    self._offset = rng.uniform(0, self.SIZE)

  def _octave(self, x):
    i = math.floor(x)
    f = x - i
    g0 = self._grad[int(i) % self.SIZE]
    g1 = self._grad[int(i + 1) % self.SIZE]
    # Quintic fade between the two gradients' ramps
    u = f * f * f * (f * (f * 6 - 15) + 10)
    return 2.0 * (g0 * f + (g1 * (f - 1) - g0 * f) * u)

  def __call__(self, t):
    x = t * self.frequency + self._offset
    v = self._octave(x) + 0.33 * self._octave(2.3 * x + 17.0)
    return max(-1.0, min(1.0, v / 1.33 * 1.6))
