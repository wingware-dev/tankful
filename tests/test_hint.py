import unittest
from unittest import mock

from tankful.game import hint
from tankful.game.hint import SelectionHint

GROUP = object()
OTHER = object()


class SelectionHintTests(unittest.TestCase):

  def setUp(self):
    self.hint = SelectionHint()

  def run_for(self, seconds, selected=GROUP, step=0.05):
    for _ in range(round(seconds / step)):
      self.hint.update(selected, step)

  def test_hidden_until_something_is_selected(self):
    self.run_for(10, selected=None)
    self.assertEqual(self.hint.alpha, 0.0)
    self.assertEqual(self.hint.snapshot(),
                     {'shown': False, 'alpha': 0.0, 'text': None})

  def test_fades_in_on_the_first_selection(self):
    self.hint.update(GROUP, 0.0)
    self.assertEqual(self.hint.alpha, 0.0)
    self.run_for(hint.FADE_IN / 2)
    self.assertAlmostEqual(self.hint.alpha, 0.5, places=2)
    self.run_for(hint.FADE_IN)
    self.assertEqual(self.hint.alpha, 1.0)
    self.assertEqual(self.hint.snapshot()['text'], hint.TEXT)

  def test_fades_out_after_showing(self):
    self.hint.update(GROUP, 0.0)
    self.run_for(hint.FADE_IN + hint.SHOW)
    self.assertAlmostEqual(self.hint.alpha, 1.0, places=6)
    self.run_for(hint.FADE_OUT / 2)
    self.assertAlmostEqual(self.hint.alpha, 0.5, places=2)
    self.run_for(hint.FADE_OUT)
    self.assertEqual(self.hint.alpha, 0.0)

  def test_keeps_going_when_deselected(self):
    self.hint.update(GROUP, 0.0)
    self.run_for(1.0)
    self.run_for(1.0, selected=None)
    self.assertEqual(self.hint.alpha, 1.0)
    self.run_for(hint.SHOW + hint.FADE_OUT, selected=None)
    self.assertEqual(self.hint.alpha, 0.0)

  def test_shown_once_only(self):
    self.hint.update(GROUP, 0.0)
    self.run_for(self.hint.duration + 1)
    self.run_for(1.0, selected=None)
    self.run_for(2.0, selected=OTHER)
    self.assertEqual(self.hint.alpha, 0.0)
    self.assertTrue(self.hint.snapshot()['shown'])

  def test_held_still_while_the_sim_is(self):
    # Under the harness dt is 0 between waits
    self.hint.update(GROUP, 0.0)
    self.run_for(1.0)
    age = self.hint.age
    for _ in range(100):
      self.hint.update(GROUP, 0.0)
    self.assertEqual(self.hint.age, age)

  def test_draws_through_post_draw(self):
    scene = mock.Mock(post_draw=[])
    h = SelectionHint(scene=scene, window=lambda: (1280, 720))
    self.assertEqual(scene.post_draw, [h.draw])

  def test_draws_nothing_while_hidden(self):
    h = SelectionHint(window=lambda: (1280, 720))
    with mock.patch.object(h, '_draw') as draw:
      h.draw()
    draw.assert_not_called()

  def test_draw_without_bge_is_logged_once(self):
    h = SelectionHint(window=lambda: (1280, 720))
    h.update(GROUP, 0.0)
    h.update(GROUP, 1.0)
    with self.assertLogs('tankful.hint', 'ERROR') as logs:
      h.draw()
      h.draw()
    self.assertEqual(len(logs.records), 1)


if __name__ == '__main__':
  unittest.main()
