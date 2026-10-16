"""Venv side of the test harness: start the game and drive it.

tools/harness.py is the command line front end.  See
tankful.harness_protocol for the commands and docs/harness.md for the
display backends.
"""

import json
import os
import socket
import subprocess
import sys
import time

from tankful import harness_protocol as proto
from tankful import launcher
from tankful import pngstats

CONNECT_TIMEOUT = 180.0
REPLY_TIMEOUT = 60.0
SHOT_TIMEOUT = 15.0


class HarnessError(RuntimeError):
  pass


class Client:
  """Sends requests over a connected socket and waits for each reply."""

  def __init__(self, sock, timeout=REPLY_TIMEOUT):
    self.sock = sock
    self.timeout = timeout
    self._buffer = proto.LineBuffer()
    self._pending = []
    self._next_id = 1

  def request(self, msg, timeout=None):
    msg = dict(msg)
    proto.validate(msg)
    msg['id'] = self._next_id
    self._next_id += 1
    self.sock.sendall(proto.encode(msg))
    extra = msg.get('seconds', 0) if msg['cmd'] == 'wait' else 0
    return self._reply(msg['id'], (timeout or self.timeout) + extra)

  def _reply(self, want, timeout):
    deadline = time.monotonic() + timeout
    while True:
      for i, resp in enumerate(self._pending):
        if resp.get('id') == want:
          return self._pending.pop(i)
        if resp.get('id') is None:
          self._pending.pop(i)
          raise HarnessError('game rejected a message: %s'
                             % resp.get('error'))
      left = deadline - time.monotonic()
      if left <= 0:
        raise HarnessError('no reply to request %d within %gs'
                           % (want, timeout))
      self.sock.settimeout(left)
      try:
        data = self.sock.recv(65536)
      except socket.timeout:
        continue
      if not data:
        raise HarnessError('game closed the harness connection')
      self._pending += [proto.decode(l) for l in self._buffer.feed(data)]

  def close(self):
    self.sock.close()


def connect(port, proc=None, timeout=CONNECT_TIMEOUT, host='127.0.0.1'):
  """Connect to the game, retrying while it starts up."""
  deadline = time.monotonic() + timeout
  while True:
    if proc is not None and proc.poll() is not None:
      raise HarnessError('game exited with code %d before the harness '
                         'connected' % proc.returncode)
    try:
      sock = socket.create_connection((host, port), timeout=2.0)
    except OSError:
      if time.monotonic() > deadline:
        raise HarnessError('could not connect to the game on port %d '
                           'within %gs' % (port, timeout))
      time.sleep(0.5)
      continue
    # Docker publishes the port before the game listens: the connection
    # opens and then closes at once.  A first request proves it is real.
    client = Client(sock)
    try:
      client.request({'cmd': 'state'}, timeout=10.0)
    except (HarnessError, OSError):
      client.close()
      if time.monotonic() > deadline:
        raise
      time.sleep(0.5)
      continue
    return client


def start_game(backend, port, rebuild=False, stdout=None):
  cmd = [sys.executable, os.path.join(launcher.ROOT, 'run_tankful.py'),
         '--backend', backend, '--harness', str(port)]
  if rebuild:
    cmd.append('--rebuild')
  return subprocess.Popen(cmd, cwd=launcher.ROOT, stdout=stdout,
                          stderr=subprocess.STDOUT if stdout else None)


def load_script(path):
  """Read a script: a JSON list of commands, or an object with
  'commands' (and optionally 'backend')."""
  with open(path) as f:
    data = json.load(f)
  if isinstance(data, list):
    data = {'commands': data}
  if not isinstance(data, dict) or not isinstance(data.get('commands'), list):
    raise proto.ProtocolError('%s: expected a list of commands or an object '
                              'with "commands"' % path)
  data['commands'] = [proto.parse_command(c) for c in data['commands']]
  return data


def git_add(path, root=launcher.ROOT):
  """Track a new screenshot under docs/shots/ so it joins the change set."""
  rel = os.path.relpath(os.path.abspath(os.path.join(root, path)), root)
  if rel.split(os.sep)[:2] != ['docs', 'shots']:
    return False
  subprocess.run(['git', 'add', '--', rel], cwd=root, check=True)
  return True


def read_shot(path, timeout=None, poll=0.1):
  """Return pngstats.stats for a screenshot, waiting while it is missing
  or truncated: the game can reply before a large PNG is fully written."""
  timeout = SHOT_TIMEOUT if timeout is None else timeout
  deadline = time.monotonic() + timeout
  while True:
    try:
      return pngstats.stats(path)
    except (FileNotFoundError, pngstats.PngTruncated) as exc:
      if time.monotonic() > deadline:
        raise HarnessError('screenshot %s still incomplete after %gs: %s'
                           % (path, timeout, exc))
    time.sleep(poll)


def run_script(client, commands, add_shots=True, log=print):
  """Run commands in order; return a list of (command, reply), stopping
  at the first failure."""
  results = []
  for msg in commands:
    reply = client.request(msg)
    results.append((msg, reply))
    if not reply.get('ok'):
      log('FAILED %s: %s' % (_describe(msg), reply.get('error')))
      break
    note = ''
    if msg['cmd'] == 'screenshot':
      full = os.path.join(launcher.ROOT, msg['path'])
      try:
        summary = read_shot(full)
      except HarnessError as exc:
        reply['ok'] = False
        reply['error'] = str(exc)
        log('FAILED %s: %s' % (_describe(msg), exc))
        break
      reply['image'] = summary
      note = ' %(width)dx%(height)d mean %(mean)s max %(max)s' % summary
      if pngstats.is_black(summary):
        reply['ok'] = False
        reply['error'] = 'screenshot is black'
        log('FAILED %s: black image%s' % (_describe(msg), note))
        break
      if add_shots and git_add(msg['path']):
        note += ' (git add)'
    elif msg['cmd'] == 'state':
      note = ' ' + json.dumps(reply.get('state'))
    log('ok %s%s' % (_describe(msg), note))
    if msg['cmd'] == 'quit':
      break
  return results


def _describe(msg):
  args = ' '.join(str(v) for k, v in msg.items() if k not in ('cmd', 'id'))
  return (msg['cmd'] + ' ' + args).strip()
