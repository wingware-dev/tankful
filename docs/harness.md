# The test harness

`tools/harness.py` starts tankful with `--harness PORT`, connects to the
game over a localhost socket, and runs a script of commands against it:
clicks, key presses, waits, screenshots and state dumps.  It is how the
game is checked the way a user sees it, without showing a window on the
user's screen or touching their mouse and keyboard.

    python tools/harness.py tools/scripts/01-skeleton.json
    python tools/harness.py SCRIPT.json --backend docker --log build/game.log

It exits 0 when every command succeeded.  Each screenshot is checked for
being non-black, and those under `docs/shots/` are `git add`ed.

## Scripts and commands

A script is a JSON list of commands, or `{"backend": ..., "commands":
[...]}`.  A command is text or the JSON object it stands for
(`tankful/harness_protocol.py` has the wire format):

| Text | Does |
|---|---|
| `click X Y [BUTTON]` | a click at window pixel X, Y (top left origin) |
| `key down NAME`, `key up NAME` | `left`, `right`, `up`, `down`, `l`, `space`, `escape`, ... |
| `wait 1.5`, `wait 1.5s` | waits game time, in seconds |
| `wait 30f`, `wait 30 frames` | waits a number of frames |
| `screenshot PATH` | saves the next frame (PATH relative to the project root) |
| `state` | returns the sim state, input state, window and scene info |
| `quit` | ends the game (added at the end if a script leaves it out) |

Commands run in order, one per frame at most for wait and screenshot, so
a script reads like a user session.  Clicks and keys go into the game's
input layer (`tankful.game.input.InputState`), the same object the real
keyboard and mouse feed, so game code cannot tell them apart and the same
script behaves the same on every OS.  Screenshots use
`bge.render.makeScreenshot`.  The game end is
`tankful/game/harness_channel.py`, polled once per frame without blocking.

## Display backends

`run_tankful.py --backend NAME` (and `harness.py --backend NAME`):

- **`offscreen`** (the harness default on macOS and Windows): a real
  player window, moved off the desktop.  The player's `-w` rejects
  negative coordinates, and macOS pulls titled windows back onto a
  screen, so the window starts at 320x200, asked for at (20000, 20000).
  On its first frame the game makes it borderless, moves it to
  (-30000, -30000), gives it its full 1280x720 size, and makes the app an
  accessory app (no Dock icon).  See `tankful/game/offscreen_macos.py`
  and `offscreen_windows.py`.
- **`xvfb`** (the harness default on Linux): the player on a private
  Xvfb display.
- **`docker`**: the Linux UPBGE build in a container
  (`tools/docker/Dockerfile`: Xvfb plus Mesa llvmpipe), running
  `run_tankful.py --backend xvfb` there with the project mounted at
  `/tankful`.  It needs `python tools/fetch_upbge.py --platform linux`
  first, and builds the image on first use.
- **`window`**: an ordinary window, for use by hand.

## Results on this Mac (2026-10-16)

Apple M2 Pro, macOS 15.7, two displays, UPBGE 0.50, Docker Desktop
29.8.  "Works" means a harness run whose screenshots show the tank,
checked by eye as well as by the non-black test.

| Backend | Result |
|---|---|
| `offscreen` (macOS) | **Works.**  1280x720 screenshots of the tank (mean brightness 87, `docs/shots/01-skeleton.png`).  The game keeps running at 60 fps with its window at (-30000, -30000), which `state` reports as `window_frames`. |
| `xvfb` (macOS) | Not applicable: the macOS player draws through Cocoa, not X11, so XQuartz's Xvfb cannot host it. |
| `docker` (linux/amd64 under Rosetta) | **Fails: the game engine segfaults on start.**  The image builds, and Blender itself works in it: its UI comes up on Xvfb, and `blender -b build/tankful.blend -f 1` renders the scene with EEVEE on llvmpipe (about 0.6 s per sample).  But `blenderplayer` segfaults right after loading its Python modules, even on Blender's factory scene, and so does the embedded engine (`view3d.game_start`).  ptrace does not work under Rosetta, so there is no backtrace past stripped addresses. |
| `xvfb` (Linux host) | Not tried: the only Linux here is the container above. |
| `offscreen` (Windows) | Not tried: no Windows machine. |

The `offscreen` backend has two known blemishes on macOS:

- While the player loads the scene, for about a second, its 320x200
  window is wherever Cocoa clamps (20000, 20000) to, presumably the edge
  of a display, until the game moves it.
- The app may take focus at launch, before it becomes an accessory app.

Neither could be checked from the sandbox this work ran in, which cannot
read the window list.

## UPBGE 0.50 quirks found on the way

- In background mode (`blender -b`), the logic brick operators crash in
  their undo push unless the undo stack already has a step:
  `tools/build_scene.py` calls `bpy.ops.ed.undo_push()` first.
- The player renders through the saved 3D viewport (as
  `__default__cam__`) unless that viewport is in camera view, whatever
  `scene.camera` says.  Setting `scene.active_camera` in game does not
  change it.  `build_scene.py` sets every 3D view to camera perspective.
- The player rejects windows smaller than its usage example's 320x200
  ("window size too small").
- The player ignores SIGTERM, so `run_tankful.py` falls back to SIGKILL
  after 5 s.
- The area light's soft shadow left the player's frames grainy, so the
  skeleton scene has it off for now.
