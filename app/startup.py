"""Manage the current Windows user's optional logon entry."""
from pathlib import Path
import subprocess
import sys

_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAME = "SubtitleForEveryone"


def enabled():
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY) as key:
            return bool(winreg.QueryValueEx(key, _NAME)[0])
    except FileNotFoundError:
        return False


def set_enabled(value):
    import winreg

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _KEY, 0, winreg.KEY_SET_VALUE) as key:
        if value:
            command = [sys.executable]
            if not getattr(sys, "frozen", False):
                executable = Path(sys.executable)
                windowless = executable.with_name("pythonw.exe")
                command = [str(windowless if windowless.is_file() else executable),
                           str(Path(__file__).resolve().parents[1] / "launch.py")]
            winreg.SetValueEx(key, _NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(command))
        else:
            try:
                winreg.DeleteValue(key, _NAME)
            except FileNotFoundError:
                pass
