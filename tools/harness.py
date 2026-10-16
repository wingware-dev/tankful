"""Run tankful under the test harness and drive it with a script.

  python tools/harness.py SCRIPT.json [--backend offscreen] [--rebuild]
                          [--no-git-add] [--log PATH]

SCRIPT.json is a list of commands, or {"backend": ..., "commands": [...]}.
Commands are text ("click 640 360", "key down left", "wait 2",
"wait 30f", "screenshot docs/shots/01-skeleton.png", "state", "quit") or
JSON objects; see tankful/harness_protocol.py.  Screenshots under
docs/shots/ are checked for being non-black and added to git.

The default backend is offscreen on macOS and Windows, xvfb on Linux;
docker runs the Linux build headless on any host.  See docs/harness.md.
Exits 0 when every command succeeded.
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tankful import harness_client  # noqa: E402
from tankful import launcher  # noqa: E402


def default_backend():
  return 'xvfb' if launcher.platform_key() == 'linux' else 'offscreen'


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument('script')
  parser.add_argument('--backend', choices=launcher.BACKENDS)
  parser.add_argument('--rebuild', action='store_true',
                      help='rebuild the scene first')
  parser.add_argument('--no-git-add', action='store_true',
                      help="don't git add screenshots under docs/shots/")
  parser.add_argument('--log', help='write the game output here instead of '
                                    'to the terminal')
  args = parser.parse_args(argv)

  script = harness_client.load_script(args.script)
  backend = args.backend or script.get('backend') or default_backend()
  commands = script['commands']
  if not commands or commands[-1]['cmd'] != 'quit':
    commands.append({'cmd': 'quit'})

  port = launcher.pick_port()
  log_file = open(args.log, 'w') if args.log else None
  print('harness: backend %s, port %d' % (backend, port))
  proc = harness_client.start_game(backend, port, args.rebuild, log_file)
  ok = False
  try:
    client = harness_client.connect(port, proc)
    try:
      results = harness_client.run_script(client, commands,
                                          add_shots=not args.no_git_add)
    finally:
      client.close()
    ok = len(results) == len(commands) and all(r.get('ok') for _, r in results)
    try:
      code = proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
      code = _stop(proc)
      print('harness: game did not quit; terminated')
    print('harness: game exited with code %s' % code)
  except harness_client.HarnessError as exc:
    print('harness: %s' % exc, file=sys.stderr)
  finally:
    if proc.poll() is None:
      _stop(proc)
    if log_file:
      log_file.close()
  return 0 if ok else 1


def _stop(proc):
  # SIGTERM lets run_tankful.py stop the player (with SIGKILL if need be)
  # before it exits; it gets 5s for that, so wait a little longer
  proc.terminate()
  try:
    return proc.wait(timeout=10)
  except subprocess.TimeoutExpired:
    proc.kill()
    return proc.wait()


if __name__ == '__main__':
  sys.exit(main())
