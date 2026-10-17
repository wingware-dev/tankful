"""The hints that tell a new viewer how to pick and steer a fish.

A small pill at the bottom of the window, in two stages, each shown once
a run:

- Clicking: CLICK_DELAY seconds into the run, while nothing has been
  selected yet, it fades in saying to click a fish, and stays until a
  click selects one (tankful.game.steering).
- Steering: on that first selection it says the arrows steer the fish
  and a click on open water lets it go (in place of the click hint, at
  full strength, if that was showing; else fading in), stays SHOW
  seconds and fades out, whatever is selected later.

Under the harness (TANKFUL_HARNESS_PORT) the click hint is off, so
scripts' shots of an unselected tank don't change; TANKFUL_CLICK_HINT=1
turns it on there, and =0 off anywhere (click_hint_wanted).

Its timing is plain Python (SelectionHint.update); only draw() needs
UPBGE's blf and gpu, through the scene's post_draw and
tankful.game.factor_hud.overlay.
"""

import logging
import os

from tankful.game import factor_hud

log = logging.getLogger('tankful.hint')

CLICK_TEXT = 'Click a fish to select it'
TEXT = 'Arrow keys steer it  ·  Click open water to let go'
# Seconds of game time: the click hint's wait from the start of the run;
# fading in, the steering hint fully shown, fading out
CLICK_DELAY = 3.0
FADE_IN = 0.3
SHOW = 6.0
FADE_OUT = 1.0
# Layout, in window pixels at a 720 pixel tall window (as the factor
# HUD's), scaled with its height: the text's size, the pill's padding
# and height, and its bottom's distance from the window's
TEXT_SIZE = 16
PAD = 16
HEIGHT = 36
BOTTOM = 28
PANEL_COLOR = factor_hud.PANEL_COLOR
TEXT_COLOR = factor_hud.TEXT_COLOR


def click_hint_wanted(environ):
  """Whether to show the click hint: TANKFUL_CLICK_HINT's 1 or 0 if set,
  else not under the harness."""
  value = environ.get('TANKFUL_CLICK_HINT', '').strip()
  if value in ('0', '1'):
    return value == '1'
  if value:
    log.warning('ignoring bad TANKFUL_CLICK_HINT %r', value)
  return not environ.get('TANKFUL_HARNESS_PORT')


class SelectionHint:
  """update() once per frame with the current selection; draws itself
  through the scene's post_draw when given a scene."""

  def __init__(self, scene=None, window=None, click_hint=None):
    """window: a function giving the window's (width, height), for
    draw().  click_hint: whether to show the click hint, by default as
    click_hint_wanted(os.environ) says."""
    if click_hint is None:
      click_hint = click_hint_wanted(os.environ)
    self.click_hint = click_hint
    # Seconds of the run before the first selection
    self.waited = 0.0
    # Seconds of the steering hint since the first selection, or None
    # before it
    self.age = None
    self._window = window
    self._draw_failed = False
    if scene is not None:
      scene.post_draw.append(self.draw)

  def update(self, selected, dt):
    """selected: the current selection (a group or None)."""
    dt = max(0.0, dt)
    if self.age is None:
      if selected is None:
        self.waited += dt
        return
      # Take over the click hint's pill as it stands
      self.age = FADE_IN * self._click_alpha()
      log.info('showing the steering hint')
      return
    if self.age < self.duration:
      self.age += dt

  @property
  def duration(self):
    return FADE_IN + SHOW + FADE_OUT

  @property
  def stage(self):
    """'click', 'steer' or None: which hint is showing."""
    if self.age is None:
      return 'click' if self._click_alpha() > 0 else None
    return 'steer' if self.age < self.duration else None

  @property
  def text(self):
    return {'click': CLICK_TEXT, 'steer': TEXT}.get(self.stage)

  @property
  def alpha(self):
    """How much of the hint shows, 0 to 1."""
    age = self.age
    if age is None:
      return self._click_alpha()
    if age >= self.duration:
      return 0.0
    if age < FADE_IN:
      return age / FADE_IN
    return min(1.0, (self.duration - age) / FADE_OUT)

  def _click_alpha(self):
    if not self.click_hint:
      return 0.0
    return max(0.0, min(1.0, (self.waited - CLICK_DELAY) / FADE_IN))

  def snapshot(self):
    return {'shown': self.age is not None, 'stage': self.stage,
            'alpha': round(self.alpha, 3), 'text': self.text,
            'click_hint': self.click_hint}

  # Drawing, under UPBGE

  def draw(self):
    if self._draw_failed or self._window is None or self.alpha <= 0:
      return
    try:
      self._draw(self._window())
    except Exception:
      # Once only: a draw error every frame would flood the log
      self._draw_failed = True
      log.exception('steering hint: draw failed, hint off')

  def _draw(self, window):
    w, h = window
    s = max(0.5, h / 720.0)
    a = self.alpha
    value = self.text
    with factor_hud.overlay(window, s) as paint:
      width = paint.text_width(value, TEXT_SIZE) + 2 * PAD * s
      bottom = h - BOTTOM * s
      rect = ((w - width) / 2, bottom - HEIGHT * s, (w + width) / 2, bottom)
      paint.fill(factor_hud.rect_triangles(rect),
                 PANEL_COLOR[:3] + (PANEL_COLOR[3] * a,))
      paint.text(rect[0] + PAD * s, (rect[1] + rect[3]) / 2, value,
                 TEXT_SIZE, TEXT_COLOR[:3] + (TEXT_COLOR[3] * a,))
