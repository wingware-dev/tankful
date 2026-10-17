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
instead, and the committed shot keeps showing that step.  With the
fixed timestep (below), such a shot can be retaken exactly by running
its script at the commit that ended its step, with `docs/shots/` put
back in it: `docs/shots/04-school.png` is `04-school.json` at 1f3c71a.

## Scripts and commands

A script is a JSON list of commands, or `{"backend": ..., "commands":
[...]}`.  A command is text or the JSON object it stands for
(`tankful/harness_protocol.py` has the wire format):

| Text | Does |
|---|---|
| `click X Y [BUTTON]` | a click at window pixel X, Y (top left origin) |
| `key down NAME`, `key up NAME` | `left`, `right`, `up`, `down`, `l`, `space`, `escape`, ... |
| `wait 1.5`, `wait 1.5s` | waits game time, in seconds (90 frames at the fixed step) |
| `wait 30f`, `wait 30 frames` | waits a number of frames |
| `screenshot PATH` | saves the next frame (PATH relative to the project root) |
| `state` | returns the sim state, input state, window and scene info, the frame rate (`fps`) and the player's frame time by category in ms (`profile`) |
| `quit` | ends the game (added at the end if a script leaves it out) |

Commands run in order, one per frame at most for wait and screenshot, so
a script reads like a user session.  Clicks and keys go into the game's
input layer (`tankful.game.input.InputState`), the same object the real
keyboard and mouse feed, so game code cannot tell them apart and the same
script behaves the same on every OS.  Screenshots use
`bge.render.makeScreenshot`.  The game end is
`tankful/game/harness_channel.py`, polled once per frame without blocking.

## Fixed timestep

Under `--harness` the sim does not step with real frame time, which
would make each run differ.  It steps a fixed 1/60 s per frame
(`HARNESS_DT` in `tankful/game/main.py`), and only on frames where a
`wait` runs; the rest of the time it holds still, though the game keeps
drawing.  So a script's waits alone set the game time: `wait 1.5` is
exactly 90 steps, `wait 30f` 30 steps, and the frames spent starting
up, connecting and going between commands (each command waits for the
last one's reply) add none.  The same script then gives the same sim
state, and a screenshot or `state` sees the tank exactly as the waits
before it left it: `tank.time` is the sum of the waits.

Two consequences:

- Game time no longer follows the clock.  Where the game runs below
  60 fps, as in the docker backend, `wait 10` takes longer than 10 s
  (about 160 s at 3.8 fps).
- Clicks and keys reach the game on the frame they arrive, but the sim
  only moves during a wait, so follow them with one (`key down left`,
  `wait 1`, `key up left`).

What the sim does not decide still varies a little between runs: the
renderer's accumulation of past frames (see the quirks below) depends
on how many frames were drawn, so screenshots repeat in composition,
not to the pixel.

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
  label).  Mesa's shader cache is kept in `build/docker-cache/mesa/`,
  so only the first run after a shader change compiles EEVEE's shaders
  on llvmpipe (about a minute); delete that directory to start cold.
- **`window`**: an ordinary window, for use by hand.

`TANKFUL_WINDOW=WIDTHxHEIGHT` (at least 320x200) changes the window
size from 1280x720 for every backend, and the docker backend passes it
into the container.  Screenshots come out at that size, and `click`
coordinates are pixels of that window, so scripts written for 1280x720
click elsewhere.  For docker runs, `TANKFUL_WINDOW=640x360` renders
about 2.7 times faster:

    TANKFUL_WINDOW=640x360 python tools/harness.py SCRIPT.json --backend docker

## Results on this Mac (2026-10-16)

Apple M2 Pro, macOS 15.7, two displays, UPBGE 0.50, Docker Desktop
29.8.  "Works" means a harness run whose screenshots show the tank,
checked by eye as well as by the non-black test.

| Backend | Result |
|---|---|
| `offscreen` (macOS) | **Works.**  1280x720 screenshots of the tank (mean brightness 87, `docs/shots/01-skeleton.png`).  The game keeps running at 60 fps with its window at (-30000, -30000), which `state` reports as `window_frames`. |
| `xvfb` (macOS) | Not applicable: the macOS player draws through Cocoa, not X11, so XQuartz's Xvfb cannot host it. |
| `docker` (linux/amd64 under Rosetta) | **Works, slowly.**  1280x720 screenshots of the tank and fish (mean brightness 90).  With a warm shader cache, startup takes about 8 s and the game runs at 3.8 fps (10.4 fps at `TANKFUL_WINDOW=640x360`), so `tools/scripts/01-skeleton.json` takes 31 s (15 s at 640x360).  A cold shader cache adds about a minute to startup.  Fine for checking what a scene looks like; not for anything timing-sensitive.  llvmpipe already uses all 12 of the Docker VM's CPUs: `LP_NUM_THREADS=16` is no faster, and 4 threads halve the frame rate. |
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
  now cast no shadows (`tools/species/angelfish.py`), which brings the
  frame rate back to 52-55.  These readings vary by about 2 fps between runs.
- Every object that moves costs time of its own, shadow or not:
  fifteen neon tetras built as separate rigs (an armature with a body
  and a fin mesh each, 45 moving objects) took the frame rate from
  about 53 to 45, and still about 47 with no skinning at all, or with
  the light's shadows off.  Built as one armature for the whole school,
  each member's bones under a Root bone that the game places and turns
  (`tools/species/neon_tetra.py`, `tankful/game/fishes.py`), they cost about
  2 fps.  UPBGE's `use_gpu_deform` on the Armature modifier made no
  measurable difference either way; it is on.
- The player re-evaluates an armature's pose only when its object has
  moved that frame: setting bone channels and calling `update()` on a
  rig that stays put leaves it frozen in its first pose.  `fishes.py`
  sets the school rig's `worldPosition` (to where it already is) each
  frame.
- Blended surfaces get no motion vectors, so the frame accumulation
  reprojects a moving blended fin with whatever is behind it and
  clamps the result: fins with dark bars break up into blocks and
  speckle along the bars.  Taking the fins out of the shadowed light
  (light linking, with a shadowless twin light for them) made no
  difference; dithered transparency was grainier still and cost about
  4 fps.  Drawing the angelfish's dorsal, anal and caudal fins opaque
  (dithered, so only their faded outer edge is see-through), with their
  color blended toward the water's where they would be clear, makes
  them clean (`fin_material` in `tools/species/angelfish.py`).  Only nearly
  clear fins with no detail, the angelfish's pectorals and the tetras'
  fins, stay blended.
- The caustic projection on the fins cost about 3 fps for the two
  angelfish, so fins have none.  That was most likely the cost of
  reading the moving projector's space, not of the moving pattern (see
  "Frame budget").
- A bone's scale animates in the player (`channel.scale`), as its
  rotation does: the pleco's sucker disc and jaws work that way
  (`tankful.sim.species.pleco.scales`).
- A pleco on the front glass shows the viewer its belly, which the lamp
  above the tank barely lights: its materials glow faintly with their
  own color (`FILL` in `tools/species/pleco.py`), or it is a dark
  silhouette.

## Frame budget

The game should hold 48 fps or better on this Mac (M2 Pro) with every
fish in.  Measure with a script of waits and `state` commands; take the
later readings, since `fps` is a running average that starts low:

    {"commands": ["wait 120f", "wait 4", "state", "wait 4", "state", "quit"]}

| Tank (2026-10-16) | fps | Logic / Depsgraph / Rasterizer (ms) |
|---|---|---|
| Two angelfish (step 3) | 52-54 | |
| Plus 15 tetras as 45 separate objects | 44-46 | 1.7 / 3.5 / 18.0 |
| Plus 15 tetras as one school object | 48-52 | |
| The same, with opaque angelfish fins and no caustics on fins | 53-56 | 1.9 / 2.7 / 13.0 |
| Plus the pleco (step 5) | 50-53 | 2.0 / 3.0 / 14.0 |
| The step 4 tank again, measured alongside, for comparison | 51-55 | 1.9 / 2.7 / 14.1 |

The pleco costs about 1 fps, within the readings' spread.  The Mac ran
slower for these last two rows than for the earlier ones, and single
readings on both dipped as low as 30-44 fps; repeat a run before
trusting one low reading.

With all seven species in (35 fish), the tank fell to 37-42 fps.  On a
quiet machine, with each species taken out in turn (a project copy
without its `tools/species/<name>.py`), two runs of three readings each:

| Tank (2026-10-16, all seven species) | fps | Logic / Depsgraph / Rasterizer (ms) |
|---|---|---|
| No fish at all | 52-57 | 0.4 / 1.7 / 10.3 |
| The step 5 tank again | 54-55 | 2.0 / 2.6 / 13.3 |
| Every species | 37-42 | 3.7 / 3.5 / 17.4 |
| Without the angelfish (2) | 45-48 | 3.4 / 3.1 / 14.6 |
| Without the neon tetras (15) | 45-48 | 1.7 / 2.9 / 16.6 |
| Without the honey gouramis (2) | 44-49 | 3.3 / 3.1 / 14.6 |
| Without the corydoras (5) | 42-44 | 3.5 / 3.1 / 16.4 |
| Without the guppies (6) | 42-43 | 3.0 / 3.3 / 16.9 |
| Without the cherry shrimp (5) | 41-43 | 3.2 / 3.3 / 16.9 |
| Without the pleco | 40-41 | 3.6 / 3.3 / 17.4 |
| Every species, fish bodies off the projector (below) | 47-51 | 3.7 / 3.2 / 13.0 |
| For comparison: every species, the projector held still | 54-59 | 3.8 / 3.4 / 3.7 |
| Every species, the scenery off the projector too, but the god rays | 55-57 | 3.8 / 3.8 / 4.8 |
| Every species, nothing reading the projector (now) | 54-57 | 3.8 / 3.9 / 4.2 |
| The same again, measured alongside the next row | 55-56 | 3.8 / 3.6 / 4.1 |
| Every species, the sim's neighbor checks trimmed (now, below) | 55-56 | 3.2 / 3.8 / 4.3 |
| The same again, measured alongside the next row | 54-57 | 3.1 / 4.0 / 4.1 |
| Every species, with blob shadows under the fish (now, below) | 52-56 | 3.4 / 4.3 / 4.3 |

So the angelfish and the gouramis cost the most: about 2.5 ms of
`Rasterizer` per pair, all of it from the caustic projection on their
bodies (with it taken off, the full tank ran 48-51 fps; making the
gouramis' pectorals opaque, or giving both gouramis one set of
materials, changed nothing).  The cost is not the pattern's shading:
3D Voronoi and noise instead of 4D made no difference.  It is that their
materials read the space of the CausticProjector, which the game moves
every frame: an object whose material reads a moving object's space is
redrawn at a cost each frame, about 1 ms for each fish body, and the
scenery's caustics (sand, rocks, plants, water and god rays), which read
it the same way, cost about 13 ms of the frame between them (the last
row).  Every material that shows the caustics, the shimmer or the god
rays' flicker now reads the projector's place from its object's color
instead, through the `ProjectorSpace` node group
(`projector_space_group` in `tools/scene_env.py`), and
`tankful.game.scenery` sets that color on each such object as it moves
the projector (`caustic_followers`, 28 objects): the same pattern,
rendered side by side to within 1/255, and screenshots of the sand,
water surface and god rays match the old ones while moving as much
between frames.  That took `Rasterizer` from about 13 ms to 4.2 ms
(the last two rows); setting the color on static objects costs nothing
measurable.  The tetras' 2 ms is in `Logic`, the sim's step and
the game's posing of the fish, which grew from about 2 ms at step 5 to
3.7 ms with all 35 fish.  The pleco, the corydoras,
the guppies and the shrimp cost 0-2 fps each, near the readings' spread.

Timed inside the game, `Logic` with every species was the sim's step
(3.0 ms), the scenery (0.35 ms) and the posing (`tankful.game.fishes`,
0.25 ms for all 35 fish).  The tetras cost the most of the step because
each fish checked every other fish twice a step, in `_mind_others` and
`_keep_apart` (`tankful.sim.fish`), working out each one's distance:
35 fish make about 2400 such checks a step, against 800 without the
15 tetras, and each tetra checks its schoolmates a third time for the
boids rules.  Fish of other kinds a separation (or a gap) or more apart
along any one axis are now passed over before anything else is worked
out, and `vec.length`, `vec.normalized` and `vec.closest_on_segment`
(which the decor checks call about 650 times a step) are written out
instead of calling the smaller helpers: the step went from 3.0 to 2.5 ms
in the game, and `Logic` from 3.8 to 3.2 ms (the last two rows).  The
sim moves exactly as before: every fish's place, heading and speed after
3000 steps of the full tank are the same to the last bit.  Without the
tetras the step takes about 40% of what it does with them, still the
pairwise checks and each tetra's decor checks.

The fish's blob shadows (the last two rows, `docs/shots/08-shadows.png`)
are two soft blended discs per fish on the sand under it, a dark core
and a fainter halo, all 70 on the bones of one armature
(`FishShadows.Rig`) and in one mesh (`build_shadows` in
`tools/scene_fish.py`); each frame `tankful.game.fishes.shadow_pose`
lays them on the sand's slope under their fish and scales them, the
core shrinking away and the halo spreading, then shrinking, as the fish
rises.  Their material reads nothing but its UVs.  Measured in eight
alternating pairs of runs, with and without them, from two project
copies outside the working copy (another task's harness runs at the
same time pulled both down to 30 fps at times; those readings are left
out), they cost about 0.3 ms of `Logic` (placing them), 0.25 ms of
`Depsgraph` (the armature's 70 bones) and 0.2 ms of `Rasterizer`, about
1 fps, within the readings' spread.

So for more fish:

- Small fish that come in numbers go in one object per group, as the
  school does.  A fish with its own rig costs about 0.4 fps.
- Small fish get a plain material: no caustic projection and no thin
  film (`tools/species/neon_tetra.py`).
- Caustics come only through the `CausticProjection` group (or
  `ProjectorSpace`), and no material reads another object's space (a
  Texture Coordinate node's Object) while that object moves: it cost
  0.4-1 ms of the frame for each object reading it.
- No fish casts a shadow: each has a blob shadow on one shared rig and
  mesh (`build_shadows`), which a new species gets with no work.
- The sim's step for 17 fish takes about 1 ms (`Logic`), and for all 35
  about 2.5 ms (`Logic` 3.2 ms); each fish checks every other one, so
  that grows with the square of the fish, but it passes over fish of
  other kinds far off on any axis.  It checks the decor only near each
  fish, and school members' bodies only against near neighbors.
