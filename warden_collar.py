import os
import socket
import json
import tkinter as tk
from tkinter import ttk, messagebox

# --- 接続先設定（ホストPC上で直接動かすため localhost に変更） ---
SERVER_HOST = os.environ.get("SERVER_HOST", "localhost")
SERVER_PORT = 50007

# テスト用サンプルNMEAデータ (羽後町周辺)
NMEA_PRESETS = {
    "拠点1の危険エリア (役場近く)": "$GPGGA,123519,3911.707,N,14026.027,E,1,08,0.9,54.7,M,46.9,M,,*42",
    "拠点1と2の重なり合う注意エリア": "$GPGGA,123519,3912.100,N,14025.500,E,1,08,0.9,54.7,M,46.9,M,,*47",
    "拠点3の危険エリア (道の駅近く)": "$GPGGA,123519,3911.880,N,14026.880,E,1,08,0.9,54.7,M,46.9,M,,*42",
    "全拠点から外れた安全エリア": "$GPGGA,123519,3915.000,N,14030.000,E,1,08,0.9,54.7,M,46.9,M,,*44"
}

def latlon_to_nmea_gga(lat, lon):
    lat_dir = 'N' if lat >= 0 else 'S'
    abs_lat = abs(lat)
    lat_deg = int(abs_lat)
    lat_min = (abs_lat - lat_deg) * 60.0
    nmea_lat = f"{lat_deg:02d}{lat_min:06.3f}"
    
    lon_dir = 'E' if lon >= 0 else 'W'
    abs_lon = abs(lon)
    lon_deg = int(abs_lon)
    lon_min = (abs_lon - lon_deg) * 60.0
    nmea_lon = f"{lon_deg:03d}{lon_min:06.3f}"
    
    return f"$GPGGA,123519,{nmea_lat},{lat_dir},{nmea_lon},{lon_dir},1,08,0.9,54.7,M,46.9,M,,*42"

class CollarApp:
    def __init__(self, root):
        self.root = root
        self.root.title("【首輪端末側】GPS・個体属性・制御インターフェース")
        self.root.geometry("620x720")
        
        # --- 1. 個体・首輪端末属性情報入力セクション ---
        frame_attr = ttk.LabelFrame(self.root, text="首輪端末 ID & 個体属性設定", padding=10)
        frame_attr.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(frame_attr, text="首輪 ID:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.ent_collar_id = ttk.Entry(frame_attr, width=15)
        self.ent_collar_id.insert(0, "BEAR-001")
        self.ent_collar_id.grid(row=0, column=1, sticky=tk.W, pady=3)
        
        ttk.Label(frame_attr, text="性別:").grid(row=0, column=2, sticky=tk.W, padx=(10,0), pady=3)
        self.combo_sex = ttk.Combobox(frame_attr, values=["オス", "メス", "不明"], state="readonly", width=8)
        self.combo_sex.current(0)
        self.combo_sex.grid(row=0, column=3, sticky=tk.W, pady=3)
        
        ttk.Label(frame_attr, text="推定年齢:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.ent_age = ttk.Entry(frame_attr, width=15)
        self.ent_age.insert(0, "4歳")
        self.ent_age.grid(row=1, column=1, sticky=tk.W, pady=3)
        
        ttk.Label(frame_attr, text="捕獲エリア:").grid(row=1, column=2, sticky=tk.W, padx=(10,0), pady=3)
        self.ent_capture_area = ttk.Entry(frame_attr, width=15)
        self.ent_capture_area.insert(0, "羽後町三輪")
        self.ent_capture_area.grid(row=1, column=3, sticky=tk.W, pady=3)

        ttk.Label(frame_attr, text="捕獲日:").grid(row=2, column=0, sticky=tk.W, pady=3)
        self.ent_capture_date = ttk.Entry(frame_attr, width=15)
        self.ent_capture_date.insert(0, "2026-10-01")
        self.ent_capture_date.grid(row=2, column=1, sticky=tk.W, pady=3)

        # --- 2. NMEAデータ入力セクション ---
        frame_input = ttk.LabelFrame(self.root, text="GPS位置情報 送信設定", padding=10)
        frame_input.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(frame_input, text="1. プリセット選択:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.combo_preset = ttk.Combobox(frame_input, values=list(NMEA_PRESETS.keys()), state="readonly", width=38)
        self.combo_preset.grid(row=0, column=1, columnspan=2, padx=5, pady=3, sticky=tk.W)
        self.combo_preset.bind("<<ComboboxSelected>>", self.on_preset_select)
        self.combo_preset.current(0)
        
        ttk.Separator(frame_input, orient="horizontal").grid(row=1, column=0, columnspan=3, sticky="ew", pady=5)
        
        ttk.Label(frame_input, text="2. 任意の緯度・経度入力:").grid(row=2, column=0, sticky=tk.W, pady=3)
        frame_latlon = ttk.Frame(frame_input)
        frame_latlon.grid(row=2, column=1, columnspan=2, sticky=tk.W)
        
        ttk.Label(frame_latlon, text="緯度:").pack(side=tk.LEFT)
        self.ent_lat = ttk.Entry(frame_latlon, width=12)
        self.ent_lat.pack(side=tk.LEFT, padx=(2, 8))
        self.ent_lat.insert(0, "39.195116")
        
        ttk.Label(frame_latlon, text="経度:").pack(side=tk.LEFT)
        self.ent_lon = ttk.Entry(frame_latlon, width=12)
        self.ent_lon.pack(side=tk.LEFT, padx=(2, 5))
        self.ent_lon.insert(0, "140.433785")
        
        btn_gen_nmea = ttk.Button(frame_input, text="NMEA変換", command=self.generate_nmea_from_latlon)
        btn_gen_nmea.grid(row=3, column=1, sticky=tk.W, pady=3)
        
        ttk.Separator(frame_input, orient="horizontal").grid(row=4, column=0, columnspan=3, sticky="ew", pady=5)
        
        ttk.Label(frame_input, text="3. 送信NMEA:").grid(row=5, column=0, sticky=tk.W, pady=3)
        self.ent_nmea = ttk.Entry(frame_input, width=50)
        self.ent_nmea.grid(row=5, column=1, columnspan=2, padx=5, pady=3, sticky=tk.W)
        self.ent_nmea.insert(0, list(NMEA_PRESETS.values())[0])
        
        btn_send = ttk.Button(frame_input, text="基地局へ属性＆GPS送信 (LTE-M)", command=self.send_data)
        btn_send.grid(row=6, column=0, columnspan=3, pady=8)
        
        # --- 3. 基地局からの指示受信表示セクション ---
        frame_recv = ttk.LabelFrame(self.root, text="基地局からの制御指示 (受信結果)", padding=10)
        frame_recv.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.lbl_zone = ttk.Label(frame_recv, text="現在エリア判定: --", font=("Helvetica", 11, "bold"))
        self.lbl_zone.pack(anchor=tk.W, pady=2)
        
        self.lbl_interval = ttk.Label(frame_recv, text="次回GPS測定/送信頻度: --", font=("Helvetica", 10))
        self.lbl_interval.pack(anchor=tk.W, pady=2)
        
        self.lbl_stimulation = ttk.Label(frame_recv, text="刺激装置ステータス: --", font=("Helvetica", 10, "bold"))
        self.lbl_stimulation.pack(anchor=tk.W, pady=2)
        
        self.lbl_dist = ttk.Label(frame_recv, text="最寄拠点からの直線距離: --", font=("Helvetica", 10))
        self.lbl_dist.pack(anchor=tk.W, pady=2)
        
        self.txt_resp_log = tk.Text(frame_recv, height=6, width=50)
        self.txt_resp_log.pack(fill=tk.BOTH, expand=True, pady=3)

    def on_preset_select(self, event):
        selected_key = self.combo_preset.get()
        if selected_key in NMEA_PRESETS:
            self.ent_nmea.delete(0, tk.END)
            self.ent_nmea.insert(0, NMEA_PRESETS[selected_key])

    def generate_nmea_from_latlon(self):
        try:
            lat = float(self.ent_lat.get().strip())
            lon = float(self.ent_lon.get().strip())
            nmea_str = latlon_to_nmea_gga(lat, lon)
            self.ent_nmea.delete(0, tk.END)
            self.ent_nmea.insert(0, nmea_str)
        except ValueError:
            messagebox.showerror("入力エラー", "緯度・経度には有効な数値を入力してください。")

    def send_data(self):
        collar_id = self.ent_collar_id.get().strip()
        nmea_str = self.ent_nmea.get().strip()
        
        if not collar_id:
            messagebox.showwarning("入力エラー", "首輪IDを入力してください。")
            return
        if not nmea_str:
            messagebox.showwarning("入力エラー", "NMEAデータを入力してください。")
            return
            
        payload = {
            "collar_id": collar_id,
            "attributes": {
                "sex": self.combo_sex.get(),
                "age": self.ent_age.get().strip(),
                "capture_area": self.ent_capture_area.get().strip(),
                "capture_date": self.ent_capture_date.get().strip()
            },
            "nmea": nmea_str
        }
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((SERVER_HOST, SERVER_PORT))
            sock.sendall(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
            
            response_data = sock.recv(2048).decode('utf-8')
            sock.close()
            
            res = json.loads(response_data)
            self.update_ui_with_response(res)
        except Exception as e:
            messagebox.showerror("通信エラー", f"基地局への接続に失敗しました:\n{e}")

    def update_ui_with_response(self, res):
        if res.get("status") == "OK":
            zone = res["zone"]
            dist = res["distance_km"]
            closest = res.get("closest_location", "--")
            interval = res["next_interval_sec"]
            stimulation = res["stimulation"]
            
            zone_color = "red" if zone == "DANGER" else ("orange" if zone == "WARNING" else "green")
            
            self.lbl_zone.config(text=f"現在エリア判定: {zone}", foreground=zone_color)
            self.lbl_interval.config(text=f"次回GPS測定/送信頻度: {interval}秒 周期")
            self.lbl_stimulation.config(text=f"刺激装置ステータス: {stimulation}", foreground=zone_color)
            self.lbl_dist.config(text=f"最寄拠点からの直線距離: {dist} km ({closest})")
            
            self.txt_resp_log.delete("1.0", tk.END)
            self.txt_resp_log.insert(tk.END, json.dumps(res, indent=2, ensure_ascii=False))
        else:
            messagebox.showerror("エラー", f"基地局側エラー: {res.get('message')}")

if __name__ == "__main__":
    root = tk.Tk()
    app = CollarApp(root)
    root.mainloop()