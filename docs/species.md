# Adding a species

Each species lives in two modules of its own, and the registry lists it
in one line, so species can be added side by side without touching each
other's files:

| File | What it holds |
|---|---|
| `tankful/sim/species/<name>.py` | its behaviour: build and gait, who of it lives in the tank, and its rig's pose |
| `tools/species/<name>.py` | its model: meshes, rig and materials |
| `tankful/sim/species/__init__.py` | the registry, `NAMES`: one line per species |

`<name>` is the same in all three, and is the species' `Species.name`
(`'neon_tetra'`).  Everything else reads the registry:

- the sim: `tankful.sim.species.stock(tank)` stocks every species, in
  the order of `NAMES` (`tankful/game/main.py`);
- the game's fish driver, `tankful/game/fishes.py`, finds each fish's
  bones and pose with `species.of(fish.species)`;
- the scene builder, `build_fish` in `tools/scene_fish.py`, calls each
  `tools/species/<name>.py`'s `build(scene)`, in the same order;
- the launcher's `SCENE_SOURCES` includes both of each species' modules,
  so changing either rebuilds the scene.

So adding a species is: write its two modules, and add its line to
`NAMES`.  Add it at the end, so the fish already in the tank keep their
order: the tank steps its fish in that order, and harness runs repeat
only while it holds.

## The sim module

`tankful/sim/species/<name>.py` defines:

- `SPECIES`: a `tankful.sim.species.base.Species`, its size, speeds,
  turn limits, depth band, gait and so on (the fields are commented in
  `base.py`).
- `stock(tank)`: adds its fish to the tank and returns them.  Use the
  shared helpers:
  - a fish of its own, `tankful.sim.fish.stock(tank, residents)` with a
    list of `base.Resident`s (as `angelfish.py`);
  - a school, `tankful.sim.school.stock(tank, specs)` with a list of
    `school.SchoolSpec`s (as `neon_tetra.py`);
  - a behaviour of its own, a subclass of `tankful.sim.fish.Fish` in
    the module (as the pleco's `Pleco`, which clings to the glass).
- `BONES`: the bones of its rig, which the model builder must make.
  They start with the spine chain, `('Head',) + swim.SPINE`.
- `pose(fish)`: `{bone: (rx, ry, rz)}` for every bone in `BONES`, each
  frame.  `tankful.sim.swim.spine_pose(fish)` gives the Head and the
  swimming spine; add the fins to it.
- `scales(fish)`: `{bone: (sx, sy, sz)}` for bones that scale, usually
  `{}` (the pleco's mouth works by scaling).

Give each fish a unique object name and its own seed, and test the
module in `tests/test_<name>.py`; `tests/test_species.py` checks every
registered species has all of the above.

## The model module

`tools/species/<name>.py` runs inside UPBGE's Blender, with `tools/` on
`sys.path`, and defines `build(scene)`.  For each fish it makes:

- `<name>.Rig`: an armature with the bones of `BONES`, each with roll 0
  (see `tankful/sim/swim.py`);
- the meshes, skinned to it, with `visible_shadow` off (moving shadow
  casters cost too much, `docs/harness.md`).

A school is one armature for all its members instead, with each
member's bones prefixed `<member>:` under a `<member>:Root` bone (as
`neon_tetra.py`); the fish driver handles both kinds.

The shared helpers are in `tools/scene_fish.py`: `Shape` for a body's
profile and spine joints, `add_body` (lofting) and `add_eye`, `fin`,
`spine_weights`, `MeshBuilder`, `eye_material` and `band`; and
`tools/scene_env.py` has `new_material`, `lit_surface` and the
caustics.  Take the fish's size from the sim (`res.species.length *
res.size`) and its start from the sim module's residents.  Keep to the
frame budget in `docs/harness.md`: small fish that come in numbers go
in one object per group with plain materials.

## Checking it

Add a harness script under `tools/scripts/` that shows the new species,
and its shot under `docs/shots/`.  With the fixed timestep, the
existing scripts (`04-school.json`, `05-sucker.json`) give the same
tank as before as long as the new species stocks after the others; its
own fish may push into theirs, though, so check the shots.
