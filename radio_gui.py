import tkinter as tk
from tkinter import messagebox, simpledialog
import time
import json
import os
import subprocess
import re
from smbus2 import SMBus, i2c_msg

I2C_BUS = 10
ADDR_SEQ = 0x10
ADDR_RAND = 0x11
PRESETS_FILE = os.path.expanduser("~/radio_presets.json")

class ModernHiFiRadio:
    def __init__(self, root):
        self.root = root
        self.root.title("Hi-Fi FM Receiver")
        self.root.geometry("340x480")
        self.root.resizable(False, False)
        
        self.bg_dark = "#1E222A"      
        self.bg_panel = "#282C34"     
        self.accent_cyan = "#00FFCC"   
        self.text_light = "#BBC2CF"    
        self.text_muted = "#5C6370"    

        self.root.configure(bg=self.bg_dark)

        try:
            self.bus = SMBus(I2C_BUS)
        except Exception:
            print("[ ВНИМАНИЕ ] Шина I2C не найдена. Включен демонстрационный режим.")
            self.bus = None

        self.frequency = 87.5
        self.volume = 12
        self.band = 0x02
        self.station_name = [" "] * 8
        
        self.atten_mode = 0
        self.atten_names = ["MAX (Дом)", "MID (Улица)", "LOCAL (Вышка)"]
        
        self.presets = {
            "1": 87.5, "2": 89.7, "3": 92.9, "4": 100.5, "5": 104.0,
            "6": 104.4, "7": 105.9, "8": 106.3, "9": 107.0
        }
        
        self.last_rssi_time = 0
        self.display_rssi = 0
        self.preset_buttons = {}

        self.load_presets()
        self.setup_ui()
        self.apply_settings()
        self.poll_hardware()

    def setup_ui(self):
        self.display_frame = tk.Frame(self.root, bg=self.bg_panel, bd=0, highlightbackground="#3E4452", highlightthickness=1)
        self.display_frame.pack(padx=15, pady=15, fill=tk.X)

        self.freq_label = tk.Label(self.display_frame, text="87.5 MHz", fg="#FFFFFF", bg=self.bg_panel, font=("Helvetica", 32, "bold"))
        self.freq_label.pack(pady=(10, 0))

        self.rds_label = tk.Label(self.display_frame, text="RDS: Поиск...", fg=self.accent_cyan, bg=self.bg_panel, font=("Courier", 11, "bold"))
        self.rds_label.pack(pady=5)

        self.bar_frame = tk.Frame(self.display_frame, bg=self.bg_panel)
        self.bar_frame.pack(pady=(0, 10))
        self.bars = []
        for i in range(10):
            b = tk.Frame(self.bar_frame, bg="#3E4452", width=12, height=12)
            b.pack(side=tk.LEFT, padx=2)
            self.bars.append(b)

        self.status_label = tk.Label(self.display_frame, text="SIG: 0 dBuV  |  VOL: 12/15  |  ATT: MAX", fg=self.text_light, bg=self.bg_panel, font=("Arial", 9))
        self.status_label.pack(pady=(0, 8))

        self.ctrl_frame = tk.Frame(self.root, bg=self.bg_dark)
        self.ctrl_frame.pack(fill=tk.X, padx=15, pady=5)

        btn_style = {"bg": "#2C313C", "fg": "#FFFFFF", "activebackground": "#3E4452", "activeforeground": "#FFFFFF", "bd": 0, "font": ("Arial", 10, "bold"), "height": 2}
        
        tk.Button(self.ctrl_frame, text="◀ -0.1", width=6, command=lambda: self.step_freq(-0.1), **btn_style).grid(row=0, column=0, padx=3, pady=2)
        tk.Button(self.ctrl_frame, text="ВВОД (F)", width=10, command=self.manual_input, bg="#3E4452", fg=self.accent_cyan, activebackground="#4B5263", activeforeground=self.accent_cyan, bd=0, font=("Arial", 10, "bold")).grid(row=0, column=1, columnspan=2, padx=3, pady=2, sticky="nsew")
        tk.Button(self.ctrl_frame, text="+0.1 ▶", width=6, command=lambda: self.step_freq(0.1), **btn_style).grid(row=0, column=3, padx=3, pady=2)

        tk.Button(self.ctrl_frame, text="VOL -", width=6, command=lambda: self.step_vol(-1), **btn_style).grid(row=1, column=0, padx=3, pady=4)
        tk.Button(self.ctrl_frame, text="ЧУЙКА (A)", width=8, command=self.toggle_attenuator, **btn_style).grid(row=1, column=1, padx=3, pady=4)
        tk.Button(self.ctrl_frame, text="ПОИСК", width=8, command=self.trigger_scan, bg="#005544", fg="#FFFFFF", activebackground="#007755", bd=0, font=("Arial", 10, "bold")).grid(row=1, column=2, padx=3, pady=4)
        tk.Button(self.ctrl_frame, text="VOL +", width=6, command=lambda: self.step_vol(1), **btn_style).grid(row=1, column=3, padx=3, pady=4)

        self.fav_label = tk.Label(self.root, text="ИЗБРАННЫЕ СТАНЦИИ (ЛКМ — Вызов, ПКМ — Запись)", fg=self.text_muted, bg=self.bg_dark, font=("Arial", 8, "bold"))
        self.fav_label.pack(pady=(15, 2))

        self.grid_frame = tk.Frame(self.root, bg=self.bg_dark)
        self.grid_frame.pack(pady=5)

        for i in range(1, 10):
            slot = str(i)
            btn = tk.Button(self.grid_frame, text=f"{slot}\n{self.presets[slot]:.1f}", width=8, height=2, font=("Arial", 10, "bold"), bg="#282C34", fg=self.text_light, bd=0, activebackground="#3E4452", activeforeground="#FFFFFF")
            
            btn.bind("<Button-1>", lambda event, s=slot: self.preset_click(s))
            btn.bind("<Button-3>", lambda event, s=slot: self.preset_save(s))
            
            row = (i - 1) // 3
            col = (i - 1) % 3
            btn.grid(row=row, column=col, padx=5, pady=5)
            self.preset_buttons[slot] = btn

    def apply_settings(self):
        if 50.0 <= self.frequency < 76.0:
            self.band = 0x03  
            chan = int((self.frequency - 50.0) / 0.1)
        else:
            self.band = 0x02  
            self.frequency = max(76.0, min(108.0, self.frequency))
            chan = int((self.frequency - 76.0) / 0.1)

        reg02 = [0xC0, 0x09]  
        reg03_msb = (chan >> 2) & 0xFF
        reg03_lsb = ((chan & 0x03) << 6) | 0x10 | (self.band << 2)
        
        if self.atten_mode == 0:
            reg05_msb, reg05_lsb = 0x10, 0x80 | (self.volume & 0x0F)
        elif self.atten_mode == 1:
            reg05_msb, reg05_lsb = 0x20, 0x80 | (self.volume & 0x0F)
        else:
            reg05_msb, reg05_lsb = 0x30, 0x00 | (self.volume & 0x0F)

        data = reg02 + [reg03_msb, reg03_lsb] + [0x00, 0x00, reg05_msb, reg05_lsb]
        
        if self.bus:
            try:
                write = i2c_msg.write(ADDR_SEQ, data)
                self.bus.i2c_rdwr(write)
            except Exception:
                pass
                
        self.freq_label.configure(text=f"{self.frequency:.1f} MHz")
        self.update_status_line()

    def poll_hardware(self):
        """ Замедленный до 250 мс опрос шины полностью убирает цифровой треск звука """
        if self.bus:
            try:
                write = i2c_msg.write(ADDR_RAND, [])
                read = i2c_msg.read(ADDR_RAND, 12)
                self.bus.i2c_rdwr(write, read)
                res = list(read)
                
                if len(res) >= 12:
                    reg0a_msb, reg0b_msb = res[0], res[2]
                    rssi = (reg0b_msb >> 1) & 0x7F
                    
                    if time.time() - self.last_rssi_time > 5.0:
                        self.display_rssi = rssi
                        self.last_rssi_time = time.time()
                        self.update_ui_bars(self.display_rssi)
                        self.update_status_line()
                    
                    if reg0a_msb & 0x80:
                        reg0c_msb, reg0c_lsb, reg0f_msb, reg0f_lsb = res[4], res[5], res[10], res[11]
                        group_type = (reg0c_msb >> 3) & 0x1F
                        if group_type == 0 or group_type == 1:
                            idx = (reg0c_lsb & 0x03) * 2
                            c1 = chr(reg0f_msb) if 32 <= reg0f_msb < 127 else " "
                            c2 = chr(reg0f_lsb) if 32 <= reg0f_lsb < 127 else " "
                            self.station_name[idx] = c1
                            self.station_name[idx+1] = c2
                            
                            st_name = "".join(self.station_name).strip()
                            if st_name:
                                self.rds_label.configure(text=st_name)
            except Exception:
                pass
                
        # 250 мс — тихий и безопасный режим для CH341A
        self.root.after(250, self.poll_hardware)

    def update_ui_bars(self, rssi):
        active_count = min(10, rssi // 8)
        for i, bar in enumerate(self.bars):
            if i < active_count:
                bar.configure(bg=self.accent_cyan)
            else:
                bar.configure(bg="#3E4452")

    def update_status_line(self):
        self.status_label.configure(
            text=f"SIG: {self.display_rssi} dBuV  |  VOL: {self.volume}/15  |  ATT: {self.atten_names[self.atten_mode]}"
        )

    def step_freq(self, delta):
        self.frequency = round(max(50.0, min(108.0, self.frequency + delta)), 1)
        self.clear_rds()
        self.apply_settings()

    def step_vol(self, delta):
        self.volume = max(0, min(15, self.volume + delta))
        self.apply_settings()

    def toggle_attenuator(self):
        self.atten_mode = (self.atten_mode + 1) % 3
        self.apply_settings()
        self.last_rssi_time = 0

    def clear_rds(self):
        self.station_name = [" "] * 8
        self.rds_label.configure(text="RDS: Поиск...")

    def preset_click(self, slot):
        self.frequency = self.presets[slot]
        self.clear_rds()
        self.apply_settings()
        self.last_rssi_time = 0

    def preset_save(self, slot):
        self.presets[slot] = self.frequency
        self.save_presets()
        self.preset_buttons[slot].configure(text=f"{slot}\n{self.frequency:.1f}")
        messagebox.showinfo("Пресет сохранен", f"Частота {self.frequency:.1f} МГц успешна записана в ячейку {slot}!")

    def manual_input(self):
        res = simpledialog.askstring("Прямой ввод", "Введите частоту (50.0 - 108.0 МГц):")
        if res:
            try:
                val = float(res.replace(",", "."))
                if 50.0 <= val <= 108.0:
                    self.frequency = round(val, 1)
                    self.clear_rds()
                    self.apply_settings()
                    self.last_rssi_time = 0
            except ValueError:
                pass

    def trigger_scan(self):
        """ Программный автопоиск по RSSI, адаптированный под GUI """
        self.rds_label.configure(text="СКАН...")
        self.root.update()
        
        step = 0.1
        start_freq = self.frequency
        thresholds = {0: 24, 1: 18, 2: 6}
        target_threshold = thresholds[self.atten_mode]
        
        while True:
            self.frequency = round(self.frequency + step, 1)
            if self.frequency > 108.0: 
                self.frequency = 50.0
            if self.frequency == start_freq: 
                break
                
            self.apply_settings()
            self.root.update()
            time.sleep(0.06)
            
            if self.bus:
                try:
                    write = i2c_msg.write(ADDR_RAND, [])
                    read = i2c_msg.read(ADDR_RAND, 4)
                    self.bus.i2c_rdwr(write, read)
                    res = list(read)
                    if len(res) >= 3:
                        rssi = (res[2] >> 1) & 0x7F
                        if rssi >= target_threshold:
                            break
                except Exception:
                    pass
            else:
                time.sleep(0.02)
                break
                
        self.clear_rds()
        self.apply_settings()
        self.last_rssi_time = 0

    def load_presets(self):
        if os.path.exists(PRESETS_FILE):
            try:
                with open(PRESETS_FILE, "r") as f: 
                    self.presets.update(json.load(f))
            except Exception: 
                pass

    def save_presets(self):
        try:
            with open(PRESETS_FILE, "w") as f: 
                json.dump(self.presets, f)
        except Exception: 
            pass

if __name__ == "__main__":
    root = tk.Tk()
    app = ModernHiFiRadio(root)
    root.mainloop()
