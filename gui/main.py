# gui/main.py

import os
import sys
import json
import threading
import logging
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from configparser import ConfigParser

THIS_DIR         = os.path.dirname(os.path.abspath(__file__))
USB_LOGGER_DIR = os.path.abspath(os.path.join(THIS_DIR, ".."))
sys.path.insert(0, USB_LOGGER_DIR)

import pythoncom
import usb_logger_win
from utils.summary import load_summary, save_summary, SUMMARY_FILE
from utils.config  import WMI_POLL, LOG_FILE, SCRIPT_DIR
from utils.eject   import eject_drive_api

import pystray
from PIL import Image, ImageDraw
import msvcrt
from win10toast import ToastNotifier
import win10toast

def _fixed_on_destroy(self, hwnd, msg, wparam, lparam):
    return 0

win10toast.ToastNotifier.on_destroy = _fixed_on_destroy

LOCK_FILE = os.path.join(os.environ["TEMP"], "usb_logger_gui.lock")

def is_another_instance_running():
    global lockfile
    try:
        lockfile = open(LOCK_FILE, "w")
        msvcrt.locking(lockfile.fileno(), msvcrt.LK_NBLCK, 1)
        return False
    except OSError:
        return True

LOG_PATH     = os.path.join(USB_LOGGER_DIR, LOG_FILE)
SUMMARY_PATH = os.path.join(SCRIPT_DIR, SUMMARY_FILE)
CONFIG_PATH  = os.path.join(USB_LOGGER_DIR, "config.ini")
LOG_FILE_PATH_TO_CLEAR = os.path.join(USB_LOGGER_DIR, LOG_FILE)

# Dark Mode Colors
DARK_BG = "#212121"
DARK_FG = "#E0E0E0"
DARK_ACCENT = "#424242"
DARK_HIGHLIGHT = "#2979FF"
DARK_TEXT_BG = "#2D2D2D"
DARK_WARNING = "#FFB74D"
DARK_ERROR = "#F44336"
DARK_SUCCESS = "#4CAF50"

def start_monitor(stop_event):
    pythoncom.CoInitialize()
    try:
        usb_logger_win.main(stop_event=stop_event)
    except KeyboardInterrupt:
        logging.info("Monitor thread received KeyboardInterrupt, shutting down...")
    except Exception as e:
        logging.error(f"Error in monitor thread: {e}")
    finally:
        pythoncom.CoUninitialize()

def create_tray_icon_image():
    """Create a simple USB icon for the tray."""
    img = Image.new("RGB", (64, 64), "black")
    d = ImageDraw.Draw(img)
    d.text((20, 20), "USB", fill="white")
    return img

def format_bytes(size_bytes):
    """Format bytes into a human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes/1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes/(1024*1024):.2f} MB"
    else:
        return f"{size_bytes/(1024*1024*1024):.2f} GB"

class USBLoggerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("USB Logger Dashboard")
        self.geometry("900x650")
        self.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)

        # Set up tray icon
        self.tray_icon = None
        self.icon_image = create_tray_icon_image()
        self.initialize_tray_icon() # Initialize the tray icon

        # Apply dark theme
        self.apply_dark_theme()

        # Monitor control state
        self.monitor_running = True  # Initially running
        self.stop_event = threading.Event()

        # Notebook tabs
        self.nb = ttk.Notebook(self)
        self.dash_tab = ttk.Frame(self.nb)
        self.dev_tab  = ttk.Frame(self.nb)
        self.set_tab  = ttk.Frame(self.nb)
        for frame, label in ((self.dash_tab,"Dashboard"),
                                    (self.dev_tab, "Devices"),
                                    (self.set_tab, "Settings")):
            self.nb.add(frame, text=label)
        self.nb.pack(fill="both", expand=True)

        self._build_dashboard()
        self._build_devices()
        self._build_settings()
        
        self.notifier = ToastNotifier()
        _orig_arrival = usb_logger_win.handle_usb_arrival
        def _patched_arrival(drive_letter, device_id):
            _orig_arrival(drive_letter, device_id)
            print(f"[DEBUG] patched_arrival: {drive_letter} {device_id}")
            self.notifier.show_toast(
                "USB Attached",
                f"{drive_letter} is now online",
                duration=4,
                threaded=True
            )
        usb_logger_win.handle_usb_arrival = _patched_arrival

        # start monitor thread
        self.stop_event = threading.Event()
        self.monitor_thread = threading.Thread(
            target=start_monitor,
            args=(self.stop_event,),
            daemon=True
        )
        self.monitor_thread.start()

        # Handle Ctrl+C in main thread
        self.bind_all("<Control-c>", self.handle_keyboard_interrupt)
        
        # Start the tray icon in a separate thread
        tray_thread = threading.Thread(target=self._run_tray, daemon=True)
        tray_thread.start()

    def toggle_monitor(self):
        if self.monitor_running:
            self.stop_event.set()
            self.toggle_monitor_btn.config(text="Start Monitoring")
            logging.info("Stopping Monitor...")
            self.monitor_running = False
        else:
            self.stop_event.clear()
            self.monitor_thread = threading.Thread(target=start_monitor, args=(self.stop_event,), daemon=True)
            self.monitor_thread.start()
            self.toggle_monitor_btn.config(text="Stop Monitoring")
            logging.info("Monitoring started.")
            self.monitor_running = True
        # Update tray menu text after toggling
        if self.tray_icon:
            self.tray_icon.update_menu()

    def apply_dark_theme(self):
        """Apply dark mode theme to the application."""
        self.configure(bg=DARK_BG)
        style = ttk.Style()

        # Configure the base theme
        style.theme_use('clam')

        # Configure colors for various elements
        style.configure('TFrame', background=DARK_BG)
        style.configure('TLabel', background=DARK_BG, foreground=DARK_FG)
        style.configure('TButton', background=DARK_ACCENT, foreground=DARK_FG)
        style.configure('TNotebook', background=DARK_BG)
        style.configure('TNotebook.Tab', background=DARK_ACCENT, foreground=DARK_FG, padding=[10, 2])
        style.map('TNotebook.Tab', background=[('selected', DARK_HIGHLIGHT)],
                        foreground=[('selected', DARK_FG)])
        style.configure('Treeview',
                                 background=DARK_BG,
                                 foreground=DARK_FG,
                                 fieldbackground=DARK_BG)
        style.map('Treeview', background=[('selected', DARK_HIGHLIGHT)])
        style.configure('TScrollbar', background=DARK_ACCENT, troughcolor=DARK_BG, bordercolor=DARK_BG)
        style.configure('TCombobox', background=DARK_BG, foreground=DARK_FG, fieldbackground=DARK_BG)
        style.configure('Vertical.TScrollbar', background=DARK_ACCENT)
        style.configure('Horizontal.TScrollbar', background=DARK_ACCENT)
        style.configure('TPanedwindow', background=DARK_BG)

        # ─── Hover / Active State Overrides ──────────────────────────────────────
        HOVER_BG = "#1A237E"
        HOVER_ACCENT = "#1A237E"

        # Buttons: background glows when hovered
        style.map(
            'TButton',
            background=[('active', HOVER_ACCENT), ('!active', DARK_ACCENT)],
            foreground=[('active', DARK_FG)]
        )

        # Tabs lighten on hover, but stay highlighted when selected
        # ─── Tabs: unify hover & selected to light blue ───────────────────────────
        style.map(
            'TNotebook.Tab',
            background=[
                ('active',      DARK_HIGHLIGHT),  # hover
                ('selected',    DARK_HIGHLIGHT),  # selected
                ('!selected',   DARK_ACCENT)      # idle
            ],
            foreground=[
                ('active',      DARK_FG),
                ('selected',    DARK_FG),
                ('!selected',   DARK_FG)
            ]
        )

        # give Treeview a focus/hover background
        style.map(
            'Treeview',
            background=[
                ('selected', DARK_HIGHLIGHT),
                ('focus',    HOVER_BG)
            ]
        )

        # Treeview rows
        style.map(
            'Treeview',
            background=[
                ('selected', DARK_HIGHLIGHT),
            ]
        )
        # ─── Combobox & drop‑down dark styling ──────────────────────────────────
        # Style the combobox “field” and arrow
        style.configure(
            'TCombobox',
            fieldbackground=DARK_BG,
            background=DARK_BG,
            foreground=DARK_FG,
            arrowcolor=DARK_FG
        )
        style.map(
            'TCombobox',
            fieldbackground=[('readonly', DARK_BG)],
            foreground=[('readonly', DARK_FG)]
        )

        # Make every Listbox (including the Combobox drop‑down) dark
        self.option_add('*Listbox.background',        DARK_BG)
        self.option_add('*Listbox.foreground',        DARK_FG)
        self.option_add('*Listbox.selectBackground',DARK_HIGHLIGHT)
        self.option_add('*Listbox.selectForeground',DARK_FG)

    def handle_keyboard_interrupt(self, event=None):
        """Handle Ctrl+C event properly"""
        self.exit_app()
        return "break"  # Prevent default handling

    def _clear_log_file(self):
        """Clears the content of the specified log file."""
        try:
            with open(LOG_FILE_PATH_TO_CLEAR, 'w') as f:
                f.write('')  # Truncate the file
            messagebox.showinfo("Log Cleared", "Log file has been cleared.")
            self._poll_log() # Refresh the log view in the GUI
        except Exception as e:
            logging.error(f"Error clearing log file: {e}")
            messagebox.showerror("Error", f"Could not clear log file: {e}")

    # ─── Dashboard Tab ──────────────────────────────────────────────────────────
    def _build_dashboard(self):
        frm = self.dash_tab
        frm.configure(style='TFrame')

        # log viewer
        self.log_text = tk.Text(frm, state="disabled", wrap="none",
                                     bg=DARK_TEXT_BG, fg=DARK_FG,
                                     insertbackground=DARK_FG)
        ysb = ttk.Scrollbar(frm, orient="vertical",  command=self.log_text.yview)
        xsb = ttk.Scrollbar(frm, orient="horizontal", command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)

        # Add buttons at the bottom
        btn_frame = ttk.Frame(frm, style='TFrame')

        self.toggle_monitor_btn = ttk.Button(btn_frame, text="Stop Monitoring", command=self.toggle_monitor)
        self.toggle_monitor_btn.pack(side="left", padx=5, pady=5)

        clear_log_btn = ttk.Button(btn_frame, text="Clear Log", command=self._clear_log_file)
        clear_log_btn.pack(side="left", padx=5, pady=5)

        view_log_btn = ttk.Button(btn_frame, text="View Log in External Editor",
                                         command=self.on_view_log)
        view_log_btn.pack(side="right", padx=5, pady=5)

        exit_btn = ttk.Button(btn_frame, text="Exit", command=self.exit_app)
        exit_btn.pack(side="right", padx=5, pady=5)

        # Grid layout
        self.log_text.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        btn_frame.grid(row=2, column=0, columnspan=2, sticky="ew")

        frm.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)

        self.after(1000, self._poll_log)

    def _poll_log(self):
        if not self.winfo_exists():
            return

        if os.path.exists(LOG_PATH):
            try:
                with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()[-200:]
                self.log_text.config(state="normal")
                self.log_text.delete("1.0", "end")
                self.log_text.insert("end", "".join(lines))
                self.log_text.see("end")
                self.log_text.config(state="disabled")
            except Exception as e:
                logging.error(f"Error reading log file: {e}")

        try:
            self.after(1000, self._poll_log)
        except tk.TclError:
            pass

    # ─── Devices Tab ───────────────────────────────────────────────────────────
    def _build_devices(self):
        frm = self.dev_tab
        frm.configure(style='TFrame')

        # Create a PanedWindow to divide the frame
        pw = ttk.PanedWindow(frm, orient=tk.HORIZONTAL)
        pw.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left pane - device list
        left_frame = ttk.Frame(pw)
        pw.add(left_frame, weight=1)

        # Right pane - device details
        right_frame = ttk.Frame(pw)
        pw.add(right_frame, weight=1)

        # Set up the left pane with the device list
        cols = ("first_seen", "last_drive", "last_state")
        self.tree = ttk.Treeview(left_frame, columns=cols, show="headings", style='Treeview')
        self.tree.heading("first_seen", text="First Seen")
        self.tree.heading("last_drive", text="Drive")
        self.tree.heading("last_state", text="State")

        # Adjust column widths
        self.tree.column("first_seen", width=150)
        self.tree.column("last_drive", width=50)
        self.tree.column("last_state", width=80)

        # Add scrollbars
        tree_ysb = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree.yview)
        tree_xsb = ttk.Scrollbar(left_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_ysb.set, xscrollcommand=tree_xsb.set)

        # Pack the treeview with scrollbars
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_ysb.grid(row=0, column=1, sticky="ns")
        tree_xsb.grid(row=1, column=0, sticky="ew")
        left_frame.rowconfigure(0, weight=1)
        left_frame.columnconfigure(0, weight=1)

        # Add selection event
        self.tree.bind("<<TreeviewSelect>>", self.on_device_select)

        """
        # Button frame for left pane
        btn_frame = ttk.Frame(left_frame, style='TFrame')
        ttk.Button(btn_frame, text="Eject Selected", command=self.on_eject).pack(side="left", padx=5)
        btn_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=5)
        """

        # Set up the right pane with device details
        self.device_details_frame = ttk.Frame(right_frame)
        self.device_details_frame.pack(fill=tk.BOTH, expand=True)

        # Device details header
        self.dev_header = ttk.Label(self.device_details_frame, text="Device Details",
                                         font=("TkDefaultFont", 12, "bold"),
                                         foreground=DARK_FG, background=DARK_BG)
        self.dev_header.pack(fill=tk.X, pady=(0, 10))

        # Device details text
        self.details_text = scrolledtext.ScrolledText(self.device_details_frame,
                                                                         wrap=tk.WORD,
                                                                         bg=DARK_TEXT_BG,
                                                                         fg=DARK_FG,
                                                                         font=("TkDefaultFont", 10),
                                                                         height=20)
        self.details_text.pack(fill=tk.BOTH, expand=True)
        self.details_text.insert(tk.END, "Select a device to view details")
        self.details_text.config(state=tk.DISABLED)

        self._update_devices()

    def _update_devices(self):
        if not self.winfo_exists():  # Check if window still exists
            return

        try:
            # Remember selected item
            selected = self.tree.selection()
            selected_id = selected[0] if selected else None

            self.tree.delete(*self.tree.get_children())
            summary = load_summary()
            for dev, data in summary.items():
                # Show a shorter version of the device ID
                display_id = dev.split("\\")[-2] if "\\" in dev else dev
                if len(display_id) > 20:
                    display_id = display_id[:17] + "..."

                # Add to tree view with simplified data
                self.tree.insert("", "end", iid=dev, values=(
                    data.get("first_seen", "")[:16],
                    data.get("last_drive_letter", ""),
                    data.get("last_state", ""),
                ))

            # Restore selection if possible
            if selected_id and selected_id in summary:
                self.tree.selection_set(selected_id)
                self.tree.see(selected_id)

            self.after(2000, self._update_devices)
        except tk.TclError:
            # Widget destroyed, stop updating
            pass
        except Exception as e:
            logging.error(f"Error updating devices: {e}")
            self.after(2000, self._update_devices)

    def on_device_select(self, event):
        """Show details for the selected device."""
        selected = self.tree.selection()
        if not selected:
            return

        dev_id = selected[0]
        self.display_device_details(dev_id)

    def display_device_details(self, dev_id):
        """Display detailed information for a device."""
        summary = load_summary()
        if dev_id not in summary:
            return

        data = summary[dev_id]

        # Format the details
        details = []
        details.append(f"🔹 Device ID: {dev_id}")
        details.append(f"🔹 First Seen: {data.get('first_seen', 'Unknown')}")
        details.append(f"🔹 Last Seen: {data.get('last_seen', 'Unknown')}")
        details.append(f"🔹 Last Drive Letter: {data.get('last_drive_letter', 'Unknown')}")
        details.append(f"🔹 Last State: {data.get('last_state', 'Unknown')}")
        details.append(f"🔹 Total Connections: {data.get('arrival_count', 0)}")
        details.append(f"🔹 Eject Success Count: {data.get('total_eject_success', 0)}")
        details.append(f"🔹 Eject Failure Count: {data.get('total_eject_failure', 0)}")

        # Volume details
        vol_details = data.get("volume_details", {})
        if vol_details:
            details.append("\n📁 Volume Details:")
            details.append(f"  • Name: {vol_details.get('VolumeName', 'Unknown')}")
            details.append(f"  • File System: {vol_details.get('FileSystem', 'Unknown')}")

            # Format size and free space
            size = vol_details.get('Size', '0')
            free = vol_details.get('FreeSpace', '0')
            try:
                size_bytes = int(size)
                free_bytes = int(free)
                details.append(f"  • Total Size: {format_bytes(size_bytes)}")
                details.append(f"  • Free Space: {format_bytes(free_bytes)}")
                details.append(f"  • Used Space: {format_bytes(size_bytes - free_bytes)}")
                used_percent = ((size_bytes - free_bytes) / size_bytes) * 100 if size_bytes > 0 else 0
                details.append(f"  • Used: {used_percent:.1f}%")
            except (ValueError, TypeError):
                details.append(f"  • Size: {size}")
                details.append(f"  • Free Space: {free}")

        # File enumeration details
        enum_data = data.get("extra_data", {}).get("files_enumeration", {})
        if enum_data:
            details.append("\n📄 Top-Level Files and Directories:")
            for file_name, file_info in enum_data.items():
                is_dir = file_info.get("is_dir", False)
                icon = "📁" if is_dir else "📄"
                details.append(f"  {icon} {file_name}")
                details.append(f"    • Created: {file_info.get('created', 'Unknown')}")
                details.append(f"    • Modified: {file_info.get('modified', 'Unknown')}")

                # Format size for files
                if not is_dir:
                    size = file_info.get("size", 0)
                    try:
                        details.append(f"    • Size: {format_bytes(int(size))}")
                    except (ValueError, TypeError):
                        details.append(f"    • Size: {size}")

        # Update the details text widget
        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete("1.0", tk.END)
        self.details_text.insert(tk.END, "\n".join(details))
        self.details_text.config(state=tk.DISABLED)

    def on_eject(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select a device","Pick a row first")
            return
        dev = sel[0]
        summary = load_summary()
        drive = summary.get(dev, {}).get("last_drive_letter")
        if not drive:
            messagebox.showerror("No drive letter", f"No letter recorded for {dev}")
            return
        ok = eject_drive_api(drive, dev)
        
        self.notifier.show_toast(
            "USB Eject",
            f"{drive} {'ejected' if ok else 'failed to eject'}",
            duration=4,
            threaded=True
        )
        
        messagebox.showinfo("Eject", f"{drive} {'ejected' if ok else 'failed to eject'}")

    def on_view_log(self):
        if os.path.exists(LOG_PATH):
            webbrowser.open(f"file:///{LOG_PATH}")
        else:
            messagebox.showwarning("Missing log", f"Log not found:\n{LOG_PATH}")

    # ─── Settings Tab ──────────────────────────────────────────────────────────
    def _build_settings(self):
        frm = self.set_tab
        frm.configure(style='TFrame')

        # Create a settings container with padding
        settings_frame = ttk.Frame(frm, style='TFrame')
        settings_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Settings title
        ttk.Label(settings_frame, text="Application Settings",
                        font=("TkDefaultFont", 12, "bold"),
                        foreground=DARK_FG).grid(row=0, column=0, columnspan=2, pady=(0, 20), sticky="w")

        # Enumeration Level
        ttk.Label(settings_frame, text="Enumeration Level:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.enum_var = tk.StringVar()
        cb = ttk.Combobox(settings_frame, textvariable=self.enum_var, values=["none","root"], state="readonly")
        cb.grid(row=1, column=1, padx=10, pady=10, sticky="w")
        ttk.Label(settings_frame, text="Controls the depth of file enumeration on new devices",
                        foreground="#AAAAAA").grid(row=2, column=0, columnspan=2, padx=10, sticky="w")

        """
        # Dark mode toggle
        ttk.Label(settings_frame, text="Dark Mode:").grid(row=3, column=0, padx=10, pady=10, sticky="w")
        self.dark_mode_var = tk.BooleanVar(value=True)  # Default to dark mode
        dark_check = ttk.Checkbutton(settings_frame, variable=self.dark_mode_var,
                                         command=self.toggle_theme)
        dark_check.grid(row=3, column=1, padx=10, pady=10, sticky="w")
        ttk.Label(settings_frame, text="Enable dark theme for the application",
                        foreground="#AAAAAA").grid(row=4, column=0, columnspan=2, padx=10, sticky="w")
        """

        # Log file location
        ttk.Label(settings_frame, text="Log file location:").grid(row=5, column=0, padx=10, pady=10, sticky="w")
        log_path = ttk.Label(settings_frame, text=LOG_PATH, foreground="#AAAAAA")
        log_path.grid(row=5, column=1, padx=10, pady=10, sticky="w")

        # Summary file location
        ttk.Label(settings_frame, text="Summary file location:").grid(row=6, column=0, padx=10, pady=10, sticky="w")
        sum_path = ttk.Label(settings_frame, text=SUMMARY_PATH, foreground="#AAAAAA")
        sum_path.grid(row=6, column=1, padx=10, pady=10, sticky="w")

        # File paths
        file_frame = ttk.Frame(settings_frame, style='TFrame')
        file_frame.grid(row=7, column=0, columnspan=2, padx=10, pady=10, sticky="ew")

        """
        ttk.Button(file_frame, text="Open Log Directory",
                    command=lambda: webbrowser.open(f"file:///{os.path.dirname(LOG_PATH)}")
                    ).pack(side="left", padx=(0, 10))
        """

        ttk.Button(file_frame, text="Open Main Directory",
                    command=lambda: webbrowser.open(f"file:///{os.path.dirname(SUMMARY_PATH)}")
                    ).pack(side="left")

        # make column 1 expandable (so its contents can align left)
        settings_frame.columnconfigure(1, weight=1)

        # place Apply under column 1, aligned to the left edge
        ttk.Button(settings_frame, text="Apply Settings", command=self._apply_settings) \
            .grid(row=7, column=1, sticky="w", padx=10, pady=20)

        # Load current settings
        cfg = ConfigParser()
        if os.path.exists(CONFIG_PATH):
            cfg.read(CONFIG_PATH)
        self.enum_var.set(cfg.get("Enumeration","level",fallback="none"))

    """
    def toggle_theme(self):
        # Just show a message for now - would need app restart to fully apply
        messagebox.showinfo("Theme Change",
                            "Theme preference saved. Restart application to apply changes.")
    """

    def _apply_settings(self):
        cfg = ConfigParser()
        if os.path.exists(CONFIG_PATH):
            cfg.read(CONFIG_PATH)

        if not cfg.has_section("Enumeration"):
            cfg.add_section("Enumeration")
        cfg.set("Enumeration","level", self.enum_var.get())

        """
        if not cfg.has_section("UI"):
            cfg.add_section("UI")
        cfg.set("UI", "dark_mode", str(self.dark_mode_var.get()))
        """

        with open(CONFIG_PATH, "w") as f:
            cfg.write(f)
        messagebox.showinfo("Settings","Settings saved. Some changes require application restart.")

    # ─── Tray & Exit ───────────────────────────────────────────────────────────
    def initialize_tray_icon(self):
        """Initialize the tray icon safely."""
        if self.tray_icon is None:
            try:
                def get_monitor_status(icon):
                    return "Stop Monitoring" if self.monitor_running else "Start Monitoring"

                self.tray_icon = pystray.Icon(
                    "USBLogger",
                    self.icon_image,
                    menu=pystray.Menu(
                        pystray.MenuItem("Show", lambda: self.after(0, self.show_window)),
                        pystray.MenuItem(get_monitor_status, lambda: self.after(0, self.toggle_monitor)),
                        pystray.MenuItem("Exit", lambda: self.after(0, self.exit_app)),
                    ),
                    on_double_click=lambda icon: self.after(0, self.show_window)
                )
                return True
            except Exception as e:
                logging.error(f"Error creating tray icon: {e}")
                return False
        return True

    def minimize_to_tray(self):
        """Minimize the application to system tray."""
        if self.initialize_tray_icon():
            self.withdraw()
            try:
                # Run the tray icon in a separate thread
                tray_thread = threading.Thread(target=self._run_tray, daemon=True)
                tray_thread.start()
            except Exception as e:
                logging.error(f"Error running tray icon: {e}")
                self.deiconify()  # Show window again on error
        else:
            # If we can't create the tray icon, just minimize
            self.iconify()

    def _run_tray(self):
        """Run the tray icon in a thread-safe way."""
        try:
            if self.tray_icon and not self.tray_icon.visible:
                self.tray_icon.run()
        except Exception as e:
            logging.error(f"Error in tray icon: {e}")

    def show_window(self):
        """Show the window from tray."""
        try:
            self.deiconify()
        except Exception as e:
            logging.error(f"Error showing window: {e}")

    def exit_app(self):
        """Clean exit the application."""
        # Save device summary before exit
        try:
            summary = load_summary()
            save_summary(summary)
            logging.info("Summary saved on exit")
        except Exception as e:
            logging.error(f"Error saving summary on exit: {e}")

        # Clean exit
        try:
            # Stop tray icon if it exists and is running
            if hasattr(self, 'tray_icon') and self.tray_icon and self.tray_icon.visible:
                try:
                    self.tray_icon.stop()
                except:
                    pass
        except:
            pass

        # signal the monitor’s stop_event
        self.stop_event.set()
        # wait up to 5 s for it to finish
        self.monitor_thread.join(timeout=5)
        
        # Destroy the window and exit
        self.destroy()
        
        try:
            msvcrt.locking(lockfile.fileno(), msvcrt.LK_UNLCK, 1)
            lockfile.close()
            os.remove(LOCK_FILE)
        except:
            pass
        
        sys.exit(0)

if __name__=="__main__":
    
    if is_another_instance_running():
        messagebox.showerror("Already Running", "USB Logger is already running.")
        sys.exit(1)
    
    try:
        # Set up basic logging
        logging.basicConfig(
            level=logging.INFO,
            format='CONSOLE: %(levelname)s - %(message)s'
        )
        app = USBLoggerGUI()
        app.mainloop()
    except KeyboardInterrupt:
        logging.info("Application received KeyboardInterrupt, shutting down...")
        if 'app' in locals():
            app.exit_app()
        sys.exit(0)
