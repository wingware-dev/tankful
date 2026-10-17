"""The hint that tells a new viewer how to steer the fish they picked.

The first time a click selects a fish (tankful.game.steering), a small
pill at the bottom of the window says the arrows steer it and a click on
open water lets it go.  It fades in, stays SHOW seconds and fades out,
and is not shown again in that run, whatever is selected later.

Its timing is plain Python (SelectionHint.update); only draw() needs
UPBGE's blf and gpu, through the scene's post_draw and
tankful.game.factor_hud.overlay.
"""

import logging

from tankful.game import factor_hud

log = logging.getLogger('tankful.hint')

TEXT = 'Arrow keys steer it  ·  Click open water to let go'
# Seconds of game time: fading in, fully shown, fading out
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


class SelectionHint:
  """update() once per frame with the current selection; draws itself
  through the scene's post_draw when given a scene."""

  def __init__(self, scene=None, window=None):
    """window: a function giving the window's (width, height), for
    draw()."""
    # Seconds since the first selection, or None before it
    self.age = None
    self._window = window
    self._draw_failed = False
    if scene is not None:
      scene.post_draw.append(self.draw)

  def update(self, selected, dt):
    """selected: the current selection (a group or None)."""
    if self.age is None:
      if selected is not None:
        self.age = 0.0
        log.info('showing the steering hint')
      return
    if self.age < self.duration:
      self.age += max(0.0, dt)

  @property
  def duration(self):
    return FADE_IN + SHOW + FADE_OUT

  @property
  def alpha(self):
    """How much of the hint shows, 0 to 1."""
    age = self.age
    if age is None or age >= self.duration:
      return 0.0
    if age < FADE_IN:
      return age / FADE_IN
    return min(1.0, (self.duration - age) / FADE_OUT)

  def snapshot(self):
    return {'shown': self.age is not None, 'alpha': round(self.alpha, 3),
            'text': TEXT if self.alpha > 0 else None}

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
    with factor_hud.overlay(window, s) as paint:
      width = paint.text_width(TEXT, TEXT_SIZE) + 2 * PAD * s
      bottom = h - BOTTOM * s
      rect = ((w - width) / 2, bottom - HEIGHT * s, (w + width) / 2, bottom)
      paint.fill(factor_hud.rect_triangles(rect),
                 PANEL_COLOR[:3] + (PANEL_COLOR[3] * a,))
      paint.text(rect[0] + PAD * s, (rect[1] + rect[3]) / 2, TEXT,
                 TEXT_SIZE, TEXT_COLOR[:3] + (TEXT_COLOR[3] * a,))
