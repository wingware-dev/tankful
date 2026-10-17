"""The user's hand on a fish: selecting it and steering it with the
arrow keys (step 9).

Control is the state machine.  What it selects is a group as
tankful.sim.school.group_of gives it: a fish of its own, or the whole
school, shoal or colony one of its members is in.  Its state runs

  IDLE -> SELECTED -> STEERING -> RELEASING -> SELECTED

- IDLE: nothing selected.
- SELECTED: a group is selected and swims as it always does.
- STEERING: an arrow key is down.  The group's targets (targets) each
  get the Control's Steer, whose weight ramps up over RAMP_IN, and whose
  direction is the arrows' in the screen plane: x to the viewer's right
  and z up.  The fish keep the depth (y) they had when the steering
  began (tankful.sim.fish.Fish._steered).
- RELEASING: no arrow is down.  The Steer keeps the last direction while
  its weight falls to 0 over BLEND_OUT, the fish's own steering blending
  back in; then it is taken off the targets and the state is SELECTED.

Selecting another group, or nothing, while a Steer is on lets that Steer
blend out on its own (Control.fading), so the fish let go always eases.

A target is what a Steer drives: a School as one (its goal, which its
members follow in formation), and every other group member by member.
A target reads only its steer attribute, so the sim knows nothing of
keys: the Control sets it, and takes it off.
"""

import math

from tankful.sim import school as sim_school

IDLE, SELECTED, STEERING, RELEASING = (
  'idle', 'selected', 'steering', 'releasing')

# The arrow keys, as tankful.game.input names them, and their direction
# in the screen plane: (x, z)
ARROWS = {'left': (-1.0, 0.0), 'right': (1.0, 0.0), 'up': (0.0, 1.0),
          'down': (0.0, -1.0)}
# How long (s) the steering takes to come in fully, and to blend back out
# to the fish's own once the keys are up
RAMP_IN = 0.25
BLEND_OUT = 1.5


class Steer:
  """What the user asks of the targets it is on: a direction in the
  screen plane, (x, z), a unit vector, and how much of the fish's
  steering it has, weight, 0 to 1."""

  def __init__(self, targets):
    self.targets = list(targets)
    self.direction = (0.0, 0.0)
    self.weight = 0.0

  def attach(self):
    for t in self.targets:
      t.steer = self

  def detach(self):
    for t in self.targets:
      if t.steer is self:
        t.steer = None

  def fade(self, dt):
    """Blend out by dt; whether it has gone."""
    self.weight = max(0.0, self.weight - dt / BLEND_OUT)
    return self.weight <= 0.0

  def snapshot(self):
    return {'direction': [round(v, 3) for v in self.direction],
            'weight': round(self.weight, 3)}


def targets(group):
  """What a Steer on group (a fish, or a group from
  tankful.sim.school.group_of) drives."""
  if isinstance(group, sim_school.School):
    return [group]
  members = getattr(group, 'members', None)
  if members is not None:
    return list(members)
  return [group]


def arrows(keys):
  """The direction the arrow keys in keys ask for, (x, z) as a unit
  vector, or None when none is down or they cancel out."""
  x = z = 0.0
  for key in keys:
    d = ARROWS.get(key)
    if d is not None:
      x += d[0]
      z += d[1]
  n = math.hypot(x, z)
  if n < 1e-9:
    return None
  return (x / n, z / n)


class Control:

  def __init__(self):
    self.selected = None
    self.steer = None
    # Steers let go of when the selection changed, still blending out
    self.fading = []
    self._released = False

  @property
  def state(self):
    if self.selected is None:
      return IDLE
    if self.steer is None:
      return SELECTED
    return RELEASING if self._released else STEERING

  def select(self, group):
    """Make group (a fish or a group, or None) the current one."""
    if group is self.selected:
      return
    self._let_go()
    self.selected = group

  def _let_go(self):
    if self.steer is not None:
      self.fading.append(self.steer)
      self.steer = None

  def update(self, dt, keys):
    """Advance by dt (s) with keys, the key names down now."""
    for s in list(self.fading):
      if s.fade(dt):
        s.detach()
        self.fading.remove(s)
    direction = arrows(keys) if self.selected is not None else None
    if direction is not None:
      if self.steer is None:
        self.steer = self._take_up(targets(self.selected))
      self.steer.direction = direction
      self.steer.weight = min(1.0, self.steer.weight + dt / RAMP_IN)
      self._released = False
    elif self.steer is not None:
      self._released = True
      if self.steer.fade(dt):
        self.steer.detach()
        self.steer = None

  def _take_up(self, group_targets):
    """A Steer for group_targets: one still blending out on them, picked
    up where it is, or a new one."""
    for s in self.fading:
      if s.targets == group_targets:
        self.fading.remove(s)
        s.attach()
        return s
    s = Steer(group_targets)
    s.attach()
    return s

  def is_selected(self, fish):
    """Whether fish is the current one, or in the current group."""
    if self.selected is None:
      return False
    return sim_school.group_of(fish) is self.selected

  def snapshot(self):
    sel = self.selected
    return {
      'state': self.state,
      'selected': getattr(sel, 'name', None),
      'members': [f.name for f in getattr(sel, 'members', ())]
      if sel is not None else [],
      'steer': self.steer.snapshot() if self.steer else None,
      'fading': len(self.fading),
    }
