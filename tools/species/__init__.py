"""The model builders, one per species (tankful.sim.species.NAMES).

Each tools/species/<name>.py has build(scene), which tools/scene_fish.py
calls in the registry's order to add that species' fish to the scene.
They run inside UPBGE's Blender, with tools/ on sys.path, so they import
the shared helpers as scene_fish and scene_env.
"""
