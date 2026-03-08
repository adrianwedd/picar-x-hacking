"""Monkey-patch os.getlogin() for systemd environments.

picarx.py calls os.getlogin() in Picarx.__init__() for fileDB ownership.
Under systemd there is no /dev/tty or utmp entry, so os.getlogin() raises
OSError: [Errno 6] No such device or address.

Import this module (or set PYTHONSTARTUP to point here) before importing
picarx to avoid the error.
"""
import os as _os

_original_getlogin = _os.getlogin


def _safe_getlogin():
    try:
        return _original_getlogin()
    except OSError:
        return _os.environ.get("LOGNAME", _os.environ.get("USER", "pi"))


_os.getlogin = _safe_getlogin
