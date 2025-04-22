import os, json, logging
from .config import SCRIPT_DIR

SUMMARY_FILE = 'unique_devices_summary.json'

def load_summary():
    path = os.path.join(SCRIPT_DIR, SUMMARY_FILE)
    try:
        with open(path) as f:
            data = json.load(f)
            logging.debug(f"Loaded summary ({len(data)})")
            return data
    except FileNotFoundError:
        logging.info("No summary file found; starting fresh.")
        return {}
    except Exception as e:
        logging.error(f"Error loading summary: {e}")
        return {}

def save_summary(summary):
    path = os.path.join(SCRIPT_DIR, SUMMARY_FILE)
    try:
        with open(path, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        logging.debug(f"Saved summary ({len(summary)})")
    except Exception as e:
        logging.critical(f"Error saving summary: {e}")
