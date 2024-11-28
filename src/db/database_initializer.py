import sqlite3
import os
import yaml
from utils import log, log_error, load_config

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '../../config/config.yaml')
    with open(config_path, 'r') as file:
        return yaml.safe_load(file)

def initialize_or_verify_database():
    """
    Ensure that the necessary database and tables are created.
    """
    try:
        # Load configuration to get the database path
        config = load_config()
        db_path = os.path.join(os.path.dirname(__file__), '../../', config['data_storage']['database_file'])
        db_path = os.path.abspath(db_path)

        base_dir = os.path.dirname(os.path.abspath(__file__))
        sql_file_path = os.path.join(base_dir, '../../queries/mevguard_tracking.sql')

        # Establish a connection to the SQLite database
        if not os.path.exists(db_path):
            log(f"Database file not found at path {db_path}, creating a new one.")

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Read the SQL script for creating necessary tables
        with open(sql_file_path, 'r') as sql_file:
            sql_script = sql_file.read()

        # Execute the SQL script to create tables if they do not exist
        try:
            cursor.executescript(sql_script)
            log("Database tables initialized or verified successfully.")
            
            # Check and log the current tables in the database
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            log(f"Current tables in the database: {tables}")

        except sqlite3.Error as e:
            log_error(f"[ERROR] Database initialization failed: {e}")

        # Commit and close the connection
        conn.commit()
        conn.close()
    except Exception as e:
        log_error(f"[ERROR] Failed to initialize or verify the database: {e}")

if __name__ == "__main__":
    initialize_or_verify_database()
