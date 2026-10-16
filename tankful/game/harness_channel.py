"""In-game end of the test harness: a localhost socket taking commands.

Started when the game runs with --harness PORT (run_tankful.py passes
it on as TANKFUL_HARNESS_PORT).  The channel is polled once per frame
from the game loop and never blocks it: one client at a time, commands
run in order, and wait / screenshot hold the queue until they finish.
See tankful.harness_protocol for the commands.

CommandProcessor holds all the logic and knows nothing of sockets or
bge, so tests drive it directly; HarnessChannel adds the socket.
"""

import errno
import logging
import os
import socket
import time

from tankful import harness_protocol as proto

log = logging.getLogger('tankful.harness')

SCREENSHOT_TIMEOUT = 15.0


class CommandProcessor:
  """Runs harness commands against the game, one frame at a time.

  input_state: a tankful.game.input.InputState to inject events into
  screenshot(abs_path): asks the engine to save the next frame
  get_state(): returns a JSON-able dict
  request_quit(): ends the game
  root: directory relative screenshot paths are resolved against
  """

  def __init__(self, input_state, screenshot, get_state, request_quit,
               root, clock=time.monotonic, file_size=None):
    self.input = input_state
    self._screenshot = screenshot
    self._get_state = get_state
    self._request_quit = request_quit
    self.root = root
    self._clock = clock
    self._file_size = file_size or _file_size
    self._queue = []
    self._busy = None     # (msg, until-test) for wait / screenshot
    self.frame = 0
    self.quitting = False
    self._quit_requested = False

  def submit(self, msg):
    self._queue.append(msg)

  def tick(self):
    """Advance one frame; return the responses that are now ready."""
    self.frame += 1
    out = []
    while True:
      if self._busy is not None:
        msg, done = self._busy
        result = done()
        if result is None:
          break
        self._busy = None
        out.append(_reply(msg, **result))
        continue
      if not self._queue or self.quitting:
        break
      msg = self._queue.pop(0)
      try:
        proto.validate(msg)
        result = self._start(msg)
      except proto.ProtocolError as exc:
        out.append(_reply(msg, ok=False, error=str(exc)))
        continue
      if callable(result):
        self._busy = (msg, result)
      else:
        out.append(_reply(msg, **result))
    return out

  def _start(self, msg):
    """Start msg; return a result dict, or a callable to poll each frame
    that returns None until done and then the result dict."""
    cmd = msg['cmd']
    if cmd == 'click':
      self.input.click(msg['x'], msg['y'], msg.get('button', 'left'))
      return {'ok': True}
    if cmd == 'key':
      if msg['action'] == 'down':
        self.input.key_down(msg['name'])
      else:
        self.input.key_up(msg['name'])
      return {'ok': True}
    if cmd == 'wait':
      if 'frames' in msg:
        end = self.frame + int(msg['frames'])
        return lambda: {'ok': True} if self.frame >= end else None
      end = self._clock() + float(msg['seconds'])
      return lambda: {'ok': True} if self._clock() >= end else None
    if cmd == 'screenshot':
      return self._start_screenshot(msg['path'])
    if cmd == 'state':
      return {'ok': True, 'state': self._get_state()}
    if cmd == 'quit':
      self.quitting = True
      return {'ok': True}
    raise proto.ProtocolError('unknown command %r' % cmd)

  def _start_screenshot(self, path):
    full = path if os.path.isabs(path) else os.path.join(self.root, path)
    full = os.path.normpath(full)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    if self._file_size(full) is not None:
      os.remove(full)
    self._screenshot(full)
    deadline = self._clock() + SCREENSHOT_TIMEOUT
    last = [None]

    def done():
      # The engine writes the file after the frame is drawn, perhaps over
      # several frames: done when it exists and its size holds steady.
      size = self._file_size(full)
      if size and size == last[0]:
        return {'ok': True, 'path': path, 'bytes': size}
      last[0] = size
      if self._clock() > deadline:
        return {'ok': False, 'path': path,
                'error': 'screenshot not written within %gs' % SCREENSHOT_TIMEOUT}
      return None
    return done

  def finish(self):
    """Call after the responses from tick() are sent; quits (once) if
    asked."""
    if self.quitting and not self._quit_requested:
      self._quit_requested = True
      self._request_quit()


def _file_size(path):
  try:
    return os.path.getsize(path)
  except OSError:
    return None


def _reply(msg, **fields):
  out = {'id': msg.get('id') if isinstance(msg, dict) else None}
  out.update(fields)
  return out


class HarnessChannel:
  """Non-blocking localhost server feeding a CommandProcessor."""

  def __init__(self, processor, port, host='127.0.0.1', listener=None):
    self.processor = processor
    if listener is None:
      listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
      listener.bind((host, port))
      listener.listen(1)
    listener.setblocking(False)
    self._listener = listener
    self._client = None
    self._buffer = proto.LineBuffer()
    self._outgoing = b''

  def poll(self):
    """Call once per frame, before game logic reads input."""
    self._accept()
    self._read()
    for resp in self.processor.tick():
      self._outgoing += proto.encode(resp)
    self._flush()
    if self.processor.quitting and not self._outgoing:
      self.processor.finish()

  def _accept(self):
    if self._client is not None:
      return
    try:
      conn, addr = self._listener.accept()
    except (BlockingIOError, InterruptedError):
      return
    conn.setblocking(False)
    self._client = conn
    self._buffer = proto.LineBuffer()
    log.info('harness client connected from %s', addr)

  def _read(self):
    if self._client is None:
      return
    while True:
      try:
        data = self._client.recv(65536)
      except (BlockingIOError, InterruptedError):
        return
      except OSError as exc:
        log.warning('harness client error: %s', exc)
        self._drop()
        return
      if not data:
        self._drop()
        return
      for line in self._buffer.feed(data):
        try:
          self.processor.submit(proto.decode(line))
        except proto.ProtocolError as exc:
          self._outgoing += proto.encode({'id': None, 'ok': False,
                                          'error': str(exc)})

  def _flush(self):
    while self._outgoing and self._client is not None:
      try:
        sent = self._client.send(self._outgoing)
      except (BlockingIOError, InterruptedError):
        return
      except OSError as exc:
        if exc.errno not in (errno.EPIPE, errno.ECONNRESET):
          log.warning('harness send failed: %s', exc)
        self._drop()
        return
      self._outgoing = self._outgoing[sent:]

  def _drop(self):
    log.info('harness client disconnected')
    try:
      self._client.close()
    except OSError as exc:
      log.warning('closing harness client: %s', exc)
    self._client = None
    self._outgoing = b''

  def close(self):
    if self._client is not None:
      self._drop()
    self._listener.close()
