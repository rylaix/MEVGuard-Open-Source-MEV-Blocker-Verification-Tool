import os
import json
import time
from dune_client.client import DuneClient
from dune_client.query import QueryBase
from dune_client.models import DuneError, ExecutionState
from dotenv import load_dotenv
import yaml

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path, override=True)

# Load additional config if needed
config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
with open(config_path, 'r') as file:
    config = yaml.safe_load(file)

# Initialize DuneClient
dune_api_key = os.getenv('DUNE_API_KEY')
dune_client = DuneClient(api_key=dune_api_key)

# Get the gather_to_start_dune_query_id from the config
gather_to_start_dune_query_id = config.get('gather_to_start_dune_query_id')

def log_discrepancy_and_abort(message):
    """Log an error message and abort the script."""
    log_path = os.path.join(os.path.dirname(__file__), '..', 'logs', 'logfile')
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'a') as log_file:
        log_file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
    print(message)
    exit(1)

def execute_query_and_get_results():
    """Execute the query on Dune and get the results."""
    try:
        # Construct the query
        query = QueryBase(gather_to_start_dune_query_id)

        execution_response = dune_client.execute_query(query)
        execution_id = execution_response.execution_id
        print(f"Query execution ID: {execution_id}")

        # Polling interval specified in config.yaml
        polling_interval = config.get('polling_rate_seconds', 10)  # Default to 10 seconds if not set

        # Wait for the query execution to complete
        while True:
            try:
                status = dune_client.get_execution_status(execution_id).state
                if status == ExecutionState.COMPLETED:
                    print(f"Query {execution_id} completed.")
                    # Fetch the latest result from the executed query
                    result = dune_client.get_execution_results(execution_id)

                    # Ensure the results are retrieved as a list of dictionaries
                    blocks = result.get_rows()

                    # Debugging: Print the retrieved data to check the structure
                    print("Retrieved blocks data:", blocks)

                    print(f"Identified {len(blocks)} results.")
                    return blocks
                elif status == ExecutionState.FAILED:
                    log_discrepancy_and_abort(f"Query {execution_id} failed.")
                else:
                    print(f"Query {execution_id} is executing, waiting {polling_interval} seconds...")
                    time.sleep(polling_interval)

            except DuneError as e:
                log_discrepancy_and_abort(f"Error with Dune query execution: {e}")

    except DuneError as e:
        log_discrepancy_and_abort(f"Error executing query: {e}")

def store_data(blocks):
    """Store the block data into the data directory."""
    # Convert blocks to dictionary
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    os.makedirs(data_dir, exist_ok=True)

    if blocks:
        # Debugging: Print the structure of the first result
        print("First block data:", blocks[0])

        # Attempt to access blockNumber safely
        if 'blockNumber' in blocks[0]:
            latest_block = blocks[0]['blockNumber']  # Assuming the first result is the latest block
            with open(f"{data_dir}/block_{latest_block}.json", 'w') as f:
                json.dump(blocks, f, indent=4)
            print(f"Stored data for block {latest_block}")
        else:
            print("blockNumber not found in the query results.")
    else:
        print("No blocks to store.")

if __name__ == "__main__":
    # Fetch the latest block data
    blocks = execute_query_and_get_results()

    if not blocks:
        print("No data retrieved. Exiting the script.")
        exit(1)

    # Store the retrieved data
    store_data(blocks)
