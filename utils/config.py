# utils/config.py
import os
import sys
import logging
import configparser

# Where to look for config.ini
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SCRIPT_DIR, 'config.ini')

# Default values
DEFAULTS = {
    'RequiredFile':         'auth_key.txt',
    'LogFile':              'usb_monitor.log',
    'WmiPollInterval':      '2',
    'MountStabilityDelay':  '3',
    'ExpectedAuthKey':      None,
    'EnumLevel':            'none',
    'MaxRootFiles':         '100',
}

cfg = configparser.ConfigParser()
files_read = cfg.read(CONFIG_PATH)

if not files_read:
    logging.warning(f"No config.ini found at {CONFIG_PATH}; using all defaults.")

# Paths & filenames
REQUIRED_FILE = cfg.get('Paths', 'RequiredFile',         fallback=DEFAULTS['RequiredFile'])
LOG_FILE      = cfg.get('Paths', 'LogFile',              fallback=DEFAULTS['LogFile'])

# Timings
try:
    WMI_POLL   = cfg.getint('Timings', 'WmiPollInterval',    fallback=int(DEFAULTS['WmiPollInterval']))
except ValueError:
    logging.warning("Invalid WmiPollInterval in config.ini; defaulting to %s", DEFAULTS['WmiPollInterval'])
    WMI_POLL = int(DEFAULTS['WmiPollInterval'])

try:
    MOUNT_DELAY = cfg.getint('Timings', 'MountStabilityDelay', fallback=int(DEFAULTS['MountStabilityDelay']))
except ValueError:
    logging.warning("Invalid MountStabilityDelay in config.ini; defaulting to %s", DEFAULTS['MountStabilityDelay'])
    MOUNT_DELAY = int(DEFAULTS['MountStabilityDelay'])

# Authorization key
EXPECTED_KEY = cfg.get('Settings', 'ExpectedAuthKey', fallback=DEFAULTS['ExpectedAuthKey'])
if EXPECTED_KEY is None:
    logging.critical("ExpectedAuthKey missing in config.ini under [Settings]")
    sys.exit("Configuration error: ExpectedAuthKey is required")

# Enumeration
ENUM_LEVEL = cfg.get('Enumeration', 'level', fallback=DEFAULTS['EnumLevel']).lower()
if ENUM_LEVEL not in ('none', 'root'):
    logging.warning("Invalid Enumeration level '%s'; defaulting to 'none'", ENUM_LEVEL)
    ENUM_LEVEL = 'none'

try:
    MAX_ROOT = cfg.getint('Enumeration', 'MaxRootFiles', fallback=int(DEFAULTS['MaxRootFiles']))
except ValueError:
    logging.warning("Invalid MaxRootFiles in config.ini; defaulting to %s", DEFAULTS['MaxRootFiles'])
    MAX_ROOT = int(DEFAULTS['MaxRootFiles'])
