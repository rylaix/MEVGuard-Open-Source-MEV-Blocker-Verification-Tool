import os
import sqlite3
import yaml
from utils import log, load_config

# Base directory for consistent path handling
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))

def get_database_path():
    """
    Retrieve the database file path from the configuration.
    :return: Absolute path to the database file.
    """
    config = load_config()
    db_path = os.path.join(BASE_DIR, config['data_storage']['database_file'])
    return os.path.abspath(db_path)

def connect_to_database():
    """
    Establish a connection to the SQLite database.
    :return: SQLite connection object.
    """
    try:
        db_path = get_database_path()
        if not os.path.exists(db_path):
            log(f"[INFO] Database file not found at {db_path}. Creating a new one.")
        
        conn = sqlite3.connect(db_path)
        return conn
    except sqlite3.Error as e:
        log(f"[ERROR] Failed to connect to the database: {e}")
        raise e