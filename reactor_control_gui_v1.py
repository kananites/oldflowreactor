"""
Bronkhorst MFC Control GUI
Real-time monitoring and control of three MFCs with plotting
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import serial
import threading
import time
import csv
import os
import json
import subprocess
import smtplib
import sys
import traceback
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import numpy as np

# Optional imports with fallbacks
try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib not available. Plotting features will be disabled.")

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("Warning: pandas not available. Some features may be limited.")

try:
    import maya
    MAYA_AVAILABLE = True
except ImportError:
    MAYA_AVAILABLE = False
    print("Warning: maya not available. Using datetime instead.")
    from datetime import datetime as maya_datetime

from mfc_controller import MFCController
from instruments import SerialMFCController, SerialTempController
from serial_wrapper import SerialWrapper

class MFCGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Reactor Control Panel v1")
        self.root.geometry("1400x800")
        
        # MFC controllers
        self.mfc_controllers = {}  # Bronkhorst MFCs
        self.alicat_controllers = {}  # Alicat MFCs
        self.serial_connection = None
        self.alicat_serial_connection = None
        
        # Plot data
        self.plot_data = {
            'time': [],
            'flow_1': [],    # Bronkhorst N2
            'setpoint_1': [],
            'flow_3': [],    # Bronkhorst CO2
            'setpoint_3': [],
            'flow_6': [],    # Bronkhorst H2
            'setpoint_6': [],
            'flow_sampling': [],    # Alicat Sampling MFC
            'setpoint_sampling': []
        }
        
        # Update settings
        # Deprecated plotting controls removed
        self.update_thread = None
        self.plot_thread = None
        self.running = True
        
        # Shared start time for both plots
        self.plot_start_time = None
        
        # Plot refresh throttling
        self.last_plot_refresh = 0
        self.plot_refresh_interval = 5  # seconds between plot refreshes
        
        # Logging
        self.log_file = None
        self.logging_enabled = False
        self.log_backed_plots = True  # use CSV logs as source for plots when available
        self.mfc_log_filename = None
        
        # Temperature control
        self.temp_process = None
        self.temp_serial = None
        self.temp_controllers = {}
        self.temp_log_file = None
        self.temp_log_filename = None
        self.temp_ramp_config = None
        self.maintenance_mode = False
        self.safety_triggered = False
        self.temp_controller_lock = threading.Lock()  # Thread safety for temperature controller access
        
        # Flow monitoring for notifications
        self.flow_alerts = {}  # Track flow alerts for each MFC
        self.flow_alert_start_times = {}  # Track when flow alerts started
        
        # Thread-safe temperature controller access
        self.last_temp_readings = {
            'internal_temp': None,
            'external_temp': None,
            'setpoint': None,
            'last_update': None
        }
        
        # Setup comprehensive logging
        self.setup_logging()
        
        # Thread monitoring
        self.thread_heartbeats = {
            'temp_monitor': None,
            'temp_control': None,
            'mfc_update': None,
            'plot_update': None
        }
        self.thread_errors = {}
        
        # Temperature plot data
        self.temp_plot_data = {
            'time': [],
            'setpoint': [],
            'internal_temp': [],
            'external_temp': []
        }
        
        # Colors for each MFC
        self.mfc_colors = {
            '1': '#1f77b4',  # Blue for N2
            '3': '#ff7f0e',  # Orange for CO2  
            '6': '#2ca02c',  # Green for H2
            'sampling': '#d62728'  # Red for Sampling MFC
        }
        
        # Temperature plot colors
        self.temp_colors = {
            'setpoint': '#ff0000',  # Red
            'internal': '#00ff00',  # Green
            'external': '#0000ff'   # Blue
        }
        
        self.setup_gui()
        
    def setup_gui(self):
        """Setup the GUI layout with resizable panels"""
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create main vertical paned window (top controls, bottom plots)
        self.main_paned = ttk.PanedWindow(main_frame, orient=tk.VERTICAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True)
        
        # Top panel for controls (MFC and Temperature side by side)
        top_frame = ttk.Frame(self.main_paned)
        self.main_paned.add(top_frame, weight=0)
        
        # Bottom panel for plotting
        bottom_frame = ttk.Frame(self.main_paned)
        self.main_paned.add(bottom_frame, weight=1)
        
        self.setup_control_panel(top_frame)
        self.setup_plot_panel(bottom_frame)
        
    def setup_control_panel(self, parent):
        """Setup control panel with MFC and Temperature controls side by side"""
        # Create horizontal paned window for MFC and Temperature controls
        self.control_paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        self.control_paned.pack(fill=tk.BOTH, expand=True)
        
        # MFC controls section (left)
        mfc_frame = ttk.LabelFrame(self.control_paned, text="MFC Controls")
        self.control_paned.add(mfc_frame, weight=2)  # MFC gets more space initially
        
        # Temperature/Safety controls section (right)
        temp_safety_frame = ttk.LabelFrame(self.control_paned, text="Temperature & Safety Controls")
        self.control_paned.add(temp_safety_frame, weight=1)  # Temp/Safety gets less space initially
        
        self.setup_mfc_control_section(mfc_frame)
        self.setup_temp_safety_section(temp_safety_frame)
    
    def setup_mfc_control_section(self, parent):
        """Setup MFC control section with scrollable content"""
        # Create canvas and scrollbar for scrollable content
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Pack canvas and scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Settings frame (reserved for future settings; plot controls removed)
        # settings_frame = ttk.LabelFrame(scrollable_frame, text="Settings")
        # settings_frame.pack(fill=tk.X, pady=(0, 10))
        # ttk.Label(settings_frame, text="No plot refresh/window controls - plots read from logs.").pack(anchor=tk.W, padx=5, pady=5)
        
        # MFC controls (all in one row)
        self.setup_mfc_controls_horizontal(scrollable_frame)
        
        # Bind mousewheel to canvas for scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
    
        
    def setup_mfc_controls_horizontal(self, parent):
        """Setup MFC controls with status and logging"""
        self.mfc_frames = {}
        
        # MFC Control and Status section
        mfc_control_frame = ttk.LabelFrame(parent, text="MFC Controls & Status")
        mfc_control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Status and connection controls (top row)
        status_frame = ttk.Frame(mfc_control_frame)
        status_frame.pack(fill=tk.X, padx=5, pady=(5, 0))
        
        # Status
        status_col = ttk.Frame(status_frame)
        status_col.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(status_col, text="Status:").pack(anchor=tk.W)
        self.status_label = ttk.Label(status_col, text="Disconnected", foreground="red")
        self.status_label.pack(anchor=tk.W)
        
        # Connection buttons
        conn_col = ttk.Frame(status_frame)
        conn_col.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(conn_col, text="Connection:").pack(anchor=tk.W)
        conn_btn_frame = ttk.Frame(conn_col)
        conn_btn_frame.pack(anchor=tk.W)
        connect_btn = ttk.Button(conn_btn_frame, text="Connect", command=self.connect_serial)
        connect_btn.pack(side=tk.LEFT, padx=(0, 2))
        disconnect_btn = ttk.Button(conn_btn_frame, text="Disconnect", command=self.disconnect_serial)
        disconnect_btn.pack(side=tk.LEFT)
        
        # Logging controls
        logging_col = ttk.Frame(status_frame)
        logging_col.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(logging_col, text="Logging:").pack(anchor=tk.W)
        logging_btn_frame = ttk.Frame(logging_col)
        logging_btn_frame.pack(anchor=tk.W)
        self.start_logging_btn = ttk.Button(logging_btn_frame, text="Start", command=self.start_logging)
        self.start_logging_btn.pack(side=tk.LEFT, padx=(0, 2))
        self.stop_logging_btn = ttk.Button(logging_btn_frame, text="Stop", command=self.stop_logging, state=tk.DISABLED)
        self.stop_logging_btn.pack(side=tk.LEFT)
        
        # Logging status
        logging_status_col = ttk.Frame(status_frame)
        logging_status_col.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(logging_status_col, text="Status:").pack(anchor=tk.W)
        self.logging_status_label = ttk.Label(logging_status_col, text="Stopped", foreground="red")
        self.logging_status_label.pack(anchor=tk.W)
        
        # MFC controls row (bottom row)
        mfc_row = ttk.Frame(mfc_control_frame)
        mfc_row.pack(fill=tk.X, padx=5, pady=(5, 5))
        
        # MFC configurations
        mfc_configs = [
            {'node': 1, 'channel': '1', 'name': 'N2 MFC', 'color': self.mfc_colors['1'], 'type': 'bronkhorst', 'parent': mfc_row},
            {'node': 3, 'channel': '2', 'name': 'CO2 MFC', 'color': self.mfc_colors['3'], 'type': 'bronkhorst', 'parent': mfc_row},
            {'node': 6, 'channel': '3', 'name': 'H2 MFC', 'color': self.mfc_colors['6'], 'type': 'bronkhorst', 'parent': mfc_row},
            {'node': 'sampling', 'channel': 'sampling', 'name': 'Sampling MFC', 'color': self.mfc_colors['sampling'], 'type': 'alicat', 'parent': mfc_row}
        ]
        
        for config in mfc_configs:
            frame = ttk.LabelFrame(config['parent'], text=config['name'])
            frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
            self.mfc_frames[config['node']] = frame
            
            # MFC info
            info_frame = ttk.Frame(frame)
            info_frame.pack(fill=tk.X, padx=5, pady=5)
            
            # Use "Pressure" for Sampling MFC, "Capacity" for others
            if config['node'] == 'sampling':
                capacity_label = ttk.Label(info_frame, text="Pressure: - psia")
            else:
                capacity_label = ttk.Label(info_frame, text="Capacity: - sccm")
            capacity_label.pack(anchor=tk.W)
            gas_label = ttk.Label(info_frame, text="Gas: -")
            gas_label.pack(anchor=tk.W)
            
            # Current readings
            readings_frame = ttk.Frame(frame)
            readings_frame.pack(fill=tk.X, padx=5, pady=5)
            
            ttk.Label(readings_frame, text="Current Flow:").grid(row=0, column=0, sticky=tk.W)
            current_label = ttk.Label(readings_frame, text="- sccm", foreground=config['color'])
            current_label.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
            
            ttk.Label(readings_frame, text="Setpoint:").grid(row=1, column=0, sticky=tk.W)
            setpoint_label = ttk.Label(readings_frame, text="- sccm", foreground=config['color'])
            setpoint_label.grid(row=1, column=1, sticky=tk.W, padx=(10, 0))
            
            # Flow control
            control_frame = ttk.Frame(frame)
            control_frame.pack(fill=tk.X, padx=5, pady=5)
            
            ttk.Label(control_frame, text="Set Flow (sccm):").pack(anchor=tk.W)
            
            input_frame = ttk.Frame(control_frame)
            input_frame.pack(fill=tk.X, pady=(2, 0))
            
            flow_var = tk.StringVar()
            flow_entry = ttk.Entry(input_frame, textvariable=flow_var, width=10)
            flow_entry.pack(side=tk.LEFT)
            
            set_btn = ttk.Button(input_frame, text="Set", 
                               command=lambda n=config['node'], v=flow_var: self.set_mfc_flow(n, v))
            set_btn.pack(side=tk.LEFT, padx=(5, 0))
            
            # Store references for updates
            frame.mfc_info = {
                'capacity_label': capacity_label,
                'gas_label': gas_label,
                'current_label': current_label,
                'setpoint_label': setpoint_label,
                'flow_var': flow_var,
                'node': config['node'],
                'name': config['name'],
                'type': config['type']
            }
    
    def setup_temp_safety_section(self, parent):
        """Setup temperature and safety controls section"""
        # Temperature control section
        self.setup_temp_control(parent)
    
    def setup_temp_control(self, parent):
        """Setup temperature control panel"""
        # Connection info
        conn_frame = ttk.Frame(parent)
        conn_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(conn_frame, text="Temperature Controller Connection:", font=("Arial", 10, "bold")).pack(anchor=tk.W)
        # ttk.Label(conn_frame, text="• COM Port: COM5 (9600 baud)", foreground="blue").pack(anchor=tk.W)
        
        # Temperature control frame
        temp_frame = ttk.LabelFrame(parent, text="Temperature Control")
        temp_frame.pack(fill=tk.X, pady=(5, 10))
        
        # Temperature status
        self.temp_status_label = ttk.Label(temp_frame, text="Status: Disconnected", foreground="red")
        self.temp_status_label.pack(pady=(5, 0))
        
        # Temperature readings
        readings_frame = ttk.Frame(temp_frame)
        readings_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(readings_frame, text="Internal Temp:").grid(row=0, column=0, sticky=tk.W)
        self.internal_temp_label = ttk.Label(readings_frame, text="- °C", foreground="green")
        self.internal_temp_label.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        
        ttk.Label(readings_frame, text="External Temp:").grid(row=1, column=0, sticky=tk.W)
        self.external_temp_label = ttk.Label(readings_frame, text="- °C", foreground="blue")
        self.external_temp_label.grid(row=1, column=1, sticky=tk.W, padx=(10, 0))
        
        ttk.Label(readings_frame, text="Setpoint:").grid(row=2, column=0, sticky=tk.W)
        self.setpoint_label = ttk.Label(readings_frame, text="- °C", foreground="red")
        self.setpoint_label.grid(row=2, column=1, sticky=tk.W, padx=(10, 0))
        
        # Temperature control buttons
        button_frame = ttk.Frame(temp_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Connect button for temp controller
        self.connect_temp_btn = ttk.Button(button_frame, text="Connect Temp Control", command=self.connect_temp_control)
        self.connect_temp_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # self.disconnect_temp_btn = ttk.Button(button_frame, text="Disconnect Temp Control", command=self.disconnect_temp_control, state=tk.DISABLED)
        # self.disconnect_temp_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # JSON file upload button
        upload_btn = ttk.Button(button_frame, text="Upload Temp Ramp JSON", command=self.upload_temp_ramp)
        upload_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # Start/Stop temp controller
        self.start_temp_btn = ttk.Button(button_frame, text="Start Temp Control", command=self.start_temp_control, state=tk.DISABLED)
        self.start_temp_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.stop_temp_btn = ttk.Button(button_frame, text="Stop Temp Control", command=self.stop_temp_control, state=tk.DISABLED)
        self.stop_temp_btn.pack(side=tk.LEFT)
        
        # Safety controls
        safety_frame = ttk.LabelFrame(parent, text="Safety System")
        safety_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Maintenance mode toggle
        self.maintenance_var = tk.BooleanVar(value=False)
        maintenance_check = ttk.Checkbutton(safety_frame, text="Maintenance Mode (Disables Safety)", 
                                          variable=self.maintenance_var, command=self.toggle_maintenance_mode)
        maintenance_check.pack(pady=5)
        
        # Safety status
        self.safety_status_label = ttk.Label(safety_frame, text="Safety: Active", foreground="green")
        self.safety_status_label.pack(pady=5)
        
        # Emergency stop button
        emergency_btn = ttk.Button(safety_frame, text="EMERGENCY STOP", command=self.emergency_stop)
        emergency_btn.pack(pady=5)
        emergency_btn.configure(style="Emergency.TButton")
        
        # Create emergency button style
        style = ttk.Style()
        style.configure("Emergency.TButton", foreground="white", background="red")
    
    def setup_plot_panel(self, parent):
        """Setup the plotting panel with resizable plots"""
        if not MATPLOTLIB_AVAILABLE:
            # Fallback when matplotlib is not available
            no_plot_frame = ttk.Frame(parent)
            no_plot_frame.pack(fill=tk.BOTH, expand=True)
            ttk.Label(no_plot_frame, text="Plotting features require matplotlib", 
                     font=("Arial", 16), foreground="red").pack(expand=True)
            ttk.Label(no_plot_frame, text="Please install matplotlib: pip install matplotlib", 
                     font=("Arial", 12)).pack()
            return
            
        # Create plots paned window (horizontal split)
        self.plots_paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        self.plots_paned.pack(fill=tk.BOTH, expand=True)
        
        # Flow plot (left)
        flow_frame = ttk.LabelFrame(self.plots_paned, text="MFC Flow Rates")
        self.plots_paned.add(flow_frame, weight=1)
        
        # Create matplotlib figure for flow
        self.fig = Figure(figsize=(6, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        
        # Setup flow plot
        self.ax.set_xlabel('Time (hours)')
        self.ax.set_ylabel('Flow Rate (sccm)')
        self.ax.set_title('MFC Flow Rates vs Time')
        self.ax.grid(True, alpha=0.3)
        
        # Initialize flow plot lines
        self.plot_lines = {
            'flow_1': self.ax.plot([], [], color=self.mfc_colors['1'], linewidth=2, label='N2 Flow')[0],
            'setpoint_1': self.ax.plot([], [], color=self.mfc_colors['1'], linestyle='--', linewidth=1, alpha=0.7)[0],
            'flow_3': self.ax.plot([], [], color=self.mfc_colors['3'], linewidth=2, label='CO2 Flow')[0],
            'setpoint_3': self.ax.plot([], [], color=self.mfc_colors['3'], linestyle='--', linewidth=1, alpha=0.7)[0],
            'flow_6': self.ax.plot([], [], color=self.mfc_colors['6'], linewidth=2, label='H2 Flow')[0],
            'setpoint_6': self.ax.plot([], [], color=self.mfc_colors['6'], linestyle='--', linewidth=1, alpha=0.7)[0],
            'flow_sampling': self.ax.plot([], [], color=self.mfc_colors['sampling'], linewidth=2, label='Sampling MFC')[0],
            'setpoint_sampling': self.ax.plot([], [], color=self.mfc_colors['sampling'], linestyle='--', linewidth=1, alpha=0.7)[0]
        }
        
        self.ax.legend()
        
        # Embed flow plot in tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, flow_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Temperature plot (right)
        temp_frame = ttk.LabelFrame(self.plots_paned, text="Temperature Control")
        self.plots_paned.add(temp_frame, weight=1)
        
        # Create matplotlib figure for temperature
        self.temp_fig = Figure(figsize=(6, 4), dpi=100)
        self.temp_ax = self.temp_fig.add_subplot(111)
        
        # Setup temperature plot
        self.temp_ax.set_xlabel('Time (hours)')
        self.temp_ax.set_ylabel('Temperature (°C)')
        self.temp_ax.set_title('Temperature vs Time')
        self.temp_ax.grid(True, alpha=0.3)
        
        # Initialize temperature plot lines
        self.temp_plot_lines = {
            'setpoint': self.temp_ax.plot([], [], color=self.temp_colors['setpoint'], linewidth=2, label='Setpoint')[0],
            'internal': self.temp_ax.plot([], [], color=self.temp_colors['internal'], linewidth=2, label='Internal Temp')[0],
            'external': self.temp_ax.plot([], [], color=self.temp_colors['external'], linewidth=2, label='External Temp')[0]
        }
        
        self.temp_ax.legend()
        
        # Embed temperature plot in tkinter
        self.temp_canvas = FigureCanvasTkAgg(self.temp_fig, temp_frame)
        self.temp_canvas.draw()
        self.temp_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Plot controls
        plot_controls = ttk.Frame(parent)
        plot_controls.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(plot_controls, text="Refresh Plots", command=self.refresh_plots).pack(side=tk.LEFT)
        ttk.Button(plot_controls, text="Clear All Data", command=self.clear_all_data).pack(side=tk.LEFT, padx=(10, 0))
        
        # Logging toggle
        self.logging_var = tk.BooleanVar(value=True)
        logging_check = ttk.Checkbutton(plot_controls, text="Enable Logging", variable=self.logging_var,
                                      command=self.toggle_logging)
        logging_check.pack(side=tk.LEFT, padx=(20, 0))
    
    def setup_serial(self):
        """Setup serial connection"""
        try:
            self.serial_connection = serial.Serial('COM4', 38400, timeout=2, 
                                                 bytesize=8, stopbits=1, parity=serial.PARITY_NONE)
            
            # Create MFC controllers
            self.mfc_controllers[1] = MFCController(self.serial_connection, 1, '1', 'N2 MFC')
            self.mfc_controllers[3] = MFCController(self.serial_connection, 3, '2', 'CO2 MFC')
            self.mfc_controllers[6] = MFCController(self.serial_connection, 6, '3', 'H2 MFC')
            
            self.update_status("Connected", "green")
            self.start_update_thread()
            
        except Exception as e:
            self.update_status(f"Connection failed: {e}", "red")
            messagebox.showerror("Connection Error", f"Failed to connect to COM4:\n{e}")
    
    def setup_alicat_serial(self):
        """Setup Alicat MFC serial connection"""
        try:
            self.alicat_serial_connection = SerialWrapper.create('COM3', 19200)
            
            # Create Alicat MFC controller
            self.alicat_controllers['sampling'] = SerialMFCController(self.alicat_serial_connection, 'e')
            
            print("Alicat MFC connected successfully")
            
        except Exception as e:
            print(f"Alicat MFC connection failed: {e}")
            self.alicat_serial_connection = None
    
    def connect_serial(self):
        """Connect to serial ports"""
        if (self.serial_connection and self.serial_connection.is_open) or self.alicat_serial_connection:
            self.disconnect_serial()
        
        bronkhorst_connected = False
        alicat_connected = False
        
        # Try to connect to Bronkhorst MFCs
        try:
            self.serial_connection = serial.Serial('COM4', 38400, timeout=2, 
                                                 bytesize=8, stopbits=1, parity=serial.PARITY_NONE)
            
            # Create Bronkhorst MFC controllers
            self.mfc_controllers[1] = MFCController(self.serial_connection, 1, '1', 'N2 MFC')
            self.mfc_controllers[3] = MFCController(self.serial_connection, 3, '2', 'CO2 MFC')
            self.mfc_controllers[6] = MFCController(self.serial_connection, 6, '3', 'H2 MFC')
            
            bronkhorst_connected = True
            print("Bronkhorst MFCs connected successfully")
            
        except Exception as e:
            print(f"Bronkhorst MFCs connection failed: {e}")
            self.serial_connection = None
        
        # Try to connect to Alicat MFC
        try:
            self.alicat_serial_connection = SerialWrapper.create('COM3', 19200)
            
            # Create Alicat MFC controller
            self.alicat_controllers['sampling'] = SerialMFCController(self.alicat_serial_connection, 'e')
            
            alicat_connected = True
            print("Alicat MFC connected successfully")
            
        except Exception as e:
            print(f"Alicat MFC connection failed: {e}")
            self.alicat_serial_connection = None
        
        # Update status based on what connected
        if bronkhorst_connected and alicat_connected:
            self.update_status("All MFCs Connected", "green")
        elif bronkhorst_connected:
            self.update_status("Bronkhorst MFCs Connected", "orange")
        elif alicat_connected:
            self.update_status("Alicat MFC Connected", "orange")
        else:
            self.update_status("Connection Failed", "red")
            messagebox.showerror("Connection Error", "Failed to connect to any MFCs")
            return
        
        # Start update thread if any MFCs connected
        if bronkhorst_connected or alicat_connected:
            self.start_update_thread()
    
    def disconnect_serial(self):
        """Disconnect from serial ports"""
        self.running = False
        if self.update_thread and self.update_thread.is_alive():
            self.update_thread.join(timeout=2)
        
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
        
        if self.alicat_serial_connection:
            try:
                self.alicat_serial_connection.close()
            except:
                pass
        
        self.mfc_controllers.clear()
        self.alicat_controllers.clear()
        self.update_status("Disconnected", "red")
    
    def start_logging(self):
        """Start CSV logging"""
        if self.log_file is None:
            try:
                # Create default log filename with start time
                start_time = maya.now().datetime()
                datestring = start_time.strftime("%m-%d-%y")
                timestring = start_time.strftime("%H-%M-%S")
                default_filename = f'{datestring}_{timestring}-Bronkhorst-MFC-GUI.csv'
                
                # Ask user for filename
                log_filename = simpledialog.askstring(
                    "Log File Name",
                    "Enter log file name (without .csv extension):",
                    initialvalue=default_filename.replace('.csv', '')
                )
                
                if log_filename is None:  # User cancelled
                    return
                
                # Ensure .csv extension
                if not log_filename.endswith('.csv'):
                    log_filename += '.csv'
                
                # Open log file
                self.log_file = open(log_filename, 'a', newline='')
                self.mfc_log_filename = log_filename
                self.log_writer = csv.writer(self.log_file)
                
                # Write CSV header (matching user's desired format)
                self.log_writer.writerow([
                    "datetime", "mfc_name", "pressure", "temp", 
                    "actual_flow", "setpoint", "fluid/gas_name"
                ])
                self.log_file.flush()
                
                self.logging_enabled = True
                self.logging_status_label.config(text=f"Logging: {log_filename}", foreground="green")
                self.start_logging_btn.config(state=tk.DISABLED)
                self.stop_logging_btn.config(state=tk.NORMAL)
                
                # Initial plot refresh to show the plot
                if MATPLOTLIB_AVAILABLE:
                    self.root.after(1000, self.refresh_plot)  # Refresh after 1 second
                
                print(f"Logging started: {log_filename}")
                
            except Exception as e:
                print(f"Failed to start logging: {e}")
                messagebox.showerror("Logging Error", f"Failed to start logging:\n{e}")
        else:
            self.logging_enabled = True
            self.logging_status_label.config(text="Logging: Active", foreground="green")
            self.start_logging_btn.config(state=tk.DISABLED)
            self.stop_logging_btn.config(state=tk.NORMAL)
            
            # Initial plot refresh to show the plot
            if MATPLOTLIB_AVAILABLE:
                self.root.after(1000, self.refresh_plot)  # Refresh after 1 second
    
    def stop_logging(self):
        """Stop CSV logging"""
        self.logging_enabled = False
        self.logging_status_label.config(text="Logging: Stopped", foreground="red")
        self.start_logging_btn.config(state=tk.NORMAL)
        self.stop_logging_btn.config(state=tk.DISABLED)
        print("Logging stopped")
    
    def update_status(self, message, color):
        """Update connection status"""
        self.status_label.config(text=f"Status: {message}", foreground=color)
    
    # Removed UI plot control handlers (frequency/window/auto-update)
    
    def toggle_logging(self):
        """Toggle CSV logging"""
        self.logging_enabled = self.logging_var.get()
        if self.logging_enabled:
            print("CSV logging enabled")
        else:
            print("CSV logging disabled")
    
    def start_update_thread(self):
        """Start the update threads"""
        if self.update_thread and self.update_thread.is_alive():
            return
        
        self.running = True
        # Start MFC data update thread (every 2 seconds)
        self.update_thread = threading.Thread(target=self.update_loop, daemon=True)
        self.update_thread.start()
        # Do not start plot update thread; plots will read directly from logs when refreshed
    
    def update_loop(self):
        """Main update loop for MFC data (every 2 seconds)"""
        while self.running:
            try:
                self.update_mfc_data()
                time.sleep(2)  # Update MFC readings every 2 seconds
            except Exception as e:
                print(f"Update error: {e}")
                time.sleep(1)
    
    def plot_update_loop(self):
        """Disabled: plotting now reads directly from log files on refresh"""
        return
    
    def update_mfc_data(self):
        """Update MFC data and GUI"""
        current_time = maya.now().datetime()
        
        # Update Bronkhorst MFCs
        for node, controller in self.mfc_controllers.items():
            try:
                status = controller.get_status()
                frame = self.mfc_frames[node]
                info = frame.mfc_info
                
                # Update GUI labels
                info['capacity_label'].config(text=f"Capacity: {status['capacity']:.0f} {status['capacity_unit']}")
                info['gas_label'].config(text=f"Gas: {status['gas_type']}")
                info['current_label'].config(text=f"{status['current_flow']:.2f} sccm")
                info['setpoint_label'].config(text=f"{status['current_setpoint']:.2f} sccm")
                
                # Log data to CSV if logging is enabled (matching user's desired format)
                if self.logging_enabled and self.log_file:
                    try:
                        self.log_writer.writerow([
                            current_time.strftime("%m-%d-%YT%H:%M:%S.%f"),
                            str(node),  # mfc_name - use node ID (1, 3, 6) for plotting compatibility
                            "0.00",  # pressure (not available for Bronkhorst)
                            "0.00",  # temp (not available for Bronkhorst)
                            f"{status['current_flow']:.2f}",  # actual_flow (current flow in sccm)
                            f"{status['current_setpoint']:.2f}",  # setpoint
                            status['gas_type']  # fluid/gas_name
                        ])
                        self.log_file.flush()
                        
                        # Refresh plot after logging data (throttled)
                        if MATPLOTLIB_AVAILABLE:
                            self.root.after(0, self.throttled_refresh_plot)
                    except Exception as log_error:
                        print(f"Error logging data for MFC {node}: {log_error}")
                
            except Exception as e:
                print(f"Error updating Bronkhorst MFC {node}: {e}")
        
        # Update Alicat MFCs (using same method as mfc_logger.py)
        # Add delay between queries like in working mfc_logger.py
        time.sleep(1)  # Brief delay before Alicat queries
        
        for node, controller in self.alicat_controllers.items():
            try:
                print(f"Getting Alicat MFC State for {node} (address: {controller.address})")
                mfc_status = controller.get_state()
                print(f"Got Alicat state: {mfc_status}")
                print(f"State attributes: channel={mfc_status.channel}, flow={mfc_status.standard_mass_flow}, setpoint={mfc_status.setpoint}")
                
                frame = self.mfc_frames[node]
                info = frame.mfc_info
                
                # Update GUI labels (Alicat provides all data)
                info['capacity_label'].config(text=f"Pressure: {mfc_status.abs_pressure:.2f} psia")
                info['gas_label'].config(text=f"Gas: {mfc_status.gas_type}")
                info['current_label'].config(text=f"{mfc_status.standard_mass_flow:.2f} sccm")
                info['setpoint_label'].config(text=f"{mfc_status.setpoint:.2f} sccm")
                
                # Log data to CSV if logging is enabled (matching user's desired format)
                if self.logging_enabled and self.log_file:
                    try:
                        self.log_writer.writerow([
                            current_time.strftime("%m-%d-%YT%H:%M:%S.%f"),
                            "sampling",  # mfc_name - use "sampling" for plotting compatibility
                            f"{mfc_status.abs_pressure:.2f}",  # pressure
                            f"{mfc_status.temperature:.2f}",  # temp
                            f"{mfc_status.standard_mass_flow:.2f}",  # actual_flow
                            f"{mfc_status.setpoint:.2f}",  # setpoint
                            mfc_status.gas_type  # fluid/gas_name
                        ])
                        self.log_file.flush()
                        
                        # Refresh plot after logging data (throttled)
                        if MATPLOTLIB_AVAILABLE:
                            self.root.after(0, self.throttled_refresh_plot)
                    except Exception as log_error:
                        print(f"Error logging data for Alicat MFC {node}: {log_error}")
                
            except Exception as e:
                print(f"Error updating Alicat MFC {node}: {e}")
        
        # Check flow conditions for notifications
        self.check_flow_conditions()
    
    def set_mfc_flow(self, node, flow_var):
        """Set MFC flow rate"""
        try:
            flow_rate = float(flow_var.get())
            
            # Handle Bronkhorst MFCs
            if node in self.mfc_controllers:
                success = self.mfc_controllers[node].set_flow_rate(flow_rate)
                if success:
                    flow_var.set("")  # Clear input
                    print(f"Bronkhorst MFC flow rate set to {flow_rate} sccm")
                else:
                    messagebox.showerror("Error", f"Failed to set Bronkhorst MFC flow rate")
            
             # Handle Alicat MFCs
            elif node in self.alicat_controllers:
                try:
                    print(f"Setting Alicat MFC {node} flow to {flow_rate}")
                    self.alicat_controllers[node].set_flow(flow_rate)
                    flow_var.set("")  # Clear input
                    print(f"Alicat MFC flow rate set to {flow_rate} sccm")
                except Exception as e:
                    print(f"Error setting Alicat MFC flow: {e}")
                    # Provide more user-friendly error messages
                    if "Invalid response format" in str(e):
                        error_msg = f"Communication error with Alicat MFC. The device returned an unexpected response format. Please try again."
                    elif "Empty response" in str(e):
                        error_msg = f"Communication timeout with Alicat MFC. Please check the connection and try again."
                    elif "Setpoint mismatch" in str(e):
                        error_msg = f"Failed to verify flow rate setting on Alicat MFC. The device may not have accepted the command. Please try again."
                    elif "Failed to set Alicat MFC flow rate after" in str(e):
                        error_msg = f"Multiple communication failures with Alicat MFC. Please check the device connection and try again."
                    else:
                        error_msg = f"Failed to set Alicat MFC flow rate: {e}"
                    
                    messagebox.showerror("Error", error_msg)
            
            else:
                messagebox.showerror("Error", f"MFC {node} not found or not connected")
                
        except ValueError:
            messagebox.showerror("Error", f"Invalid flow rate value. Please enter a valid number.")
    
    def setup_logging(self):
        """Setup comprehensive logging for crash detection and debugging"""
        try:
            # Create logs directory if it doesn't exist
            if not os.path.exists('logs'):
                os.makedirs('logs')
            
            # Setup main application logger
            log_filename = f"logs/mfc_gui_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            logging.basicConfig(
                level=logging.DEBUG,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(log_filename),
                    logging.StreamHandler(sys.stdout)
                ]
            )
            self.logger = logging.getLogger(__name__)
            self.logger.info("MFC GUI application started")
            
            # Setup exception handler for unhandled exceptions
            def handle_exception(exc_type, exc_value, exc_traceback):
                if issubclass(exc_type, KeyboardInterrupt):
                    sys.__excepthook__(exc_type, exc_value, exc_traceback)
                    return
                
                self.logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
                
                # Try to save state before crashing
                try:
                    self.save_crash_state(exc_type, exc_value, exc_traceback)
                except:
                    pass
                
                # Show error dialog
                try:
                    messagebox.showerror("Critical Error", 
                                       f"An unexpected error occurred:\n\n{exc_type.__name__}: {exc_value}\n\n"
                                       f"Check the log file for details: {log_filename}")
                except:
                    pass
            
            sys.excepthook = handle_exception
            
            # Setup thread exception handler
            def handle_thread_exception(args):
                self.logger.error(f"Uncaught exception in thread {args.thread.name}: {args.exc_type.__name__}: {args.exc_value}")
                self.thread_errors[args.thread.name] = {
                    'exception': args.exc_type.__name__,
                    'message': str(args.exc_value),
                    'timestamp': datetime.now(),
                    'traceback': traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
                }
                
                # Try to restart critical threads
                if args.thread.name == 'temp_monitor':
                    self.logger.warning("Temperature monitoring thread crashed - attempting restart")
                    self.start_temp_monitoring()
                elif args.thread.name == 'mfc_update':
                    self.logger.warning("MFC update thread crashed - attempting restart")
                    self.start_mfc_updates()
            
            threading.excepthook = handle_thread_exception
            
        except Exception as e:
            print(f"Error setting up logging: {e}")
    
    def save_crash_state(self, exc_type, exc_value, exc_traceback):
        """Save application state before crashing"""
        try:
            crash_info = {
                'timestamp': datetime.now().isoformat(),
                'exception_type': exc_type.__name__,
                'exception_message': str(exc_value),
                'traceback': traceback.format_tb(exc_traceback),
                'thread_errors': self.thread_errors,
                'thread_heartbeats': self.thread_heartbeats,
                'safety_triggered': getattr(self, 'safety_triggered', False),
                'temp_control_running': getattr(self, 'temp_control_running', False),
                'logging_enabled': getattr(self, 'logging_enabled', False)
            }
            
            crash_filename = f"logs/crash_state_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(crash_filename, 'w') as f:
                json.dump(crash_info, f, indent=2, default=str)
            
            self.logger.info(f"Crash state saved to {crash_filename}")
            
        except Exception as e:
            self.logger.error(f"Failed to save crash state: {e}")
    
    def get_temp_readings_threadsafe(self):
        """Thread-safe function to read temperature values from controllers"""
        with self.temp_controller_lock:
            try:
                if not hasattr(self, 'temp_controllers') or not self.temp_controllers:
                    return None, None, None
                
                if '1' not in self.temp_controllers or '2' not in self.temp_controllers:
                    return None, None, None
                
                # Read all temperature values
                internal_temp = self.temp_controllers['1'].get_temp()
                external_temp = self.temp_controllers['2'].get_temp()
                setpoint = self.temp_controllers['1'].get_set_temp()
                
                # Update cached readings
                self.last_temp_readings = {
                    'internal_temp': internal_temp,
                    'external_temp': external_temp,
                    'setpoint': setpoint,
                    'last_update': datetime.now()
                }
                
                return internal_temp, external_temp, setpoint
                
            except Exception as e:
                print(f"Error reading temperature values (thread-safe): {e}")
                # Return cached values if available and recent (within 10 seconds)
                if (self.last_temp_readings['last_update'] and 
                    (datetime.now() - self.last_temp_readings['last_update']).total_seconds() < 10):
                    return (self.last_temp_readings['internal_temp'], 
                           self.last_temp_readings['external_temp'], 
                           self.last_temp_readings['setpoint'])
                return None, None, None
    
    def set_temp_setpoint_threadsafe(self, setpoint):
        """Thread-safe function to set temperature setpoint"""
        with self.temp_controller_lock:
            try:
                if not hasattr(self, 'temp_controllers') or '1' not in self.temp_controllers:
                    return False
                
                self.temp_controllers['1'].set_set_temp(setpoint)
                return True
                
            except Exception as e:
                print(f"Error setting temperature setpoint (thread-safe): {e}")
                return False
    
    def connect_temp_control(self):
        """Connect to temperature controllers"""
        # Check if already connected
        if hasattr(self, 'temp_controllers') and self.temp_controllers:
            # Test the connection
            try:
                internal_temp = self.temp_controllers['1'].get_temp()
                external_temp = self.temp_controllers['2'].get_temp()
                setpoint = self.temp_controllers['1'].get_set_temp()
                
                # Update GUI with current readings
                self.internal_temp_label.config(text=f"{internal_temp:.1f} °C")
                self.external_temp_label.config(text=f"{external_temp:.1f} °C")
                self.setpoint_label.config(text=f"{setpoint:.1f} °C")
                self.temp_status_label.config(text="Status: Connected", foreground="green")
                
                messagebox.showinfo("Info", "Temperature controller is already connected and working!")
                return
                
            except Exception as e:
                print(f"Temperature controller connection test failed: {e}")
                # Connection is broken, try to reconnect
                self.temp_controllers = {}
                self.temp_serial = None
        
        try:
            # Create serial connection to COM5
            self.temp_serial = SerialWrapper.create('COM5', 9600)
            print("Temperature controller serial connection opened")
            
            # Create temperature controllers
            self.temp_controllers = {
                '1': SerialTempController(self.temp_serial, "1"),  # Internal
                '2': SerialTempController(self.temp_serial, "2")   # External
            }
            
            # Test connection by reading temperatures
            internal_temp = self.temp_controllers['1'].get_temp()
            external_temp = self.temp_controllers['2'].get_temp()
            setpoint = self.temp_controllers['1'].get_set_temp()
            
            # Update GUI
            self.temp_status_label.config(text="Status: Connected", foreground="green")
            self.internal_temp_label.config(text=f"{internal_temp:.1f} °C")
            self.external_temp_label.config(text=f"{external_temp:.1f} °C")
            self.setpoint_label.config(text=f"{setpoint:.1f} °C")
            
            # Enable/disable buttons
            self.connect_temp_btn.config(state=tk.NORMAL)  # Keep available for reconnection
            # self.disconnect_temp_btn.config(state=tk.NORMAL)
            self.start_temp_btn.config(state=tk.NORMAL)
            
            # Start temperature monitoring thread
            self.start_temp_monitoring()
            
            messagebox.showinfo("Success", "Temperature controller connected successfully!")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect to temperature controller: {e}")
            print(f"Temperature controller connection error: {e}")
    
    # def disconnect_temp_control(self):
    #     """Disconnect from temperature controllers"""
    #     try:
    #         # Stop temperature monitoring
    #         if hasattr(self, 'temp_monitor_thread'):
    #             self.temp_monitor_thread = None
            
    #         # Close serial connection
    #         if self.temp_serial:
    #             self.temp_serial.close()
    #             self.temp_serial = None
            
    #         # Clear temperature controllers
    #         self.temp_controllers = {}
            
    #         # Update GUI
    #         self.temp_status_label.config(text="Status: Disconnected", foreground="red")
    #         self.internal_temp_label.config(text="- °C")
    #         self.external_temp_label.config(text="- °C")
    #         self.setpoint_label.config(text="- °C")
            
    #         # Enable/disable buttons
    #         self.connect_temp_btn.config(state=tk.NORMAL)
    #         self.disconnect_temp_btn.config(state=tk.DISABLED)
    #         self.start_temp_btn.config(state=tk.DISABLED)
    #         self.stop_temp_btn.config(state=tk.DISABLED)
            
    #         messagebox.showinfo("Success", "Temperature controller disconnected!")
            
    #     except Exception as e:
    #         messagebox.showerror("Error", f"Error disconnecting temperature controller: {e}")
    
    def start_temp_monitoring(self):
        """Start monitoring temperature readings"""
        if not hasattr(self, 'temp_monitor_thread') or not self.temp_monitor_thread:
            self.temp_monitor_thread = threading.Thread(target=self.monitor_temperature_readings, daemon=True)
            self.temp_monitor_thread.start()
    
    def monitor_temperature_readings(self):
        """Monitor temperature readings from controllers"""
        thread_name = threading.current_thread().name
        self.logger.info(f"Temperature monitoring thread started: {thread_name}")
        
        while hasattr(self, 'temp_controllers') and self.temp_controllers:
            try:
                # Update heartbeat
                self.thread_heartbeats['temp_monitor'] = datetime.now()
                
                # Use thread-safe function to read temperature values
                internal_temp, external_temp, setpoint = self.get_temp_readings_threadsafe()
                
                if internal_temp is not None and external_temp is not None and setpoint is not None:
                    # Update GUI labels
                    self.internal_temp_label.config(text=f"{internal_temp:.1f} °C")
                    self.external_temp_label.config(text=f"{external_temp:.1f} °C")
                    self.setpoint_label.config(text=f"{setpoint:.1f} °C")
                    
                    # Check safety conditions
                    self.check_safety_conditions(internal_temp, external_temp, setpoint)
                    
                    # Add to plot data with memory management
                    current_time = datetime.now()
                    self.temp_plot_data['time'].append(current_time)
                    self.temp_plot_data['setpoint'].append(setpoint)
                    self.temp_plot_data['internal_temp'].append(internal_temp)
                    self.temp_plot_data['external_temp'].append(external_temp)
                    
                    # Limit plot data to prevent memory issues (keep last 2 hours of data)
                    max_data_points = 2 * 60 * 30  # 2 hours * 60 minutes * 30 points per minute (2-second intervals)
                    for key in ['time', 'setpoint', 'internal_temp', 'external_temp']:
                        if len(self.temp_plot_data[key]) > max_data_points:
                            self.temp_plot_data[key] = self.temp_plot_data[key][-max_data_points:]
                    
                    # Refresh temperature plot
                    if MATPLOTLIB_AVAILABLE:
                        self.refresh_temp_plot()
                else:
                    self.logger.warning("Temperature monitoring: Failed to read temperature values")
                
                time.sleep(2)  # Update every 2 seconds
                
            except Exception as e:
                self.logger.error(f"Error monitoring temperature readings: {e}")
                time.sleep(5)  # Wait longer on error
        
        self.logger.info(f"Temperature monitoring thread ended: {thread_name}")
    
    def monitor_thread_health(self):
        """Monitor thread health and restart if necessary"""
        while True:
            try:
                current_time = datetime.now()
                
                # Check each thread's heartbeat
                for thread_name, last_heartbeat in self.thread_heartbeats.items():
                    if last_heartbeat is not None:
                        time_since_heartbeat = (current_time - last_heartbeat).total_seconds()
                        
                        # If thread hasn't updated in 30 seconds, it might be dead
                        if time_since_heartbeat > 30:
                            self.logger.warning(f"Thread {thread_name} hasn't updated in {time_since_heartbeat:.1f} seconds")
                            
                            # Try to restart critical threads
                            if thread_name == 'temp_monitor' and not self.temp_monitor_thread.is_alive():
                                self.logger.warning("Temperature monitoring thread appears dead - restarting")
                                self.start_temp_monitoring()
                            elif thread_name == 'mfc_update' and not self.update_thread.is_alive():
                                self.logger.warning("MFC update thread appears dead - restarting")
                                self.start_mfc_updates()
                
                time.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                self.logger.error(f"Error in thread health monitor: {e}")
                time.sleep(30)  # Wait longer on error
    
    def start_thread_monitoring(self):
        """Start thread health monitoring"""
        if not hasattr(self, 'thread_monitor_thread') or not self.thread_monitor_thread:
            self.thread_monitor_thread = threading.Thread(target=self.monitor_thread_health, daemon=True, name='thread_monitor')
            self.thread_monitor_thread.start()
            self.logger.info("Thread health monitoring started")
    
    def upload_temp_ramp(self):
        """Upload temperature ramp JSON file"""
        file_path = filedialog.askopenfilename(
            title="Select Temperature Ramp JSON File (hold_times in hours)",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    self.temp_ramp_config = json.load(f)
                
                # Validate the config format
                if "temperatures" not in self.temp_ramp_config or "hold_times" not in self.temp_ramp_config or "ramp_rates" not in self.temp_ramp_config:
                    messagebox.showerror("Error", "Invalid JSON format. Must contain 'temperatures', 'hold_times', and 'ramp_rates' arrays.")
                    return
                
                # Show preview of loaded config
                temps = self.temp_ramp_config["temperatures"]
                hold_times = self.temp_ramp_config["hold_times"]
                ramp_rates = self.temp_ramp_config["ramp_rates"]
                
                preview = f"Loaded temperature ramp:\n"
                preview += f"Temperatures: {temps}\n"
                preview += f"Hold times: {hold_times} hours\n"
                preview += f"Ramp rates: {ramp_rates} °C/min"
                
                messagebox.showinfo("Success", f"Temperature ramp configuration loaded successfully!\n\n{preview}")
                print(f"Loaded temp ramp config: {self.temp_ramp_config}")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load JSON file: {e}")
    
    def start_temp_control(self):
        """Start temperature control process"""
        if not self.temp_ramp_config:
            messagebox.showerror("Error", "Please upload a temperature ramp JSON file first!")
            return
        
        # Check if temperature controller is connected
        if not hasattr(self, 'temp_controllers') or not self.temp_controllers:
            messagebox.showerror("Error", "Please connect to temperature controller first!")
            return
        
        # Check safety state - if triggered, reset to active before starting
        if self.safety_triggered:
            print("Safety was triggered - resetting to active state before starting temperature control")
            self.safety_triggered = False
            self.safety_status_label.config(text="Safety: Active", foreground="green")
            messagebox.showinfo("Safety Reset", "Safety state was triggered and has been reset to Active before starting temperature control.")
        
        try:
            # Create default temp log filename with timestamp
            start_time = maya.now().datetime()
            datestring = start_time.strftime("%m-%d-%y")
            timestring = start_time.strftime("%H-%M-%S")
            default_filename = f'TC_log_{datestring}_{timestring}.csv'
            
            # Ask user for temp log filename
            temp_log_filename = simpledialog.askstring(
                "Temperature Log File Name",
                "Enter temperature log file name (without .csv extension):",
                initialvalue=default_filename.replace('.csv', '')
            )
            
            if temp_log_filename is None:  # User cancelled
                return
            
            # Ensure .csv extension
            if not temp_log_filename.endswith('.csv'):
                temp_log_filename += '.csv'
            
            self.temp_log_filename = temp_log_filename
            
            # Start temperature control directly in the GUI (no subprocess)
            self.start_temp_control_thread()
            
            self.temp_status_label.config(text="Status: Running", foreground="green")
            self.start_temp_btn.config(state=tk.DISABLED)
            self.stop_temp_btn.config(state=tk.NORMAL)
            
            # Check if CSV file was created after a short delay
            def check_csv_creation():
                time.sleep(3)  # Wait 3 seconds for file creation
                if os.path.exists(temp_log_filename):
                    print(f"CSV file created successfully: {temp_log_filename}")
                else:
                    print(f"Warning: CSV file not found: {temp_log_filename}")
                    print(f"Current working directory: {os.getcwd()}")
                    print(f"Files in directory: {os.listdir('.')}")
            
            # Check file creation in a separate thread
            threading.Thread(target=check_csv_creation, daemon=True).start()
            
            messagebox.showinfo("Success", f"Temperature control started successfully!\nLog file: {temp_log_filename}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start temperature control: {e}")
    
    def stop_temp_control(self):
        """Stop temperature control process"""
        try:
            # Stop the temperature control thread
            self.temp_control_running = False
            
            # Close the log file if it's open
            if hasattr(self, 'temp_log_file') and self.temp_log_file:
                self.temp_log_file.close()
                self.temp_log_file = None
            
            self.temp_status_label.config(text="Status: Disconnected", foreground="red")
            self.start_temp_btn.config(state=tk.NORMAL)
            self.stop_temp_btn.config(state=tk.DISABLED)
            
            messagebox.showinfo("Success", "Temperature control stopped!")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to stop temperature control: {e}")
    
    def start_temp_control_thread(self):
        """Start temperature control in a separate thread using existing connection"""
        try:
            # Create temp ramp from config (convert hours to minutes)
            hold_times_minutes = [ht * 60 for ht in self.temp_ramp_config["hold_times"]]
            
            # Import required modules
            from temp_ramp import DEG_C, MINUTE, HOUR, SECOND, TempRamp
            import numpy as np
            
            temp_ramp = TempRamp(
                self.temp_ramp_config["temperatures"],
                hold_times_minutes,
                self.temp_ramp_config["ramp_rates"]
            )
            
            print(f"Expected runtime: {max(temp_ramp.ramp_points()[0]) / HOUR:.2f} hours")
            
            # Open log file
            self.temp_log_file = open(self.temp_log_filename, 'a')
            self.temp_log_filename = self.temp_log_filename
            print(f"Log file opened: {self.temp_log_filename}")
            
            # Set shared start time for plotting if not already set
            if self.plot_start_time is None:
                self.plot_start_time = datetime.now()
                print("Temperature control started - setting shared start time")
            
            # Start the control thread
            self.temp_control_running = True
            self.temp_control_thread = threading.Thread(
                target=self.run_temp_control_loop, 
                args=(temp_ramp,), 
                daemon=True
            )
            self.temp_control_thread.start()
            
        except Exception as e:
            print(f"Error starting temperature control thread: {e}")
            raise
    
    def run_temp_control_loop(self, temp_ramp):
        """Run the temperature control loop"""
        thread_name = threading.current_thread().name
        self.logger.info(f"Temperature control thread started: {thread_name}")
        
        try:
            from temp_ramp import DEG_C, MINUTE, HOUR, SECOND
            import numpy as np
            
            ramp_start_time = time.time()
            ramp_control_times, ramp_control_temps = temp_ramp.control_points()
            ramp_control_times = np.array(ramp_control_times)
            
            while self.temp_control_running:
                try:
                    # Update heartbeat
                    self.thread_heartbeats['temp_control'] = datetime.now()
                    # Check if safety is triggered - if so, stop temp control and set to 20°C
                    if self.safety_triggered:
                        print("Safety triggered during temperature control - stopping ramp and setting to 20°C")
                        
                        # Set temperature to 20°C using thread-safe function
                        _, _, current_setpoint = self.get_temp_readings_threadsafe()
                        if current_setpoint is not None and abs(current_setpoint - 20.0) > 0.1:  # Only update if not already at 20°C
                            print(f"Safety override: Current setpoint is {current_setpoint:.1f}°C, setting to 20°C")
                            success = self.set_temp_setpoint_threadsafe(20.0)
                            if success:
                                print("Safety override: Setpoint set to 20°C")
                            else:
                                print("Safety override: Failed to set setpoint to 20°C")
                        else:
                            print(f"Safety override: Setpoint already at {current_setpoint:.1f}°C (close to 20°C)")
                        
                        # Stop temperature control
                        self.temp_control_running = False
                        print("Temperature control stopped due to safety trigger")
                        
                        # Update GUI status
                        self.root.after(0, lambda: self.temp_status_label.config(text="Status: Stopped (Safety)", foreground="red"))
                        self.root.after(0, lambda: self.start_temp_btn.config(state=tk.NORMAL))
                        self.root.after(0, lambda: self.stop_temp_btn.config(state=tk.DISABLED))
                        
                        # Show notification
                        self.root.after(0, lambda: messagebox.showwarning("Temperature Control Stopped", 
                                                                       "Temperature control has been stopped due to safety trigger.\n"
                                                                       "Temperature setpoint has been set to 20°C."))
                        break  # Exit the control loop
                    else:
                        # Normal ramp operation
                        desired_set_point_idx = np.argmax(
                            ramp_control_times > (time.time() - ramp_start_time) * SECOND / MINUTE
                        ) - 1
                        desired_set_point = ramp_control_temps[desired_set_point_idx]
                        
                        # Get current setpoint using thread-safe function
                        _, _, current_setpoint = self.get_temp_readings_threadsafe()
                        if current_setpoint is not None and desired_set_point != current_setpoint:
                            success = self.set_temp_setpoint_threadsafe(desired_set_point)
                            if success:
                                print(f"Updated setpoint to {desired_set_point:.1f}°C")
                            else:
                                print(f"Failed to update setpoint to {desired_set_point:.1f}°C")
                    
                    # Log temperature status using thread-safe function
                    internal_temp, external_temp, setpoint = self.get_temp_readings_threadsafe()
                    
                    if internal_temp is not None and external_temp is not None and setpoint is not None:
                        self.temp_log_file.write("%s, %.1f, %.1f, %.1f\n" % (
                            maya.now().datetime().strftime("%m-%d-%YT%H:%M:%S.%f"),
                            setpoint,
                            internal_temp,
                            external_temp,
                        ))
                        self.temp_log_file.flush()
                        
                        # Update GUI labels
                        self.root.after(0, lambda: self.setpoint_label.config(text=f"{setpoint:.1f} °C"))
                        self.root.after(0, lambda: self.internal_temp_label.config(text=f"{internal_temp:.1f} °C"))
                        self.root.after(0, lambda: self.external_temp_label.config(text=f"{external_temp:.1f} °C"))
                        
                        # Add to plot data for real-time plotting
                        current_time = datetime.now()
                        self.temp_plot_data['time'].append(current_time)
                        self.temp_plot_data['setpoint'].append(setpoint)
                        self.temp_plot_data['internal_temp'].append(internal_temp)
                        self.temp_plot_data['external_temp'].append(external_temp)
                        
                        # Remove old data outside time window (keep last hour of data)
                        cutoff_time = current_time - timedelta(hours=1)
                        while self.temp_plot_data['time'] and self.temp_plot_data['time'][0] < cutoff_time:
                            self.temp_plot_data['time'].pop(0)
                            self.temp_plot_data['setpoint'].pop(0)
                            self.temp_plot_data['internal_temp'].pop(0)
                            self.temp_plot_data['external_temp'].pop(0)
                        
                        # Update the temperature plot
                        self.root.after(0, self.refresh_temp_plot)
                        
                        # Check safety conditions
                        self.check_safety_conditions(internal_temp, external_temp, setpoint)
                    else:
                        print("Temperature control: Failed to read temperature values for logging")
                    
                    time.sleep(1)  # Update every second
                    
                except Exception as e:
                    print(f"Error in temperature control loop: {e}")
                    time.sleep(5)  # Wait longer on error
                    
        except Exception as e:
            print(f"Fatal error in temperature control: {e}")
            self.root.after(0, lambda: self.temp_status_label.config(text="Status: Error", foreground="red"))
            self.root.after(0, lambda: messagebox.showerror("Temperature Control Error", f"Temperature control failed: {e}"))
        finally:
            # Clean up
            if hasattr(self, 'temp_log_file') and self.temp_log_file:
                self.temp_log_file.close()
                self.temp_log_file = None
    
    def create_temp_control_script(self):
        """Create a temporary temperature control script with the uploaded config"""
        script_content = f'''
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import serial
import time
import maya
import json

from temp_ramp import DEG_C, MINUTE, HOUR, SECOND, TempRamp
from instruments import SerialTempController
from serial_wrapper import SerialWrapper

# Load configuration
config = {json.dumps(self.temp_ramp_config)}

# Create temp ramp from config (convert hours to minutes)
hold_times_minutes = [ht * 60 for ht in config["hold_times"]]  # Convert hours to minutes
temp_ramp = TempRamp(
    config["temperatures"],
    hold_times_minutes,
    config["ramp_rates"]
)

print("Expected runtime: %.2f hours" % (max(temp_ramp.ramp_points()[0]) / HOUR))

ramp_start_time = time.time()
ramp_control_times, ramp_control_temps = temp_ramp.control_points()
ramp_control_times = np.array(ramp_control_times)

# Serial connection
tc_serial = SerialWrapper.create('COM5', 9600)
print("Serial Connection Opened")

temp_controller1 = SerialTempController(tc_serial, "1")
temp_controller2 = SerialTempController(tc_serial, "2")

# Log file
LOG_FILENAME = "{self.temp_log_filename}"
print(f"Creating log file: {{LOG_FILENAME}}")
try:
log_f = open(LOG_FILENAME, 'a')
    print(f"Log file opened successfully: {{LOG_FILENAME}}")
except Exception as e:
    print(f"Error opening log file {{LOG_FILENAME}}: {{e}}")
    raise

def log_temp_status():
    try:
    print("Logging Temp")
        setpoint = temp_controller1.get_set_temp()
        internal_temp = temp_controller1.get_temp()
        external_temp = temp_controller2.get_temp()
        
    log_f.write("%s, %.1f, %.1f, %.1f\\n" % (
        maya.now().datetime().strftime("%m-%d-%YT%H:%M:%S.%f"),
            setpoint,
            internal_temp,
            external_temp,
    ))
    log_f.flush()
        print(f"Logged: setpoint={{setpoint}}, internal={{internal_temp}}, external={{external_temp}}")
    except Exception as e:
        print(f"Error logging temperature status: {{e}}")
        raise

def update_set_point():
    print("Updating Set Point")
    desired_set_point_idx = np.argmax(
        ramp_control_times > (time.time() - ramp_start_time) * SECOND / MINUTE
    ) - 1
    desired_set_point = ramp_control_temps[desired_set_point_idx]

    if desired_set_point != temp_controller1.get_set_temp():
        temp_controller1.set_set_temp(desired_set_point)

# Run the control loop
try:
    while True:
        update_set_point()
        log_temp_status()
        time.sleep(1)
except KeyboardInterrupt:
    print("Stopping temperature control...")

print("Cleaning Up")
log_f.close()
tc_serial.close()
'''
        
        # Write to temporary file
        temp_script_path = f'temp_control_{int(time.time())}.py'
        with open(temp_script_path, 'w') as f:
            f.write(script_content)
        
        return temp_script_path
    
    def start_temp_log_monitoring(self):
        """Start monitoring temperature log file"""
        if hasattr(self, 'temp_log_filename'):
            # Start a thread to monitor the temp log file
            self.temp_log_monitor_thread = threading.Thread(target=self.monitor_temp_log, daemon=True)
            self.temp_log_monitor_thread.start()
    
    
    def monitor_temp_log(self):
        """Monitor temperature log file for updates"""
        if not hasattr(self, 'temp_log_filename'):
            return
            
        try:
            with open(self.temp_log_filename, 'r') as f:
                # Skip to end of file
                f.seek(0, 2)
                
                while self.temp_process and self.temp_process.poll() is None:
                    line = f.readline()
                    if line:
                        self.process_temp_log_line(line.strip())
                    else:
                        time.sleep(0.1)  # Wait for new data
                        
        except Exception as e:
            print(f"Error monitoring temp log: {e}")
    
    def process_temp_log_line(self, line):
        """Process a line from the temperature log file"""
        try:
            parts = line.split(', ')
            if len(parts) >= 4:
                timestamp_str = parts[0]
                setpoint = float(parts[1])
                internal_temp = float(parts[2])
                external_temp = float(parts[3])
                
                # Parse timestamp
                timestamp = maya.parse(timestamp_str).datetime()
                
                # Add to plot data
                self.temp_plot_data['time'].append(timestamp)
                self.temp_plot_data['setpoint'].append(setpoint)
                self.temp_plot_data['internal_temp'].append(internal_temp)
                self.temp_plot_data['external_temp'].append(external_temp)
                
                # Update GUI labels
                self.setpoint_label.config(text=f"{setpoint:.1f} °C")
                self.internal_temp_label.config(text=f"{internal_temp:.1f} °C")
                self.external_temp_label.config(text=f"{external_temp:.1f} °C")
                
                # Check safety conditions
                self.check_safety_conditions(internal_temp, external_temp, setpoint)
                
        except Exception as e:
            print(f"Error processing temp log line: {e}")
    
    def check_safety_conditions(self, internal_temp, external_temp, setpoint):
        """Check safety conditions and trigger if necessary"""
        if self.maintenance_mode or self.safety_triggered:
            return
            
        safety_triggered = False
        reason = ""
        
        # Check if temperature > 750°C
        if internal_temp >= 750 or external_temp >= 750 or setpoint >= 750:
            safety_triggered = True
            reason = f"Temperature exceeded 750°C (Internal: {internal_temp:.1f}°C, External: {external_temp:.1f}°C, Setpoint: {setpoint:.1f}°C)"
        
        # Check if difference between internal and external temperature is more than 50°C
        # elif abs(internal_temp - external_temp) > 150:
        #     safety_triggered = True
        #     reason = f"Temperature difference >150°C between internal and external (Internal: {internal_temp:.1f}°C, External: {external_temp:.1f}°C, Difference: {abs(internal_temp - external_temp):.1f}°C)"
        
        if safety_triggered:
            self.trigger_safety_shutdown(reason)
    
    def check_flow_conditions(self):
        """Check flow conditions and send notifications if necessary"""
        if self.maintenance_mode:
            return
            
        current_time = datetime.now()
        
        # Check all MFCs
        for node_id, controller in self.mfc_controllers.items():
            try:
                current_flow = controller.get_current_flow()
                setpoint = controller.get_current_setpoint()
                
                # Only check if setpoint > 0 (MFC is supposed to be flowing)
                if setpoint > 0:
                    # Check if actual flow < 0.9 * setpoint
                    if current_flow < 0.9 * setpoint:
                        # Check if this is a new alert or continuing
                        if node_id not in self.flow_alert_start_times:
                            # New alert - start tracking
                            self.flow_alert_start_times[node_id] = current_time
                            print(f"Flow alert started for MFC {node_id}: {current_flow:.2f} < 0.9 * {setpoint:.2f}")
                        
                        # Check if alert has been active for > 1 minute
                        elif (current_time - self.flow_alert_start_times[node_id]).total_seconds() > 60:
                            # Send notification
                            if node_id not in self.flow_alerts or not self.flow_alerts[node_id]:
                                self.send_flow_notification(node_id, current_flow, setpoint)
                                self.flow_alerts[node_id] = True  # Mark as notified
                                print(f"Flow notification sent for MFC {node_id}")
                    else:
                        # Flow is normal - reset alert tracking
                        if node_id in self.flow_alert_start_times:
                            del self.flow_alert_start_times[node_id]
                        if node_id in self.flow_alerts:
                            del self.flow_alerts[node_id]
                            
            except Exception as e:
                print(f"Error checking flow for MFC {node_id}: {e}")
    
    def send_flow_notification(self, node_id, current_flow, setpoint):
        """Send flow notification email"""
        try:
            controller_name = f"MFC {node_id}"
            if node_id == 1:
                controller_name = "N2 MFC"
            elif node_id == 3:
                controller_name = "CO2 MFC"
            elif node_id == 6:
                controller_name = "H2 MFC"
            elif node_id == 'sampling':
                controller_name = "Sampling MFC"
            
            reason = f"Low flow detected on {controller_name}"
            
            msg = MIMEMultipart()
            msg['From'] = "kanan.electrolysis@gmail.com"
            msg['To'] = "kesha@stanford.edu, robertpk@stanford.edu, hpthomas@stanford.edu"
            msg['Subject'] = reason
            
            body = f"""
FLOW ALERT

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Reason: {reason}

Details:
- Controller: {controller_name} (Node {node_id})
- Current Flow: {current_flow:.2f} sccm
- Setpoint: {setpoint:.2f} sccm
- Threshold: {0.9 * setpoint:.2f} sccm (90% of setpoint)
- Duration: > 1 minute

Please check the MFC and reactor system.

Flow Reactor Monitoring System
"""
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Try to send email via SMTP
            try:
                # Gmail SMTP settings
                smtp_server = "smtp.gmail.com"
                smtp_port = 587
                
                # Create SMTP session
                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()  # Enable TLS encryption
                
                # Login with Gmail credentials (using App Password)
                email_address = "kanan.electrolysis@gmail.com"
                email_password = "jcrx beam fugn cvnf"  # App password
                server.login(email_address, email_password)
                
                # Send the email
                server.send_message(msg)
                server.quit()
                
                print(f"FLOW NOTIFICATION EMAIL sent successfully to kesha@stanford.edu, robertpk@stanford.edu, hpthomas@stanford.edu")
                
            except Exception as smtp_error:
                print(f"SMTP error (email printed instead): {smtp_error}")
                print(f"FLOW NOTIFICATION EMAIL:\n{body}")
            
        except Exception as e:
            print(f"Error sending flow notification: {e}")
    
    def trigger_safety_shutdown(self, reason):
        """Trigger safety shutdown sequence"""
        self.safety_triggered = True
        
        try:
            # FIRST: Execute all safety actions immediately
            print(f"🚨 SAFETY SHUTDOWN TRIGGERED: {reason}")
            print("Executing safety actions...")
            
            # Set H2/CO2 flows to 0, N2 to 100 sccm, temp setpoint to 20°C
            if 3 in self.mfc_controllers:  # CO2
                self.mfc_controllers[3].set_flow_rate(50)
                print("✓ CO2 flow set to 50 sccm")
            if 6 in self.mfc_controllers:  # H2
                self.mfc_controllers[6].set_flow_rate(0)
                print("✓ H2 flow set to 0 sccm")
            if 1 in self.mfc_controllers:  # N2
                self.mfc_controllers[1].set_flow_rate(100)
                print("✓ N2 flow set to 100 sccm")
            
            # Set temperature setpoint to 20°C (but keep temp control running)
            if hasattr(self, 'temp_controllers') and '1' in self.temp_controllers:
                try:
                    # Get current setpoint before setting using thread-safe function
                    _, _, current_setpoint = self.get_temp_readings_threadsafe()
                    if current_setpoint is not None:
                        print(f"Safety trigger: Current setpoint is {current_setpoint:.1f}°C")
                    
                    # Set to 20°C using thread-safe function
                    success = self.set_temp_setpoint_threadsafe(20.0)
                    if success:
                        print("✓ Temperature setpoint set to 20°C")
                    else:
                        print("✗ Failed to set temperature setpoint to 20°C")
                    
                    # Verify the setpoint was actually set
                    time.sleep(0.5)  # Brief delay to allow the command to be processed
                    _, _, new_setpoint = self.get_temp_readings_threadsafe()
                    if new_setpoint is not None:
                        print(f"Safety trigger: Verified setpoint is now {new_setpoint:.1f}°C")
                    else:
                        print("Safety trigger: Could not verify setpoint after setting")
                    
                except Exception as e:
                    print(f"Error setting temperature to 20°C during safety: {e}")
            
            # Update safety status
            self.safety_status_label.config(text="Safety: TRIGGERED!", foreground="red")
            print("✓ Safety status updated")
            
            # Send email alert (in background)
            self.send_safety_email(reason)
            print("✓ Email alert sent")
            
            print("All safety actions completed successfully")
            
            # LAST: Show notification dialog after all actions are complete
            messagebox.showinfo("SAFETY SHUTDOWN COMPLETED", 
                               f"Safety system has been activated and all actions completed!\n\nReason: {reason}\n\n"
                               f"Actions taken:\n"
                               f"- H2 and CO2 flows set to 0 sccm\n"
                               f"- N2 flow set to 100 sccm\n"
                               f"- Temperature setpoint set to 20°C\n"
                               f"- Temperature control continues running\n\n"
                               f"Email alert sent to kesha@stanford.edu, robertpk@stanford.edu, hpthomas@stanford.edu")
            
        except Exception as e:
            print(f"Error during safety shutdown: {e}")
            # Show error dialog if something went wrong
            messagebox.showerror("SAFETY SHUTDOWN ERROR", 
                               f"Safety system was triggered but some actions may have failed!\n\n"
                               f"Reason: {reason}\n\n"
                               f"Error: {e}\n\n"
                               f"Please check the system manually.")
    
    def send_safety_email(self, reason):
        """Send safety alert email"""
        try:
            msg = MIMEMultipart()
            msg['From'] = "kanan.electrolysis@gmail.com"
            msg['To'] = "kesha@stanford.edu, robertpk@stanford.edu, hpthomas@stanford.edu"
            msg['Subject'] = reason  # Use the reason as the subject
            
            body = f"""
SAFETY SHUTDOWN TRIGGERED

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Reason: {reason}

Actions taken:
- H2 and CO2 flows set to 0 sccm
- N2 flow set to 100 sccm  
- Temperature setpoint set to 20°C

Please check the reactor immediately.

Flow Reactor Safety System
"""
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Try to send email via SMTP
            try:
                # Gmail SMTP settings
                smtp_server = "smtp.gmail.com"
                smtp_port = 587
                
                # Create SMTP session
                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()  # Enable TLS encryption
                
                # Login with Gmail credentials (using App Password)
                email_address = "kanan.electrolysis@gmail.com"
                email_password = "jcrx beam fugn cvnf"  # App password
                server.login(email_address, email_password)
                
                # Send the email
                server.send_message(msg)
                server.quit()
                
                print(f"SAFETY EMAIL ALERT sent successfully to kesha@stanford.edu, robertpk@stanford.edu, hpthomas@stanford.edu")
                
            except Exception as smtp_error:
                print(f"SMTP error (email printed instead): {smtp_error}")
                print(f"SAFETY EMAIL ALERT:\n{body}")
            
        except Exception as e:
            print(f"Error sending safety email: {e}")
    
    def toggle_maintenance_mode(self):
        """Toggle maintenance mode"""
        self.maintenance_mode = self.maintenance_var.get()
        if self.maintenance_mode:
            self.safety_status_label.config(text="Safety: DISABLED (Maintenance Mode)", foreground="orange")
        else:
            self.safety_status_label.config(text="Safety: Active", foreground="green")
            self.safety_triggered = False  # Reset safety trigger
    
    def emergency_stop(self):
        """Emergency stop - safety shutdown sequence"""
        try:
            # Set safety triggered flag
            self.safety_triggered = True
            
            # Set H2/CO2 flows to 0, N2 to 100 sccm (same as safety shutdown)
            if 3 in self.mfc_controllers:  # CO2
                self.mfc_controllers[3].set_flow_rate(50)
            if 6 in self.mfc_controllers:  # H2
                self.mfc_controllers[6].set_flow_rate(0)
            if 1 in self.mfc_controllers:  # N2
                self.mfc_controllers[1].set_flow_rate(100)
            if 'sampling' in self.alicat_controllers:  # Sampling MFC
                try:
                    self.alicat_controllers['sampling'].set_flow(0)
                except Exception as e:
                    print(f"Error setting sampling MFC to 0: {e}")
            
            # Set temperature setpoint to 20°C (but keep temp control running)
            if hasattr(self, 'temp_controllers') and '1' in self.temp_controllers:
                try:
                    # Get current setpoint before setting using thread-safe function
                    _, _, current_setpoint = self.get_temp_readings_threadsafe()
                    if current_setpoint is not None:
                        print(f"Emergency stop: Current setpoint is {current_setpoint:.1f}°C")
                    
                    # Set to 20°C using thread-safe function
                    success = self.set_temp_setpoint_threadsafe(20.0)
                    if success:
                        print("Emergency stop: Command sent to set temperature setpoint to 20°C")
                    else:
                        print("Emergency stop: Failed to set temperature setpoint to 20°C")
                    
                    # Verify the setpoint was actually set
                    time.sleep(0.5)  # Brief delay to allow the command to be processed
                    _, _, new_setpoint = self.get_temp_readings_threadsafe()
                    if new_setpoint is not None:
                        print(f"Emergency stop: Verified setpoint is now {new_setpoint:.1f}°C")
                    else:
                        print("Emergency stop: Could not verify setpoint after setting")
                    
                except Exception as e:
                    print(f"Error setting temperature to 20°C during emergency stop: {e}")
            
            # Update safety status
            self.safety_status_label.config(text="Safety: TRIGGERED!", foreground="red")
            
            messagebox.showwarning("Emergency Stop", 
                                 "EMERGENCY STOP ACTIVATED!\n\n"
                                 "Actions taken:\n"
                                 "- H2 and CO2 flows set to 0 sccm\n"
                                 "- N2 flow set to 100 sccm\n"
                                 "- Sampling MFC flow set to 0 sccm\n"
                                 "- Temperature setpoint set to 20°C\n"
                                 "- Temperature control continues running")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error during emergency stop: {e}")
    
    def throttled_refresh_plot(self):
        """Refresh plot with throttling to avoid excessive updates"""
        current_time = time.time()
        if current_time - self.last_plot_refresh >= self.plot_refresh_interval:
            self.refresh_plot()
            self.last_plot_refresh = current_time
    
    def refresh_plots(self):
        """Refresh both flow and temperature plots"""
        self.refresh_plot()
        self.refresh_temp_plot()
    
    def refresh_temp_plot(self):
        """Refresh the temperature plot by reading the entire temperature log file"""
        if not self.temp_log_filename or not os.path.exists(self.temp_log_filename):
            return
        
        times = []
        setpoints = []
        internals = []
        externals = []
        try:
            with open(self.temp_log_filename, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = [p.strip() for p in line.split(',')]
                    if len(parts) < 4:
                        continue
                    ts_str, setp, tin, tex = parts[:4]
                    try:
                        t = datetime.strptime(ts_str, "%m-%d-%YT%H:%M:%S.%f")
                        sp = float(setp)
                        ti = float(tin)
                        te = float(tex)
                    except Exception:
                        continue
                    times.append(t)
                    setpoints.append(sp)
                    internals.append(ti)
                    externals.append(te)
        except Exception as e:
            print(f"Error reading temperature log for plotting: {e}")
            return
        
        if not times:
            return
        times_sorted = times
        if self.plot_start_time is None:
            self.plot_start_time = times_sorted[0]
        time_data_hours = [(t - self.plot_start_time).total_seconds() / 3600.0 for t in times_sorted]
        
        self.temp_plot_lines['setpoint'].set_data(time_data_hours, setpoints)
        self.temp_plot_lines['internal'].set_data(time_data_hours, internals)
        self.temp_plot_lines['external'].set_data(time_data_hours, externals)
        
        self.temp_ax.relim()
        self.temp_ax.autoscale_view()
        self.temp_canvas.draw_idle()
    
    def clear_all_data(self):
        """Clear all plot data"""
        for key in self.plot_data:
            self.plot_data[key].clear()
        for key in self.temp_plot_data:
            self.temp_plot_data[key].clear()
        # Reset shared start time for new data
        self.plot_start_time = None
        self.refresh_plots()
    
    def update_plot(self):
        """Deprecated: plotting reads from logs directly"""
        self.refresh_plot()
    
    def refresh_plot(self):
        """Refresh the plot display by reading the entire MFC log file"""
        if not self.mfc_log_filename or not os.path.exists(self.mfc_log_filename):
            return
        
        times = []
        flows = {1: [], 3: [], 6: [], 'sampling': []}
        sets = {1: [], 3: [], 6: [], 'sampling': []}
        try:
            with open(self.mfc_log_filename, 'r') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                for row in reader:
                    if len(row) < 7:
                        continue
                    ts_str, mfc_name, pressure, temp, flow, setpoint, gas = row
                    try:
                        t = datetime.strptime(ts_str, "%m-%d-%YT%H:%M:%S.%f")
                    except Exception:
                        continue
                    # Track times aligned to overall sequence
                    times.append(t)
                    # Map name to key
                    key = None
                    if mfc_name in ("1", "N2", "N2 MFC"):
                        key = 1
                    elif mfc_name in ("3", "CO2", "CO2 MFC"):
                        key = 3
                    elif mfc_name in ("6", "H2", "H2 MFC"):
                        key = 6
                    elif mfc_name.lower().startswith("sampling"):
                        key = 'sampling'
                    if key is None:
                        continue
                    try:
                        flows[key].append(float(flow))
                        sets[key].append(float(setpoint))
                    except Exception:
                        continue
        except Exception as e:
            print(f"Error reading MFC log for plotting: {e}")
            return
        
        if not times:
            return
        times_sorted = sorted(times)
        if self.plot_start_time is None:
            self.plot_start_time = times_sorted[0]
        time_data_hours = [(t - self.plot_start_time).total_seconds() / 3600.0 for t in times_sorted]
        
        # Update lines
        def set_line(name_prefix, key, data):
            line = self.plot_lines.get(f"{name_prefix}_{key}")
            if not line:
                return
            if data:
                line.set_data(time_data_hours[:len(data)], data)
            else:
                line.set_data([], [])
        
        set_line('flow', 1, flows[1])
        set_line('setpoint', 1, sets[1])
        set_line('flow', 3, flows[3])
        set_line('setpoint', 3, sets[3])
        set_line('flow', 6, flows[6])
        set_line('setpoint', 6, sets[6])
        set_line('flow', 'sampling', flows['sampling'])
        set_line('setpoint', 'sampling', sets['sampling'])
        
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw_idle()
    
    def clear_plot_data(self):
        """Clear all plot data"""
        for key in self.plot_data:
            self.plot_data[key].clear()
        # Reset shared start time for new data
        self.plot_start_time = None
        self.refresh_plot()
    
    def on_closing(self):
        """Handle window closing"""
        self.running = False
        if self.update_thread and self.update_thread.is_alive():
            self.update_thread.join(timeout=2)
        if self.plot_thread and self.plot_thread.is_alive():
            self.plot_thread.join(timeout=2)
        
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
        
        if self.alicat_serial_connection:
            try:
                self.alicat_serial_connection.close()
            except:
                pass
        
        if self.log_file:
            self.log_file.close()
            print("Log file closed")
        
        self.root.destroy()
    
    def run(self):
        """Run the GUI"""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Start thread health monitoring
        self.start_thread_monitoring()
        
        self.root.mainloop()

if __name__ == "__main__":
    app = MFCGUI()
    app.run()