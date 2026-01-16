"""
Logging utility for Maxi AI.
Provides centralized logging functionality.
"""

import logging
import os
from datetime import datetime

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Create a UTF-8 file handler
file_handler = logging.FileHandler(
    f"logs/maxi_{datetime.now().strftime('%Y%m%d')}.log",
    encoding='utf-8'  # Ensure Unicode (emoji) support
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        file_handler,
        logging.StreamHandler()
    ]
)

# Get logger
logger = logging.getLogger("maxi")

def log_info(message: str):
    """Log an info message."""
    logger.info(message)

def log_error(message: str):
    """Log an error message."""
    logger.error(message)

def log_debug(message: str):
    """Log a debug message."""
    logger.debug(message)

def log_warning(message: str):
    """Log a warning message."""
    logger.warning(message)
