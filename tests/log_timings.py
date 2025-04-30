import sys
import os
import re
import subprocess

current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, root_dir)
from src.utils import load_config

# Function to check if pandas is installed, and if not, install it
def ensure_pandas_installed():
    try:
        import pandas
    except ImportError:
        print("Pandas not found. Installing pandas...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pandas"])

# Ensure pandas is installed before proceeding
ensure_pandas_installed()
import pandas as pd

# Load the config file

config = load_config()

# Extract the logs directory from the config
logs_dir = config['data_storage']['logs_directory']
log_file_path = os.path.join(root_dir, logs_dir, 'simulation_timings.log')

# Define regex patterns to identify different types of interactions
local_operation_pattern = re.compile(r'Local operation time for balance check \(tx (0x[a-fA-F0-9]+)\): ([\d.]+) seconds')
server_response_pattern = re.compile(r'Server response time for balance check \(tx (0x[a-fA-F0-9]+)\): ([\d.]+) seconds')
local_simulation_pattern = re.compile(r'Local simulation time for transaction (0x[a-fA-F0-9]+): ([\d.]+) seconds')

# Containers to store parsed data
local_operations = []
server_responses = []
local_simulations = []

# Load the log file
with open(log_file_path, 'r') as file:
    log_lines = file.readlines()

# Extracting the relevant data
for line in log_lines:
    local_match = local_operation_pattern.search(line)
    server_match = server_response_pattern.search(line)
    simulation_match = local_simulation_pattern.search(line)

    if local_match:
        local_operations.append({
            'Transaction Hash': local_match.group(1),
            'Interaction Type': 'Local Operation',
            'Duration (seconds)': float(local_match.group(2))
        })
    elif server_match:
        server_responses.append({
            'Transaction Hash': server_match.group(1),
            'Interaction Type': 'Server Response',
            'Duration (seconds)': float(server_match.group(2))
        })
    elif simulation_match:
        local_simulations.append({
            'Transaction Hash': simulation_match.group(1),
            'Interaction Type': 'Local Simulation',
            'Duration (seconds)': float(simulation_match.group(2))
        })

# Combine all interactions into a single DataFrame
all_interactions = local_operations + server_responses + local_simulations
interaction_df = pd.DataFrame(all_interactions)

# Task 1: Count the total time for local and server operations
# Filter and sum durations for local operations (including balance checks and simulations) and server responses
total_local_time = interaction_df[interaction_df['Interaction Type'].str.contains('Local')]['Duration (seconds)'].sum()
total_server_time = interaction_df[interaction_df['Interaction Type'] == 'Server Response']['Duration (seconds)'].sum()

print(f"Total Local Time: {total_local_time} seconds")
print(f"Total Server Time: {total_server_time} seconds")

# Task 2: Count the time needed for a single transaction to be processed locally and server-side (approx)
# Calculate the average time per transaction for local and server interactions
avg_local_duration = interaction_df[interaction_df['Interaction Type'].str.contains('Local')]['Duration (seconds)'].mean()
avg_server_duration = interaction_df[interaction_df['Interaction Type'] == 'Server Response']['Duration (seconds)'].mean()

print(f"Average Local Duration per Transaction: {avg_local_duration} seconds")
print(f"Average Server Duration per Transaction: {avg_server_duration} seconds")

# Task 3: Count the total number of unique transaction hashes in the log file
unique_transaction_hashes = interaction_df['Transaction Hash'].nunique()

print(f"Total Unique Transactions: {unique_transaction_hashes}")
