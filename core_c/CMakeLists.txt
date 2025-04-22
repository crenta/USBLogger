cmake_minimum_required(VERSION 3.10)
project(usb_monitor_core)

set(CMAKE_C_STANDARD 99)

include_directories(include)

# Create a shared library (DLL on Windows)
add_library(usb_monitor_core SHARED src/monitoring.c src/device_utils.c)

# define a macro so that functions are properly exported.
target_compile_definitions(usb_monitor_core PRIVATE USB_MONITOR_CORE_EXPORTS)
