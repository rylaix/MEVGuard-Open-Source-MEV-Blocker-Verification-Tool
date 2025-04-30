import os
import re

# Get the current directory of this script
current_dir = os.path.dirname(os.path.abspath(__file__))
# Set the path for the logs directory and files
logs_dir = os.path.abspath(os.path.join(current_dir, '..', 'logs'))
log_file_path = os.path.join(logs_dir, 'logfile.log')
error_log_file_path = os.path.join(logs_dir, 'errors_logs.log')
warning_log_file_path = os.path.join(logs_dir, 'warnings_logs.log')

# Regular expression patterns to capture error and warning lines
error_pattern = re.compile(r'ERROR.*')  # Adjust the regex based on the specific error format if needed
warning_pattern = re.compile(r'WARNING.*')  # Adjust the regex based on the specific warning format if needed

# Ensure the logs directory exists
if not os.path.exists(logs_dir):
    print(f"Logs directory does not exist: {logs_dir}")
    exit(1)

# Check if the log file exists
if not os.path.isfile(log_file_path):
    print(f"Log file does not exist: {log_file_path}")
    exit(1)

# Function to extract logs with context based on the given pattern
def extract_logs_with_context(pattern, log_lines, lines_before=10, lines_after=10):
    blocks = []
    for index, line in enumerate(log_lines):
        if pattern.search(line):  # Match lines based on the provided pattern
            # Capture lines_before and lines_after around the match
            start_index = max(0, index - lines_before)
            end_index = min(len(log_lines), index + lines_after + 1)
            context = log_lines[start_index:end_index]
            blocks.append(''.join(context).strip())  # Collect the log and its context
    return blocks

# Read the log file
with open(log_file_path, 'r') as log_file:
    log_lines = log_file.readlines()

# Extract errors and their context
error_blocks = extract_logs_with_context(error_pattern, log_lines)

# Extract warnings and their context
warning_blocks = extract_logs_with_context(warning_pattern, log_lines)

# Write the extracted errors to the error log file
if error_blocks:
    with open(error_log_file_path, 'w') as error_log_file:
        error_log_file.write('\n\n'.join(error_blocks))  # Separate each error block with one empty line
    print(f"Errors and their context have been extracted to: {error_log_file_path}")
else:
    print("No errors found in the log file.")

# Write the extracted warnings to the warning log file
if warning_blocks:
    with open(warning_log_file_path, 'w') as warning_log_file:
        warning_log_file.write('\n\n'.join(warning_blocks))  # Separate each warning block with one empty line
    print(f"Warnings and their context have been extracted to: {warning_log_file_path}")
else:
    print("No warnings found in the log file.")
