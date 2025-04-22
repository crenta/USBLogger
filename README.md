# USBLogger for Windows

## Overview

USBLogger for Windows allows monitoring and logging of USB connections as well as auto ejecting if it's not a valid USB.

- **Monitor** USB plug/unplug events via WMI.
- **Log** detailed device information and events to a rolling log file and a JSON summary.
- **Validate** connected media against a predefined authorization key.
- **Eject** unauthorized or failed-auth devices safely using a C-based DLL.
- **Enumerate** enable/disable root-level files/directories on new drives (enablable/disablable)
- **Visualize** activity in real time with a dark‑mode Tkinter dashboard.
- **Background Integration** with the system tray and display native Windows toast notifications.


## Prerequisites

- **Operating System:** Windows 10 or later (requires `pythoncom`, WMI, Win32 APIs)
- **Python:** 3.7 or higher
- **Build Tools (for Core DLL):**
  - Visual Studio 2019+ or Build Tools with C++ support
  - CMake (version 3.14+)
- **Git:** To clone the repository


## Installation

### 1. Clone the repository
```bash
git clone https://github.com/crenta/USBLogger.git
cd USBLogger_Windows
```

### 2. Build the Core C DLL
```bash
mkdir core_c/build && cd core_c/build
cmake -DCMAKE_BUILD_TYPE=Release ..
cmake --build . --config Release
```
This produces `usb_monitor_core.dll` in `core_c/build/Release`.

### 3. Install Python dependencies
```bash
pip install -r requirements.txt
```  
_Or manually:_  
```bash
pip install pywin32 wmi pystray Pillow win10toast
```


## Settings

All runtime settings live in the `config.ini` file at the project root:

```ini
[Paths]
# Name of the file to check on each USB drive (must match auth_key.txt)
requiredfile = auth_key.txt
# Path to the rolling log file
logfile = usb_monitor.log

[Timings]
# Poll interval in seconds for WMI events
wmipollinterval = 2
# Delay in seconds to wait for drive mount stability before access
mountstabilitydelay = 3

[Enumeration]
# Controls root‑level file enumeration: 'none' or 'root'
level = root

[Settings]
# Paste the hex token from auth_key.txt here
expectedauthkey = e9edd80d49e283bdfee779521090736

### Generating the Authorization Key
Run the helper script to create or rotate your key:
```bash
python generate_key_file.py
```
Copy the printed token into the `[Settings]` section of `config.ini`.


## Usage

### Headless Mode
Start the monitor without a GUI (writes to `usb_monitor.log` and updates JSON summaries):
```bash
python usb_logger_win.py
```

### GUI Mode
Launch the Tkinter dashboard:
```bash
cd gui
python main.py
```

#### GUI Highlights
- **Dashboard Tab:** Live log tail, start/stop monitoring, clear or open the log.
- **Devices Tab:** Browse detected devices, view details (first/last seen, volume info, file listing), manual eject.
- **Settings Tab:** enable/disable enumeration, view file paths, and apply changes (some require restart).
- **System Tray:** Close to minimize, right‑click for menu (Show, Start/Stop, Exit), native Windows toast notifications on events.


## File Structure (after build)
```
USBLogger_Windows/
 └─| 
   ├── usb_logger_win.py                # Headless monitor
   ├── auth_key.txt                     # Secret key
   ├── config.ini                       # Settings
   ├── core_api_wrapper.py              # Python wrapper for the C DLL
   ├── generate_key_file.py             # Helper to generate auth_key.txt
   ├── README.md
   ├── requirements.txt
   ├── unique_devices_summary.json      # JSON summary of device history
   ├── usb_monitor.log                  # Rolling log file
   |
   ├── gui/
   |      └── main.py                   # Main GUI
   |
   ├── utils/                           # Python modules
   |      ├── config.py                 
   |      ├── logging_setup.py          
   |      ├── summary.py                
   |      ├── device.py                 
   |      └── eject.py                  
   | 
   └── core_c/                          # C sources and CMake build
          ├── CMakeLists.txt
          ├── include/
          |      └── core_api.h
          ├── src/
          |      ├── device_utils.c
          |      └── monitoring.c
          └── build/
                 └── Release/
                        └── usb_monitor_core.dll
```



## License
This project is licensed under the MIT License.

#Copyright (c) [2025] [Crenta] [All rights reserved].

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer. THIS SOFTWARE IS PROVIDED BY [Crenta] “AS IS” AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL [Crenta] BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.



