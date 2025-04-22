import logging
import os
from logging.handlers import RotatingFileHandler
from .config import LOG_FILE

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    
    # console
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("CONSOLE: %(levelname)s - %(message)s"))
    
    # Compute absolute path: go up one level from utils/, into USBLogger_Windows/
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_path = os.path.join(base_dir, LOG_FILE)

    # Ensure the directory exists
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    
    # rotating file
    fh = RotatingFileHandler(log_path, maxBytes=5*1024*1024, backupCount=0)
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    
    logger.handlers.clear()
    logger.addHandler(ch)
    logger.addHandler(fh)
    
    return logger