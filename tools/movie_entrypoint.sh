#!/bin/sh
set -eu
exec xvfb-run -a -s "-screen 0 1280x1024x24" python /opt/citrackastra/wrapper.py "$@"
