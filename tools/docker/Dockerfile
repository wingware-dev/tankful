# Headless Linux host for the UPBGE player: Xvfb plus Mesa's llvmpipe
# software OpenGL, and a PulseAudio server with only a null sink, since
# the player segfaults on start when it can open no audio device.  The
# project (with vendor/upbge/linux/ from "tools/fetch_upbge.py --platform
# linux") is mounted at /tankful, so the image holds only system
# libraries.  run_tankful.py --backend docker
# builds it on first use and whenever this file changes, for linux/amd64
# (emulated on Apple Silicon); see docs/harness.md.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 xvfb xauth \
      libgl1 libegl1 libglx-mesa0 libgl1-mesa-dri libgles2 \
      libx11-6 libx11-xcb1 libxext6 libxi6 libxxf86vm1 libxfixes3 \
      libxrender1 libxrandr2 libxinerama1 libxcursor1 libxkbcommon0 \
      libxkbcommon-x11-0 libsm6 libice6 libxcb1 libdbus-1-3 \
      libfontconfig1 libfreetype6 libwayland-client0 libwayland-cursor0 \
      libwayland-egl1 libdecor-0-0 libasound2t64 libpulse0 libtbb12 \
      pulseaudio \
    && rm -rf /var/lib/apt/lists/*

# Force software rendering whatever the host offers
ENV LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe

# Start the null-sink sound server, then run the command
ENTRYPOINT ["sh", "-c", "pulseaudio -D --exit-idle-time=-1 --log-level=error && exec \"$@\"", "tankful-entry"]
