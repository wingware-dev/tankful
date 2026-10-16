import os
import unittest

from tankful import launcher

MAC_ROOT = '/proj'


def fake_fs(files, dirs=None):
  """exists and listdir over a set of file paths (directories implied)."""
  files = set(files)
  dirs = dict(dirs or {})
  for f in files:
    d = os.path.dirname(f)
    while d and d != '/':
      dirs.setdefault(os.path.dirname(d), set()).add(os.path.basename(d))
      d = os.path.dirname(d)

  def exists(path):
    return path in files

  def listdir(path):
    if path not in dirs:
      raise FileNotFoundError(path)
    return list(dirs[path])
  return exists, listdir


def mac_app(base):
  return [base + '/Blender.app/Contents/MacOS/Blender',
          base + '/Blenderplayer.app/Contents/MacOS/Blenderplayer']


class FindUpbgeTests(unittest.TestCase):

  def find(self, files, env=None, platform='darwin'):
    exists, listdir = fake_fs(files)
    return launcher.find_upbge(env=env or {}, root=MAC_ROOT,
                               platform=platform, exists=exists,
                               listdir=listdir)

  def test_vendor_macos(self):
    up = self.find(mac_app('/proj/vendor/upbge/macos'))
    self.assertEqual(up.player, '/proj/vendor/upbge/macos/Blenderplayer.app'
                                '/Contents/MacOS/Blenderplayer')
    self.assertEqual(up.blender, '/proj/vendor/upbge/macos/Blender.app'
                                 '/Contents/MacOS/Blender')

  def test_vendor_linux_in_subdirectory(self):
    base = '/proj/vendor/upbge/linux/upbge-0.50-linux-x64'
    up = self.find([base + '/blender', base + '/blenderplayer'],
                   platform='linux')
    self.assertEqual(up, launcher.Upbge(base + '/blender',
                                        base + '/blenderplayer'))

  def test_vendor_windows(self):
    base = os.path.join('/proj/vendor/upbge/windows', 'upbge-0.50')
    up = self.find([os.path.join(base, 'blender.exe'),
                    os.path.join(base, 'blenderplayer.exe')], platform='win32')
    self.assertTrue(up.player.endswith('blenderplayer.exe'))

  def test_env_override_wins_over_vendor(self):
    files = mac_app('/proj/vendor/upbge/macos') + mac_app('/opt/mine')
    up = self.find(files, env={'TANKFUL_UPBGE': '/opt/mine'})
    self.assertTrue(up.player.startswith('/opt/mine/'))

  def test_env_override_may_name_the_app_or_binary(self):
    files = mac_app('/opt/mine')
    for value in ('/opt/mine/Blender.app',
                  '/opt/mine/Blender.app/Contents/MacOS/Blender'):
      up = self.find(files, env={'TANKFUL_UPBGE': value})
      self.assertTrue(up.player.startswith('/opt/mine/'), value)

  def test_env_override_linux_binary(self):
    up = self.find(['/x/blender', '/x/blenderplayer'],
                   env={'TANKFUL_UPBGE': '/x/blenderplayer'}, platform='linux')
    self.assertEqual(up.player, '/x/blenderplayer')

  def test_bad_env_override_is_an_error_not_a_fallback(self):
    with self.assertRaises(launcher.LaunchError) as cm:
      self.find(mac_app('/proj/vendor/upbge/macos'),
                env={'TANKFUL_UPBGE': '/nowhere'})
    self.assertIn('/nowhere', str(cm.exception))

  def test_standard_install_paths(self):
    up = self.find(mac_app('/Applications/UPBGE'))
    self.assertTrue(up.player.startswith('/Applications/UPBGE/'))
    up = self.find(['/opt/upbge/blender', '/opt/upbge/blenderplayer'],
                   platform='linux')
    self.assertEqual(up.player, '/opt/upbge/blenderplayer')

  def test_player_without_blender(self):
    up = self.find(['/proj/vendor/upbge/linux/blenderplayer'],
                   platform='linux')
    self.assertIsNone(up.blender)
    with self.assertRaises(launcher.LaunchError):
      launcher.build_scene_command(up)

  def test_not_found_lists_where_it_looked(self):
    with self.assertRaises(launcher.LaunchError) as cm:
      self.find([])
    msg = str(cm.exception)
    self.assertIn('fetch_upbge.py', msg)
    self.assertIn('/proj/vendor/upbge/macos', msg)

  def test_platform_key(self):
    self.assertEqual(launcher.platform_key('darwin'), 'macos')
    self.assertEqual(launcher.platform_key('win32'), 'windows')
    self.assertEqual(launcher.platform_key('linux'), 'linux')


class SceneAndCommandTests(unittest.TestCase):

  UP = launcher.Upbge('/u/blender', '/u/blenderplayer')

  def test_scene_is_stale(self):
    times = {'b.blend': 10, 'src.py': 5}
    def mtime(path):
      if path not in times:
        raise FileNotFoundError(path)
      return times[path]
    self.assertFalse(launcher.scene_is_stale('b.blend', ['src.py'], mtime))
    times['src.py'] = 11
    self.assertTrue(launcher.scene_is_stale('b.blend', ['src.py'], mtime))
    del times['b.blend']
    self.assertTrue(launcher.scene_is_stale('b.blend', ['src.py'], mtime))

  def test_scene_sources_exist(self):
    # A missing source would make every launch fail in scene_is_stale
    for path in launcher.SCENE_SOURCES:
      self.assertTrue(os.path.isfile(path), path)

  def test_build_scene_command_fails_on_python_errors(self):
    cmd = launcher.build_scene_command(self.UP, '/out.blend')
    self.assertEqual(cmd[:2], ['/u/blender', '-b'])
    self.assertIn('--python-exit-code', cmd)
    self.assertEqual(cmd[-3:], ['--', '--output', '/out.blend'])

  def test_player_command_window(self):
    cmd = launcher.player_command(self.UP, 'window', blend='/t.blend',
                                  window=(800, 600))
    self.assertEqual(cmd, ['/u/blenderplayer', '-w', '800', '600', '/t.blend'])

  def test_player_command_offscreen_starts_small_and_far(self):
    cmd = launcher.player_command(self.UP, 'offscreen', blend='/t.blend')
    w, h, x, y = (int(v) for v in cmd[2:6])
    self.assertEqual((w, h), launcher.OFFSCREEN_START_SIZE)
    self.assertGreater(min(x, y), 10000)
    self.assertTrue(all(v >= 0 for v in (w, h, x, y)),
                    'the player rejects negative numbers')

  def test_player_command_extra_args(self):
    cmd = launcher.player_command(self.UP, 'xvfb', blend='/t.blend',
                                  extra=['--x'])
    self.assertEqual(cmd[-3:], ['/t.blend', '-', '--x'])

  def test_game_env(self):
    env = launcher.game_env({'A': '1'}, root='/r', harness_port=5,
                            harness_host='0.0.0.0', debug=True,
                            offscreen=True, window=(640, 480))
    self.assertEqual(env['A'], '1')
    self.assertEqual(env['TANKFUL_ROOT'], '/r')
    self.assertEqual(env['TANKFUL_HARNESS_PORT'], '5')
    self.assertEqual(env['TANKFUL_HARNESS_HOST'], '0.0.0.0')
    self.assertEqual(env['TANKFUL_DEBUG'], '1')
    self.assertEqual(env['TANKFUL_OFFSCREEN'], '640x480')
    plain = launcher.game_env({}, root='/r')
    for key in ('TANKFUL_HARNESS_PORT', 'TANKFUL_DEBUG', 'TANKFUL_OFFSCREEN'):
      self.assertNotIn(key, plain)

  def test_docker_command(self):
    cmd = launcher.docker_command('/proj', ['--harness', '7'], 7)
    self.assertIn('/proj:/tankful', cmd)
    self.assertIn('127.0.0.1:7:7', cmd)
    self.assertIn('TANKFUL_HARNESS_HOST=0.0.0.0', cmd)
    i = cmd.index(launcher.DOCKER_IMAGE)
    self.assertEqual(cmd[i + 1:], ['python3', '/tankful/run_tankful.py',
                                   '--backend', 'xvfb', '--harness', '7'])

  def test_free_display(self):
    taken = {'/tmp/.X11-unix/X99', '/tmp/.X100-lock'}
    self.assertEqual(launcher.free_display(lambda p: p in taken), 101)


if __name__ == '__main__':
  unittest.main()
