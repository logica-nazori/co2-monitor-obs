import os
import sys
import json
import asyncio
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData


# --- Constants ---
SWITCHBOT_COMPANY_ID = 0x0969
SWITCHBOT_SERVICE_UUID = "0000fd3d-0000-1000-8000-00805f9b34fb"
DEVICE_TYPE_CO2_SERVICE = 0x35
APP_NAME = "CO2配信モニター for OBS"
CONFIG_FILE = "config.json"


# --- BLE Parser ---
def parse_manufacturer_data(mac_address: str, data: bytes) -> dict | None:
    if len(data) < 15:
        return None
    mac_from_data = ":".join(f"{b:02X}" for b in data[0:6])
    if mac_from_data != mac_address.upper():
        return None
    temp_decimal = (data[8] & 0x0F) * 0.1
    temp_integer = data[9] & 0x7F
    temperature = temp_integer + temp_decimal
    humidity = data[10] & 0x7F
    co2 = (data[13] << 8) | data[14]
    return {
        "co2": co2,
        "temperature": round(temperature, 1),
        "humidity": humidity,
    }


# --- Config ---
def get_config_path():
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, CONFIG_FILE)


def load_config() -> dict:
    path = get_config_path()
    defaults = {
        "device_mac": "",
        "co2_threshold": 1000,
        "temp_high_threshold": 30.0,
        "temp_low_threshold": 16.0,
        "humidity_high_threshold": 70,
        "humidity_low_threshold": 30,
        "enable_co2_alert": True,
        "enable_temp_alert": False,
        "enable_humidity_alert": False,
        "scan_interval": 5,
        "output_dir": "",
        "alert_co2": "⚠ CO2が高いです！換気してください！",
        "alert_temp_high": "🌡 暑すぎます！エアコンをつけましょう！",
        "alert_temp_low": "🌡 寒すぎます！暖房をつけましょう！",
        "alert_humid_high": "💧 湿度が高すぎます！",
        "alert_humid_low": "💧 乾燥しています！加湿しましょう！",
    }
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)
                defaults.update(saved)
        except Exception:
            pass
    return defaults


def save_config(config: dict):
    path = get_config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# --- File Writer ---
def write_to_file(filepath: str, content: str):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    except IOError:
        pass


# --- Device Scanner ---
async def scan_for_devices(timeout=10):
    devices_found = []
    found_macs = set()

    def callback(device: BLEDevice, adv: AdvertisementData):
        mac = None
        dtype = "SwitchBotデバイス"
        name = device.name or "(名前なし)"

        if SWITCHBOT_COMPANY_ID in adv.manufacturer_data:
            mfr = adv.manufacturer_data[SWITCHBOT_COMPANY_ID]
            if len(mfr) >= 6:
                mac = ":".join(f"{b:02X}" for b in mfr[0:6])
                if len(mfr) >= 15:
                    dtype = "CO2センサー"

        if mac is None:
            for uuid, data in adv.service_data.items():
                if uuid.lower() == SWITCHBOT_SERVICE_UUID and len(data) >= 1:
                    mac = device.address.upper()
                    if data[0] == DEVICE_TYPE_CO2_SERVICE:
                        dtype = "CO2センサー"
                    break

        if mac and mac not in found_macs:
            found_macs.add(mac)
            devices_found.append({"mac": mac, "name": name, "type": dtype})

    scanner = BleakScanner(detection_callback=callback)
    await scanner.start()
    await asyncio.sleep(timeout)
    await scanner.stop()
    return devices_found


# --- Main GUI ---
class CO2MonitorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("520x720")
        self.root.resizable(False, False)
        self.root.configure(bg="#1a1a2e")

        self.config = load_config()
        self.monitoring = False
        self.monitor_thread = None
        self.stop_event = threading.Event()

        self._build_ui()
        self._load_config_to_ui()

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        bg = "#1a1a2e"
        card_bg = "#16213e"
        accent = "#0f3460"
        highlight = "#e94560"
        text_color = "#eee"
        green = "#00d474"

        style.configure("Card.TFrame", background=card_bg)
        style.configure("BG.TFrame", background=bg)
        style.configure("Title.TLabel", background=bg, foreground=highlight,
                        font=("Segoe UI", 16, "bold"))
        style.configure("Card.TLabel", background=card_bg, foreground=text_color,
                        font=("Segoe UI", 10))
        style.configure("CardSmall.TLabel", background=card_bg, foreground="#aaa",
                        font=("Segoe UI", 9))
        style.configure("Big.TLabel", background=card_bg, foreground=green,
                        font=("Segoe UI", 28, "bold"))
        style.configure("Info.TLabel", background=card_bg, foreground="#aaa",
                        font=("Segoe UI", 11))
        style.configure("Status.TLabel", background=bg, foreground="#888",
                        font=("Segoe UI", 9))
        style.configure("Accent.TButton", background=accent, foreground=text_color,
                        font=("Segoe UI", 10, "bold"), padding=(10, 5))
        style.map("Accent.TButton",
                  background=[("active", highlight), ("disabled", "#333")])
        style.configure("Start.TButton", background=green, foreground="#000",
                        font=("Segoe UI", 12, "bold"), padding=(10, 8))
        style.map("Start.TButton",
                  background=[("active", "#00b863"), ("disabled", "#555")])
        style.configure("Stop.TButton", background=highlight, foreground="#fff",
                        font=("Segoe UI", 12, "bold"), padding=(10, 8))
        style.map("Stop.TButton",
                  background=[("active", "#c73151"), ("disabled", "#555")])
        style.configure("Card.TCheckbutton", background=card_bg, foreground=text_color,
                        font=("Segoe UI", 9))

        # Scrollable container
        canvas = tk.Canvas(self.root, bg=bg, highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        main_frame = ttk.Frame(canvas, style="BG.TFrame")
        canvas.create_window((0, 0), window=main_frame, anchor="nw")

        def on_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas.find_all()[0], width=e.width)
        canvas.bind("<Configure>", on_configure)

        # Title
        ttk.Label(main_frame, text=f"🌿 {APP_NAME}", style="Title.TLabel").pack(
            pady=(15, 10))

        # --- Settings Card ---
        settings_frame = ttk.Frame(main_frame, style="Card.TFrame", padding=15)
        settings_frame.pack(fill="x", padx=15, pady=(0, 8))

        row0 = ttk.Frame(settings_frame, style="Card.TFrame")
        row0.pack(fill="x", pady=(0, 5))
        ttk.Label(row0, text="デバイスMAC:", style="Card.TLabel").pack(side="left")
        self.mac_var = tk.StringVar()
        self.mac_entry = ttk.Entry(row0, textvariable=self.mac_var, width=22,
                                   font=("Consolas", 10))
        self.mac_entry.pack(side="left", padx=(5, 5))
        self.scan_btn = ttk.Button(row0, text="🔍 検索", style="Accent.TButton",
                                   command=self._scan_devices)
        self.scan_btn.pack(side="left")

        row1 = ttk.Frame(settings_frame, style="Card.TFrame")
        row1.pack(fill="x", pady=(5, 5))
        ttk.Label(row1, text="出力フォルダ:", style="Card.TLabel").pack(side="left")
        self.out_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.out_var, width=28,
                  font=("Segoe UI", 9)).pack(side="left", padx=(5, 5))
        ttk.Button(row1, text="📁", style="Accent.TButton",
                   command=self._browse_output).pack(side="left")

        row2 = ttk.Frame(settings_frame, style="Card.TFrame")
        row2.pack(fill="x", pady=(5, 0))
        ttk.Label(row2, text="間隔(秒):", style="Card.TLabel").pack(side="left")
        self.interval_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.interval_var, width=4,
                  font=("Consolas", 10)).pack(side="left", padx=(5, 0))

        # --- Alert Settings Card ---
        alert_frame = ttk.Frame(main_frame, style="Card.TFrame", padding=15)
        alert_frame.pack(fill="x", padx=15, pady=(0, 8))

        ttk.Label(alert_frame, text="⚠ アラート設定", style="Card.TLabel",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))

        # CO2 threshold
        co2_row = ttk.Frame(alert_frame, style="Card.TFrame")
        co2_row.pack(fill="x", pady=(0, 3))
        self.co2_alert_var = tk.BooleanVar()
        ttk.Checkbutton(co2_row, text="CO2アラート", variable=self.co2_alert_var,
                        style="Card.TCheckbutton").pack(side="left")
        self.threshold_var = tk.StringVar()
        ttk.Entry(co2_row, textvariable=self.threshold_var, width=6,
                  font=("Consolas", 10)).pack(side="left", padx=(10, 3))
        ttk.Label(co2_row, text="ppm超", style="CardSmall.TLabel").pack(side="left")

        co2_msg_row = ttk.Frame(alert_frame, style="Card.TFrame")
        co2_msg_row.pack(fill="x", pady=(0, 6))
        ttk.Label(co2_msg_row, text="  文言:", style="CardSmall.TLabel").pack(side="left")
        self.alert_co2_var = tk.StringVar()
        ttk.Entry(co2_msg_row, textvariable=self.alert_co2_var, width=38,
                  font=("Segoe UI", 9)).pack(side="left", padx=(5, 0))

        # Temperature threshold
        temp_row = ttk.Frame(alert_frame, style="Card.TFrame")
        temp_row.pack(fill="x", pady=(0, 3))
        self.temp_alert_var = tk.BooleanVar()
        ttk.Checkbutton(temp_row, text="温度アラート", variable=self.temp_alert_var,
                        style="Card.TCheckbutton").pack(side="left")
        self.temp_low_var = tk.StringVar()
        ttk.Entry(temp_row, textvariable=self.temp_low_var, width=5,
                  font=("Consolas", 10)).pack(side="left", padx=(10, 2))
        ttk.Label(temp_row, text="°C以下 /", style="CardSmall.TLabel").pack(side="left")
        self.temp_high_var = tk.StringVar()
        ttk.Entry(temp_row, textvariable=self.temp_high_var, width=5,
                  font=("Consolas", 10)).pack(side="left", padx=(5, 2))
        ttk.Label(temp_row, text="°C以上", style="CardSmall.TLabel").pack(side="left")

        temp_msg_row = ttk.Frame(alert_frame, style="Card.TFrame")
        temp_msg_row.pack(fill="x", pady=(0, 3))
        ttk.Label(temp_msg_row, text="  高温:", style="CardSmall.TLabel").pack(side="left")
        self.alert_temp_high_var = tk.StringVar()
        ttk.Entry(temp_msg_row, textvariable=self.alert_temp_high_var, width=38,
                  font=("Segoe UI", 9)).pack(side="left", padx=(5, 0))
        temp_msg_row2 = ttk.Frame(alert_frame, style="Card.TFrame")
        temp_msg_row2.pack(fill="x", pady=(0, 6))
        ttk.Label(temp_msg_row2, text="  低温:", style="CardSmall.TLabel").pack(side="left")
        self.alert_temp_low_var = tk.StringVar()
        ttk.Entry(temp_msg_row2, textvariable=self.alert_temp_low_var, width=38,
                  font=("Segoe UI", 9)).pack(side="left", padx=(5, 0))

        # Humidity threshold
        humid_row = ttk.Frame(alert_frame, style="Card.TFrame")
        humid_row.pack(fill="x", pady=(0, 3))
        self.humid_alert_var = tk.BooleanVar()
        ttk.Checkbutton(humid_row, text="湿度アラート", variable=self.humid_alert_var,
                        style="Card.TCheckbutton").pack(side="left")
        self.humid_low_var = tk.StringVar()
        ttk.Entry(humid_row, textvariable=self.humid_low_var, width=4,
                  font=("Consolas", 10)).pack(side="left", padx=(10, 2))
        ttk.Label(humid_row, text="%以下 /", style="CardSmall.TLabel").pack(side="left")
        self.humid_high_var = tk.StringVar()
        ttk.Entry(humid_row, textvariable=self.humid_high_var, width=4,
                  font=("Consolas", 10)).pack(side="left", padx=(5, 2))
        ttk.Label(humid_row, text="%以上", style="CardSmall.TLabel").pack(side="left")

        humid_msg_row = ttk.Frame(alert_frame, style="Card.TFrame")
        humid_msg_row.pack(fill="x", pady=(0, 3))
        ttk.Label(humid_msg_row, text="  高湿:", style="CardSmall.TLabel").pack(side="left")
        self.alert_humid_high_var = tk.StringVar()
        ttk.Entry(humid_msg_row, textvariable=self.alert_humid_high_var, width=38,
                  font=("Segoe UI", 9)).pack(side="left", padx=(5, 0))
        humid_msg_row2 = ttk.Frame(alert_frame, style="Card.TFrame")
        humid_msg_row2.pack(fill="x", pady=(0, 0))
        ttk.Label(humid_msg_row2, text="  低湿:", style="CardSmall.TLabel").pack(side="left")
        self.alert_humid_low_var = tk.StringVar()
        ttk.Entry(humid_msg_row2, textvariable=self.alert_humid_low_var, width=38,
                  font=("Segoe UI", 9)).pack(side="left", padx=(5, 0))

        # --- Monitor Display Card ---
        display_frame = ttk.Frame(main_frame, style="Card.TFrame", padding=20)
        display_frame.pack(fill="x", padx=15, pady=(0, 8))

        self.co2_label = ttk.Label(display_frame, text="--- ppm", style="Big.TLabel")
        self.co2_label.pack()

        info_row = ttk.Frame(display_frame, style="Card.TFrame")
        info_row.pack(pady=(10, 0))
        self.temp_label = ttk.Label(info_row, text="🌡 --.-°C", style="Info.TLabel")
        self.temp_label.pack(side="left", padx=15)
        self.humid_label = ttk.Label(info_row, text="💧 --%", style="Info.TLabel")
        self.humid_label.pack(side="left", padx=15)

        self.alert_label = ttk.Label(display_frame, text="", style="Card.TLabel",
                                     font=("Segoe UI", 11, "bold"),
                                     foreground=highlight, wraplength=450)
        self.alert_label.pack(pady=(10, 0))

        # --- Start/Stop Button ---
        self.start_btn = ttk.Button(main_frame, text="▶  モニタリング開始",
                                    style="Start.TButton",
                                    command=self._toggle_monitoring)
        self.start_btn.pack(fill="x", padx=15, pady=(0, 8))

        # --- Status Bar ---
        self.status_label = ttk.Label(main_frame, text="待機中",
                                      style="Status.TLabel")
        self.status_label.pack(pady=(0, 10))

    def _load_config_to_ui(self):
        self.mac_var.set(self.config.get("device_mac", ""))
        self.out_var.set(self.config.get("output_dir", ""))
        self.co2_alert_var.set(self.config.get("enable_co2_alert", True))
        self.threshold_var.set(str(self.config.get("co2_threshold", 1000)))
        self.interval_var.set(str(self.config.get("scan_interval", 5)))
        self.temp_alert_var.set(self.config.get("enable_temp_alert", False))
        self.temp_high_var.set(str(self.config.get("temp_high_threshold", 30.0)))
        self.temp_low_var.set(str(self.config.get("temp_low_threshold", 16.0)))
        self.humid_alert_var.set(self.config.get("enable_humidity_alert", False))
        self.humid_high_var.set(str(self.config.get("humidity_high_threshold", 70)))
        self.humid_low_var.set(str(self.config.get("humidity_low_threshold", 30)))
        self.alert_co2_var.set(self.config.get("alert_co2", "⚠ CO2が高いです！換気してください！"))
        self.alert_temp_high_var.set(self.config.get("alert_temp_high", "🌡 暑すぎます！エアコンをつけましょう！"))
        self.alert_temp_low_var.set(self.config.get("alert_temp_low", "🌡 寒すぎます！暖房をつけましょう！"))
        self.alert_humid_high_var.set(self.config.get("alert_humid_high", "💧 湿度が高すぎます！"))
        self.alert_humid_low_var.set(self.config.get("alert_humid_low", "💧 乾燥しています！加湿しましょう！"))

    def _save_config_from_ui(self):
        self.config["device_mac"] = self.mac_var.get().strip()
        self.config["output_dir"] = self.out_var.get().strip()
        self.config["enable_co2_alert"] = self.co2_alert_var.get()
        try:
            self.config["co2_threshold"] = int(self.threshold_var.get())
        except ValueError:
            self.config["co2_threshold"] = 1000
        try:
            self.config["scan_interval"] = int(self.interval_var.get())
        except ValueError:
            self.config["scan_interval"] = 5
        self.config["enable_temp_alert"] = self.temp_alert_var.get()
        try:
            self.config["temp_high_threshold"] = float(self.temp_high_var.get())
        except ValueError:
            self.config["temp_high_threshold"] = 30.0
        try:
            self.config["temp_low_threshold"] = float(self.temp_low_var.get())
        except ValueError:
            self.config["temp_low_threshold"] = 16.0
        self.config["enable_humidity_alert"] = self.humid_alert_var.get()
        try:
            self.config["humidity_high_threshold"] = int(self.humid_high_var.get())
        except ValueError:
            self.config["humidity_high_threshold"] = 70
        try:
            self.config["humidity_low_threshold"] = int(self.humid_low_var.get())
        except ValueError:
            self.config["humidity_low_threshold"] = 30
        self.config["alert_co2"] = self.alert_co2_var.get()
        self.config["alert_temp_high"] = self.alert_temp_high_var.get()
        self.config["alert_temp_low"] = self.alert_temp_low_var.get()
        self.config["alert_humid_high"] = self.alert_humid_high_var.get()
        self.config["alert_humid_low"] = self.alert_humid_low_var.get()
        save_config(self.config)

    def _browse_output(self):
        d = filedialog.askdirectory()
        if d:
            self.out_var.set(d)

    def _scan_devices(self):
        self.scan_btn.configure(state="disabled")
        self.status_label.configure(
            text="BLEスキャン中... (センサーのボタンを押すと検出されやすくなります)")

        def do_scan():
            loop = asyncio.new_event_loop()
            devices = loop.run_until_complete(scan_for_devices(10))
            loop.close()
            self.root.after(0, lambda: self._show_scan_results(devices))

        threading.Thread(target=do_scan, daemon=True).start()

    def _show_scan_results(self, devices):
        self.scan_btn.configure(state="normal")

        if not devices:
            self.status_label.configure(text="デバイスが見つかりませんでした")
            messagebox.showinfo("スキャン結果",
                                "SwitchBotデバイスが見つかりませんでした。\n\n"
                                "以下をお試しください：\n"
                                "• CO2センサーのボタンを長押ししてから再度検索\n"
                                "• センサーの電源が入っていることを確認\n"
                                "• PCのBluetooth範囲内にあることを確認")
            return

        co2_devices = [d for d in devices if "CO2" in d["type"]]
        if len(co2_devices) == 1:
            self.mac_var.set(co2_devices[0]["mac"])
            self.status_label.configure(
                text=f"CO2センサーを自動選択: {co2_devices[0]['mac']}")
            return

        win = tk.Toplevel(self.root)
        win.title("デバイス選択")
        win.geometry("400x250")
        win.configure(bg="#1a1a2e")
        win.transient(self.root)
        win.grab_set()

        ttk.Label(win, text="検出されたデバイス:", style="Card.TLabel").pack(
            pady=(10, 5))

        listbox = tk.Listbox(win, font=("Consolas", 10), height=8,
                             bg="#16213e", fg="#eee", selectbackground="#0f3460")
        for d in devices:
            listbox.insert(tk.END, f"{d['mac']}  [{d['type']}]")
        listbox.pack(fill="x", padx=15, pady=5)

        def select():
            sel = listbox.curselection()
            if sel:
                self.mac_var.set(devices[sel[0]]["mac"])
                self.status_label.configure(text=f"選択: {devices[sel[0]]['mac']}")
            win.destroy()

        ttk.Button(win, text="選択", style="Accent.TButton",
                   command=select).pack(pady=10)

    def _toggle_monitoring(self):
        if self.monitoring:
            self._stop_monitoring()
        else:
            self._start_monitoring()

    def _start_monitoring(self):
        mac = self.mac_var.get().strip()
        if not mac:
            messagebox.showwarning("設定エラー",
                                   "デバイスMACアドレスを入力するか、\n"
                                   "「検索」ボタンでデバイスを探してください。")
            return

        self._save_config_from_ui()
        self.monitoring = True
        self.stop_event.clear()

        self.start_btn.configure(text="⏹  モニタリング停止", style="Stop.TButton")
        self.mac_entry.configure(state="disabled")
        self.scan_btn.configure(state="disabled")
        self.status_label.configure(text="モニタリング中...")

        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def _stop_monitoring(self):
        self.monitoring = False
        self.stop_event.set()
        self.start_btn.configure(text="▶  モニタリング開始", style="Start.TButton")
        self.mac_entry.configure(state="normal")
        self.scan_btn.configure(state="normal")
        self.status_label.configure(text="停止しました")

    def _monitor_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        mac = self.config["device_mac"].upper()
        threshold = self.config["co2_threshold"]
        interval = self.config["scan_interval"]
        output_dir = self.config.get("output_dir", "").strip()

        enable_co2_alert = self.config.get("enable_co2_alert", True)
        enable_temp_alert = self.config.get("enable_temp_alert", False)
        temp_high = self.config.get("temp_high_threshold", 30.0)
        temp_low = self.config.get("temp_low_threshold", 16.0)
        enable_humid_alert = self.config.get("enable_humidity_alert", False)
        humid_high = self.config.get("humidity_high_threshold", 70)
        humid_low = self.config.get("humidity_low_threshold", 30)

        if output_dir:
            base = output_dir
        elif getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))

        co2_path = os.path.join(base, "co2_level.txt")
        temp_path = os.path.join(base, "temperature.txt")
        humid_path = os.path.join(base, "humidity.txt")
        alert_path = os.path.join(base, "alert.txt")

        while not self.stop_event.is_set():
            try:
                result_holder = [None]

                def callback(device: BLEDevice, adv: AdvertisementData):
                    if SWITCHBOT_COMPANY_ID not in adv.manufacturer_data:
                        return
                    mfr = adv.manufacturer_data[SWITCHBOT_COMPANY_ID]
                    parsed = parse_manufacturer_data(mac, mfr)
                    if parsed:
                        result_holder[0] = parsed

                scanner = BleakScanner(detection_callback=callback)
                loop.run_until_complete(scanner.start())
                loop.run_until_complete(asyncio.sleep(interval))
                loop.run_until_complete(scanner.stop())

                result = result_holder[0]
                if result:
                    co2 = result["co2"]
                    temp = result["temperature"]
                    humid = result["humidity"]

                    # Update OBS files
                    write_to_file(co2_path, f"CO2: {co2} ppm")
                    write_to_file(temp_path, f"{temp}°C")
                    write_to_file(humid_path, f"{humid}%")

                    # Build alert messages
                    alert_co2_msg = self.config.get("alert_co2", "⚠ CO2が高いです！換気してください！")
                    alert_temp_high_msg = self.config.get("alert_temp_high", "🌡 暑すぎます！")
                    alert_temp_low_msg = self.config.get("alert_temp_low", "🌡 寒すぎます！")
                    alert_humid_high_msg = self.config.get("alert_humid_high", "💧 湿度が高すぎます！")
                    alert_humid_low_msg = self.config.get("alert_humid_low", "💧 乾燥しています！")

                    alerts = []
                    if enable_co2_alert and co2 > threshold:
                        alerts.append(alert_co2_msg)
                    if enable_temp_alert:
                        if temp > temp_high:
                            alerts.append(alert_temp_high_msg)
                        elif temp < temp_low:
                            alerts.append(alert_temp_low_msg)
                    if enable_humid_alert:
                        if humid > humid_high:
                            alerts.append(alert_humid_high_msg)
                        elif humid < humid_low:
                            alerts.append(alert_humid_low_msg)

                    alert_text = "\n".join(alerts)
                    write_to_file(alert_path, alert_text)

                    # Update GUI
                    now = datetime.now().strftime("%H:%M:%S")
                    self.root.after(0, lambda c=co2, t=temp, h=humid,
                                    n=now, a=alert_text:
                                    self._update_display(c, t, h, n, a))

            except Exception as e:
                self.root.after(0, lambda err=str(e):
                    self.status_label.configure(text=f"エラー: {err}"))

        loop.close()

    def _update_display(self, co2, temp, humid, time_str, alert_text):
        if co2 < 600:
            color = "#00d474"
        elif co2 < 800:
            color = "#7dd87d"
        elif co2 < 1000:
            color = "#ffa500"
        else:
            color = "#e94560"

        self.co2_label.configure(text=f"{co2} ppm", foreground=color)
        self.temp_label.configure(text=f"🌡 {temp}°C")
        self.humid_label.configure(text=f"💧 {humid}%")
        self.status_label.configure(text=f"最終更新: {time_str}")
        self.alert_label.configure(text=alert_text)


def main():
    root = tk.Tk()
    app = CO2MonitorApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app._stop_monitoring(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
