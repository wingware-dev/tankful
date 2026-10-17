"""Plant sway: the bend of each bone in a leaf chain over time.

The filter's current (tankful.sim.environment.current_at) leans each
plant away from its outflow, gusting slowly, and the leaves wave in it, a
wave travelling up each leaf so the tips move most and lag the base.  The
game applies the angles to the plant armatures' bones
(tankful.game.scenery).
"""

import math

# The shares of the amplitude in the current's steady lean and in the
# leaves' waving, their sum within 1.2 with the waving's peak of 1.5
LEAN = 0.4
WAVE = 0.5


def current(t):
  """The current's strength at time t: a slow, irregular gust, 0.35 to 1."""
  g = math.sin(0.21 * t) * math.sin(0.083 * t + 1.1)
  return 0.675 + 0.325 * g


def chain_angles(t, bones, phase, amplitude, frequency, leaf=0,
                 flow=(0.0, 0.0)):
  """[(bend_x, bend_y), ...] in radians for each bone, base first.

  bend_x tips the bone toward the viewer and away, bend_y side to side.
  Each bone's bend adds to its parent's, so the tip's total lean is the
  sum, which stays within 1.2 * amplitude on either axis.  leaf offsets
  the phase so the leaves of one plant do not move as one.  flow is the
  current, (fx, fy) in the tank's x and y, at most 1 long: the leaves
  lean with it (tip_lean).
  """
  if bones < 1:
    return []
  gust = current(t)
  w = 2 * math.pi * frequency
  p = phase + 1.7 * leaf
  out = []
  # The bend is spread over the chain, weighted toward the tip
  weights = [(i + 1) for i in range(bones)]
  total = float(sum(weights))
  for i, weight in enumerate(weights):
    share = amplitude * weight / total
    lag = 0.55 * i
    side = math.sin(w * t + p - lag) + 0.5 * math.sin(1.9 * w * t + 2 * p - lag)
    fore = math.sin(0.8 * w * t + p + 0.9 - lag)
    # A leaf's bones have no roll and stand roughly upright, so a bone's
    # x axis is the tank's x and its z the tank's -y (tip_lean)
    out.append((share * gust * (fore * WAVE - LEAN * flow[1]),
                share * gust * (side * WAVE - LEAN * flow[0])))
  return out


def tip_lean(angles):
  """Roughly which way and how far, in radians, a chain's tip leans in
  the tank's x and y, from its chain_angles."""
  return (-sum(a[1] for a in angles), -sum(a[0] for a in angles))
