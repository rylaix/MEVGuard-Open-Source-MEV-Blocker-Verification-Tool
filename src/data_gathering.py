import os
import json
import time
from utils import setup_logging, log, log_error
from web3 import Web3
from web3.datastructures import AttributeDict
from dune_client.client import DuneClient
from dune_client.models import DuneError, ExecutionState
from dune_client.query import QueryBase
from dune_client.types import QueryParameter
from dotenv import load_dotenv
from multiprocessing import Pool, cpu_count
import yaml
import requests

from bundle_simulation import greedy_bundle_selection, simulate_bundles, store_simulation_results
from state_management import initialize_web3, simulate_transaction_bundle, update_block_state, verify_transaction_inclusion 


# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path, override=True)

# Load additional config if needed
config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
with open(config_path, 'r') as file:
    config = yaml.safe_load(file)

# Load paths from config.yaml
data_dir = config['data_storage']['data_directory']
logs_dir = config['data_storage']['logs_directory']
log_filename = config['data_storage']['log_filename']
simulation_results_dir = config['data_storage']['simulation_output_directory']

# Ensure data and logs directories exist
os.makedirs(data_dir, exist_ok=True)
os.makedirs(logs_dir, exist_ok=True)
os.makedirs(simulation_results_dir, exist_ok=True)

# Load SQL queries from files
backrun_query_path = os.path.join(os.path.dirname(__file__), '..', 'queries', 'fetch_backruns.sql')
with open(backrun_query_path, 'r') as file:
    local_backrun_query_sql = file.read()

fetch_remaining_transactions_query_path = os.path.join(os.path.dirname(__file__), '..', 'queries', 'fetch_remaining_transactions.sql')
with open(fetch_remaining_transactions_query_path, 'r') as file:
    local_non_mev_query_sql = file.read()

# Initialize Web3 and DuneClient outside the class
rpc_node_url = os.getenv('RPC_NODE_URL')
dune_api_key = os.getenv('DUNE_API_KEY')
web3 = Web3(Web3.HTTPProvider(rpc_node_url))
dune_client = DuneClient(api_key=dune_api_key)

# Load query ID
all_mev_blocker_bundle_per_block = config['all_mev_blocker_bundle_per_block']  # Updated to use config.yaml

# List to keep track of retried blocks
retried_blocks = []

def convert_to_dict(obj):
    """Convert AttributeDict or bytes objects into serializable dictionaries."""
    try:
        if isinstance(obj, AttributeDict):
            return {key: convert_to_dict(value) for key, value in obj.items()}
        if isinstance(obj, list):
            return [convert_to_dict(item) for item in obj]
        if isinstance(obj, bytes):
            return obj.hex()
        return obj
    except Exception as e:
        log(f"Error converting to dict: {e}")
        return str(obj)  # Fallback to string representation if any error occurs

def fetch_block_contents(block_number):
    """Fetch the contents of a block given its number, with optional retry logic for rate-limiting."""
    retries = config['rate_limit_handling']['max_retries']
    delay = config['rate_limit_handling']['initial_delay_seconds']
    exponential_backoff = config['rate_limit_handling']['exponential_backoff']
    enable_retry = config['rate_limit_handling'].get('enable_retry', True)  # Default to True if not set

    for attempt in range(retries if enable_retry else 1):  # No retries if retry is disabled
        try:
            block = web3.eth.get_block(block_number, full_transactions=True)
            return block
        except requests.exceptions.HTTPError as err:
            if err.response.status_code == 429:  # Too Many Requests
                if enable_retry:
                    log(f"Rate limit exceeded for block {block_number}, retrying after {delay} seconds... (Attempt {attempt+1}/{retries})")
                    time.sleep(delay)
                    if exponential_backoff:
                        delay *= 2  # Exponential backoff if enabled
                    # Add the block number to the retried blocks list
                    if block_number not in retried_blocks:  # Avoid duplicates
                        retried_blocks.append(block_number)
                        log(f"Added block {block_number} to retried blocks list.")  # Log as soon as added
                        log(f"Current retried blocks: {', '.join(map(str, retried_blocks))}")  # Dynamic list logging
                else:
                    log(f"Rate limit exceeded for block {block_number}. Skipping retries.")
                    break
            else:
                log(f"Failed to process block {block_number}: {err}")
                raise
    log(f"Exceeded retry limit for block {block_number}.")
    return None


def log_discrepancy_and_abort(message):
    """Log an error message and abort the script."""
    log_path = os.path.join(logs_dir, log_filename)
    with open(log_path, 'a') as log_file:
        log_file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
    log(message)
    exit(1)

def compare_and_validate_sql(query_id, local_sql):
    """Fetch the SQL content from Dune using the query ID and compare it with the local SQL."""
    if not config.get('validate_sql', True):
        log("SQL validation is disabled. Skipping check.")
        return True

    try:
        # Fetch the query details directly from Dune's API without converting it to a DuneQuery object
        response = dune_client._get(f"/query/{query_id}")

        # Check if the response contains SQL
        existing_sql = response.get('sql')
        if existing_sql is None:
            log_discrepancy_and_abort(f"SQL content not found for query ID {query_id}. Full response: {response}")

        # Compare the fetched SQL with the local SQL
        if existing_sql.strip() != local_sql.strip():
            log_discrepancy_and_abort(
                f"Local SQL differs from the Dune query for query ID {query_id}. "
                "Please update the Dune query or local SQL to match."
            )
        else:
            log(f"Dune query SQL matches local SQL for query ID {query_id}.")
            return True

    except DuneError as e:
        log_discrepancy_and_abort(f"Error fetching SQL content from Dune for query ID {query_id}: {e}")

    return False

def execute_query_and_get_results(query_id, start_block=None, end_block=None):
    """Execute the query on Dune and get the results."""
    try:
        # Create query parameters
        parameters = [
            QueryParameter.number_type(name="start_block", value=start_block),
            QueryParameter.number_type(name="end_block", value=end_block)
        ]

        # Construct the query object
        query = QueryBase(query_id=query_id, params=parameters)

        # Execute the query
        execution_response = dune_client.execute_query(query)
        execution_id = execution_response.execution_id
        log(f"Query execution ID: {execution_id}")

        # Polling interval specified in config.yaml
        polling_interval = config.get('polling_rate_seconds', 10)  # Default to 10 seconds if not set

        # Wait for the query execution to complete
        while True:
            try:
                status = dune_client.get_execution_status(execution_id).state
                if status == ExecutionState.COMPLETED:
                    log(f"Query {execution_id} completed.")
                    # Fetch the latest result from the executed query
                    result = dune_client.get_execution_results(execution_id)
                    bundles = result.get_rows()
                    log(f"Identified {len(bundles)} results.")
                    return bundles
                elif status == ExecutionState.FAILED:
                    log(f"Query {execution_id} failed.")
                    return []
                else:
                    log(f"Query {execution_id} is executing, waiting {polling_interval} seconds...")
                    time.sleep(polling_interval)

            except DuneError as e:
                log(f"Error with Dune query execution: {e}")
                return []

    except DuneError as e:
        log(f"Error executing query: {e}")
        return []

def get_latest_processed_block():
    """Get the latest processed block from the data directory."""
    files = [f for f in os.listdir(data_dir) if f.startswith("block_") and f.endswith(".json")]
    if not files:
        log("No processed blocks found, starting from default block range.")
        return None
    latest_file = max(files, key=lambda f: int(f.split('_')[1].split('.')[0]))
    latest_block = int(latest_file.split('_')[1].split('.')[0])
    return latest_block

def get_simulated_blocks():
    """
    Check the simulation results directory to find blocks that have already been simulated.
    :return: A list of block numbers that have already been simulated
    """
    simulated_files = [f for f in os.listdir(simulation_results_dir) if f.endswith('.json')]
    simulated_blocks = [int(f.split('_')[1].split('.')[0]) for f in simulated_files]
    return simulated_blocks

def load_existing_block_and_bundles(block_number):
    """
    Load the block and bundles from the data folder.
    :param block_number: The block number to load
    :return: Block data and bundles data
    """
    block_file = os.path.join(data_dir, f"block_{block_number}.json")
    bundles_file = os.path.join(data_dir, f"bundles_{block_number}.json")

    with open(block_file, 'r') as block_f:
        block_data = json.load(block_f)

    with open(bundles_file, 'r') as bundles_f:
        bundles_data = json.load(bundles_f)

    return block_data, bundles_data

def simulate_unprocessed_blocks():
    """
    Simulate all unprocessed (unsimulated) blocks by looking into the `data` directory.
    """
    # List all blocks saved in the data directory
    all_blocks = [int(f.split('_')[1].split('.')[0]) for f in os.listdir(data_dir) if f.startswith('block_')]
    
    # Get the blocks that have already been simulated
    simulated_blocks = get_simulated_blocks()

    # Filter out the blocks that have already been simulated
    unprocessed_blocks = [block for block in all_blocks if block not in simulated_blocks]

    if not unprocessed_blocks:
        log("No new blocks to simulate.")
        return

    for block_number in unprocessed_blocks:
        log(f"Processing block {block_number}...")

        try:
            block_data, bundles_data = load_existing_block_and_bundles(block_number)

            if bundles_data:
                # Apply greedy algorithm to select the best bundles
                max_selected_bundles = config['bundle_simulation']['max_selected_bundles']

                selected_bundles = greedy_bundle_selection(bundles_data, max_selected_bundles)

                # Simulate the selected bundles
                log(f"Simulating bundles for block {block_number}...")
                simulation_results = simulate_bundles(selected_bundles, web3, block_number)

                # Store the simulation results
                simulation_output_file = os.path.join(simulation_results_dir, f"simulation_{block_number}.json")
                log(f"Storing the simulation results for block {block_number}...")
                store_simulation_results(simulation_results, simulation_output_file)

        except Exception as e:
            log(f"Error while processing block {block_number}: {e}")

def get_mev_blocker_bundles():
    """
    Prepare and execute Dune Analytics query to get MEV Blocker bundles.
    """
    # Compare and validate the SQL
    if not compare_and_validate_sql(all_mev_blocker_bundle_per_block, local_backrun_query_sql):
        return None

    # Get the latest block number from the blockchain
    latest_block_number = web3.eth.block_number
    block_delay_seconds = config.get('block_delay_seconds', 10)

    # Determine start_block and end_block
    start_block = config.get('start_block')
    if start_block is None or start_block <= 0:
        latest_processed_block = get_latest_processed_block()
        start_block = latest_processed_block if latest_processed_block else latest_block_number - 100

    end_block = config.get('end_block')
    if end_block is None or end_block <= 0:
        end_block = latest_block_number - int(block_delay_seconds // 12)

    log(f"Start block: {start_block}, End block: {end_block}")

    # Execute the query and get results
    return execute_query_and_get_results(all_mev_blocker_bundle_per_block, start_block, end_block)

def store_data(block, bundles):
    """
    Store the block and bundles data into the data directory.
    """
    # Convert block to dictionary
    block_dict = convert_to_dict(block)

    # Save block data
    with open(os.path.join(data_dir, f"block_{block['number']}.json"), 'w') as f:
        json.dump(block_dict, f, indent=4)

    # Save bundles data
    with open(os.path.join(data_dir, f"bundles_{block['number']}.json"), 'w') as f:
        json.dump(bundles, f, indent=4)

    log(f"Stored data for block {block['number']}")

def process_block(block_number, bundles):
    """
    Process a single block: fetch, simulate, validate, and store data.
    """
    try:
        # Load block data and extract block_time
        block_data, bundles_data = load_existing_block_and_bundles(block_number)
        block_time = block_data['timestamp']  # Extract block timestamp
        
        log(f"Processing block {block_number}...")
        
        # Simulate bundles and store results
        simulation_results = simulate_bundles(bundles, web3, block_number, block_time)
        simulation_output_file = os.path.join(simulation_results_dir, f"simulation_{block_number}.json")
        store_simulation_results(simulation_results, simulation_output_file)

        # Verify transaction inclusion
        for bundle in bundles:
            for tx in bundle['transactions']:
                tx_hash = tx.get('hash')
                if tx_hash:
                    included = verify_transaction_inclusion(web3, block_number, tx_hash)
                    if not included:
                        log_error(f"Transaction {tx_hash} not included in block {block_number}")
                else:
                    log_error(f"Missing transaction hash in block {block_number}")

    except Exception as e:
        log_error(f"Error while processing block {block_number}: {e}")


if __name__ == "__main__":
    # Initialize logging
    setup_logging()

    log("Starting data gathering process...")

    # Fetch MEV Blocker bundles
    bundles = get_mev_blocker_bundles()

    # Option, which handles logic when 0 results are returned
    abort_on_empty_first_query = config.get('abort_on_empty_first_query', True)

    if not bundles:
        if abort_on_empty_first_query:
            log("No bundles retrieved. Exiting the script.")
            exit(1)
        else:
            log("No bundles retrieved. Proceeding to the next query...")

    # Determine the number of blocks to process
    latest_block_number = web3.eth.block_number
    latest_processed_block = get_latest_processed_block() or latest_block_number - config.get('start_block_offset', 100)

    # Check if `num_blocks_to_process` is set to "all"
    num_blocks_to_process = config.get('num_blocks_to_process', 5)
    if num_blocks_to_process == "all":
        # Gather all blocks from the latest processed block to the latest block on the blockchain
        block_numbers = list(range(latest_processed_block, latest_block_number + 1))
    else:
        # Gather a specified number of blocks (e.g., 5)
        block_numbers = [latest_processed_block - i for i in range(num_blocks_to_process)]

    # Store block data and bundles before further processing
    log("Fetching and storing block data and bundles...")
    for block_number in block_numbers:
        try:
            block_data = web3.eth.get_block(block_number, full_transactions=True)
            log(f"Fetched block data for block {block_number} with {len(block_data['transactions'])} transactions.")

            # Store block data and bundles
            store_data(block_data, bundles)
            log(f"Stored block data and bundles for block {block_number}.")

        except Exception as e:
            log_error(f"Error fetching or storing block data for block {block_number}: {e}")
            continue

    # Greedy algorithm to select the best bundles
    max_selected_bundles = config['bundle_simulation']['max_selected_bundles']
    log(f"Selecting the best {max_selected_bundles} bundles using the greedy algorithm...")

    selected_bundles = greedy_bundle_selection(bundles, max_selected_bundles)

    # Check if simulation is enabled
    simulation_enabled = config['bundle_simulation']['simulation_enabled']
    if simulation_enabled:
        log("Simulating the selected bundles...")

        # Ensure block time is passed to simulation
        block_time = block_data.get('timestamp')  # Correctly fetch block time
        simulation_results = simulate_bundles(selected_bundles, web3, latest_block_number, block_time)

        # Store the simulation results
        simulation_output_file = os.path.join(data_dir, config['bundle_simulation']['simulation_output_file'])
        log(f"Storing the simulation results to {simulation_output_file}...")
        store_simulation_results(simulation_results, simulation_output_file)

    log("All tasks for this phase completed successfully.")
