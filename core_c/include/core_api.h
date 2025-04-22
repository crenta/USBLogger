// Internal headers defining structures or helper functions used only within the C code.
#include <windows.h> // Needed for BOOL, LPCWSTR etc.




#ifndef CORE_API_H
#define CORE_API_H

#ifdef __cplusplus
extern "C" {
#endif

// function to initialize the monitoring engine
__declspec(dllexport) int initialize_monitor(void);

// Function to eject a drive based on its volume path (e.g., "\\.\E:")
__declspec(dllexport) BOOL EjectVolumeByPath(LPCWSTR volumePath);


#ifdef __cplusplus
}
#endif

#endif
