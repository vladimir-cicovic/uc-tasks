#!/bin/sh
# Reset the lab target: remove the fixes and the test service, clear the
# logs and start nginx again with a low limit.
# Usage: ./reset-lab.sh [-e lab_nofile=64]
set -eu
cd "$(dirname "$0")"
exec ansible-playbook test/reset-lab.yml "$@"
