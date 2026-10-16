"""Move the player window off the desktop on Windows via user32.

The player's -w option takes no negative coordinates, so the window is
found among this process's top-level windows, made a borderless popup
and moved far outside the virtual desktop.  Untested so far: see
docs/harness.md.
"""

import ctypes
import logging
from ctypes import wintypes

log = logging.getLogger('tankful.offscreen')

GWL_STYLE = -16
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020


def _process_windows():
  user32 = ctypes.windll.user32
  pid = ctypes.windll.kernel32.GetCurrentProcessId()
  found = []
  proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

  def visit(hwnd, _):
    owner = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
    if owner.value == pid and user32.IsWindowVisible(hwnd):
      found.append(hwnd)
    return True
  user32.EnumWindows(proc_type(visit), 0)
  return found


def window_frames():
  frames = []
  for hwnd in _process_windows():
    r = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
    frames.append([r.left, r.top, r.right - r.left, r.bottom - r.top])
  return frames


def hide_offscreen(size=None, x=-30000, y=-30000):
  """Make each window a borderless popup at (x, y), of size (w, h)
  pixels if given; return the frames."""
  user32 = ctypes.windll.user32
  user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
  flags = SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
  if not size:
    flags |= SWP_NOSIZE
  w, h = size or (0, 0)
  for hwnd in _process_windows():
    user32.SetWindowLongW(hwnd, GWL_STYLE,
                          ctypes.c_long(WS_POPUP | WS_VISIBLE).value)
    user32.SetWindowPos(hwnd, 0, x, y, w, h, flags)
  frames = window_frames()
  log.info('moved player window off screen: %s', frames)
  return frames
