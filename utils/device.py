import wmi, time, logging


# get the path 
def get_physical_drive_path(drive_letter, volume_guid):
    r"""
    Maps a Volume GUID (e.g., r'\\?\Volume{...}') and its Drive Letter
    to its physical drive path (e.g., r'\\.\PhysicalDriveX') using WMI.

    Requires Administrator privileges.

    Args:
        drive_letter (str): The drive letter assigned (e.g., "E:"). # Added explanation
        volume_guid (str): The DeviceID of the Win32_Volume (e.g., r'\\?\Volume{...}').
                           (Used mainly for logging context now). # Added explanation

    Returns:
        str: The physical drive path (e.g., r'\\.\PhysicalDriveX') or None if not found/error.
    """
    # Use volume_guid only for logging now
    logging.debug(f"Attempting to find physical drive path for Drive: {drive_letter}, Volume GUID: {volume_guid}")
    try:
        c = wmi.WMI() # Create a WMI instance

        # Find the Win32_LogicalDisk using the Drive Letter ---
        # Validate the provided drive_letter
        if not drive_letter or not drive_letter.endswith(':'):
             logging.error(f"Invalid drive letter provided to get_physical_drive_path: '{drive_letter}'")
             return None

        esc_drive_letter = drive_letter.replace("'", "\\'") # Escape single quotes if present
        query_ld = f"SELECT * FROM Win32_LogicalDisk WHERE DeviceID = '{esc_drive_letter}'"
        logging.debug(f"WMI Query (LogicalDisk): {query_ld}")
        logical_disk_results = c.query(query_ld)
        if not logical_disk_results:
             logging.error(f"WMI Query failed: Could not find Win32_LogicalDisk for DriveLetter: {drive_letter}")
             return None
        logical_disk = logical_disk_results[0]

        # --- Step 3: Find the associated Win32_DiskPartition(s) ---
        logging.debug(f"Finding partitions associated with LogicalDisk: {drive_letter}")
        partitions = logical_disk.associators(wmi_result_class='Win32_DiskPartition')
        if not partitions:
            logging.error(f"WMI Query failed: Could not find associated Win32_DiskPartition for {drive_letter}")
            return None
        partition = partitions[0] # Assume first partition
        logging.debug(f"Found Partition: {partition.DeviceID}")

        # --- Step 4: Find the associated Win32_DiskDrive ---
        logging.debug(f"Finding disk drive associated with Partition: {partition.DeviceID}")
        disk_drives = partition.associators(wmi_result_class='Win32_DiskDrive')
        if not disk_drives:
            logging.error(f"WMI Query failed: Could not find associated Win32_DiskDrive for partition {partition.DeviceID}")
            return None
        disk_drive = disk_drives[0] # Assume one drive
        physical_drive_path = disk_drive.DeviceID
        logging.debug(f"Found Physical Drive Path: {physical_drive_path} for Volume: {volume_guid}") # Keep volume_guid for log context

        # --- Step 5: Validate and Return Path ---
        if physical_drive_path and physical_drive_path.lower().startswith(r"\\.\physicaldrive"):
             return physical_drive_path
        else:
             logging.error(f"Obtained unexpected DeviceID format for Disk Drive: {physical_drive_path}")
             return None

    except wmi.x_wmi as e:
        logging.error(f"WMI Error during physical drive path lookup for {drive_letter}: {e}", exc_info=True)
        # Log COM error details if available
        if hasattr(e, 'com_error'):
             logging.error(f"COM Error details: {e.com_error}")
        return None
    except Exception as e:
        logging.error(f"Unexpected Python error during physical drive path lookup for {drive_letter}: {e}", exc_info=True)
        return None

def get_volume_details(drive_letter, volume_guid): # Keep volume_guid for logging
    """
    Retrieves Volume Name, File System, Size, and Free Space using WMI,
    querying by Drive Letter after mount. Includes retries for timing issues.
    Requires Administrator privileges.

    Args:
        drive_letter (str): The drive letter (e.g., "E:").
        volume_guid (str): The Volume GUID (e.g., r'?\\Volume{...}') for logging context.

    Returns:
        dict: A dictionary containing 'VolumeName', 'FileSystem', 'Size', 'FreeSpace',
              or an empty dictionary if details cannot be retrieved. Returns sizes in bytes as strings.
    """
    details = {}
    # ---- Use drive_letter for the primary query ----
    logging.debug(f"Attempting to get volume details for Drive: {drive_letter} (GUID: {volume_guid}) via WMI.")

    if not drive_letter or not drive_letter.endswith(':'):
         logging.error(f"Invalid drive letter '{drive_letter}' passed to get_volume_details.")
         return {} # Return empty if drive letter is invalid

    # --- Optional Retry Loop ---
    max_attempts = 3
    retry_delay = 0.7
    for attempt in range(1, max_attempts + 1):
        try:
            c = wmi.WMI()
            # Escape single quotes in drive_letter for WQL query
            escaped_drive_letter = drive_letter.replace("'", "\\'")
            # ---- Query by DriveLetter ----
            query = f"SELECT Name, Label, FileSystem, Capacity, FreeSpace FROM Win32_Volume WHERE DriveLetter = '{escaped_drive_letter}'"
            logging.debug(f"WMI Query (Volume Details, Attempt {attempt}): {query}")
            volume_results = c.query(query)

            if volume_results:
                volume = volume_results[0]
                # Use Label for VolumeName if available, otherwise fallback to Name (like drive letter)
                details['VolumeName'] = getattr(volume, 'Label', None) or getattr(volume, 'Name', None)
                details['FileSystem'] = getattr(volume, 'FileSystem', None)
                capacity = getattr(volume, 'Capacity', None)
                free_space = getattr(volume, 'FreeSpace', None)
                details['Size'] = str(capacity) if capacity is not None else None
                details['FreeSpace'] = str(free_space) if free_space is not None else None
                logging.info(f"Successfully retrieved volume details on attempt {attempt}.") # INFO on success
                return details # <<< Success, return immediately

            else:
                # Log warning only on last attempt or if retrying
                log_level = logging.WARNING if attempt == max_attempts else logging.DEBUG
                logging.log(log_level, f"WMI Query (Attempt {attempt}) found no Win32_Volume details for DriveLetter: {drive_letter}")
                if attempt < max_attempts:
                     logging.debug(f"Retrying volume details query in {retry_delay}s...")
                     time.sleep(retry_delay)
                else:
                     logging.error(f"Failed to get volume details for {drive_letter} after {max_attempts} attempts.")
                     return {} # <<< Failed after all attempts

        except wmi.x_wmi as e:
            logging.error(f"WMI Error (Attempt {attempt}) getting volume details for {drive_letter}: {e}", exc_info=False) # Don't need full stack trace usually
            if hasattr(e, 'com_error'):
                logging.error(f"COM Error details: {e.com_error}")
            # Decide whether to retry on WMI errors or just fail
            if attempt < max_attempts:
                logging.warning(f"Retrying after WMI error in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                logging.error(f"Failed to get volume details for {drive_letter} due to WMI error after {max_attempts} attempts.")
                return {} # Failed after WMI error

        except Exception as e:
            logging.error(f"Unexpected Python error (Attempt {attempt}) getting volume details for {drive_letter}: {e}", exc_info=True) # Show stack trace here
            return {} # Stop retrying on unexpected Python errors

    # This part should ideally not be reached if the loop logic is correct
    logging.error(f"Volume details retrieval failed for {drive_letter} after loop completion (unexpected).")
    return {}