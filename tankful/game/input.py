"""The game's single source of keyboard and mouse input.

Game code asks an InputState, never bge.logic.keyboard or mouse directly.
Real events are fed in from bge each frame (feed_from_bge), and the test
harness injects events through the same methods, so injected input acts
exactly like real input on every OS, without touching the user's actual
mouse or keyboard.

Key names are lower case: letters and digits ('l', 'f', '1'), 'left',
'right', 'up', 'down', 'space', 'escape', 'enter', 'tab', and so on.
Mouse positions are window pixels from the top left corner.
"""


def normalize_key(name):
  """Map a key name, ours or a bge event name, to our lower-case form."""
  n = name.strip().lower()
  if n.endswith('key') and len(n) > 3:
    n = n[:-3]
  if n.endswith('arrow'):
    n = n[:-5]
  return {'esc': 'escape', 'ret': 'enter', 'return': 'enter'}.get(n, n)


class InputState:

  def __init__(self):
    self._down = set()
    self._pressed = set()
    self._released = set()
    self._clicks = []
    self.mouse = (0, 0)

  # Feeding events (from bge or the harness)

  def key_down(self, name):
    key = normalize_key(name)
    if key not in self._down:
      self._down.add(key)
      self._pressed.add(key)

  def key_up(self, name):
    key = normalize_key(name)
    if key in self._down:
      self._down.discard(key)
      self._released.add(key)

  def click(self, x, y, button='left'):
    self.mouse = (x, y)
    self._clicks.append((x, y, button))

  def move_mouse(self, x, y):
    self.mouse = (x, y)

  # Queries for game code

  def is_down(self, name):
    return normalize_key(name) in self._down

  def was_pressed(self, name):
    """True only in the frame the key went down."""
    return normalize_key(name) in self._pressed

  def was_released(self, name):
    return normalize_key(name) in self._released

  def clicks(self):
    """Clicks this frame, as (x, y, button) tuples."""
    return list(self._clicks)

  def keys_down(self):
    return sorted(self._down)

  def end_frame(self):
    """Forget the one-frame events; call after game logic each frame."""
    self._pressed.clear()
    self._released.clear()
    self._clicks.clear()

  def snapshot(self):
    return {'keys_down': self.keys_down(), 'mouse': list(self.mouse)}


_BUTTONS = {'LEFTMOUSE': 'left', 'MIDDLEMOUSE': 'middle',
            'RIGHTMOUSE': 'right'}


_event_names = None


def event_names(events):
  """Map bge event codes to names, from the bge.events constants.

  (events.EventToString raises for some codes that keyboard.inputs has.)
  """
  global _event_names
  if _event_names is None:
    _event_names = {getattr(events, n): n for n in dir(events)
                    if n.isupper() and isinstance(getattr(events, n), int)}
  return _event_names


def feed_from_bge(state, logic, events, render):
  """Copy this frame's real bge keyboard and mouse events into state."""
  names = event_names(events)
  for code, inp in logic.keyboard.activeInputs.items():
    name = names.get(code)
    if name is None:
      continue
    if inp.activated:
      state.key_down(name)
    if inp.released:
      state.key_up(name)
  w, h = render.getWindowWidth(), render.getWindowHeight()
  mx, my = logic.mouse.position
  state.move_mouse(int(mx * w), int(my * h))
  for code, inp in logic.mouse.activeInputs.items():
    button = _BUTTONS.get(names.get(code))
    if button and inp.activated:
      state.click(state.mouse[0], state.mouse[1], button)
