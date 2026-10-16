"""Wire format shared by tools/harness.py and tankful.game.harness_channel.

Each message is one JSON object on one line (UTF-8, '\\n' terminated).
Requests carry 'cmd' and an integer 'id'; each response echoes the 'id'
and has 'ok' (bool), plus 'error' when ok is false.

Commands:
  {"cmd": "click", "x": 100, "y": 200, "button": "left"}
      x and y are window pixels from the top left corner.
  {"cmd": "key", "action": "down" | "up", "name": "left"}
  {"cmd": "wait", "seconds": 1.5}   or   {"cmd": "wait", "frames": 30}
  {"cmd": "screenshot", "path": "docs/shots/01-skeleton.png"}
      A relative path is relative to the project root.
  {"cmd": "state"}   -> response has "state": the sim snapshot
  {"cmd": "quit"}

Scripts may also give a command as text, which parse_command turns into
the above: "click 100 200", "key down left", "wait 1.5", "wait 1.5s",
"wait 30f", "wait 30 frames", "screenshot PATH", "state", "quit".
"""

import json

COMMANDS = ('click', 'key', 'wait', 'screenshot', 'state', 'quit')


class ProtocolError(ValueError):
  pass


def encode(msg):
  return (json.dumps(msg, separators=(',', ':')) + '\n').encode('utf-8')


def decode(line):
  """Decode one line (bytes or str) into a dict; ProtocolError if bad."""
  if isinstance(line, bytes):
    try:
      line = line.decode('utf-8')
    except UnicodeDecodeError as exc:
      raise ProtocolError('not UTF-8: %s' % exc)
  try:
    msg = json.loads(line)
  except ValueError as exc:
    raise ProtocolError('bad JSON: %s' % exc)
  if not isinstance(msg, dict):
    raise ProtocolError('message must be a JSON object')
  return msg


class LineBuffer:
  """Splits a byte stream into lines, holding any partial last line."""

  def __init__(self):
    self._data = b''

  def feed(self, data):
    self._data += data
    *lines, self._data = self._data.split(b'\n')
    return [l for l in lines if l.strip()]


def _number(text, what):
  try:
    return float(text) if '.' in text else int(text)
  except ValueError:
    raise ProtocolError('%s must be a number, not %r' % (what, text))


def _parse_wait(args):
  if not args or len(args) > 2:
    raise ProtocolError('usage: wait SECONDS | wait Nf | wait N frames')
  amount = args[0].lower()
  unit = args[1].lower() if len(args) == 2 else ''
  if not unit:
    if amount.endswith('f'):
      unit, amount = 'frames', amount[:-1]
    elif amount.endswith('s'):
      unit, amount = 'seconds', amount[:-1]
    else:
      unit = 'seconds'
  if unit in ('f', 'frame', 'frames'):
    return {'cmd': 'wait', 'frames': int(_number(amount, 'frames'))}
  if unit in ('s', 'sec', 'second', 'seconds'):
    return {'cmd': 'wait', 'seconds': float(_number(amount, 'seconds'))}
  raise ProtocolError('unknown wait unit %r' % unit)


def parse_command(item):
  """Turn a script item (text, list or dict) into a request dict."""
  if isinstance(item, dict):
    msg = dict(item)
  else:
    words = item.split() if isinstance(item, str) else [str(w) for w in item]
    if not words:
      raise ProtocolError('empty command')
    name, args = words[0].lower(), words[1:]
    if name == 'click':
      if len(args) not in (2, 3):
        raise ProtocolError('usage: click X Y [BUTTON]')
      msg = {'cmd': 'click', 'x': _number(args[0], 'x'),
             'y': _number(args[1], 'y')}
      if len(args) == 3:
        msg['button'] = args[2].lower()
    elif name == 'key':
      if len(args) != 2:
        raise ProtocolError('usage: key down|up NAME')
      msg = {'cmd': 'key', 'action': args[0].lower(), 'name': args[1]}
    elif name == 'wait':
      msg = _parse_wait(args)
    elif name == 'screenshot':
      if len(args) != 1:
        raise ProtocolError('usage: screenshot PATH')
      msg = {'cmd': 'screenshot', 'path': args[0]}
    elif name in ('state', 'quit'):
      if args:
        raise ProtocolError('%s takes no arguments' % name)
      msg = {'cmd': name}
    else:
      raise ProtocolError('unknown command %r' % name)
  validate(msg)
  return msg


def validate(msg):
  """Raise ProtocolError unless msg is a well-formed request."""
  cmd = msg.get('cmd')
  if cmd not in COMMANDS:
    raise ProtocolError('unknown command %r' % (cmd,))
  if cmd == 'click':
    for k in ('x', 'y'):
      if not isinstance(msg.get(k), (int, float)) or isinstance(msg.get(k), bool):
        raise ProtocolError('click needs numeric %s' % k)
  elif cmd == 'key':
    if msg.get('action') not in ('down', 'up'):
      raise ProtocolError('key action must be down or up')
    if not isinstance(msg.get('name'), str) or not msg['name']:
      raise ProtocolError('key needs a name')
  elif cmd == 'wait':
    has_s, has_f = 'seconds' in msg, 'frames' in msg
    if has_s == has_f:
      raise ProtocolError('wait needs exactly one of seconds or frames')
    value = msg['seconds'] if has_s else msg['frames']
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
      raise ProtocolError('wait amount must be a non-negative number')
  elif cmd == 'screenshot':
    if not isinstance(msg.get('path'), str) or not msg['path']:
      raise ProtocolError('screenshot needs a path')
