# Import statements
import wmi
import time
import os
import logging
import atexit # To save summary on exit
import datetime # For timestamps
import threading
import queue
# cspell:ignore pythoncom
import pythoncom

from utils.config import REQUIRED_FILE, WMI_POLL, MOUNT_DELAY, ENUM_LEVEL, MAX_ROOT, EXPECTED_KEY
from utils.logging_setup import setup_logging
from utils.summary       import load_summary, save_summary
from utils.device        import get_physical_drive_path, get_volume_details
from utils.eject         import eject_drive_api

# placeholders so handlers can see them
unique_devices_summary = {}
processed_volumes       = {}
logger                  = None

def _arrival_watcher(q: queue.Queue, stop_event):
    # set up COM on *this* thread
    pythoncom.CoInitialize()
    try:
        # Outer recovery loop
        while not stop_event.is_set():
            try:
                # (Re)establish WMI connection each time we retry
                wmi_con = wmi.WMI()
                watcher = wmi_con.watch_for(
                    raw_wql=f"SELECT * FROM __InstanceCreationEvent WITHIN {WMI_POLL} "
                            "WHERE TargetInstance ISA 'Win32_Volume' AND TargetInstance.DriveType=2"
                )
                # Inner event‑pumping loop
                while not stop_event.is_set():
                    try:
                        evt = watcher(timeout_ms=1000)
                        if evt and evt.DriveLetter and evt.DeviceID:
                            q.put(('arrival', evt.DriveLetter, evt.DeviceID))
                    except wmi.x_wmi_timed_out:
                        continue
                    
            except Exception as e:
                # Log any fatal COM/WMI error, then retry after a pause
                logger.error("Arrival‑watcher error, retrying in 5s: %s", e, exc_info=True)
                time.sleep(5)

    finally:
        pythoncom.CoUninitialize()

def _removal_watcher(q: queue.Queue, stop_event):
    pythoncom.CoInitialize()
    try:
        while not stop_event.is_set():
            try:
                wmi_con = wmi.WMI()
                watcher = wmi_con.watch_for(
                    raw_wql=f"SELECT * FROM __InstanceDeletionEvent WITHIN {WMI_POLL} "
                            "WHERE TargetInstance ISA 'Win32_Volume' AND TargetInstance.DriveType=2"
                )
                while not stop_event.is_set():
                    try:
                        evt = watcher(timeout_ms=1000)
                        if evt and evt.DeviceID:
                            q.put(('removal', evt.DeviceID))
                    except wmi.x_wmi_timed_out:
                        continue
                    
            except Exception as e:
                    logger.error("Removal‑watcher COM error: %s", e, exc_info=True)
                    time.sleep(5)
    finally:
        pythoncom.CoUninitialize()



def handle_usb_arrival(drive_letter, device_id):
    """
    Handles the logic when a new USB drive is detected. Checks for a required file,
    updates the in-memory summary of the device, and attempts ejection if the file
    is not found or valid.
    """
    
    global stop_event
    if globals().get("stop_event") and stop_event.is_set():
        logging.info(f"Ignoring arrival for {device_id} because monitoring is stopped.")
        return
    
    logging.debug(f"handle_usb_arrival entered for {drive_letter} ({device_id})") #DEBUG

    # --- Prevent rapid re-processing ---
    current_transient_state = processed_volumes.get(device_id) # Check the *transient* state dict
    if current_transient_state not in ['removed', 'ejected', None, 'failed_eject_dll', 'allowed', 'failed_auth', 'access_error']:
         logging.debug(f"Ignoring event for {device_id}. Current transient state is '{current_transient_state}', indicating active processing.")
         return

    # --- Log Arrival Info ---
    logging.info(f"--- USB Drive Arrival Detected ---")
    logging.info(f"  Drive Letter: {drive_letter}")
    logging.info(f"  Volume GUID:  {device_id}")
    logging.info(f"---------------------------------")

    # Set the state to checking
    processed_volumes[device_id] = 'checking'
    logging.info(f"State for {device_id} set to 'checking'")
    

    # --- Update In-Memory Summary: Record Arrival ---
    now_iso = datetime.datetime.now().isoformat()
    logging.debug(f"[Summary] Updating summary for arrived device {device_id}") # DEBUG
    
    # Use .setdefault() which gets the value if key exists, or inserts a new dict and returns it if key doesn't exist
    summary_entry = unique_devices_summary.setdefault(device_id, {})
    
    is_first_record = not summary_entry.get('first_seen')
    if is_first_record:
        summary_entry['first_seen'] = now_iso
        summary_entry['arrival_count'] = 1
        logging.info(f"[Summary] First time recording device {device_id}.") # INFO
    else:
        summary_entry['arrival_count'] = summary_entry.get('arrival_count', 0) + 1

    summary_entry['last_seen'] = now_iso
    summary_entry['last_drive_letter'] = drive_letter
    summary_entry['last_state'] = 'checking' # Initial state for this arrival

    # Initialize/Update counters and new fields
    summary_entry.setdefault('total_auth_success', 0)
    summary_entry.setdefault('total_auth_failure', 0)
    summary_entry.setdefault('total_eject_success', 0)
    summary_entry.setdefault('total_eject_failure', 0)
    summary_entry.setdefault('auth_reason', 'Pending Check')
    summary_entry.setdefault('volume_details', {})
    
    # initialize extra_data if enumeration might happen
    if ENUM_LEVEL != 'none':
         summary_entry.setdefault('extra_data', {}).setdefault('files_enumeration', {})

    logging.debug(f"[Summary] Updated entry for {device_id} after arrival: {summary_entry}") # DEBUG

    # --- Wait for mount stability ---
    logging.info(f"Waiting for {MOUNT_DELAY} seconds for mount stability...")
    time.sleep(MOUNT_DELAY)

    # --- Check if drive still exists ---
    if not os.path.exists(drive_letter + '\\'):
        logging.warning(f"Drive {drive_letter} disappeared before file check.")
        processed_volumes[device_id] = 'removed'
        # Update summary state
        now_iso = datetime.datetime.now().isoformat()
        summary_entry = unique_devices_summary.get(device_id)
        if summary_entry:
            summary_entry['last_state'] = 'removed'
            summary_entry['last_seen'] = now_iso
            logging.debug(f"[Summary] Updated entry for {device_id} after disappearing: {summary_entry}") # DEBUG
        logging.info(f"Transient state for {device_id} set to 'removed'")
        return # Stop processing this arrival

    # ------ GET VOLUME DETAILS ------
    volume_details = get_volume_details(drive_letter, device_id)
    if volume_details:
        summary_entry['volume_details'] = volume_details
        logging.debug(f"[Summary] Stored volume details for {device_id}")
    else:
        logging.warning(f"Could not retrieve volume details for {drive_letter}. Summary may be incomplete.")
        # Ensure the key exists even if empty
        summary_entry.setdefault('volume_details', {})

    # --- File Check & Content Validation --
    # --- Construct file path to required file ---
    file_to_check = os.path.join(drive_letter, REQUIRED_FILE)
    is_authorized = False
    auth_reason = "Check Not Performed"
    final_state_this_instance = 'checking' # Default before check
    
    try:
        if os.path.exists(file_to_check):
            # ----- STORE REASON IMMEDIATELY ------
            auth_reason = "File Found, Validating Content..."
            summary_entry['auth_reason'] = auth_reason # Update summary early
            
            try:
                with open(file_to_check, 'r', encoding='utf-8') as f:
                    file_content = f.read().strip()
                    
                # Validate file content against the expected key
                if file_content == EXPECTED_KEY:
                    is_authorized = True
                    auth_reason = "OK" # Final success reason
                else:
                    auth_reason = "Content Mismatch" # Final fail reason
                    logging.debug(f"Auth content mismatch on {drive_letter}.")
            except Exception as e:
                auth_reason = f"File Read Error ({type(e).__name__})" # Final fail reason
                logging.error(f"File Read Error: Drive={drive_letter}, File={REQUIRED_FILE}, Error={e}", exc_info=False)
        else:
            auth_reason = "File Not Found"


        # ----- UPDATE SUMMARY WITH FINAL AUTH REASON ------
        summary_entry['auth_reason'] = auth_reason
        now_iso = datetime.datetime.now().isoformat() # Get time after check
        
        
        # --- Log Result, Update Transient State ---
        if is_authorized:
            logging.info(f"Auth Success: Drive={drive_letter}, Reason={auth_reason}")
            processed_volumes[device_id] = 'allowed'
        else:
            logging.warning(f"Auth Failed: Drive={drive_letter}, Reason={auth_reason}")
            processed_volumes[device_id] = 'failed_auth'


        # ------ OPTIONAL: ROOT FILE ENUMERATION ------
        if ENUM_LEVEL == 'root':
            logging.info(f"Starting root file enumeration for {drive_letter}...")
            # Ensure structure exists
            files_enum_dict = summary_entry.setdefault('extra_data', {}).setdefault('files_enumeration', {})
            files_enum_dict.clear() # Clear previous enumeration for this device if any
            file_count = 0
            try:
                with os.scandir(drive_letter + '\\') as entries:
                    for entry in entries:
                        if file_count >= MAX_ROOT:
                             logging.warning(f"Reached maximum ({MAX_ROOT}) root files/folders to list for {drive_letter}.")
                             files_enum_dict['_truncated_'] = True # Indicate list is cut short
                             break
                        try:
                            stat_info = entry.stat()
                            file_data = {
                                "size": stat_info.st_size,
                                "created": datetime.datetime.fromtimestamp(stat_info.st_ctime).isoformat(),
                                "modified": datetime.datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
                                "accessed": datetime.datetime.fromtimestamp(stat_info.st_atime).isoformat(),
                                "is_dir": entry.is_dir(),
                            }
                            files_enum_dict[entry.name] = file_data
                            file_count += 1
                        except OSError as stat_err:
                            logging.warning(f"Could not stat file/dir '{entry.path}' during enumeration: {stat_err}")
                            files_enum_dict[entry.name] = {"error": f"Stat failed: {stat_err}"}
                        except Exception as entry_err: # Catch other potential errors per entry
                             logging.error(f"Unexpected error processing entry '{entry.path}': {entry_err}", exc_info=False)
                             files_enum_dict[entry.name] = {"error": f"Processing error: {entry_err}"}

                logging.info(f"Completed root file enumeration for {drive_letter}. Listed {file_count} items.")
            except OSError as scan_err:
                logging.error(f"Could not enumerate root directory {drive_letter}: {scan_err}")
                summary_entry.setdefault('extra_data', {})['files_enumeration_error'] = f"Scan failed: {scan_err}"
            except Exception as enum_err: # Catch other potential errors during scan setup
                 logging.error(f"Unexpected error during root enumeration setup for {drive_letter}: {enum_err}", exc_info=True)
                 summary_entry.setdefault('extra_data', {})['files_enumeration_error'] = f"Enum setup error: {enum_err}"


        # --- Attempt Ejection if Auth Failed ---
        if not is_authorized:
            eject_drive_api(drive_letter,
                device_id,
                unique_devices_summary,
                processed_volumes) # update summary state on eject outcome

        final_state_this_instance = processed_volumes[device_id] # Get state after check/eject attempt

    except OSError as e:
        logging.error(f"Drive Access Error: Drive={drive_letter}, Action=Check File/Content/Enumerate, Error={e}", exc_info=False)
        processed_volumes[device_id] = 'access_error'
        final_state_this_instance = 'access_error'
        summary_entry['auth_reason'] = f"Drive Access Error ({type(e).__name__})" # Update reason on access error
        
    # --- Update Summary with Final State & Auth Counters (if not handled by eject) ---
    now_iso = datetime.datetime.now().isoformat() # Get current time for final update
    summary_entry = unique_devices_summary.get(device_id) # Re-get in case eject changed it
    if summary_entry:
        # Update final state if not already set by a successful/failed eject attempt
        if final_state_this_instance not in ['ejecting', 'ejected', 'failed_eject_dll']:
             summary_entry['last_state'] = final_state_this_instance
        # Always update last_seen
        summary_entry['last_seen'] = now_iso

        # Update counters based on authorization outcome (use final_state_this_instance)
        if final_state_this_instance == 'allowed':
             summary_entry['total_auth_success'] = summary_entry.get('total_auth_success', 0) + 1
        elif final_state_this_instance in ['failed_auth', 'access_error']: # Count access error as auth failure too
             summary_entry['total_auth_failure'] = summary_entry.get('total_auth_failure', 0) + 1
        # Note: Eject counters are handled within eject_drive_api
        
        save_summary(unique_devices_summary)
        logging.debug(f"[Summary] Final updated entry for {device_id} post-check/auth/enum: {summary_entry}")
    else:
        logging.warning(f"[Summary] Cannot update summary post-check: No entry for {device_id}") # Should be rare
        
        




# --- Function for handling removal ---
def handle_usb_removal(device_id):
    
    global stop_event
    if globals().get("stop_event") and stop_event.is_set():
        logging.info(f"Ignoring arrival for {device_id} because monitoring is stopped.")
        return
    
    global unique_devices_summary # Needed to modify global dict
    global processed_volumes      # Needed to modify global dict
    logging.info(f"--- USB Drive Removal Detected ---")
    logging.info(f"   Volume GUID: {device_id}")
    logging.info(f"---------------------------------")
    logging.debug(f"[Summary] Processing removal for {device_id}") # DEBUG

    # Update transient state
    if device_id in processed_volumes:
        if processed_volumes[device_id] != 'ejected': # Don't overwrite if we ejected it
            processed_volumes[device_id] = 'removed'
            logging.info(f"Transient state for {device_id} set to 'removed'")
        else:
            logging.info(f"Volume {device_id} removed, consistent with prior 'ejected' transient state.")
            processed_volumes[device_id] = 'removed'
    else:
        logging.info(f"Untracked volume {device_id} removed.")
        processed_volumes[device_id] = 'removed' # Track it as removed now

    # --- Update Summary ---
    now_iso = datetime.datetime.now().isoformat()
    summary_entry = unique_devices_summary.get(device_id)
    if summary_entry is not None:
        summary_entry['last_state'] = 'removed'
        summary_entry['last_seen'] = now_iso
        # summary_entry['last_drive_letter'] = None     # Optional: Clear drive letter
        save_summary(unique_devices_summary)
        logging.debug(f"[Summary] Updated entry for {device_id} after removal: {summary_entry}") # DEBUG
    else:
        # This might happen if a device is removed very quickly before arrival processing finished
        logging.debug(f"[Summary] No summary entry found for removed device {device_id}.") # DEBUG







# --- Main execution block ---
def main(stop_event=None):
    global logger, unique_devices_summary, processed_volumes
    
    # ─── ensure we have a real Event ────────────────────────────────────────────
    if stop_event is None:
        stop_event = threading.Event()
    globals()['stop_event'] = stop_event
    
    # --- initialize logging, state & summary persistence ---
    logger = setup_logging()
    unique_devices_summary = load_summary()
    processed_volumes = {}
    atexit.register(lambda: save_summary(unique_devices_summary))
    
    
    # ——————————————————————————— Script Initialization ———————————————————————————
    logger.info("\n" + "=" * 30 + " Script Started " + "=" * 30)
    logger.info("Starting WMI monitoring for USB drive connections...")
    logger.warning("IMPORTANT: This script requires Administrator privileges for WMI queries and drive ejection.")
    logger.info("Press Ctrl+C to stop.")
    # —————————————————————————————————————————————————————————————————————————————

    # ─── set up the event queue & watcher threads ───────────────────────────────
    event_q = queue.Queue()
    t_arr = threading.Thread(
        target=_arrival_watcher,
        args=(event_q, stop_event),
        daemon=True
    )
    t_rem = threading.Thread(
        target=_removal_watcher,
        args=(event_q, stop_event),
        daemon=True
    )
    t_arr.start()
    t_rem.start()

    # dispatch loop: block on queue, then call your handlers
    try:
        while not (stop_event and stop_event.is_set()):
            try:
                typ, *args = event_q.get(timeout=1)
            except queue.Empty:
                # no event yet, just loop
                continue
            
            # got a real event—dispatch
            if typ == 'arrival':
                handle_usb_arrival(*args)
            else:
                handle_usb_removal(*args)
                
    except KeyboardInterrupt:
        logger.info("Stopping monitoring.")
        stop_event.set()
        
    except Exception as e:
        # only log truly unexpected errors
        logger.error("Dispatcher error: %s", e, exc_info=True)
        stop_event.set()
            
    # ─── now join before exiting ───────────────────────────────────────────
    logger.info("Waiting for watcher threads to exit…")
    t_arr.join(timeout=5)
    t_rem.join(timeout=5)
    logger.info("All threads terminated, exiting.")


if __name__ == "__main__":
    main()