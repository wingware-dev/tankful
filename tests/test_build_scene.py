import importlib.util
import os
import unittest
from unittest import mock

from tankful import launcher

_spec = importlib.util.spec_from_file_location(
  'build_scene', os.path.join(launcher.ROOT, 'tools', 'build_scene.py'))
build_scene = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_scene)


class MainOutsideBlenderTest(unittest.TestCase):

  def run_main(self, argv):
    with mock.patch.object(launcher, 'find_upbge', return_value='UP'), \
         mock.patch.object(launcher, 'build_scene', return_value=0) as bs:
      self.assertEqual(build_scene.main_outside_blender(argv), 0)
    return bs

  def test_passes_output_on(self):
    bs = self.run_main(['--output', '/tmp/x.blend'])
    bs.assert_called_once_with('UP', force=True, output='/tmp/x.blend')

  def test_accepts_blender_style_separator(self):
    bs = self.run_main(['--', '--output', '/tmp/x.blend'])
    bs.assert_called_once_with('UP', force=True, output='/tmp/x.blend')

  def test_defaults_to_game_scene(self):
    bs = self.run_main([])
    bs.assert_called_once_with('UP', force=True, output=launcher.BLEND)

  def test_rejects_unknown_arguments(self):
    with mock.patch('sys.stderr'), self.assertRaises(SystemExit):
      self.run_main(['--bogus'])


if __name__ == '__main__':
  unittest.main()
