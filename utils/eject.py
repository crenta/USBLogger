import ctypes
import logging
import datetime
from .config import SCRIPT_DIR
import os

# --- load the DLL once at import time ---
dll_path = os.path.join(SCRIPT_DIR, "core_c", "build", "Release", "usb_monitor_core.dll")
try:
    core_dll = ctypes.CDLL(dll_path)
    core_dll.EjectVolumeByPath.argtypes = [ctypes.c_wchar_p]
    core_dll.EjectVolumeByPath.restype  = ctypes.c_bool
except Exception as e:
    logging.error(f"Failed to load core DLL for eject: {e}")
    core_dll = None

def eject_drive_api(drive_letter: str,
                    device_id: str,
                    unique_devices_summary: dict,
                    processed_volumes: dict) -> bool:
    """
    Safely ejects the volume via C DLL and updates the two dicts.
    Returns True if ejected successfully.
    """
    logging.info(f"Attempting safe eject for {drive_letter} ({device_id}) via C DLL")
    processed_volumes[device_id] = 'ejecting'
    volume_path = f"\\\\.\\{drive_letter}"
    logging.debug(f"Calling C function EjectVolumeByPath with path: {volume_path}")

    success = False
    if core_dll:
        try:
            success = core_dll.EjectVolumeByPath(volume_path)
        except Exception as dll_e:
            logging.error(f"Error calling C DLL EjectVolumeByPath: {dll_e}", exc_info=True)
    else:
        logging.error("Cannot eject: Core C DLL not loaded.")

    outcome = 'ejected' if success else 'failed_eject_dll'
    now_iso = datetime.datetime.now().isoformat()

    # update summary
    entry = unique_devices_summary.get(device_id)
    if entry is not None:
        entry.update({
            'last_state': outcome,
            'last_seen': now_iso
        })
        key = 'total_eject_success' if success else 'total_eject_failure'
        entry[key] = entry.get(key, 0) + 1
        logging.debug(f"[Summary] Updated entry for {device_id}: {entry}")
    else:
        logging.warning(f"[Summary] No entry to update for {device_id}")

    # update transient state
    processed_volumes[device_id] = outcome
    if success:
        logging.info(f"Successfully ejected {drive_letter} via C DLL.")
    else:
        err = ctypes.windll.kernel32.GetLastError() if core_dll else "N/A"
        logging.error(f"C eject failed for {volume_path}. WinAPI LastError={err}")

    return success
