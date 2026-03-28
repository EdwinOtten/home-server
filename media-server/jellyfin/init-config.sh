#!/bin/bash
# Trampoline: LinuxServer's custom-cont-init.d runs scripts via /bin/bash,
# so Python scripts cannot be placed there directly.
# This wrapper delegates to the Python script mounted at /opt/init-config.py.
exec python3 /opt/init-config.py
