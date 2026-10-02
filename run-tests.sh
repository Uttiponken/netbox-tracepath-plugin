#!/usr/bin/env bash
# Runs the pure-Python tests in a throwaway NetBox container (no database needed).
# Usage: ./run-tests.sh [unittest args]     default image: netbox:latest-plugins-postgis
set -euo pipefail
cd "$(dirname "$0")"
IMAGE="${NETBOX_IMAGE:-netbox:latest-plugins-postgis}"
docker run --rm --entrypoint /opt/netbox/venv/bin/python -v "$PWD":/work -w /work "$IMAGE" \
  -c "import sys, unittest; sys.path.insert(0, '/opt/netbox/netbox'); unittest.main(module=None, argv=['unittest', 'discover', '-s', 'tests', '-t', '.', '-v'] + sys.argv[1:])" "$@"
