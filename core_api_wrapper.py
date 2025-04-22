import os
import ctypes
from ctypes import c_int

# Construct the relative path to the DLL, assuming core_api_wrapper.py is inside USBLogger_Windows
dll_path = os.path.join(
    os.path.dirname(__file__),
    "core_c", "build", "Release", "usb_monitor_core.dll"
)

# Print the absolute path to verify it's correct.
abs_dll_path = os.path.abspath(dll_path)
print("Looking for DLL at:", abs_dll_path)

try:
    core_dll = ctypes.CDLL(dll_path)
    print("DLL loaded successfully.")
except Exception as e:
    print("Failed to load usb_monitor_core.dll:", e)
    core_dll = None

def initialize_monitor():
    if core_dll is not None:
        # Set the expected argument and return types for the C function.
        core_dll.initialize_monitor.argtypes = []  
        core_dll.initialize_monitor.restype = c_int
        result = core_dll.initialize_monitor()
        return result
    else:
        return -1

if __name__ == "__main__":
    status = initialize_monitor()
    if status == 0:
        print("Monitor initialized successfully via DLL!")
    else:
        print("Monitor initialization failed with code:", status)
