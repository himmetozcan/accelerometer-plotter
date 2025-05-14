# Real-Time Accelerometer Data Viewer

<img width="1243" alt="image" src="https://github.com/user-attachments/assets/60447bef-b1b0-4bbf-b20d-e7c1b9380879" />


This application provides a web-based interface to visualize real-time accelerometer data.
It uses Python with Dash, Plotly, and Flask.

## Prerequisites

Before you begin, ensure you have Python 3 installed on your system and that it's added to your system's PATH. Pip (Python package installer) should also be available.

- **Python 3**: Download from [python.org](https://www.python.org/downloads/)
  - During installation on Windows, make sure to check the box "Add Python to PATH".

## Setup and Run

Setup scripts are provided to automate the creation of a virtual environment, installation of dependencies, and running the application.

### For macOS and Linux Users:

1.  Open your terminal.
2.  Navigate to the project directory where you downloaded these files.
3.  Make the setup script executable:
    ```bash
    chmod +x setup_and_run.sh
    ```
4.  Run the script:
    ```bash
    ./setup_and_run.sh
    ```
    This will create a virtual environment in a folder named `venv`, install the required packages, and then start the application.

### For Windows Users:

1.  Navigate to the project directory where you downloaded these files using File Explorer.
2.  Double-click the `setup_and_run.bat` file.
    This will open a command prompt, create a virtual environment in a folder named `venv`, install the required packages, and then start the application.

Once the application is running, it will print messages in the terminal/command prompt indicating the IP address and port where you can access the web interface (usually something like `http://YOUR_LOCAL_IP:8080/`).

## Sending Data

The application expects accelerometer data to be sent via HTTP POST requests to the `/sensor` endpoint (e.g., `http://YOUR_LOCAL_IP:8080/sensor`).
The expected JSON format for the payload is a list of data points:

```json
{
  "payload": [
    {
      "name": "accelerometer",
      "time": 1670000000000000000, // Nanosecond timestamp
      "values": {
        "x": 0.1,
        "y": 0.2,
        "z": 9.8
      }
    },
    // ... more data points
  ]
}
```

## Project Files

- `dash_app.py`: The main Python application using Dash.
- `requirements.txt`: A list of Python dependencies.
- `setup_and_run.sh`: Setup and run script for macOS/Linux.
- `setup_and_run.bat`: Setup and run script for Windows.
- `README.md`: This file.
- `data/`: Directory where recorded CSV files will be saved (created automatically). 
