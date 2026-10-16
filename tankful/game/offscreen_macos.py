"""Move the player window off the desktop on macOS, via ctypes and the
Objective-C runtime (no pyobjc in UPBGE's Python).

Cocoa keeps titled windows on a screen however far away -w places them,
so the window is first made borderless, which Cocoa leaves where it is
put.  The app also becomes an accessory app: no Dock icon, and it does
not take focus from the user.  See docs/harness.md for the results.
"""

import ctypes
import ctypes.util
import logging

log = logging.getLogger('tankful.offscreen')

NS_BORDERLESS = 0
NS_ACTIVATION_ACCESSORY = 1


class NSPoint(ctypes.Structure):
  _fields_ = [('x', ctypes.c_double), ('y', ctypes.c_double)]


class NSRect(ctypes.Structure):
  _fields_ = [('x', ctypes.c_double), ('y', ctypes.c_double),
              ('w', ctypes.c_double), ('h', ctypes.c_double)]


_objc = None


def _runtime():
  global _objc
  if _objc is None:
    ctypes.cdll.LoadLibrary(ctypes.util.find_library('AppKit'))
    objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library('objc'))
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    _objc = objc
  return _objc


def _send(obj, selector, restype=ctypes.c_void_p, argtypes=(), *args):
  """objc_msgSend with the given signature (arm64 and x86_64 both pass
  these small all-double structs in registers, so no _stret variant)."""
  objc = _runtime()
  fn = ctypes.cast(objc.objc_msgSend,
                   ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p,
                                    *argtypes))
  return fn(obj, objc.sel_registerName(selector.encode()), *args)


def _app():
  return _send(_runtime().objc_getClass(b'NSApplication'), 'sharedApplication')


def _windows():
  arr = _send(_app(), 'windows')
  count = _send(arr, 'count', ctypes.c_ulong)
  return [_send(arr, 'objectAtIndex:', ctypes.c_void_p, (ctypes.c_ulong,), i)
          for i in range(count)]


def window_frames():
  """Each app window's frame as [x, y, w, h] in screen points (Cocoa's
  origin is the bottom left of the main display)."""
  frames = []
  for win in _windows():
    r = _send(win, 'frame', NSRect)
    frames.append([r.x, r.y, r.w, r.h])
  return frames


def hide_offscreen(size=None, x=-30000.0, y=-30000.0):
  """Make each window borderless and move it to (x, y); return frames.

  size, if given, is the (width, height) to give it, in pixels: the
  launcher starts the window tiny so that it hardly shows wherever Cocoa
  puts it before this runs.
  """
  _send(_app(), 'setActivationPolicy:', ctypes.c_bool, (ctypes.c_long,),
        NS_ACTIVATION_ACCESSORY)
  for win in _windows():
    _send(win, 'setStyleMask:', None, (ctypes.c_ulong,), NS_BORDERLESS)
    if size:
      scale = _send(win, 'backingScaleFactor', ctypes.c_double) or 1.0
      rect = NSRect(x, y, size[0] / scale, size[1] / scale)
      _send(win, 'setFrame:display:', None, (NSRect, ctypes.c_bool), rect,
            True)
    else:
      _send(win, 'setFrameOrigin:', None, (NSPoint,), NSPoint(x, y))
  frames = window_frames()
  log.info('moved player window off screen: %s', frames)
  return frames
