"""Killable model-call subprocess; never prints credentials or upstream errors."""

import json
import sys
import os
import signal
import ctypes

# Linux: do not leave inference requests orphaned after a hard platform crash.
parent = int(os.getenv("FORGE_PARENT_PID", str(os.getppid())))
ctypes.CDLL(None).prctl(1, signal.SIGKILL)
if os.getppid() != parent:
    sys.exit(1)
from .providers import provider

try:
    request = json.load(sys.stdin)
    result = provider(request["provider"]).call(
        request["role"], request["objective"], request["context"]
    )
    sys.stdout.write(json.dumps(result))
except Exception as exc:
    sys.stderr.write(type(exc).__name__)
    sys.exit(1)
