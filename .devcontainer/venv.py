import os
import subprocess
import sys

# Define the path for the virtual environment
venv_dir = '/workspace/.venv'

def create_virtualenv():
    # Check if the virtual environment already exists
    if not os.path.exists(venv_dir):
        print("Creating virtual environment...")
        try:
            # Run the command to create a virtual environment
            subprocess.check_call([sys.executable, '-m', 'venv', venv_dir])
            print(f"Virtual environment created at {venv_dir}")

            # Fix permissions on .venv directory to allow the current user to install packages
            subprocess.check_call(['sudo', 'chown', '-R', 'vscode:vscode', venv_dir])

            # Upgrade pip to avoid issues with deprecated commands
            pip_path = os.path.join(venv_dir, 'bin', 'pip')
            subprocess.check_call([pip_path, 'install', '--upgrade', 'pip'])
            print("Successfully upgraded pip.")

            # Install the required dependencies from requirements.txt
            subprocess.check_call([pip_path, 'install', '-r', '/workspace/requirements.txt'])
            print("Successfully installed dependencies.")

        except subprocess.CalledProcessError as e:
            print(f"Error occurred while setting up virtual environment: {e}")
    else:
        print(f"Virtual environment already exists at {venv_dir}. Skipping creation.")

    # Activate the virtual environment after setup (using subprocess)
    activate_venv(venv_dir)

def activate_venv(venv_dir):
    """Activate the virtual environment by sourcing its activate script"""
    activate_script = os.path.join(venv_dir, 'bin', 'activate')

    # Ensure that the activate script exists before trying to source it
    if os.path.exists(activate_script):
        try:
            # Activate the virtual environment by running the activate script
            subprocess.check_call(['bash', '-c', f'source {activate_script} && echo Virtual environment activated.'])
        except subprocess.CalledProcessError as e:
            print(f"Error occurred while activating the virtual environment: {e}")
    else:
        print(f"Error: Virtual environment activate script not found at {activate_script}")

if __name__ == '__main__':
    create_virtualenv()
