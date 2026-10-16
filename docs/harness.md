# The test harness

`tools/harness.py` starts tankful with `--harness PORT`, connects to the
game over a localhost socket, and runs a script of commands against it:
clicks, key presses, waits, screenshots and state dumps.  It is how the
game is checked the way a user sees it, without showing a window on the
user's screen or touching their mouse and keyboard.

    python tools/harness.py tools/scripts/02-environment.json
    python tools/harness.py SCRIPT.json --backend docker --log build/game.log

It exits 0 when every command succeeded.  Each screenshot is checked for
being non-black, and those under `docs/shots/` are `git add`ed.  The
shots there record each step as it was built, so a script for an earlier
step (such as `01-skeleton.json`) now saves under `build/shots/`
instead, and the committed shot keeps showing that step.

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
  (`tools/docker/Dockerfile`: Xvfb, Mesa llvmpipe and a PulseAudio
  server with a null sink), running `run_tankful.py --backend xvfb`
  there with the project mounted at `/tankful`.  It needs
  `python tools/fetch_upbge.py --platform linux` first, and builds the
  image on first use and again whenever the Dockerfile changes (the
  image carries the Dockerfile's sha256 as its `tankful.dockerfile`
  label).
- **`window`**: an ordinary window, for use by hand.

## Results on this Mac (2026-10-16)

Apple M2 Pro, macOS 15.7, two displays, UPBGE 0.50, Docker Desktop
29.8.  "Works" means a harness run whose screenshots show the tank,
checked by eye as well as by the non-black test.

| Backend | Result |
|---|---|
| `offscreen` (macOS) | **Works.**  1280x720 screenshots of the tank (mean brightness 87, `docs/shots/01-skeleton.png`).  The game keeps running at 60 fps with its window at (-30000, -30000), which `state` reports as `window_frames`. |
| `xvfb` (macOS) | Not applicable: the macOS player draws through Cocoa, not X11, so XQuartz's Xvfb cannot host it. |
| `docker` (linux/amd64 under Rosetta) | **Works, slowly.**  1280x720 screenshots of the tank and fish (mean brightness 90), but at about 0.7 fps, so a 60-frame wait takes over a minute and `tools/scripts/01-skeleton.json` about 2 m 40 s including startup.  Fine for checking what a scene looks like; not for anything timing-sensitive. |
| `docker` (linux/amd64 under QEMU) | **Works, much more slowly** than under Rosetta: the scene took minutes to come up.  Not wired into the launcher; see below for how it was run. |
| `xvfb` (Linux host) | Not tried: the only Linux here is the container above. |
| `offscreen` (Windows) | Not tried: no Windows machine. |

The `offscreen` backend has two known blemishes on macOS:

- While the player loads the scene, for about a second, its 320x200
  window is wherever Cocoa clamps (20000, 20000) to, presumably the edge
  of a display, until the game moves it.
- The app may take focus at launch, before it becomes an accessory app.

Neither could be checked from the sandbox this work ran in, which cannot
read the window list.

### Why the player first segfaulted in Docker

At first `blenderplayer` (and the embedded `view3d.game_start`) segfaulted
in the container right after loading its Python modules, even on the
factory scene, while Blender itself and EEVEE renders worked.  ptrace
does not work under Rosetta, so the player was run under QEMU user mode
in an arm64 container instead (`qemu-x86_64 -cpu max -L <amd64 rootfs>`,
with Xvfb native and the amd64 rootfs exported from the image), where
QEMU's gdb stub (`-g PORT`, `gdb-multiarch`) gives real backtraces.  That
turned up two crashes:

1. **No audio device**: `AUD_Device_setSpeedOfSound` dereferences a null
   device in `LA_Launcher::InitEngine`, because the container has no
   sound server and the player does not fall back to a null device.  This
   was the crash under Rosetta too.  The image now runs a PulseAudio
   server whose only sink is a null sink (`pulseaudio -D` in the
   Dockerfile's entrypoint).
2. **QEMU only: addresses above 47 bits**: QEMU hands the guest the
   arm64 host's addresses (0xffff...), which a real x86-64 process never
   sees.  The player's jemalloc packs pointers and sign-extends bit 47,
   so it crashes in `extent_try_coalesce_impl` on a pointer like
   `0xffffffff93a0a440`.  `-B 0x800000000000` (guest base) keeps guest
   addresses below 0x800000000000 and fixes it.  QEMU 8.2 (Ubuntu 24.04)
   crashed internally instead (`QEMU internal SIGSEGV`); QEMU 10.0
   (Debian trixie) gave the guest segfault above.

Docker Desktop's "Use Rosetta for x86_64/amd64 emulation" setting did not
need to change: with it on, `--platform linux/amd64` containers run under
Rosetta, which is much faster than QEMU here.  The task also listed the
latest weekly UPBGE 0.53 Linux build and a native x86_64 Linux host as
things to try; with the audio fix in place neither was needed, and
neither was tried.

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
- The player segfaults on start when it can open no audio device (see
  above).
- The player ignores SIGTERM, so `run_tankful.py` falls back to SIGKILL
  after 5 s.
- The player smooths its frames by accumulating them over time with
  reprojection (EEVEE's `use_taa_reprojection`), and that is what makes
  soft shadows clean.  The area light's soft shadow, with the default
  single shadow ray, comes out grainy; `shadow_ray_count` 2,
  `shadow_step_count` 8 and the light's `shadow_filter_radius` 4 come
  out clean at 60 fps (`build_scene.py`, `setup_render` and
  `setup_light`).  Four rays are clean too, but halve the frame rate.
  Turning reprojection off leaves every frame a single, grainy sample;
  `taa_samples` makes no visible difference in the player.
- The same accumulation keeps much of past frames, and only moving
  geometry tells it where things went.  Shading that changes on a still
  surface smears, so the caustics change slowly
  (`tankful/game/scenery.py`, `CAUSTIC_SPEED`).  Texture detail finer
  than a pixel makes this far worse: the history is clamped to each
  pixel's neighborhood, and sub-pixel speckle widens that range until
  the caustics wash out completely.  Keep textures under moving light
  coarse.  Small, fast objects such as the bubbles fade too, so they are
  bright and fairly opaque.
- Setting a shader node's value through `bpy` each frame works in the
  player, but dropped the frame rate from 60 to 45 in one test.  The scenery
  animates the light by moving an empty instead (the caustic
  projector), which costs nothing.
- Moving shadow casters are what cost.  With the two angelfish
  (step 3), the frame rate went from about 57 without fish to 49.
  Skinning the meshes to their armatures made no measurable difference.
  Their shadows cost 3-4 fps (most of it from the blended fins), and the
  caustic projection in their shaders cost about as much again.  The fish
  now cast no shadows (`tools/scene_fish.py`), which brings the
  frame rate back to 52-55.  These readings vary by about 2 fps between runs.
