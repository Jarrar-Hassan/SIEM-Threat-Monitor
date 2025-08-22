import os
import time
import psutil
import threading
from datetime import datetime
from collections import deque
import pandas as pd
import plotly.express as px
from dash import Dash, dcc, html, Input, Output
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


MONITORED_DIR = os.path.expanduser("~")

# 🔍 FILTERS: Skip temporary files and system-internal junk to reduce noise.
IGNORED_EXTENSIONS = ['.tmp', '.log', '.ldb', '.sqlite', '.dat', '.lock', '.exe']
IGNORED_KEYWORDS = ['AppData\\Local', 'Microsoft\\Edge', 'Windows', 'System32', 'EBWebView', 'CustomDestinations', '.git']
MAX_LOG_ENTRIES = 500
MAX_ALERT_ENTRIES = 100

# ==================== GLOBAL STATE & HELPERS ====================
LOGS = deque(maxlen=MAX_LOG_ENTRIES)
ALERTS = deque(maxlen=MAX_ALERT_ENTRIES)
START_TIME = datetime.now()
SEEN_PIDS = set()


def current_time():
    """Returns the current time in a formatted string."""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def is_relevant_file(path):
    """Checks if a file path is relevant for monitoring."""
    ext = os.path.splitext(path)[1].lower()
    if ext in IGNORED_EXTENSIONS:
        return False
    if any(keyword.lower() in path.lower() for keyword in IGNORED_KEYWORDS):
        return False
    return True


def add_log(event_type, message):
    """Adds a new log entry and an alert if the event is significant."""
    log = {"timestamp": current_time(), "type": event_type, "message": message}
    LOGS.append(log)
    if event_type in ["CMD Opened", "File Deleted"]:
        ALERTS.append(log)


# ==================== FILE MONITORING THREAD ====================
class FileMonitorHandler(FileSystemEventHandler):
    """Custom event handler for the file system observer."""
    def on_deleted(self, event):
        if not event.is_directory and is_relevant_file(event.src_path):
            add_log("File Deleted", f"Deleted: {event.src_path}")

    def on_created(self, event):
        if not event.is_directory and is_relevant_file(event.src_path):
            add_log("File Created", f"Created: {event.src_path}")

    def on_modified(self, event):
        if not event.is_directory and is_relevant_file(event.src_path):
            add_log("File Modified", f"Modified: {event.src_path}")


def start_file_monitor():
    """Sets up and starts the file system observer."""
    observer = Observer()
    observer.schedule(FileMonitorHandler(), MONITORED_DIR, recursive=True)
    observer.start()
    try:
        while observer.is_alive():
            observer.join(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


# ==================== PROCESS MONITORING THREAD ====================
def get_process_command(proc):
    """Safely retrieves the command line of a process."""
    try:
        return " ".join(proc.cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return "N/A"
    except Exception:
        return ""


def monitor_processes():
    """Monitors for new processes and adds them to the logs."""
    while True:
        try:
            for proc in psutil.process_iter(['pid', 'name', 'create_time', 'cmdline']):
                if proc.info['pid'] not in SEEN_PIDS:
                    ctime = datetime.fromtimestamp(proc.info['create_time'])
                    if ctime >= START_TIME:
                        SEEN_PIDS.add(proc.info['pid'])
                        proc_name = proc.info['name']
                        command = get_process_command(proc)

                        if 'cmd' in proc_name.lower() or 'powershell' in proc_name.lower():
                            add_log("CMD Opened", f"PID {proc.info['pid']} - Command: {command}")
                        else:
                            add_log("Process Started", f"Name: {proc_name} | PID: {proc.info['pid']} | Command: {command}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        time.sleep(1)


# ==================== DASHBOARD UI ====================
app = Dash(__name__)
app.title = "System Activity Monitor"

# Professional color scheme and card style
card_style = {
    'backgroundColor': '#1E1E1E',
    'border': '1px solid #3A3A3A',
    'borderRadius': '8px',
    'padding': '20px',
    'boxShadow': '0 4px 8px rgba(0,0,0,0.3)',
}

app.layout = html.Div(style={'backgroundColor': "#121212", 'color': '#E0E0E0', 'fontFamily': 'Roboto, sans-serif', 'padding': '30px'},
    children=[
        html.H1(
            [html.Img(src='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADIAAAAyCAYAAAAeP4ixAAAACXBIWXMAAAsTAAALEwEAmpwYAAADwUlEQVR4nO2Xf0wUBxTHv2/Lw3gCg4Ngg0Eig0EwYnKjX0TjB41G40d/yIkaLzUaTzSaJqIgaqJiEBNqf9JoRCMGDRaNJhI3/qJiNIkJBofgBoJgB5IgsXfI7s6+d3fT7e7uw+7u7sP2B/877+7d8/aP+u7u7u7tH/7P/2/s7t1cMhgKBAJBk9h8yCVSL7dD/j/9zPz7y+7vL+/vL48+P779+Pz8cEhhKAgHAl1AIO4Egtf5D+Tf/M38/2H4+ffn39+Xg4FA4CgqFgh0A4KBD9BwH4T5hX9n/3v8+/vL4+efX35+ftYwGAoGA4EA7sHBDp9n4f0Dq23+1vLg8+jzhzX2b662/0gP+N9b2/90k2Y+P7/M5l/y8Jc8fG6l/4vFfLpD/n1P3/V7D/XJ/nFvO/w+P9/1C5YmGAwGAwLBgODv/4fB8d+Rz1928n7zN9wBwWAwGMj3hX8H+L/G/7WkO7z/qU7w/8D/6b8P4L8t6+wHgmAwGAwGAhYIBgMCwYCZ8mG+15Kufy/J6VfL/1Xy+Hckp18u/1fJ49+RnL3d+W/H5n+3dvyH4+Nfsv/92gq9S8kfB+VfsuTz03y7b/f9i/r+w/p+w/6vT/Q+r2v92k+Yf9g/f9Qv+8yv2/f/d94fB4f/d94fB4b+g2P9p/3C+w/X9B/2C/t8T9g+r2v930m9m+vPz5d/V8vg3H+eX/G6k3830n/Uf+P8b89eT84tB+4+b33+g3D8G7T9s8X/P2n+g3D/A/nEw/wB6h/2v+rYf9g//8/a/h8Fv+k3h/z/v3z8C8B+t8D+9f7gM7z9s/j8H97+fDIfDYDBI3h8+P5/9431/D/H+A/4/wA8EgmAwGAxS83/Q/b9I7v9JdP915t8dDP1D4D9I8x+I/Nvh1bZ//jA4GAwGA4EB/3f7T/D/2/P1vJqMfhfW+93p/1Xp/z3cO71/1h+j/7Xo++H97s2t7//+7/l/Yn7+v2H4A/H+g/L/u9Mv4B8IhsF+f3C+/f7Q/v/vB/+vM/w+n++wW3V6f/B/fD6k7n9A/t+w/X8n4/MvYf3A/f2u83sEwGAwGAoIBwcAgGAgEA2LgDwwgGAgGAoGBsF843+3w32Xl/7b2e9894O/N+v2C/L2U9m//b19Lg4EBAY+v4P80Yx8A4k/f6b+b2D8yBfPzD2D4f9j5r6+h/92V/s2D//2D/x77/gP+35r/+w/cQdDPA+k+v7u8v2/xXh8N+M9PzP62xPwDw/+oGA2GwGAgGBgKBv79n8X827B8G+89B+89e/m/j/4T6j3887P8w+n+P/+XmD4PBQCAYBAIBgcDfB9zG/r9P7y+n/41D/s/T/Q4H/wGAwCAYCAQCAQGA/+4/8P8f+35l/f356x/Q5D/n/5bE/09D/A+j/I9B/LgQCAoGBQCAQCBgIBoNgsH94wP/tB/q5n/3/D/sH/b2m+A6T/nEw/wB+M/4G+z8cDIbBYDAYCIKByF0I7H2P/8eR/43d/H89/j+n/s/V/h/T/M9h/59XfT/q/n+s+f8E4H80GAgEAkGz/4D7D2D/H3f6b7c/oO6/5+7/W7d/8N/B8P7T/v+L/f/3D/d/F//z+wLzH+T/h7P/8/b+3W7f30z//1X+LhYDBIOCgSDoH+H/L0j37/J/E/Efn/X/Z/v/g/h/xH4A4+H7l80AAAAASUVORK5CYII=', style={'height': '40px', 'marginRight': '15px'}),
             "System Activity Monitor"],
            style={'textAlign': 'center', 'color': '#E0E0E0', 'marginBottom': '30px', 'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center'}),

        # Row for key metrics (KPIs)
        html.Div(style={'display': 'flex', 'flexWrap': 'wrap', 'gap': '20px', 'marginBottom': '40px'},
            children=[
                html.Div(
                    children=[
                        html.H3("Uptime", style={'color': '#4CAF50'}),
                        html.P(id='kpi-uptime', style={'fontSize': '24px', 'fontWeight': 'bold', 'color': '#4CAF50'})
                    ],
                    style={**card_style, 'flex': 1, 'textAlign': 'center'}
                ),
                html.Div(
                    children=[
                        html.H3("Total Logs", style={'color': '#2196F3'}),
                        html.P(id='kpi-total-logs', style={'fontSize': '24px', 'fontWeight': 'bold', 'color': '#2196F3'})
                    ],
                    style={**card_style, 'flex': 1, 'textAlign': 'center'}
                ),
                html.Div(
                    children=[
                        html.H3("Total Alerts", style={'color': '#F44336'}),
                        html.P(id='kpi-total-alerts', style={'fontSize': '24px', 'fontWeight': 'bold', 'color': '#F44336'})
                    ],
                    style={**card_style, 'flex': 1, 'textAlign': 'center'}
                )
            ]),

        # Row for charts
        html.Div(style={'display': 'flex', 'flexWrap': 'wrap', 'gap': '20px', 'marginBottom': '40px'},
            children=[
                html.Div([
                    html.H2("Events Over Time", style={'textAlign': 'center', 'color': '#B0BEC5'}),
                    dcc.Graph(id='event-timeline-chart', config={'responsive': False}, style={'height': '300px'})
                ], style={**card_style, 'flex': 2}),
                html.Div([
                    html.H2("Event Type Breakdown", style={'textAlign': 'center', 'color': '#B0BEC5'}),
                    dcc.Graph(id='event-type-pie-chart', config={'responsive': False}, style={'height': '300px'})
                ], style={**card_style, 'flex': 1})
            ]),

        # Row for logs and alerts
        html.Div(style={'display': 'flex', 'flexWrap': 'wrap', 'gap': '20px'},
            children=[
                html.Div([
                    html.H2("🚨 Critical Alerts", style={'color': '#F44336', 'borderLeft': '4px solid #F44336', 'paddingLeft': '10px'}),
                    html.Div(id='alert-output',
                        style={'whiteSpace': 'pre-wrap', 'height': '200px', 'overflowY': 'auto',
                               'border': '1px solid #F44336', 'padding': '10px', 'borderRadius': '5px', 'backgroundColor': '#111111'})
                ], style={**card_style, 'flex': 1}),
                html.Div([
                    html.H2("📜 All Activity Logs", style={'color': '#2196F3', 'borderLeft': '4px solid #2196F3', 'paddingLeft': '10px'}),
                    html.Div(id='log-output',
                        style={'whiteSpace': 'pre-wrap', 'height': '300px', 'overflowY': 'auto',
                               'border': '1px solid #2196F3', 'padding': '10px', 'borderRadius': '5px', 'backgroundColor': '#111111'})
                ], style={**card_style, 'flex': 2})
            ]),

        dcc.Interval(id='interval', interval=1000, n_intervals=0)
    ])


@app.callback(
    Output('kpi-uptime', 'children'),
    Output('kpi-total-logs', 'children'),
    Output('kpi-total-alerts', 'children'),
    Output('event-timeline-chart', 'figure'),
    Output('event-type-pie-chart', 'figure'),
    Output('alert-output', 'children'),
    Output('log-output', 'children'),
    Input('interval', 'n_intervals')
)
def update_display(n):
    # Calculate key metrics
    uptime_seconds = (datetime.now() - START_TIME).total_seconds()
    uptime_display = f"{int(uptime_seconds // 3600)}h {int((uptime_seconds % 3600) // 60)}m {int(uptime_seconds % 60)}s"
    total_logs_display = str(len(LOGS))
    total_alerts_display = str(len(ALERTS))

    # Convert logs to a pandas DataFrame for easier plotting
    df = pd.DataFrame(list(LOGS))
    
    timeline_fig = {}
    pie_fig = {}
    
    if not df.empty:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['count'] = 1
        
        timeline_data = df.resample('1s', on='timestamp').count().reset_index()
        timeline_fig = px.line(
            timeline_data,
            x='timestamp',
            y='count',
            labels={'timestamp': 'Time', 'count': 'Number of Events'},
            template='plotly_dark'
        )
        timeline_fig.update_layout(xaxis_title="Time", yaxis_title="Events/Second", 
                                   paper_bgcolor='#1E1E1E', plot_bgcolor='#1E1E1E', font_color='#E0E0E0',
                                   title_font_color='#E0E0E0')
        timeline_fig.update_traces(line_color='#2196F3')

        pie_fig = px.pie(
            df,
            names='type',
            title='Event Type Breakdown',
            color_discrete_sequence=px.colors.sequential.deep,
            template='plotly_dark'
        )
        pie_fig.update_layout(paper_bgcolor='#1E1E1E', plot_bgcolor='#1E1E1E', font_color='#E0E0E0', title_font_color='#E0E0E0')

    # Prepare log and alert text displays
    alert_display = "\n".join(
        [f"[{a['timestamp']}] {a['type']} - {a['message']}" for a in reversed(list(ALERTS))]) or "No alerts yet."
    log_display = "\n".join(
        [f"[{l['timestamp']}] {l['type']} - {l['message']}" for l in reversed(list(LOGS))]) or "No logs yet."

    return (
        uptime_display,
        total_logs_display,
        total_alerts_display,
        timeline_fig,
        pie_fig,
        alert_display,
        log_display
    )


# ==================== MAIN EXECUTION BLOCK ====================
if __name__ == '__main__':
    print(f"✅ Started System Activity Monitor at {current_time()}")
    file_thread = threading.Thread(target=start_file_monitor, daemon=True)
    process_thread = threading.Thread(target=monitor_processes, daemon=True)

    file_thread.start()
    process_thread.start()
    
    app.run(debug=False, port=8050)
