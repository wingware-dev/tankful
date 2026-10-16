"""Run tankful: find UPBGE, rebuild the scene if stale, start the player.

  python run_tankful.py [--backend window|offscreen|xvfb|docker]
                        [--harness PORT] [--rebuild] [--debug]

Runs under the venv's Python; the game itself runs in UPBGE's Python.
Returns the player's exit code.  See README.md.
"""

import argparse
import os
import signal
import subprocess
import sys

from tankful import launcher


def parse_args(argv):
  parser = argparse.ArgumentParser(description='Run the tankful aquarium.')
  parser.add_argument('--backend', choices=launcher.BACKENDS, default='window',
                      help='where the window goes: window (normal), offscreen '
                           '(placed outside the desktop), xvfb (Linux virtual '
                           'display) or docker (Linux build in a container)')
  parser.add_argument('--harness', type=int, metavar='PORT',
                      help='accept harness commands on localhost:PORT')
  parser.add_argument('--rebuild', action='store_true',
                      help='rebuild build/tankful.blend even if up to date')
  parser.add_argument('--debug', action='store_true',
                      help='connect game code to the Wing debugger')
  return parser.parse_args(argv)


def run(args):
  if args.backend == 'docker':
    argv = []
    if args.harness is not None:
      argv += ['--harness', str(args.harness)]
    if args.rebuild:
      argv.append('--rebuild')
    code = launcher.ensure_docker_image()
    if code:
      print('Docker image build failed with exit code %d' % code,
            file=sys.stderr)
      return code
    cmd = launcher.docker_command(launcher.ROOT, argv, args.harness)
    return _run_player(cmd, os.environ)

  upbge = launcher.find_upbge()
  code = launcher.build_scene(upbge, force=args.rebuild)
  if code:
    print('Scene build failed with exit code %d' % code, file=sys.stderr)
    return code

  env = launcher.game_env(os.environ, harness_port=args.harness,
                          harness_host=os.environ.get('TANKFUL_HARNESS_HOST'),
                          debug=args.debug,
                          offscreen=args.backend == 'offscreen')
  xvfb = None
  if args.backend == 'xvfb':
    xvfb, env['DISPLAY'] = launcher.start_xvfb()
  try:
    return _run_player(launcher.player_command(upbge, args.backend), env)
  finally:
    if xvfb is not None:
      xvfb.terminate()
      xvfb.wait()


def stop(proc, grace=5.0):
  """Terminate proc, then kill it if it lingers (the UPBGE player
  ignores SIGTERM); return its exit code."""
  proc.terminate()
  try:
    return proc.wait(timeout=grace)
  except subprocess.TimeoutExpired:
    proc.kill()
    return proc.wait()


class _Terminated(Exception):
  pass


def _on_sigterm(signum, frame):
  raise _Terminated()


def _run_player(cmd, env):
  # Output goes straight through to ours; Ctrl-C or SIGTERM (as the
  # harness sends) stops the player too, instead of orphaning it
  proc = subprocess.Popen(cmd, env=env)
  previous = signal.signal(signal.SIGTERM, _on_sigterm)
  try:
    return proc.wait()
  except (KeyboardInterrupt, _Terminated):
    return stop(proc)
  finally:
    signal.signal(signal.SIGTERM, previous)


def main(argv=None):
  try:
    return run(parse_args(sys.argv[1:] if argv is None else argv))
  except launcher.LaunchError as exc:
    print('run_tankful: %s' % exc, file=sys.stderr)
    return 2


if __name__ == '__main__':
  sys.exit(main())
