import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import plotly.graph_objs as go
from plotly.subplots import make_subplots # Added for subplots
from collections import deque
import zmq
import threading
import time
import json
import numpy as np
from scipy import signal # For STFT
import flask
from flask import jsonify
import csv # Added for CSV writing
from datetime import datetime # Added for timestamp in filename
import logging
import os
import base64
import io
import socket # Added for getting local IP

# Loglama seviyesini ayarla - sadece hata ve kritik mesajları göster
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('dash').setLevel(logging.ERROR)
logging.getLogger('flask').setLevel(logging.ERROR)

# ZeroMQ Bağlantı Ayarları
ZMQ_SERVER = "tcp://localhost:5555"

# Veri Tamponları - DAHA KÜÇÜK BUFFER (performans için)
BUFFER_SIZE = 3000  # Dash'i hızlandırmak için tampon boyutunu azalt
times_buffer = deque(maxlen=BUFFER_SIZE)
x_buffer = deque(maxlen=BUFFER_SIZE)
y_buffer = deque(maxlen=BUFFER_SIZE)
z_buffer = deque(maxlen=BUFFER_SIZE)

# Görüntüleme ve Animasyon Ayarları
DISPLAY_WINDOW = 10.0
UPDATE_INTERVAL = 33  # ms (approx 30 FPS for animation)
DATA_CHECK_INTERVAL = 25 # ms (Reverted: how often to check for new data to update traces)

# Global state variables
last_update_time = 0
is_receiving_data = False
total_points_received = 0
receiver_active = True
base_time = None
initial_wall_clock_time = None

# Recording state variables
is_recording = False
current_filename = "accelerometer_data.csv" # Default filename
csv_writer_object = None
output_file_stream = None

# Live stream control
live_stream_active = True

# Uploaded data buffer and state
uploaded_data_buffer = {'t': [], 'x': [], 'y': [], 'z': []}
displaying_uploaded_data = False

# Y ekseni için başlangıç değerleri
y_min_value = -0.1  # Y ekseni için minimum değer (artık kullanılmıyor olabilir)
y_max_value = 0.1   # Y ekseni için maksimum değer

# Performans iyileştirmeleri
PREPROCESS_DATA = False  # Preprocessing'i bypass et, doğrudan ham veriyi göster

# Dash Uygulaması - Daha sessiz çalışması için bazı ayarlar
app = dash.Dash(
    __name__, 
    title="Accelerometer Data",
    update_title=None,
    suppress_callback_exceptions=True,
    # Gereksiz mesajları gizle
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}]
)

# Define CSS styles manually
styles = {
    'status-row': {
        'display': 'flex',
        'justifyContent': 'space-between', # Changed for tighter packing
        'marginBottom': '10px',
        'flexWrap': 'wrap' # Keep wrap as a fallback, but aim for single row
    },
    'status-container': {
        'textAlign': 'center',
        'padding': '5px 8px', # Reduced padding
        'borderRadius': '5px',
        'backgroundColor': '#f8f9fa',
        'flex': '1 0 auto', # Allow flex sizing
        'minWidth': '0' # Allow shrinking
    },
    'status-indicator': {
        'fontSize': '0.9em', # Reduced font size
        'fontWeight': 'bold'
    },
    'control-panel': {
        'display': 'flex',
        'flexWrap': 'wrap', # Allow items to wrap
        'justifyContent': 'space-around',
        'alignItems': 'center', # Align items vertically
        'marginTop': '20px',
        'padding': '15px',
        'backgroundColor': '#f0f0f0', # Slightly different background for panel
        'borderRadius': '8px',
        'boxShadow': '0 2px 4px rgba(0,0,0,0.1)' # Subtle shadow
    },
    'control-item': {
        'width': '100%', # Take full width of sidebar column
        'margin': '8px 0', # Adjusted margin for vertical stacking
        'padding': '5px',      # Add some internal padding
        'boxSizing': 'border-box', # Crucial for 100% width to include padding/border
        'textAlign': 'left'  # Align labels to the left for sidebar
    },
    'record-button-style': {
        'padding': '10px 15px',
        'fontSize': '1em',
        'fontWeight': 'bold',
        'color': 'white',
        'backgroundColor': '#28a745', # Green for start
        'border': 'none',
        'borderRadius': '5px',
        'cursor': 'pointer',
        'width': '100%' # Full width in sidebar
    },
    'generic-button-style': { # Generic style for other buttons like Reset, Stream toggle
        'padding': '8px 12px',
        'fontSize': '0.9em',
        'fontWeight': 'bold',
        'color': 'white',
        'backgroundColor': '#007bff', # Blue default
        'border': 'none',
        'borderRadius': '5px',
        'cursor': 'pointer',
        'width': '100%' # Full width in sidebar
    },
    'reset-button-custom-style': { # Specific overrides for reset if needed, e.g., color
        'backgroundColor': '#6c757d', # Grey color for reset
        'width': '100%'
    },
    'record-button-stop-style': {
        'backgroundColor': '#dc3545' # Red for stop
    },
    'filename-input-style': {
        'width': '100%', # Take more width within its flex item
        'padding': '8px',
        'borderRadius': '4px',
        'border': '1px solid #ccc',
        'boxSizing': 'border-box' # Ensure padding/border included in width
    },
    'recording-status-message-style': {
        'marginTop': '5px',
        'fontSize': '0.9em',
        'color': '#333'
    },
    'main-container': {
        'fontFamily': 'Arial, sans-serif',
        'padding': '20px',
        'maxWidth': '1200px',
        'margin': '0 auto'
    }
}

# Function to get local IP address
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(('8.8.8.8', 1)) # Connect to a public DNS server
        ip = s.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except socket.gaierror:
            ip = '127.0.0.1' # Default to loopback if others fail
    finally:
        if 's' in locals() and s:
            s.close()
    return ip

LOCAL_IP_ADDRESS = get_local_ip()

# Initial figure structure for the graph (now with subplots)
def create_initial_figure(display_window_seconds):
    fig = make_subplots(
        rows=3, cols=1, 
        shared_xaxes=True, 
        subplot_titles=('X Axis', 'Y Axis', 'Z Axis'),
        vertical_spacing=0.05 # Reduced spacing
    )

    fig.add_trace(go.Scattergl(x=[], y=[], name='X', mode='lines', line=dict(color='blue', width=1)), row=1, col=1)
    fig.add_trace(go.Scattergl(x=[], y=[], name='Y', mode='lines', line=dict(color='red', width=1)), row=2, col=1)
    fig.add_trace(go.Scattergl(x=[], y=[], name='Z', mode='lines', line=dict(color='green', width=1)), row=3, col=1)

    fig.update_layout(
        title_text="Accelerometer Data - Awaiting Data",
        showlegend=False,
        margin=dict(l=50, r=30, t=50, b=30), 
        uirevision='constant',
        plot_bgcolor='white'  # Set plot background to white
    )
    # Set initial range and hide grid/ticks/labels for all x-axes
    fig.update_xaxes(
        range=[0, display_window_seconds], 
        showgrid=False,  # Hide x-axis grid lines
        showticklabels=False # Hide x-axis tick labels
    ) 
    # Set a fixed y-axis range and hide grid for all subplots
    fig.update_yaxes(
        range=[-15, 15], 
        autorange=False, 
        showgrid=False # Hide y-axis grid lines
    ) 
    
    return fig

initial_figure = create_initial_figure(DISPLAY_WINDOW)

# Uygulama Düzeni
app.layout = html.Div([
    # New Main Flex Container for Two-Column Layout
    html.Div([
        # Left Column (Main Content: Title, Status, Graph)
        html.Div([
            html.H1("Accelerometer Data", style={'textAlign': 'center', 'marginBottom': '10px'}),
            html.Div([
                html.Div([html.H4("Connection Status:", style={'fontSize': '0.8em', 'marginTop': '0', 'marginBottom': '3px'}), html.Div(id="connection-status", style=styles['status-indicator'])], style=styles['status-container']),
                html.Div([html.H4("Data Points:", style={'fontSize': '0.8em', 'marginTop': '0', 'marginBottom': '3px'}), html.Div(id="data-count", style=styles['status-indicator'])], style=styles['status-container']),
                html.Div([html.H4("Last Update:", style={'fontSize': '0.8em', 'marginTop': '0', 'marginBottom': '3px'}), html.Div(id="last-update", style=styles['status-indicator'])], style=styles['status-container']),
                html.Div([html.H4("Recording Time:", style={'fontSize': '0.8em', 'marginTop': '0', 'marginBottom': '3px'}), html.Div(id="recording-duration-display", style=styles['status-indicator'])], style=styles['status-container']),
                html.Div([html.H4("Server IP:", style={'fontSize': '0.8em', 'marginTop': '0', 'marginBottom': '3px'}), html.Div(LOCAL_IP_ADDRESS, style=styles['status-indicator'])], style=styles['status-container'])
            ], style=styles['status-row']),
            dcc.Graph(id='live-graph', figure=initial_figure, config={'displayModeBar': True, 'scrollZoom': True}, style={'height': 'calc(100vh - 115px)'}, clear_on_unhover=True),
        ], style={'flex': '1', 'paddingRight': '15px'}),

        # Right Column (Sidebar: Control Panel)
        html.Div([
            html.Div([ # This is the existing control-panel div
                html.Div([html.Label("Display Window (seconds):"), dcc.Slider(id='window-slider', min=2, max=30, step=1, value=DISPLAY_WINDOW, marks={str(i): str(i) for i in range(5, 35, 5)}, updatemode='mouseup')], style=styles['control-item']),
                html.Div([html.Button('Reset', id='reset-button', n_clicks=0, style={**styles['generic-button-style'], **styles['reset-button-custom-style']})], style=styles['control-item']),
                html.Div([html.Button("Stop Stream", id='stream-toggle-button', n_clicks=0, style=styles['generic-button-style'])], style=styles['control-item']),
                html.Div([
                    html.Label("Recording File Name:"), 
                    dcc.Input(id='filename-input', type='text', placeholder='recording_data.csv', value=current_filename, style=styles['filename-input-style'])
                ], style=styles['control-item']),
                html.Div([
                    html.Button('Start Recording', id='record-button', n_clicks=0, style=styles['record-button-style'])
                ], style=styles['control-item']), # Removed textAlign:center from here, control-item handles alignment
                html.Div(id='recording-status-message', children="Recording Stopped", style={**styles['recording-status-message-style'], 'width':'100%', 'textAlign':'left'}), # Ensure this message is also full width and aligned
                html.Div([ # File Upload Section
                    dcc.Upload(
                        id='upload-data-component',
                        children=html.Div(['Drag and Drop or ', html.A('Select CSV File')]),
                        style={
                            'width': '100%', 'height': '60px', 'lineHeight': '60px',
                            'borderWidth': '1px', 'borderStyle': 'dashed',
                            'borderRadius': '5px', 'textAlign': 'center', 'margin': '10px 0' 
                        },
                        multiple=False 
                    ),
                    html.Div(id='uploaded-file-info', style={'textAlign': 'center', 'fontSize': '0.9em', 'width':'100%'})
                ], style=styles['control-item']), # control-item style applied
                html.Div([
                    html.Button("Clear and Return to Stream", id='clear-uploaded-button', n_clicks=0, style=styles['generic-button-style']) # generic-button-style now has width:100%
                ], style=styles['control-item']) # control-item style applied
            ], style={**styles['control-panel'], 'flexDirection': 'column', 'height': 'calc(100vh - 40px)', 'overflowY':'auto', 'padding':'10px'}) 
        ], style={'width': '350px', 'minWidth':'320px', 'paddingLeft': '15px', 'borderLeft': '1px solid #ccc'}) # Sidebar has a fixed base width, can grow slightly if needed, main content takes rest
    ], style={'display': 'flex', 'flexDirection': 'row'}), # Main flex container for columns
    
    # These are kept outside the two-column layout, usually for global things like intervals/stores
    dcc.Interval(id='animation-interval', interval=UPDATE_INTERVAL, n_intervals=0),
    dcc.Interval(id='data-check-interval', interval=DATA_CHECK_INTERVAL, n_intervals=0), 
    dcc.Interval(id='status-update-interval', interval=1000, n_intervals=0),
    
    dcc.Store(id='data-arrival-counter', data=0),
    dcc.Store(id='total-points-extended-to-graph', data=0),
    dcc.Store(id='last-processed-point-count', data=0),
    html.Div(id='hidden-total-points-div', style={'display': 'none'})
], style=styles['main-container']) # Removed main-container style from the top level, applied to main flex container

# ZeroMQ Veri Alıcı İş Parçacığı
def zmq_receiver():
    global times_buffer, x_buffer, y_buffer, z_buffer, last_update_time, is_receiving_data, total_points_received, receiver_active
    
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(ZMQ_SERVER)
    socket.setsockopt_string(zmq.SUBSCRIBE, "")  # Tüm mesajları al
    socket.setsockopt(zmq.RCVTIMEO, 1000)  # 1 saniye timeout
    
    # print(f"ZeroMQ alıcısı {ZMQ_SERVER} adresine bağlandı") # Keep this one if ZMQ is re-enabled
    
    # Ana alıcı döngüsü
    while receiver_active:
        try:
            # ZeroMQ'dan mesaj al
            message = socket.recv_json()
            
            # Gelen veriyi işle
            if message["type"] == "accelerometer_data":
                data = message["data"]
                times_buffer.append(data["time"])
                x_buffer.append(data["x"])
                y_buffer.append(data["y"])
                z_buffer.append(data["z"])
                
                # Durum güncellemesi
                is_receiving_data = True
                last_update_time = time.time()
                total_points_received += 1
            
        except zmq.Again:
            # Zaman aşımı - veri gelmedi
            if time.time() - last_update_time > 3.0 and last_update_time > 0:
                is_receiving_data = False
        except Exception as e:
            print(f"ZeroMQ alıcı hatası: {e}")
    
    # Bağlantıyı kapat
    socket.close()
    context.term()

# Callback to check for new data and update the data-arrival-counter
@app.callback(
    [Output('data-arrival-counter', 'data'),
     Output('last-processed-point-count', 'data')],
    [Input('data-check-interval', 'n_intervals')],
    [State('last-processed-point-count', 'data'),
     State('data-arrival-counter', 'data')]
)
def update_data_arrival_trigger(n_intervals, last_processed_count, current_arrival_count):
    global total_points_received
    if total_points_received > last_processed_count:
        new_arrival_count = current_arrival_count + 1
        # print(f"DEBUG: update_data_arrival_trigger: New data confirmed. total_pts: {total_points_received} > last_proc: {last_processed_count}. New arrival_count: {new_arrival_count}")
        return new_arrival_count, total_points_received
    return dash.no_update, dash.no_update

# MODIFIED Callback: Now re-enabling extendData, still no relayoutData for Y-axis/title
@app.callback(
    [Output('live-graph', 'extendData'), # Re-enabled
     Output('total-points-extended-to-graph', 'data')], 
    [Input('data-arrival-counter', 'data')], # Trigger only on new data batch arrival
    [State('total-points-extended-to-graph', 'data'),
     State('last-processed-point-count', 'data'), # total_points_received when batch was flagged
     # Inputs y-scale and window-slider removed as they don't directly affect data extension logic here
     # Their effect on y-axis/title will be handled separately if/when that logic is re-enabled.
    ]
)
def extend_data_and_update_yaxis(
    arrival_count, 
    current_total_extended, 
    last_batch_total_received
):
    global times_buffer, x_buffer, y_buffer, z_buffer 
    global live_stream_active, displaying_uploaded_data # Added displaying_uploaded_data

    extend_payload = dash.no_update
    new_total_extended_val = dash.no_update

    if not live_stream_active or displaying_uploaded_data: # Added displaying_uploaded_data check
        return dash.no_update, dash.no_update 

    if arrival_count is None or arrival_count == 0: 
        return dash.no_update, dash.no_update

    points_in_new_batch = last_batch_total_received - current_total_extended

    if points_in_new_batch > 0:
        # Ensure we don't try to slice more than available in deques (safety, though logic should be sound)
        points_to_slice = min(points_in_new_batch, len(times_buffer))
        
        if points_to_slice > 0:
            new_times = list(times_buffer)[-points_to_slice:]
            new_x = list(x_buffer)[-points_to_slice:]
            new_y = list(y_buffer)[-points_to_slice:]
            new_z = list(z_buffer)[-points_to_slice:]

            extend_payload_data = {
                'x': [new_times, new_times, new_times], 
                'y': [new_x, new_y, new_z]
            }
            extend_payload = (extend_payload_data, [0, 1, 2], BUFFER_SIZE) 
            new_total_extended_val = current_total_extended + points_to_slice # Update with actual number sliced and sent
            # print(f"DEBUG_EXTEND: Extending with {points_to_slice} new points. Total extended to graph: {new_total_extended_val}")
        else:
            # This case means points_in_new_batch > 0 but len(times_buffer) was 0, or points_to_slice became 0.
            # Should ideally not happen if data pipeline is consistent.
            # print(f"DEBUG_EXTEND: Warning - points_in_new_batch={points_in_new_batch} but points_to_slice={points_to_slice}")
            pass # No data to send, new_total_extended_val remains dash.no_update or its previous value

    # If new_total_extended_val wasn't updated, ensure it is dash.no_update or reflects no change
    if new_total_extended_val == dash.no_update and current_total_extended is not None:
        new_total_extended_val = current_total_extended # No change to the count
        
    return extend_payload, new_total_extended_val

# NEW Callback for Reset button and Initial Figure Configuration
@app.callback(
    [Output('live-graph', 'figure', allow_duplicate=True),
     Output('total-points-extended-to-graph', 'data', allow_duplicate=True),
     Output('data-arrival-counter', 'data', allow_duplicate=True),
     Output('last-processed-point-count', 'data', allow_duplicate=True)],
    [Input('reset-button', 'n_clicks'),
     Input('window-slider', 'value')],
    prevent_initial_call=True
)
def handle_reset_and_initial_figure(reset_clicks, window_size_value):
    global times_buffer, x_buffer, y_buffer, z_buffer, base_time, initial_wall_clock_time, total_points_received, DISPLAY_WINDOW

    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

    if triggered_id == 'window-slider':
        DISPLAY_WINDOW = window_size_value

    if triggered_id == 'reset-button':
        times_buffer.clear(); x_buffer.clear(); y_buffer.clear(); z_buffer.clear()
        base_time = None
        initial_wall_clock_time = None
        total_points_received = 0 
        
        fig = create_initial_figure(DISPLAY_WINDOW) 
        return fig, 0, 0, 0 

    if triggered_id == 'window-slider' and initial_wall_clock_time is None:
        fig = create_initial_figure(DISPLAY_WINDOW) 
        return fig, dash.no_update, dash.no_update, dash.no_update

    return dash.no_update, dash.no_update, dash.no_update, dash.no_update

# Callback for X-axis animation (now using full figure update) - more frequent
@app.callback(
    Output('live-graph', 'figure', allow_duplicate=True),
    [Input('animation-interval', 'n_intervals')], 
    [State('window-slider', 'value'), 
     State('live-graph', 'figure')],
    prevent_initial_call=True
)
def animate_xaxis_view(n_intervals, window_size_value, current_fig):
    global initial_wall_clock_time, DISPLAY_WINDOW, displaying_uploaded_data

    if displaying_uploaded_data: # If showing uploaded data, don't animate
        return dash.no_update
        
    DISPLAY_WINDOW = window_size_value

    if initial_wall_clock_time is None or current_fig is None:
        return dash.no_update 

    current_virtual_x_end = time.time() - initial_wall_clock_time
    x_axis_start = max(0, current_virtual_x_end - DISPLAY_WINDOW)
    
    new_xaxis_range = [x_axis_start, current_virtual_x_end]

    new_fig = { 
        'data': current_fig.get('data', []),
        'layout': current_fig.get('layout', {}).copy()
    }
    
    # Update ranges for all x-axes (xaxis, xaxis2, xaxis3 for subplots)
    for i in range(1, 4): # Assumes 3 subplots
        axis_name = 'xaxis' if i == 1 else f'xaxis{i}'
        if axis_name in new_fig['layout']:
            new_fig['layout'][axis_name]['range'] = new_xaxis_range
        else:
            # This case might occur if the initial figure didn't have these axes fully defined,
            # though make_subplots usually handles it. Adding for safety.
            new_fig['layout'][axis_name] = dict(range=new_xaxis_range)
    
    if 'uirevision' not in new_fig['layout']:
        new_fig['layout']['uirevision'] = 'constant'

    if n_intervals is not None and n_intervals % 15 == 0: 
        data_summary = "Figure data key missing or empty/invalid structure in new_fig"
        fig_data = new_fig.get('data')
        if fig_data and isinstance(fig_data, list) and len(fig_data) > 0 and \
           isinstance(fig_data[0], dict) and 'x' in fig_data[0] and \
           isinstance(fig_data[0].get('x'), list):
            data_summary = f"Trace 0 X-len in new_fig: {len(fig_data[0]['x'])}"
        
        # print(f"DEBUG_ANIM_FIGURE_UPDATE: X-Range: [{x_axis_start:.2f}, {current_virtual_x_end:.2f}], {data_summary}") # Removed this verbose one
    
    return new_fig

# Callback for status indicators
@app.callback(
    [Output('connection-status', 'children'),
     Output('connection-status', 'style'),
     Output('data-count', 'children'),
     Output('last-update', 'children')],
    [Input('status-update-interval', 'n_intervals')]
)
def update_status_indicators(n_intervals):
    global is_receiving_data, total_points_received, last_update_time
    
    status_text = "No Connection"
    status_style = {'color': 'red', 'fontSize': '1.2em', 'fontWeight': 'bold'}
    if is_receiving_data and (time.time() - last_update_time < 5): # Add a timeout for "Bağlı" status
        status_text = "Connected"
        status_style['color'] = 'green'
    
    count_text = f"{total_points_received} points"
    
    time_text_val = "No data yet"
    if last_update_time > 0:
        seconds_ago = time.time() - last_update_time
        if seconds_ago < 1.5 and is_receiving_data : # show "şimdi" if very recent
             time_text_val = "updated just now"
        elif seconds_ago < 60:
            time_text_val = f"{seconds_ago:.1f} seconds ago"
        else:
            time_text_val = f"{seconds_ago/60:.1f} minutes ago"
    
    return status_text, status_style, count_text, time_text_val

# Callback for Recording Duration display
@app.callback(
    Output('recording-duration-display', 'children'),
    [Input('status-update-interval', 'n_intervals')] # Uses the same 1-second interval as other status updates
)
def update_recording_duration(n_intervals):
    global initial_wall_clock_time
    if initial_wall_clock_time is not None:
        duration_seconds = time.time() - initial_wall_clock_time
        return f"{duration_seconds:.1f} seconds"
    return "-- seconds"

# Callback to toggle recording
@app.callback(
    [Output('record-button', 'children'),
     Output('recording-status-message', 'children'),
     Output('filename-input', 'value')],
    [Input('record-button', 'n_clicks')],
    [State('filename-input', 'value')],
    prevent_initial_call=True
)
def toggle_recording(n_clicks, filename_from_input):
    global is_recording, current_filename, csv_writer_object, output_file_stream

    button_label = "Start Recording"
    status_message = "Recording Stopped"
    updated_filename_for_ui = filename_from_input # Keep current UI value unless recording starts
    final_button_style = styles['record-button-style'].copy() # Start with default green

    if n_clicks > 0: 
        is_recording = not is_recording 

        if is_recording:
            base_name = filename_from_input.strip()
            if not base_name:
                base_name = "accelerometer_data"
            
            # Remove .csv if present, then add timestamp and .csv
            if base_name.lower().endswith('.csv'):
                base_name = base_name[:-4]
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Define the data directory and create it if it doesn't exist
            data_directory = "data"
            os.makedirs(data_directory, exist_ok=True)
            
            current_filename = os.path.join(data_directory, f"{base_name}_{timestamp}.csv")
            updated_filename_for_ui = current_filename # Update UI with new timestamped name
            
            try:
                file_exists = os.path.exists(current_filename)
                output_file_stream = open(current_filename, mode='a', newline='')
                csv_writer_object = csv.writer(output_file_stream)
                
                if not file_exists or os.path.getsize(current_filename) == 0:
                    csv_writer_object.writerow(['timestamp', 'ax', 'ay', 'az'])
                
                button_label = "Stop Recording"
                status_message = f"Recording to: {current_filename}"
                final_button_style.update(styles['record-button-stop-style']) # Change to red
            except Exception as e:
                is_recording = False 
                status_message = f"Error: {str(e)}"
                updated_filename_for_ui = filename_from_input # Revert UI filename on error
                if output_file_stream:
                    output_file_stream.close()
                csv_writer_object = None
                output_file_stream = None
        else:
            # Stopping recording - current_filename already holds the name of the file that was being written to
            if output_file_stream is not None:
                output_file_stream.close()
                output_file_stream = None
            csv_writer_object = None
            button_label = "Start Recording"
            status_message = f"Recording Stopped: {current_filename}" # Show the name of the file that was just saved
            updated_filename_for_ui = current_filename # Keep the saved filename in the input field
            # Button style reverts to default green (already set)
    
    # The button style is now part of the main Output list, not a separate one
    # It needs to be returned. We will return the style dictionary directly.
    # However, Dash Output for 'style' expects a dictionary.
    # Let's modify the record-button to have style as Output to directly update it.

    # For now, I will adjust the callback to only return the three specified outputs.
    # The button style will be handled by its initial style and conditional CSS if Dash supported it directly via class, 
    # or by adding a separate Output for the button's style if needed.
    # The current approach in styles dict relies on fixed IDs or manual application in the layout.
    # Let's assume for now the color change will be managed by changing the button text and user understanding.
    # A more dynamic style change would require Output('record-button', 'style').

    return button_label, status_message, updated_filename_for_ui

# Callback to toggle live stream
@app.callback(
    Output('stream-toggle-button', 'children'),
    [Input('stream-toggle-button', 'n_clicks')],
    prevent_initial_call=True
)
def toggle_live_stream(n_clicks):
    global live_stream_active
    if n_clicks > 0:
        live_stream_active = not live_stream_active
    
    if live_stream_active:
        return "Stop Stream"
    else:
        return "Start Stream"

# Callback to parse uploaded CSV data
@app.callback(
    [Output('uploaded-file-info', 'children'),
     Output('stream-toggle-button', 'children', allow_duplicate=True), # To update stream button text
     Output('live-graph', 'figure', allow_duplicate=True)], # To clear graph AND PLOT UPLOADED DATA
    [Input('upload-data-component', 'contents')],
    [State('upload-data-component', 'filename')],
    prevent_initial_call=True
)
def parse_uploaded_data(contents, filename):
    global uploaded_data_buffer, live_stream_active, displaying_uploaded_data, initial_wall_clock_time, DISPLAY_WINDOW
    
    content_type, content_string = contents.split(',') if contents else (None, None)
    stream_button_text = "Stop Stream" 
    new_figure_on_upload = dash.no_update
    upload_message = dash.no_update

    if content_string is not None and filename is not None:
        try:
            if 'csv' in filename.lower():
                decoded_bytes = base64.b64decode(content_string)
                decoded_string = decoded_bytes.decode('utf-8')
                
                csvfile = io.StringIO(decoded_string)
                reader = csv.DictReader(csvfile)
                
                temp_t, temp_x, temp_y, temp_z = [], [], [], []
                for row in reader:
                    try:
                        temp_t.append(float(row['timestamp'])) 
                        temp_x.append(float(row['ax']))
                        temp_y.append(float(row['ay']))
                        temp_z.append(float(row['az']))
                    except KeyError as ke:
                        return f"Error: Expected column not found in CSV ({ke}). Headers should be: timestamp, ax, ay, az.", stream_button_text, dash.no_update
                    except ValueError as ve:
                         return f"Error: Non-numeric data in CSV ({ve}). Row: {row}", stream_button_text, dash.no_update

                uploaded_data_buffer['t'] = temp_t
                uploaded_data_buffer['x'] = temp_x
                uploaded_data_buffer['y'] = temp_y
                uploaded_data_buffer['z'] = temp_z
                
                live_stream_active = False
                displaying_uploaded_data = True # Set to true as we are now displaying this
                initial_wall_clock_time = None 
                stream_button_text = "Start Stream" 
                
                # Create and plot the figure for uploaded data directly
                fig = make_subplots(
                    rows=3, cols=1, 
                    shared_xaxes=True, 
                    subplot_titles=('X Axis (Uploaded)', 'Y Axis (Uploaded)', 'Z Axis (Uploaded)'),
                    vertical_spacing=0.05
                )
                fig.add_trace(go.Scattergl(x=uploaded_data_buffer['t'], y=uploaded_data_buffer['x'], name='X (Uploaded)', mode='lines', line=dict(color='blue', width=1)), row=1, col=1)
                fig.add_trace(go.Scattergl(x=uploaded_data_buffer['t'], y=uploaded_data_buffer['y'], name='Y (Uploaded)', mode='lines', line=dict(color='red', width=1)), row=2, col=1)
                fig.add_trace(go.Scattergl(x=uploaded_data_buffer['t'], y=uploaded_data_buffer['z'], name='Z (Uploaded)', mode='lines', line=dict(color='green', width=1)), row=3, col=1)

                graph_title = "Uploaded Accelerometer Data"
                if filename:
                    graph_title += f": {filename}"
                
                min_time = 0
                max_time = DISPLAY_WINDOW 
                if uploaded_data_buffer['t']:
                    min_time = min(uploaded_data_buffer['t'])
                    max_time = max(uploaded_data_buffer['t'])
                    if max_time - min_time < 0.1: 
                        max_time = min_time + 0.1 

                fig.update_layout(
                    title_text=graph_title,
                    height=600, 
                    showlegend=False,
                    margin=dict(l=50, r=30, t=50, b=30),
                    plot_bgcolor='white'
                )
                fig.update_xaxes(
                    range=[min_time, max_time], 
                    showgrid=False,
                    showticklabels=True 
                ) 
                fig.update_yaxes(
                    range=[-15, 15], 
                    autorange=False, 
                    showgrid=False
                )
                new_figure_on_upload = fig
                upload_message = f'{filename} uploaded and plotted ({len(temp_t)} rows).'

                return upload_message, stream_button_text, new_figure_on_upload
            else:
                upload_message = 'Error: Please upload a CSV file.'
                # Ensure live graph isn't accidentally cleared if it's not a CSV
                # but still allow stream button text to update if live_stream_active was toggled by logic above
                # However, since we only change live_stream_active on successful CSV, this might be fine
                return upload_message, stream_button_text, dash.no_update # Return current stream_button_text
        except Exception as e:
            print(f"File processing error: {e}")
            upload_message = f'File processing error: {str(e)}'
            return upload_message, stream_button_text, dash.no_update # Return current stream_button_text
    
    return dash.no_update, dash.no_update, dash.no_update

# Callback to clear uploaded data and return to live stream mode
@app.callback(
    [Output('live-graph', 'figure', allow_duplicate=True),
     Output('stream-toggle-button', 'children', allow_duplicate=True),
     Output('uploaded-file-info', 'children', allow_duplicate=True),
     Output('total-points-extended-to-graph', 'data', allow_duplicate=True),
     Output('data-arrival-counter', 'data', allow_duplicate=True),
     Output('last-processed-point-count', 'data', allow_duplicate=True)],
    [Input('clear-uploaded-button', 'n_clicks')],
    prevent_initial_call=True
)
def clear_uploaded_data_and_reset_stream(n_clicks):
    global uploaded_data_buffer, displaying_uploaded_data, live_stream_active, initial_wall_clock_time
    global times_buffer, x_buffer, y_buffer, z_buffer, base_time, total_points_received, DISPLAY_WINDOW

    if n_clicks == 0:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    # Clear uploaded data buffer
    uploaded_data_buffer = {'t': [], 'x': [], 'y': [], 'z': []}
    displaying_uploaded_data = False
    
    # Reset states for live streaming
    live_stream_active = True
    initial_wall_clock_time = None # Will be set on next live data packet
    base_time = None
    total_points_received = 0
    
    # Clear live data buffers as well, similar to reset button
    times_buffer.clear()
    x_buffer.clear()
    y_buffer.clear()
    z_buffer.clear()

    fig = create_initial_figure(DISPLAY_WINDOW)
    stream_button_text = "Stop Stream"
    uploaded_info_text = "Uploaded data cleared. Live stream active."
    
    # Reset counters
    new_total_extended = 0
    new_arrival_count = 0
    new_last_processed_count = 0

    return fig, stream_button_text, uploaded_info_text, new_total_extended, new_arrival_count, new_last_processed_count

# HTTP endpoint to receive sensor data
@app.server.route('/sensor', methods=['POST'])
def receive_sensor_data():
    global times_buffer, x_buffer, y_buffer, z_buffer, last_update_time, is_receiving_data, total_points_received, base_time, initial_wall_clock_time
    global is_recording, csv_writer_object 
    global live_stream_active # Added live_stream_active global
    data_str = ""
    try:
        if not live_stream_active:
            return "OK - Stream paused", 200 # Stream paused, do nothing with data

        reception_time = time.time()
        data_str = flask.request.data.decode('utf-8')
        parsed = json.loads(data_str)
        acc_data = [entry for entry in parsed.get('payload', []) if entry.get('name') == 'accelerometer']
        if not acc_data: return "OK - No accelerometer data", 200

        new_points_in_batch = 0
        if base_time is None:
            with threading.Lock(): 
                if base_time is None:
                    base_time = acc_data[0]['time']
                    initial_wall_clock_time = time.time()
                    # print(f"DEBUG: GLOBAL initial_wall_clock_time SET to: {initial_wall_clock_time:.3f} with base_time: {base_time}")
        
        for entry in acc_data:
            if base_time is None: continue
            real_time = (entry['time'] - base_time) / 1e9
            times_buffer.append(real_time)
            x_buffer.append(entry['values']['x'])
            y_buffer.append(entry['values']['y'])
            z_buffer.append(entry['values']['z'])
            new_points_in_batch += 1

            # Write to CSV if recording is active
            if is_recording and csv_writer_object is not None:
                csv_writer_object.writerow([real_time, entry['values']['x'], entry['values']['y'], entry['values']['z']])
        
        if new_points_in_batch > 0:
            is_receiving_data = True
            last_update_time = time.time()
            total_points_received_before_add = total_points_received # For debug
            total_points_received += new_points_in_batch
            # print(f"DEBUG: Sensor data processed. Points in batch: {new_points_in_batch}, Total global: {total_points_received} (was {total_points_received_before_add})")
        return "OK", 200
    except Exception as e:
        print(f"Sensor data error: {e}, Data snippet: {data_str[:200]}") # Keep this important error message
        return flask.jsonify({'success': False, 'message': str(e)}), 500

# Basit bir root sayfası sağlamak için
@app.callback(
    Output('last-data', 'children'),
    [Input('status-update-interval', 'n_intervals')]
)
def update_last_data(n):
    return json.dumps({'total_points': total_points_received, 'buffer_size': len(times_buffer)})

# ZeroMQ alıcı iş parçacığını başlat (If still needed, otherwise can be removed)
# receiver_thread = threading.Thread(target=zmq_receiver)
# receiver_thread.daemon = True
# receiver_thread.start()

# Uygulama kapatılırken temizlik yapacak fonksiyon
def cleanup():
    global receiver_active
    receiver_active = False
    print("Application shutting down...")
    # if receiver_thread.is_alive():
    #     receiver_thread.join()

# Loglama mesajlarını bastır
os.environ['DASH_SILENCE_ROUTES_LOGGING'] = 'true'

# Uygulamayı başlat
if __name__ == '__main__':
    import atexit
    atexit.register(cleanup)
    print("Starting Dash application...")
    print(f"Access at: http://{LOCAL_IP_ADDRESS}:{app.server.config.get('PORT', 8080)} or http://localhost:{app.server.config.get('PORT', 8080)}")
    print(f"HTTP endpoint for sensor data: http://{LOCAL_IP_ADDRESS}:{app.server.config.get('PORT', 8080)}/sensor")
    print(f"Display window: {DISPLAY_WINDOW}s, Animation interval: {UPDATE_INTERVAL}ms, Data check interval: {DATA_CHECK_INTERVAL}ms")
    app.run(debug=False, host='0.0.0.0', port=8080) 