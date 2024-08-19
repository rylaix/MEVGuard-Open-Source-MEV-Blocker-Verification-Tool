import os
import json
import time
from web3 import Web3
from web3.datastructures import AttributeDict
from dune_client.client import DuneClient
from dune_client.models import DuneError, ExecutionState
from dune_client.query import QueryBase
from dune_client.types import QueryParameter
from dotenv import load_dotenv
from multiprocessing import Pool, cpu_count
import yaml

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

# Ensure data and logs directories exist
os.makedirs(data_dir, exist_ok=True)
os.makedirs(logs_dir, exist_ok=True)

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
all_mev_blocker_bundle_per_block = config['all_mev_blocker_bundle_per_block']  # Updated to use config.yaml
confirmed_transactions_per_block = config['confirmed_transactions_per_block']  # Updated to use config.yaml
web3 = Web3(Web3.HTTPProvider(rpc_node_url))
dune_client = DuneClient(api_key=dune_api_key)

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
        print(f"Error converting to dict: {e}")
        return str(obj)  # Fallback to string representation if any error occurs

def fetch_block_contents(block_number):
    """Fetch the contents of a block given its number."""
    block = web3.eth.get_block(block_number, full_transactions=True)
    print(f"Fetched block {block_number} with {len(block['transactions'])} transactions.")
    return block

def log_discrepancy_and_abort(message):
    """Log an error message and abort the script."""
    log_path = os.path.join(logs_dir, log_filename)
    with open(log_path, 'a') as log_file:
        log_file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
    print(message)
    exit(1)

def compare_and_validate_sql(query_id, local_sql):
    """Fetch the SQL content from Dune using the query ID and compare it with the local SQL."""
    if not config.get('validate_sql', True):
        print("SQL validation is disabled. Skipping check.")
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
            print(f"Dune query SQL matches local SQL for query ID {query_id}.")
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
                    bundles = result.get_rows()
                    print(f"Identified {len(bundles)} results.")
                    return bundles
                elif status == ExecutionState.FAILED:
                    print(f"Query {execution_id} failed.")
                    return []
                else:
                    print(f"Query {execution_id} is executing, waiting {polling_interval} seconds...")
                    time.sleep(polling_interval)

            except DuneError as e:
                print(f"Error with Dune query execution: {e}")
                return []

    except DuneError as e:
        print(f"Error executing query: {e}")
        return []

def get_latest_processed_block():
    """Get the latest processed block from the data directory."""
    files = [f for f in os.listdir(data_dir) if f.startswith("block_") and f.endswith(".json")]
    if not files:
        print("No processed blocks found, starting from default block range.")
        return None
    latest_file = max(files, key=lambda f: int(f.split('_')[1].split('.')[0]))
    latest_block = int(latest_file.split('_')[1].split('.')[0])
    return latest_block

def get_mev_blocker_bundles():
    """Prepare and execute Dune Analytics query to get MEV Blocker bundles."""
    # Compare and validate the SQL
    if not compare_and_validate_sql(all_mev_blocker_bundle_per_block, local_backrun_query_sql):
        return None

    # Get start and end blocks
    latest_block_number = web3.eth.block_number
    block_delay_seconds = config.get('block_delay_seconds', 0)
    
    # Adjusting the latest block number to account for block propagation delay
    end_block = latest_block_number - int(block_delay_seconds // 12)  # Approximate block time for Ethereum is 12 seconds
    latest_processed_block = get_latest_processed_block()
    if latest_processed_block is not None:
        start_block = latest_processed_block - config.get('start_block_offset', 100)
    else:
        start_block = latest_block_number - config.get('start_block_offset', 100)
    print(start_block, end_block)

    # Execute the query and get results
    return execute_query_and_get_results(all_mev_blocker_bundle_per_block, start_block, end_block)

def get_non_mev_transactions():
    """Prepare and execute Dune Analytics query to get non-MEV transactions."""
    # Compare and validate the SQL
    if not compare_and_validate_sql(confirmed_transactions_per_block, local_non_mev_query_sql):
        return None

    # Get start and end blocks
    latest_block_number = web3.eth.block_number
    block_delay_seconds = config.get('block_delay_seconds', 0)
    
    # Adjusting the latest block number to account for block propagation delay
    end_block = latest_block_number - int(block_delay_seconds // 12)  # Approximate block time for Ethereum is 12 seconds
    latest_processed_block = get_latest_processed_block()
    if latest_processed_block is not None:
        start_block = latest_processed_block - config.get('start_block_offset', 100)
    else:
        start_block = latest_block_number - config.get('start_block_offset', 100)
    print(start_block, end_block)

    # Execute the query and get results
    return execute_query_and_get_results(confirmed_transactions_per_block, start_block, end_block)

def store_data(block, bundles):
    """Store the block and bundles data into the data directory."""
    # Convert block to dictionary
    block_dict = convert_to_dict(block)

    with open(os.path.join(data_dir, f"block_{block['number']}.json"), 'w') as f:
        json.dump(block_dict, f, indent=4)

    with open(os.path.join(data_dir, f"bundles_{block['number']}.json"), 'w') as f:
        json.dump(bundles, f, indent=4)

    print(f"Stored data for block {block['number']}")

def process_block(block_number, bundles):
    """Process a single block: fetch, identify bundles, and store data."""
    try:
        block = fetch_block_contents(block_number)
        # Here we use the bundles fetched previously
        store_data(block, bundles)
    except Exception as e:
        print(f"Failed to process block {block_number}: {e}")

if __name__ == "__main__":
    # Fetch MEV Blocker bundles
    bundles = get_mev_blocker_bundles()

    # Option, which handles logic when 0 results are returned
    abort_on_empty_first_query = config.get('abort_on_empty_first_query', True)

    if not bundles:
        if abort_on_empty_first_query:
            print("No bundles retrieved. Exiting the script.")
            exit(1)
        else:
            print("No bundles retrieved. Proceeding to the next query...")

    # Fetch non-MEV transactions
    non_mev_transactions = get_non_mev_transactions()

    if not non_mev_transactions:
        print("No non-MEV transactions retrieved. Exiting the script.")
        exit(1)

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

    # Use multiprocessing to handle multiple blocks concurrently
    with Pool(processes=cpu_count()) as pool:
        pool.starmap(process_block, [(block_number, bundles) for block_number in block_numbers])

    print("All blocks processed.")
