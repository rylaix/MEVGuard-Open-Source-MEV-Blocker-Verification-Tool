import logging
import os
import sys
import yaml

# Optional import for colored console output (won't affect file logs)
try:
    from colorlog import ColoredFormatter
except ImportError:
    ColoredFormatter = None

# Load configuration from the config file
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
    with open(config_path, 'r') as file:
        return yaml.safe_load(file)

def setup_logging():
    """
    Setup logging to both console and file with enhanced features.
    Configuration is dynamically loaded from config.yaml.
    """
    config = load_config()
    
    # Extract log file details from config
    logs_dir = config['data_storage']['logs_directory']
    log_filename = config['data_storage']['log_filename']
    log_path = os.path.join(logs_dir, log_filename)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)  # Set global log level

    # Clear existing handlers to prevent duplicates
    if logger.hasHandlers():
        logger.handlers.clear()

    # Ensure the directory for logs exists
    if not os.path.exists(logs_dir):
        try:
            os.makedirs(logs_dir)
        except OSError as e:
            print(f"Error creating log directory {logs_dir}: {e}")

    # File Handler - logs to a file
    file_handler = logging.FileHandler(log_path, mode='a')
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console Handler - logs to console with optional color
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # Check if ColoredFormatter is available, if not, use standard Formatter
    if ColoredFormatter:
        color_formatter = ColoredFormatter(
            "%(log_color)s%(asctime)s - %(levelname)s - %(message)s",
            datefmt=None,
            reset=True,
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
            }
        )
        console_handler.setFormatter(color_formatter)
    else:
        console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)

    logger.addHandler(console_handler)

    # Log message to show the logger is working
    logger.info("Logger initialized. Logging to both console and file.")
    logger.info(f"Logs are being saved to {log_path}")

def log(message):
    """
    Logs a message with INFO level.
    """
    logging.info(message)

def log_error(message):
    """
    Logs a message with ERROR level.
    """
    logging.error(message)

def log_warning(message):
    """
    Logs a message with WARNING level.
    """
    logging.warning(message)

def log_debug(message):
    """
    Logs a message with DEBUG level.
    """
    logging.debug(message)
