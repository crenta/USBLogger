#include "core_api.h"
#include <winioctl.h>
#include <stdio.h>

#define MAX_EJECT_RETRIES 3
#define EJECT_RETRY_DELAY_MS 500

// Function to eject a drive based on its volume path (e.g., "\\.\E:")
// Returns TRUE on success (specifically, if IOCTL_STORAGE_EJECT_MEDIA succeeds), FALSE on failure.
BOOL EjectVolumeByPath(LPCWSTR volumePath) {
    HANDLE hVolume = INVALID_HANDLE_VALUE;
    BOOL bLockSuccess = FALSE;
    BOOL bDismountSuccess = FALSE;
    BOOL bEjectSuccess = FALSE; // final return value basis
    BOOL bUnlockSuccess = FALSE;
    DWORD dwBytesReturned = 0;
    DWORD dwError = 0;
    int retryCount = 0;

    // wprintf(L"C DLL: Attempting eject for volume path: %s\n", volumePath);   // DEBUG

    // --- Step 1: Get a Handle to the Volume ---
    hVolume = CreateFileW(
        volumePath,
        GENERIC_READ | GENERIC_WRITE,       // Need read/write access for lock/dismount/eject
        FILE_SHARE_READ | FILE_SHARE_WRITE, // Allow other processes to read/write (required for open)
        NULL,                               // Default security attributes
        OPEN_EXISTING,                      // Must already exist
        0,                                  // No special flags
        NULL                                // No template file
    );

    if (hVolume == INVALID_HANDLE_VALUE) {
        dwError = GetLastError();
        fwprintf(stderr, L"C DLL Error: Failed to get handle for %s. Error code: %lu\n", volumePath, dwError);
        return FALSE; // Cannot proceed
    }

    // --- Step 2: Lock the Volume (with Retries) ---
    for (retryCount = 0; retryCount < MAX_EJECT_RETRIES; ++retryCount) {
        bLockSuccess = DeviceIoControl(
            hVolume,
            FSCTL_LOCK_VOLUME,
            NULL, 0, NULL, 0,
            &dwBytesReturned,
            NULL
        );

        if (bLockSuccess) {
            // wprintf(L"C DLL: Lock acquired.\n"); // DEBUG
            break; // Success, exit retry loop
        }

        // Lock failed, check error
        dwError = GetLastError();
        // wprintf(L"C DLL: Lock attempt %d failed. Error: %lu\n", retryCount + 1, dwError); // DEBUG

        // Check if it's a retryable error AND we haven't exhausted retries
        if ((dwError == ERROR_ACCESS_DENIED || dwError == ERROR_BUSY) && (retryCount < MAX_EJECT_RETRIES - 1)) {
            wprintf(L"C DLL: Retrying lock after delay...\n");
            Sleep(EJECT_RETRY_DELAY_MS); // Wait before next attempt
            continue; // Go to next iteration of the loop
        } else {
            // Not a retryable error OR retries exhausted
            // wprintf(L"C DLL Warning: Failed to lock volume %s after %d attempts. Error: %lu. Proceeding without lock...\n", volumePath, retryCount + 1, dwError);
            bLockSuccess = FALSE; // Ensure it's marked as failed
            break; // Exit retry loop, proceed without lock
        }
    }
    // NOTE: bLockSuccess now holds the final status after retries

    // --- Step 3: Dismount the Volume ---
    // Required before ejecting removable media.
    bDismountSuccess = DeviceIoControl(
        hVolume,
        FSCTL_DISMOUNT_VOLUME,
        NULL, 0,
        NULL, 0,
        &dwBytesReturned,
        NULL
    );

    if (!bDismountSuccess) {
        dwError = GetLastError();
        fwprintf(stderr, L"C DLL Error: Failed to dismount volume %s. Error: %lu\n", volumePath, dwError);

        // Must clean up lock if it succeeded before returning
        if (bLockSuccess) {
            DeviceIoControl(hVolume, FSCTL_UNLOCK_VOLUME, NULL, 0, NULL, 0, &dwBytesReturned, NULL);
        }
        CloseHandle(hVolume);
        return FALSE; // Cannot eject if dismount fails
    }

    // --- Step 4: Send the Eject Command ---
    // Prevents the system from automatically trying to remount.
    bEjectSuccess = DeviceIoControl(
        hVolume,
        IOCTL_STORAGE_EJECT_MEDIA,
        NULL, 0,
        NULL, 0,
        &dwBytesReturned,
        NULL
    );

    if (!bEjectSuccess) {
        dwError = GetLastError();
        fwprintf(stderr, L"C DLL Error: Failed to eject media for %s via IOCTL. Error: %lu\n", volumePath, dwError);
        // Eject failed, but we still need to unlock if lock succeeded.
    } else {
        // wprintf(L"C DLL: Successfully sent IOCTL_STORAGE_EJECT_MEDIA for %s\n", volumePath); // DEBUG
    }

    // --- Step 5: Unlock the Volume (CRITICAL if Lock Succeeded) ---
    // Must be done regardless of eject success if the lock was acquired.
    if (bLockSuccess) {
        bUnlockSuccess = DeviceIoControl(
            hVolume,
            FSCTL_UNLOCK_VOLUME,
            NULL, 0,
            NULL, 0,
            &dwBytesReturned,
            NULL
        );
        if (!bUnlockSuccess) {
             dwError = GetLastError();
            fwprintf(stderr, L"C DLL Warning: Failed to unlock volume %s after operation. Error: %lu\n", volumePath, dwError);
        }
    }

    // --- Step 6: Close the Handle (CRITICAL) ---
    CloseHandle(hVolume);

    // Return TRUE only if the IOCTL_STORAGE_EJECT_MEDIA call succeeded.
    return bEjectSuccess;
}
