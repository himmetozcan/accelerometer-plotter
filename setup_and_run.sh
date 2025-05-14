#!/bin/bash

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null
then
    echo "Python 3 is not installed. Please install Python 3 and add it to your PATH."
    echo "You can download it from https://www.python.org/downloads/"
    exit 1
fi

# Check if pip is available for Python 3
if ! python3 -m pip --version &> /dev/null
then
    echo "pip for Python 3 is not available. Please ensure pip is installed with your Python 3 distribution."
    echo "Often, it can be installed with: python3 -m ensurepip --upgrade"
    exit 1
fi

# Define the virtual environment directory
VENV_DIR="venv"

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in $VENV_DIR..."
    python3 -m venv $VENV_DIR
    if [ $? -ne 0 ]; then
        echo "Failed to create virtual environment. Please check your Python 3 venv module."
        exit 1
    fi
fi

# Activate virtual environment
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "Installing dependencies from requirements.txt..."
python3 -m pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "Failed to install dependencies. Please check requirements.txt and your internet connection."
    exit 1
fi

echo "Starting the Dash application..."
python3 dash_app.py

# Deactivate virtual environment (optional, as script exit will effectively do this)
# deactivate

echo "Application closed." 