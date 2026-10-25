import math
import socket
import json
import threading
import datetime
import tkinter as tk
from tkinter import ttk, messagebox
import tkintermapview

# --- 設定パラメータ ---
HOST = "0.0.0.0"
PORT = 50007

# 初期拠点データ（デフォルト3拠点）
DEFAULT_TARGET_LOCATIONS = [
    {
        "id": 1,
        "name": "拠点1: 羽後町役場周辺",
        "lat": 39.190616,
        "lon": 140.433785,
        "danger_km": 1.0,
        "warning_km": 3.0
    },
    {
        "id": 2,
        "name": "拠点2: 羽後中学校周辺",
        "lat": 39.210000,
        "lon": 140.420000,
        "danger_km": 1.0,
        "warning_km": 3.0
    },
    {
        "id": 3,
        "name": "拠点3: 道の駅うご周辺",
        "lat": 39.198000,
        "lon": 140.448000,
        "danger_km": 1.0,
        "warning_km": 3.0
    }
]

def haversine_distance(lat1, lon1, lat2, lon2):
    """2点間の地球表面上の大円距離(km)を計算"""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def parse_nmea(nmea_str):
    """NMEAフォーマット($GPGGAまたは$GPRMC)から緯度・経度を抽出"""
    try:
        parts = nmea_str.strip().split(',')
        if not parts or len(parts) < 6:
            return None, None
        
        msg_type = parts[0]
        if "GGA" in msg_type:
            raw_lat, lat_dir = parts[2], parts[3]
            raw_lon, lon_dir = parts[4], parts[5]
        elif "RMC" in msg_type:
            raw_lat, lat_dir = parts[3], parts[4]
            raw_lon, lon_dir = parts[5], parts[6]
        else:
            return None, None
            
        if not raw_lat or not raw_lon:
            return None, None
            
        lat_deg = float(raw_lat[:2]) + float(raw_lat[2:]) / 60.0
        if lat_dir == 'S': lat_deg = -lat_deg
            
        lon_deg = float(raw_lon[:3]) + float(raw_lon[3:]) / 60.0
        if lon_dir == 'W': lon_deg = -lon_deg
            
        return lat_deg, lon_deg
    except Exception as e:
        print(f"NMEA Parse Error: {e}")
        return None, None

class MultiPointGatewayApp:
    def __init__(self, root):
        self.root = root
        self.root.title("【基地局側】野生動物制御システム - 動的拠点＆複数首輪統合管理")
        self.root.geometry("1300x750")
        
        # 拠点管理用リスト & 首輪管理用辞書
        self.locations = list(DEFAULT_TARGET_LOCATIONS)
        self.active_collars = {}  # collar_id: {data, marker}
        self.location_polygons = []
        self.location_markers = []
        
        # --- 全体レイアウト ---
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # タブ1: 統合マップ & 監視パネル
        self.tab_monitor = ttk.Frame(notebook)
        notebook.add(self.tab_monitor, text="リアルタイム監視マップ")
        
        # タブ2: 拠点設定・管理
        self.tab_settings = ttk.Frame(notebook)
        notebook.add(self.tab_settings, text="拠点登録・動的設定")
        
        self.setup_monitor_tab()
        self.setup_settings_tab()
        
        # サーバー起動
        self.start_server_thread()

    def setup_monitor_tab(self):
        # 監視画面レイアウト（左：地図、右：首輪状態・ログ）
        top_frame = ttk.Frame(self.tab_monitor, padding=5)
        top_frame.pack(fill=tk.X)
        ttk.Label(top_frame, text="【監視ステータス】 ポート 50007 待機中", font=("Helvetica", 11, "bold"), foreground="blue").pack(anchor=tk.W)

        main_frame = ttk.Frame(self.tab_monitor, padding=5)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 地図表示
        self.map_widget = tkintermapview.TkinterMapView(main_frame, width=750, height=600, corner_radius=0)
        
        # --- Googleマップのタイルサーバーに変更 ---
        self.map_widget.set_tile_server("https://mt0.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}&s=Ga", max_zoom=19)
        
        self.map_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.map_widget.set_position(39.1995, 140.4338)
        self.map_widget.set_zoom(13)
        
        # 右側情報パネル
        right_frame = ttk.Frame(main_frame, padding=5)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH)
        
        # 首輪アクティブ一覧テーブル
        ttk.Label(right_frame, text="【アクティブ首輪端末一覧】", font=("Helvetica", 10, "bold")).pack(anchor=tk.W)
        columns = ("id", "zone", "closest", "dist", "last_time")
        self.tree_collars = ttk.Treeview(right_frame, columns=columns, show="headings", height=8)
        self.tree_collars.heading("id", text="首輪ID")
        self.tree_collars.heading("zone", text="ゾーン")
        self.tree_collars.heading("closest", text="最寄拠点")
        self.tree_collars.heading("dist", text="距離(km)")
        self.tree_collars.heading("last_time", text="最終受信")
        self.tree_collars.column("id", width=90)
        self.tree_collars.column("zone", width=70)
        self.tree_collars.column("closest", width=110)
        self.tree_collars.column("dist", width=65)
        self.tree_collars.column("last_time", width=80)
        self.tree_collars.pack(fill=tk.X, pady=5)
        
        # 受信データログ
        ttk.Label(right_frame, text="【受信＆処理ログ】", font=("Helvetica", 10, "bold")).pack(anchor=tk.W, pady=(5,0))
        self.txt_log = tk.Text(right_frame, width=45, height=18)
        self.txt_log.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.draw_all_geofences()

    def setup_settings_tab(self):
        # 拠点追加・編集パネル
        frame_left = ttk.LabelFrame(self.tab_settings, text="登録拠点一覧", padding=10)
        frame_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        columns = ("id", "name", "lat", "lon", "danger", "warning")
        self.tree_locs = ttk.Treeview(frame_left, columns=columns, show="headings", height=15)
        self.tree_locs.heading("id", text="ID")
        self.tree_locs.heading("name", text="拠点名")
        self.tree_locs.heading("lat", text="緯度")
        self.tree_locs.heading("lon", text="経度")
        self.tree_locs.heading("danger", text="危険(km)")
        self.tree_locs.heading("warning", text="注意(km)")
        self.tree_locs.column("id", width=40)
        self.tree_locs.column("name", width=180)
        self.tree_locs.column("lat", width=90)
        self.tree_locs.column("lon", width=90)
        self.tree_locs.column("danger", width=70)
        self.tree_locs.column("warning", width=70)
        self.tree_locs.pack(fill=tk.BOTH, expand=True, pady=5)
        self.tree_locs.bind("<<TreeviewSelect>>", self.on_loc_select)
        
        # 拠点追加・更新フォーム
        frame_right = ttk.LabelFrame(self.tab_settings, text="拠点の新規登録 / 編集", padding=10)
        frame_right.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)
        
        ttk.Label(frame_right, text="拠点名:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.ent_loc_name = ttk.Entry(frame_right, width=25)
        self.ent_loc_name.grid(row=0, column=1, pady=5)
        
        ttk.Label(frame_right, text="緯度 (Lat):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.ent_loc_lat = ttk.Entry(frame_right, width=25)
        self.ent_loc_lat.grid(row=1, column=1, pady=5)
        
        ttk.Label(frame_right, text="経度 (Lon):").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.ent_loc_lon = ttk.Entry(frame_right, width=25)
        self.ent_loc_lon.grid(row=2, column=1, pady=5)
        
        ttk.Label(frame_right, text="危険半径 (km):").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.ent_loc_danger = ttk.Entry(frame_right, width=25)
        self.ent_loc_danger.insert(0, "1.0")
        self.ent_loc_danger.grid(row=3, column=1, pady=5)
        
        ttk.Label(frame_right, text="注意半径 (km):").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.ent_loc_warning = ttk.Entry(frame_right, width=25)
        self.ent_loc_warning.insert(0, "3.0")
        self.ent_loc_warning.grid(row=4, column=1, pady=5)
        
        btn_frame = ttk.Frame(frame_right, padding=10)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=10)
        
        ttk.Button(btn_frame, text="新規追加 / 更新", command=self.save_location).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="選択拠点を削除", command=self.delete_location).pack(side=tk.LEFT, padx=5)
        
        self.refresh_locations_tree()

    def refresh_locations_tree(self):
        for item in self.tree_locs.get_children():
            self.tree_locs.delete(item)
        for loc in self.locations:
            self.tree_locs.insert("", tk.END, values=(loc["id"], loc["name"], loc["lat"], loc["lon"], loc["danger_km"], loc["warning_km"]))

    def on_loc_select(self, event):
        selected = self.tree_locs.selection()
        if not selected:
            return
        item = self.tree_locs.item(selected[0])
        vals = item["values"]
        self.ent_loc_name.delete(0, tk.END); self.ent_loc_name.insert(0, vals[1])
        self.ent_loc_lat.delete(0, tk.END); self.ent_loc_lat.insert(0, vals[2])
        self.ent_loc_lon.delete(0, tk.END); self.ent_loc_lon.insert(0, vals[3])
        self.ent_loc_danger.delete(0, tk.END); self.ent_loc_danger.insert(0, vals[4])
        self.ent_loc_warning.delete(0, tk.END); self.ent_loc_warning.insert(0, vals[5])

    def save_location(self):
        try:
            name = self.ent_loc_name.get().strip()
            lat = float(self.ent_loc_lat.get().strip())
            lon = float(self.ent_loc_lon.get().strip())
            danger = float(self.ent_loc_danger.get().strip())
            warning = float(self.ent_loc_warning.get().strip())
            
            if not name:
                messagebox.showerror("入力エラー", "拠点名を入力してください")
                return

            existing = next((loc for loc in self.locations if loc["name"] == name), None)
            if existing:
                existing["lat"] = lat
                existing["lon"] = lon
                existing["danger_km"] = danger
                existing["warning_km"] = warning
            else:
                new_id = max([l["id"] for l in self.locations], default=0) + 1
                self.locations.append({
                    "id": new_id, "name": name, "lat": lat, "lon": lon,
                    "danger_km": danger, "warning_km": warning
                })

            self.refresh_locations_tree()
            self.draw_all_geofences()
            messagebox.showinfo("成功", f"拠点「{name}」を保存・反映しました。")
        except ValueError:
            messagebox.showerror("入力エラー", "緯度・経度・半径には正の数値を入力してください。")

    def delete_location(self):
        selected = self.tree_locs.selection()
        if not selected:
            return
        vals = self.tree_locs.item(selected[0])["values"]
        loc_id = vals[0]
        self.locations = [l for l in self.locations if l["id"] != loc_id]
        self.refresh_locations_tree()
        self.draw_all_geofences()

    def draw_all_geofences(self):
        for poly in self.location_polygons:
            poly.delete()
        for m in self.location_markers:
            m.delete()
        self.location_polygons.clear()
        self.location_markers.clear()

        def get_circle_points(lat, lon, radius_km, num_points=32):
            points = []
            for i in range(num_points):
                angle = math.radians(i * (360 / num_points))
                dx = radius_km * math.sin(angle)
                dy = radius_km * math.cos(angle)
                d_lat = dy / 111.0
                d_lon = dx / (111.0 * math.cos(math.radians(lat)))
                points.append((lat + d_lat, lon + d_lon))
            return points

        for loc in self.locations:
            lat, lon, name = loc["lat"], loc["lon"], loc["name"]
            m = self.map_widget.set_marker(
                lat, lon, text=name,
                marker_color_circle="#0055FF", marker_color_outside="#002288", text_color="#002288"
            )
            self.location_markers.append(m)
            
            warning_pts = get_circle_points(lat, lon, loc["warning_km"])
            p_warn = self.map_widget.set_polygon(warning_pts, outline_color="#FF8C00", fill_color="#FF8C00", border_width=2)
            self.location_polygons.append(p_warn)

            danger_pts = get_circle_points(lat, lon, loc["danger_km"])
            p_danger = self.map_widget.set_polygon(danger_pts, outline_color="#FF0000", fill_color="#FF0000", border_width=2)
            self.location_polygons.append(p_danger)

    def log(self, message):
        self.txt_log.insert(tk.END, message + "\n")
        self.txt_log.see(tk.END)

    def start_server_thread(self):
        t = threading.Thread(target=self.run_server, daemon=True)
        t.start()

    def run_server(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, PORT))
        sock.listen(5)
        
        while True:
            conn, addr = sock.accept()
            data = conn.recv(2048).decode('utf-8')
            if data:
                self.root.after(0, self.process_client_payload, data, conn)

    def process_client_payload(self, raw_data, conn):
        try:
            payload = json.loads(raw_data)
            collar_id = payload.get("collar_id", "UNKNOWN-001")
            attributes = payload.get("attributes", {})
            nmea_str = payload.get("nmea", "")
        except json.JSONDecodeError:
            collar_id = "BEAR-DEFAULT"
            attributes = {"sex": "不明", "age": "--", "capture_area": "羽後町", "capture_date": "--"}
            nmea_str = raw_data

        lat, lon = parse_nmea(nmea_str)
        if lat is None or lon is None:
            res = {"status": "ERROR", "message": "NMEA Parse Failed"}
            conn.sendall(json.dumps(res).encode('utf-8'))
            conn.close()
            return

        distances = []
        is_danger = False
        is_warning = False

        for loc in self.locations:
            d = haversine_distance(loc["lat"], loc["lon"], lat, lon)
            distances.append({"name": loc["name"], "dist_km": d, "danger_km": loc["danger_km"], "warning_km": loc["warning_km"]})
            if d <= loc["danger_km"]:
                is_danger = True
            elif d <= loc["warning_km"]:
                is_warning = True

        if not distances:
            closest_loc_name = "未登録"
            min_dist_km = 999.0
        else:
            closest_loc = min(distances, key=lambda x: x["dist_km"])
            closest_loc_name = closest_loc["name"]
            min_dist_km = closest_loc["dist_km"]

        if is_danger:
            zone = "DANGER"; interval_sec = 60; stimulation = "強（電気刺激）"
            circle_color = "#FF0000"; out_color = "#880000"
        elif is_warning:
            zone = "WARNING"; interval_sec = 300; stimulation = "弱（振動アラーム）"
            circle_color = "#FF8C00"; out_color = "#A05200"
        else:
            zone = "SAFE"; interval_sec = 1800; stimulation = "なし"
            circle_color = "#00AA00"; out_color = "#005500"

        if collar_id in self.active_collars and self.active_collars[collar_id].get("marker"):
            self.active_collars[collar_id]["marker"].delete()

        marker_label = f"熊 [{collar_id}] ({attributes.get('sex', '')}/{attributes.get('age', '')})\nゾーン: {zone} ({min_dist_km:.2f}km)"
        new_marker = self.map_widget.set_marker(
            lat, lon, text=marker_label,
            marker_color_circle=circle_color, marker_color_outside=out_color, text_color=circle_color
        )
        self.map_widget.set_position(lat, lon)

        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        self.active_collars[collar_id] = {
            "zone": zone, "closest": closest_loc_name, "dist": round(min_dist_km, 2),
            "last_time": now_str, "marker": new_marker, "attributes": attributes
        }
        self.update_collars_tree()

        response = {
            "status": "OK",
            "collar_id": collar_id,
            "lat": lat, "lon": lon,
            "closest_location": closest_loc_name,
            "distance_km": round(min_dist_km, 3),
            "zone": zone,
            "next_interval_sec": interval_sec,
            "stimulation": stimulation
        }
        conn.sendall(json.dumps(response, ensure_ascii=False).encode('utf-8'))
        conn.close()

        self.log(f"[{now_str}] 首輪ID: {collar_id} 受信")
        self.log(f"  属性: 性別={attributes.get('sex')}, 年齢={attributes.get('age')}, 捕獲地={attributes.get('capture_area')}")
        self.log(f"  位置: {lat:.5f}, {lon:.5f} => ゾーン: {zone} (最寄: {closest_loc_name} {min_dist_km:.2f}km)\n")

    def update_collars_tree(self):
        for item in self.tree_collars.get_children():
            self.tree_collars.delete(item)
        for cid, info in self.active_collars.items():
            self.tree_collars.insert("", tk.END, values=(cid, info["zone"], info["closest"], info["dist"], info["last_time"]))

if __name__ == "__main__":
    root = tk.Tk()
    app = MultiPointGatewayApp(root)
    root.mainloop()