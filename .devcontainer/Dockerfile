# Base image - using the official Python 3.10.10 image
FROM python:3.10.10-slim

# Install necessary system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    libssl-dev \
    pkg-config \
    libffi-dev \
    python3-dev \
    curl \
    wget

# Create a user to run VS Code in a non-root context
RUN useradd -m vscode && \
    apt-get install -y sudo && \
    echo "vscode ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Set up a working directory
WORKDIR /workspace

# Copy all project files into the container
COPY . /workspace

# Install Python dependencies
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Setting environment variables for the development container
ENV PYTHONPATH="${PYTHONPATH}:/workspace/src:/workspace/db"

# Set a default command for the container
CMD [ "sleep", "infinity" ]
