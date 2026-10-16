#!/bin/sh
set -eu
cd /home/pete-dev/flux-studio
exec /usr/bin/flock -n .process.lock .venv/bin/python deploy/launch.py >> server.log 2>&1
