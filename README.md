# Real-Time Accelerometer Data Viewer

<img width="1243" alt="image" src="https://github.com/user-attachments/assets/60447bef-b1b0-4bbf-b20d-e7c1b9380879" />


This application provides a web-based interface to visualize real-time accelerometer data.
It uses Python with Dash, Plotly, and Flask.

## Prerequisites

1. Install "Sensor Logger" app to your mobile.
   ![image](https://github.com/user-attachments/assets/a2688f1a-c40f-4832-9aba-699b422d1f30)

2. Turn on Accelerometer and Open Settings
   ![image](https://github.com/user-attachments/assets/5736bd86-a009-4a2d-af7f-afe3fd089cf9)

3. Open Data Streaming
   ![image](https://github.com/user-attachments/assets/59f0c181-f4bc-4a5f-be94-1cc951d3f313)

4. Enable Http push and edit url. For example "http://192.168.0.80/sensor". 
   ![image](https://github.com/user-attachments/assets/a2381b2c-4433-49b4-a162-d3027a4d296f)

5. In your pc, ensure you have Python 3.13 installed on your system and that it's added to your system's PATH. Pip (Python package installer) should also be available. ([python 3.13](https://www.python.org/downloads/release/python-3130/))
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

The application expects accelerometer data to be sent via HTTP POST requests to the `/sensor` endpoint (e.g., `http://YOUR_LOCAL_IP:8080/sensor`). Go to Step 4 above and make sure you enter the same local ip you see on the web UI.
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

## Note

Make sure you use firefox if you are in windows, because other browsers limit the cpu and memory usage for a single tab and it causes problems.
