import os
import json
import time
from web3 import Web3
from web3.datastructures import AttributeDict
from dune_client.client import DuneClient
from dune_client.query import QueryBase
from dune_client.models import DuneError, ExecutionState
from dotenv import load_dotenv
from multiprocessing import Pool, cpu_count
import yaml

# Load environment variables
load_dotenv()

# Explicitly specify the path to the .env file
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path)

# Debugging print statements
rpc_node_url = os.getenv('RPC_NODE_URL')
dune_api_key = os.getenv('DUNE_API_KEY')
dune_query_id = os.getenv('DUNE_QUERY_ID')

print(f"RPC_NODE_URL: {rpc_node_url}")  # Should print the URL
print(f"DUNE_API_KEY: {dune_api_key}")  # Should print the API key
print(f"DUNE_QUERY_ID: {dune_query_id}")  # Should print the query ID

if not rpc_node_url:
    raise ValueError("RPC_NODE_URL is not set. Please check your .env file.")

# Load additional config if needed
config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
with open(config_path, 'r') as file:
    config = yaml.safe_load(file)

# Load the C extension
try:
    import c_extension
except ImportError:
    c_extension = None

# Initialize Web3 and DuneClient outside the class
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

def get_mev_blocker_bundles():
    """Run Dune Analytics query to get MEV Blocker bundles."""
    query_id = os.getenv('DUNE_QUERY_ID') or config['dune_query_id']

    # Create a QueryBase object for the query
    query = QueryBase(
        query_id=int(query_id),
        params=[]
    )

    # Execute the query once
    try:
        execution_response = dune_client.execute_query(query)
    except DuneError as e:
        print(f"Error executing query: {e}")
        return []

    execution_id = execution_response.execution_id
    print(f"Query execution ID: {execution_id}")

    # Polling interval in seconds (9 minutes)
    polling_interval = 540

    # Wait for the query execution to complete
    while True:
        try:
            status = dune_client.get_execution_status(execution_id).state
            if status == ExecutionState.COMPLETED:
                print(f"Query {execution_id} completed.")
                # Fetch the latest result from the executed query
                result = dune_client.get_execution_results(execution_id)

                # Ensure the results are retrieved as a list of dictionaries
                bundles = result.get_rows()

                print(f"Identified {len(bundles)} MEV Blocker bundles.")
                return bundles
            elif status == ExecutionState.FAILED:
                print(f"Query {execution_id} failed.")
                return []
            else:
                print(f"Query {execution_id} is executing, waiting {polling_interval // 60} minutes...")
                time.sleep(polling_interval)

        except DuneError as e:
            print(f"Error with Dune query execution: {e}")
            return []

def store_data(block, bundles):
    """Store the block and bundles data into the data directory."""
    # Convert block to dictionary
    block_dict = convert_to_dict(block)

    with open(f"data/block_{block['number']}.json", 'w') as f:
        json.dump(block_dict, f, indent=4)

    with open(f"data/bundles_{block['number']}.json", 'w') as f:
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
    # Fetch MEV Blocker bundles once
    bundles = get_mev_blocker_bundles()

    if not bundles:
        print("No bundles retrieved. Exiting the script.")
        exit(1)

    # Define the block range or specific blocks to process
    latest_block_number = web3.eth.block_number
    block_numbers = [latest_block_number - i for i in range(5)]  # Example: last 5 blocks

    # Use multiprocessing to handle multiple blocks concurrently
    with Pool(processes=cpu_count()) as pool:
        pool.starmap(process_block, [(block_number, bundles) for block_number in block_numbers])

    print("All blocks processed.")
