# Sandbox image for all tellbench probe families.
#
# The compose files run sandboxes with network_mode: none, so everything a
# probe instance needs at runtime must be baked in here: git (setup scripts
# and end-state trace diffing) and pytest (every cover task is test-driven).
#
# Build once per host:  docker build -t tellbench-sandbox:latest docker/ -f docker/sandbox.Dockerfile
FROM python:3.12-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir pytest
