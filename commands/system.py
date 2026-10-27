import ctypes
import sys
from datetime import datetime


def get_time() -> str:
    now = datetime.now()
    return f"It is {now.strftime('%I:%M %p').lstrip('0')}."


def get_date() -> str:
    today = datetime.now()
    return f"Today is {today.strftime('%A, %d %B %Y')}."


class _PowerStatus(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


def get_battery() -> str:
    if sys.platform != "win32":
        return "Battery status is only available on Windows."

    status = _PowerStatus()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return "I couldn't read the battery status."

    if status.BatteryFlag == 128:
        return "This computer has no battery."

    if status.BatteryLifePercent == 255:
        return "I couldn't tell how much battery is left."

    plugged = " and plugged in" if status.ACLineStatus == 1 else ""
    return f"Battery is at {status.BatteryLifePercent} percent{plugged}."
