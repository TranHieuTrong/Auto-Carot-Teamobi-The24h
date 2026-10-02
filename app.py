import os
import sys
import re
import json
import time
import threading
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import customtkinter as ctk

from the24h_client import The24hWebClient, The24hPartnerApiClient

# Thiết lập theme cho CustomTkinter
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CONFIG_FILE = "config.json"
CATALOG_FILE = "games_catalog.json"


class The24hAutoTopupApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("THE24H AUTO TOPUP - TỰ ĐỘNG NẠP CAROT / TEAMOBI HÀNG LOẠT")
        self.geometry("1180x820")
        self.minsize(1050, 720)

        # Biến trạng thái & Client
        self.web_client = The24hWebClient()
        self.partner_client = The24hPartnerApiClient()
        self.catalog = self.load_catalog()
        self.config = self.load_config()

        self.is_running = False
        self.stop_requested = False
        self.current_worker = None

        # Danh sách hàng đợi nạp
        # Mỗi phần tử: {'id': 1, 'account': '...', 'game': 'nr', 'game_name': '...', 'server': '1', 'server_name': '...', 'item': '384', 'price': 10000, 'label': '10,000 đ', 'status': 'Chờ nạp', 'order_code': '', 'message': ''}
        self.task_list = []

        self.setup_ui()
        self.apply_config()

    def load_catalog(self):
        """Tải danh mục game, máy chủ và bảng giá từ catalog đã crawl"""
        if os.path.exists(CATALOG_FILE):
            try:
                with open(CATALOG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print("Lỗi đọc catalog:", e)
        # Fallback dữ liệu mặc định Ngọc Rồng nếu chưa có file
        return {
            "nr": {
                "name": "Ngọc Rồng",
                "items": [
                    {"id": "384", "discount": "19", "price": "10000", "label": "10,000 đ"},
                    {"id": "385", "discount": "19", "price": "20000", "label": "20,000 đ"},
                    {"id": "153", "discount": "19", "price": "50000", "label": "50,000 đ"},
                    {"id": "154", "discount": "19", "price": "100000", "label": "100,000 đ"},
                    {"id": "155", "discount": "19", "price": "200000", "label": "200,000 đ"},
                    {"id": "156", "discount": "19", "price": "500000", "label": "500,000 đ"},
                    {"id": "157", "discount": "19", "price": "1000000", "label": "1,000,000 đ"}
                ],
                "servers": [
                    {"id": "1", "name": "1 Sao"}, {"id": "2", "name": "2 Sao"}, {"id": "3", "name": "3 Sao"},
                    {"id": "6", "name": "4 Sao"}, {"id": "7", "name": "5 Sao"}, {"id": "9", "name": "6 Sao"},
                    {"id": "10", "name": "7 Sao"}, {"id": "11", "name": "8 Sao"}, {"id": "12", "name": "9 sao"},
                    {"id": "13", "name": "10 Sao"}, {"id": "14", "name": "11 sao ( vip 1 )"},
                    {"id": "15", "name": "12 sao"}, {"id": "18", "name": "13 sao"}, {"id": "20", "name": "14 sao"},
                    {"id": "22", "name": "15 sao"}, {"id": "19", "name": "VIP 2"},
                    {"id": "16", "name": "super 1"}, {"id": "17", "name": "super 2"}, {"id": "21", "name": "super 3"}
                ]
            }
        }

    def load_config(self):
        default_config = {
            "username": "xlzeruslx",
            "password": "trong1507",
            "mkc2": "",
            "save_mkc2": False,
            "game_code": "nr",
            "delay": 2.0,
            "auto_pay": True,
            "partner_id": "72232119869",
            "partner_key": ""
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_config.update(data)
            except Exception:
                pass
        return default_config

    def save_config(self):
        cfg = {
            "username": self.entry_username.get().strip(),
            "password": self.entry_password.get().strip(),
            "mkc2": self.entry_mkc2.get().strip() if self.check_save_mkc2.get() else "",
            "save_mkc2": self.check_save_mkc2.get(),
            "game_code": self.combo_game.get(),
            "delay": float(self.entry_delay.get() or "2.0"),
            "auto_pay": self.check_auto_pay.get(),
            "partner_id": self.entry_partner_id.get().strip(),
            "partner_key": self.entry_partner_key.get().strip()
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"Lỗi lưu cấu hình: {e}")

    def setup_ui(self):
        # Grid layout: Header (Row 0), Body (Row 1), Footer/Bottom Bar (Row 2)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # =========================================================================
        # 1. TOP HEADER BAR
        # =========================================================================
        header_frame = ctk.CTkFrame(self, height=65, corner_radius=0, fg_color="#1a1c23")
        header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header_frame.grid_columnconfigure(1, weight=1)

        # Title & Subtitle
        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.grid(row=0, column=0, padx=20, pady=10, sticky="w")

        lbl_title = ctk.CTkLabel(
            title_box, 
            text="⚡ THE24H AUTO TOPUP", 
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#00d2ff"
        )
        lbl_title.pack(anchor="w")

        lbl_sub = ctk.CTkLabel(
            title_box, 
            text="Nạp Carot / Teamobi Tự Động Hàng Loạt Qua Web Session & API the24h.vn", 
            font=ctk.CTkFont(size=12),
            text_color="#9aa0a6"
        )
        lbl_sub.pack(anchor="w")

        # User Info & Balance Card (Right side)
        user_info_frame = ctk.CTkFrame(header_frame, fg_color="#262934", corner_radius=8)
        user_info_frame.grid(row=0, column=2, padx=20, pady=10, sticky="e")

        self.lbl_status_badge = ctk.CTkLabel(
            user_info_frame, 
            text="🔴 Chưa đăng nhập", 
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#ff5252"
        )
        self.lbl_status_badge.pack(side="left", padx=(12, 10))

        self.lbl_user_name = ctk.CTkLabel(
            user_info_frame, 
            text="Tài khoản: --", 
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#ffffff"
        )
        self.lbl_user_name.pack(side="left", padx=10)

        self.lbl_balance = ctk.CTkLabel(
            user_info_frame, 
            text="Số dư ví: 0đ", 
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#00e676"
        )
        self.lbl_balance.pack(side="left", padx=10)

        btn_reload_balance = ctk.CTkButton(
            user_info_frame, 
            text="🔄 Làm mới", 
            width=80, 
            height=28,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self.refresh_user_info
        )
        btn_reload_balance.pack(side="left", padx=(5, 10))

        # =========================================================================
        # 2. MAIN BODY (LEFT CONFIG PANEL + RIGHT TABS PANEL)
        # =========================================================================
        body_frame = ctk.CTkFrame(self, fg_color="transparent")
        body_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=12)
        body_frame.grid_columnconfigure(1, weight=1)
        body_frame.grid_rowconfigure(0, weight=1)

        # -----------------------------
        # 2.1 LEFT PANEL: CẤU HÌNH NẠP
        # -----------------------------
        left_panel = ctk.CTkScrollableFrame(body_frame, width=380, corner_radius=10, fg_color="#1e222d")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=0)

        # Section A: Tài khoản Web the24h.vn
        sec_acc_lbl = ctk.CTkLabel(left_panel, text="🔑 1. TÀI KHOẢN THE24H.VN", font=ctk.CTkFont(size=14, weight="bold"), text_color="#00d2ff")
        sec_acc_lbl.pack(anchor="w", padx=10, pady=(10, 8))

        acc_box = ctk.CTkFrame(left_panel, fg_color="#262c3b", corner_radius=8)
        acc_box.pack(fill="x", padx=5, pady=(0, 15))

        lbl_u = ctk.CTkLabel(acc_box, text="Tên đăng nhập (Email / SĐT):", font=ctk.CTkFont(size=12))
        lbl_u.pack(anchor="w", padx=12, pady=(10, 2))
        self.entry_username = ctk.CTkEntry(acc_box, placeholder_text="Tài khoản the24h.vn")
        self.entry_username.pack(fill="x", padx=12, pady=(0, 8))

        lbl_p = ctk.CTkLabel(acc_box, text="Mật khẩu đăng nhập:", font=ctk.CTkFont(size=12))
        lbl_p.pack(anchor="w", padx=12, pady=(0, 2))
        self.entry_password = ctk.CTkEntry(acc_box, placeholder_text="Mật khẩu the24h.vn", show="*")
        self.entry_password.pack(fill="x", padx=12, pady=(0, 8))

        lbl_m = ctk.CTkLabel(acc_box, text="Mật khẩu cấp 2 (MKC2 - Để nạp Quỹ VND):", font=ctk.CTkFont(size=12, weight="bold"), text_color="#ffb74d")
        lbl_m.pack(anchor="w", padx=12, pady=(0, 2))
        self.entry_mkc2 = ctk.CTkEntry(acc_box, placeholder_text="Nhập MKC2 để tự động thanh toán", show="*")
        self.entry_mkc2.pack(fill="x", padx=12, pady=(0, 5))

        mkc2_opts = ctk.CTkFrame(acc_box, fg_color="transparent")
        mkc2_opts.pack(fill="x", padx=12, pady=(0, 8))
        self.check_show_mkc2 = ctk.CTkCheckBox(mkc2_opts, text="Hiện MKC2", font=ctk.CTkFont(size=11), command=self.toggle_show_mkc2)
        self.check_show_mkc2.pack(side="left")
        self.check_save_mkc2 = ctk.CTkCheckBox(mkc2_opts, text="Ghi nhớ MKC2", font=ctk.CTkFont(size=11))
        self.check_save_mkc2.pack(side="right")

        self.btn_login = ctk.CTkButton(
            acc_box, 
            text="ĐĂNG NHẬP THE24H", 
            fg_color="#0284c7", 
            hover_color="#0369a1",
            font=ctk.CTkFont(weight="bold"),
            command=self.handle_login_threaded
        )
        self.btn_login.pack(fill="x", padx=12, pady=(4, 12))

        # Section B: Cấu hình Gói Nạp Game
        sec_game_lbl = ctk.CTkLabel(left_panel, text="🎮 2. CẤU HÌNH GÓI NẠP CHUNG", font=ctk.CTkFont(size=14, weight="bold"), text_color="#00d2ff")
        sec_game_lbl.pack(anchor="w", padx=10, pady=(5, 8))

        game_box = ctk.CTkFrame(left_panel, fg_color="#262c3b", corner_radius=8)
        game_box.pack(fill="x", padx=5, pady=(0, 15))

        lbl_g = ctk.CTkLabel(game_box, text="Sản phẩm / Game:", font=ctk.CTkFont(size=12))
        lbl_g.pack(anchor="w", padx=12, pady=(10, 2))
        game_names = [f"{v['name']} ({k})" for k, v in self.catalog.items()]
        self.combo_game = ctk.CTkComboBox(game_box, values=game_names, command=self.on_game_changed)
        self.combo_game.pack(fill="x", padx=12, pady=(0, 8))

        lbl_s = ctk.CTkLabel(game_box, text="Chọn máy chủ (Server):", font=ctk.CTkFont(size=12))
        lbl_s.pack(anchor="w", padx=12, pady=(0, 2))
        self.combo_server = ctk.CTkComboBox(game_box, values=["Chọn máy chủ"])
        self.combo_server.pack(fill="x", padx=12, pady=(0, 8))

        lbl_i = ctk.CTkLabel(game_box, text="Gói nạp (Mệnh giá & Chiết khấu):", font=ctk.CTkFont(size=12))
        lbl_i.pack(anchor="w", padx=12, pady=(0, 2))
        self.combo_item = ctk.CTkComboBox(game_box, values=["Chọn gói nạp"], command=self.on_item_changed)
        self.combo_item.pack(fill="x", padx=12, pady=(0, 8))

        # Price & Discount Display
        self.lbl_price_info = ctk.CTkLabel(
            game_box, 
            text="Giá gốc: 10,000 đ | Chiết khấu: 19% | Thanh toán: 8,100 đ", 
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#64b5f6"
        )
        self.lbl_price_info.pack(anchor="w", padx=12, pady=(0, 10))

        # Section C: Tùy chọn nâng cao & Điều khiển
        sec_opt_lbl = ctk.CTkLabel(left_panel, text="⚙️ 3. TÙY CHỌN & ĐỘ TRỄ", font=ctk.CTkFont(size=14, weight="bold"), text_color="#00d2ff")
        sec_opt_lbl.pack(anchor="w", padx=10, pady=(5, 8))

        opt_box = ctk.CTkFrame(left_panel, fg_color="#262c3b", corner_radius=8)
        opt_box.pack(fill="x", padx=5, pady=(0, 15))

        delay_frame = ctk.CTkFrame(opt_box, fg_color="transparent")
        delay_frame.pack(fill="x", padx=12, pady=(10, 5))
        lbl_d = ctk.CTkLabel(delay_frame, text="Độ trễ giữa 2 đơn (giây):", font=ctk.CTkFont(size=12))
        lbl_d.pack(side="left")
        self.entry_delay = ctk.CTkEntry(delay_frame, width=60)
        self.entry_delay.insert(0, "2.0")
        self.entry_delay.pack(side="right")

        self.check_auto_pay = ctk.CTkCheckBox(
            opt_box, 
            text="Tự động thanh toán ngay bằng Quỹ VND", 
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#00e676"
        )
        self.check_auto_pay.select()
        self.check_auto_pay.pack(anchor="w", padx=12, pady=(5, 10))

        # Section D: Tùy chọn Partner API (Collapsible / Optional)
        sec_api_lbl = ctk.CTkLabel(left_panel, text="🌐 4. KẾT NỐI API PARTNER (NẾU CÓ)", font=ctk.CTkFont(size=14, weight="bold"), text_color="#00d2ff")
        sec_api_lbl.pack(anchor="w", padx=10, pady=(5, 8))

        api_box = ctk.CTkFrame(left_panel, fg_color="#262c3b", corner_radius=8)
        api_box.pack(fill="x", padx=5, pady=(0, 15))

        lbl_pid = ctk.CTkLabel(api_box, text="Partner ID:", font=ctk.CTkFont(size=12))
        lbl_pid.pack(anchor="w", padx=12, pady=(10, 2))
        self.entry_partner_id = ctk.CTkEntry(api_box, placeholder_text="72232119869")
        self.entry_partner_id.pack(fill="x", padx=12, pady=(0, 8))

        lbl_pkey = ctk.CTkLabel(api_box, text="Partner Key:", font=ctk.CTkFont(size=12))
        lbl_pkey.pack(anchor="w", padx=12, pady=(0, 2))
        self.entry_partner_key = ctk.CTkEntry(api_box, placeholder_text="Nhập Partner Key nếu dùng API")
        self.entry_partner_key.pack(fill="x", padx=12, pady=(0, 12))

        # -----------------------------
        # 2.2 RIGHT PANEL: TABS NẠP & BẢNG TIẾN TRÌNH
        # -----------------------------
        right_panel = ctk.CTkTabview(body_frame, fg_color="#1e222d")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)

        tab_accounts = right_panel.add("📋 DANH SÁCH TÀI KHOẢN")
        tab_log = right_panel.add("📜 NHẬT KÝ (LOG)")

        # ----- TAB 1: DANH SÁCH TÀI KHOẢN & BẢNG TRẠNG THÁI -----
        tab_accounts.grid_columnconfigure(0, weight=1)
        tab_accounts.grid_rowconfigure(1, weight=1)

        # Sub-header: Nhập văn bản danh sách
        input_card = ctk.CTkFrame(tab_accounts, fg_color="#262c3b", corner_radius=8)
        input_card.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        input_card.grid_columnconfigure(0, weight=1)

        input_toolbar = ctk.CTkFrame(input_card, fg_color="transparent")
        input_toolbar.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))

        lbl_inp = ctk.CTkLabel(
            input_toolbar, 
            text="Nhập danh sách tài khoản (Mỗi dòng 1 nick - Hỗ trợ cả định dạng: 'taikhoan' hoặc 'taikhoan|server|menhgia'):", 
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#ffffff"
        )
        lbl_inp.pack(side="left")

        btn_load_file = ctk.CTkButton(
            input_toolbar, 
            text="📂 Nhập File .TXT", 
            width=110, 
            height=28,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self.import_from_txt
        )
        btn_load_file.pack(side="right", padx=(5, 0))

        btn_sample = ctk.CTkButton(
            input_toolbar, 
            text="Mẫu dữ liệu", 
            width=80, 
            height=28,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self.fill_sample_accounts
        )
        btn_sample.pack(side="right", padx=5)

        self.txt_accounts = ctk.CTkTextbox(input_card, height=100, font=ctk.CTkFont(family="Consolas", size=12))
        self.txt_accounts.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))

        btn_load_to_table = ctk.CTkButton(
            input_card, 
            text="📥 NẠP VÀO BẢNG DANH SÁCH", 
            height=32,
            fg_color="#0284c7",
            hover_color="#0369a1",
            font=ctk.CTkFont(weight="bold"),
            command=self.load_accounts_to_table
        )
        btn_load_to_table.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))

        # Table Card: Treeview bảng dữ liệu
        table_card = ctk.CTkFrame(tab_accounts, fg_color="#262c3b", corner_radius=8)
        table_card.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        table_card.grid_columnconfigure(0, weight=1)
        table_card.grid_rowconfigure(0, weight=1)

        # Style Treeview
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", 
                        background="#1e222d", 
                        foreground="#ffffff", 
                        fieldbackground="#1e222d", 
                        rowheight=28,
                        font=("Segoe UI", 10))
        style.configure("Treeview.Heading", 
                        background="#2c3242", 
                        foreground="#00d2ff", 
                        font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#0284c7")])

        columns = ("stt", "account", "game", "server", "package", "price", "status", "order_code", "message")
        self.tree = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="browse")

        self.tree.heading("stt", text="#")
        self.tree.heading("account", text="Tài khoản Game")
        self.tree.heading("game", text="Game")
        self.tree.heading("server", text="Máy chủ")
        self.tree.heading("package", text="Gói nạp")
        self.tree.heading("price", text="Thực trả")
        self.tree.heading("status", text="Trạng thái")
        self.tree.heading("order_code", text="Mã đơn")
        self.tree.heading("message", text="Chi tiết / Ghi chú")

        self.tree.column("stt", width=40, anchor="center")
        self.tree.column("account", width=140, anchor="w")
        self.tree.column("game", width=90, anchor="center")
        self.tree.column("server", width=90, anchor="center")
        self.tree.column("package", width=90, anchor="center")
        self.tree.column("price", width=80, anchor="e")
        self.tree.column("status", width=110, anchor="center")
        self.tree.column("order_code", width=120, anchor="center")
        self.tree.column("message", width=220, anchor="w")

        # Scrollbars cho Treeview
        tree_scroll_y = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set)

        self.tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        tree_scroll_y.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)

        # Màu sắc từng hàng trạng thái
        self.tree.tag_configure("pending", foreground="#b0bec5")
        self.tree.tag_configure("running", foreground="#4fc3f7", font=("Segoe UI", 10, "bold"))
        self.tree.tag_configure("completed", foreground="#69f0ae", font=("Segoe UI", 10, "bold"))
        self.tree.tag_configure("failed", foreground="#ff5252", font=("Segoe UI", 10, "bold"))

        # Progress bar & Thống kê
        stats_frame = ctk.CTkFrame(tab_accounts, fg_color="transparent")
        stats_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 5))
        stats_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(stats_frame, height=12)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        stats_text_frame = ctk.CTkFrame(stats_frame, fg_color="transparent")
        stats_text_frame.grid(row=1, column=0, sticky="ew")

        self.lbl_stats = ctk.CTkLabel(
            stats_text_frame, 
            text="Tổng tài khoản: 0  |  Chờ: 0  |  Thành công: 0  |  Thất bại: 0  |  Tổng tiền: 0 đ",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#ffffff"
        )
        self.lbl_stats.pack(side="left")

        btn_export = ctk.CTkButton(
            stats_text_frame, 
            text="📊 Xuất Báo Cáo", 
            width=110, 
            height=28,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self.export_results
        )
        btn_export.pack(side="right")

        btn_clear_table = ctk.CTkButton(
            stats_text_frame, 
            text="🗑 Xóa Bảng", 
            width=90, 
            height=28,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self.clear_table
        )
        btn_clear_table.pack(side="right", padx=8)

        # ----- TAB 2: LOG NHẬT KÝ -----
        tab_log.grid_columnconfigure(0, weight=1)
        tab_log.grid_rowconfigure(0, weight=1)

        log_card = ctk.CTkFrame(tab_log, fg_color="#262c3b", corner_radius=8)
        log_card.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(0, weight=1)

        self.txt_log = ctk.CTkTextbox(log_card, font=ctk.CTkFont(family="Consolas", size=11))
        self.txt_log.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        btn_clear_log = ctk.CTkButton(
            log_card, 
            text="Xóa Nhật Ký", 
            width=100, 
            height=28,
            fg_color="#374151",
            hover_color="#4b5563",
            command=lambda: self.txt_log.delete("1.0", "end")
        )
        btn_clear_log.grid(row=1, column=0, sticky="e", padx=10, pady=(0, 10))

        # =========================================================================
        # 3. BOTTOM CONTROL BAR
        # =========================================================================
        bottom_frame = ctk.CTkFrame(self, height=70, corner_radius=0, fg_color="#1a1c23")
        bottom_frame.grid(row=2, column=0, sticky="ew", padx=0, pady=0)
        bottom_frame.grid_columnconfigure(0, weight=1)

        action_container = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        action_container.pack(fill="x", padx=20, pady=12)

        self.lbl_running_status = ctk.CTkLabel(
            action_container, 
            text="Sẵn sàng thực hiện", 
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#9aa0a6"
        )
        self.lbl_running_status.pack(side="left")

        self.btn_start = ctk.CTkButton(
            action_container, 
            text="🚀 BẮT ĐẦU NẠP DANH SÁCH", 
            height=40, 
            width=230,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#00c853", 
            hover_color="#00a844",
            command=self.start_recharge_batch
        )
        self.btn_start.pack(side="right", padx=(10, 0))

        self.btn_stop = ctk.CTkButton(
            action_container, 
            text="⏹ DỪNG LẠI", 
            height=40, 
            width=120,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#d32f2f", 
            hover_color="#b71c1c",
            state="disabled",
            command=self.stop_recharge_batch
        )
        self.btn_stop.pack(side="right")

    def log(self, msg: str):
        """Ghi log vào ô nhật ký thời gian thực"""
        now = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{now}] {msg}\n"
        self.txt_log.insert("end", formatted)
        self.txt_log.see("end")

    def toggle_show_mkc2(self):
        if self.check_show_mkc2.get():
            self.entry_mkc2.configure(show="")
        else:
            self.entry_mkc2.configure(show="*")

    def apply_config(self):
        """Khôi phục cài đặt lưu trước đó"""
        self.entry_username.delete(0, "end")
        self.entry_username.insert(0, self.config.get("username", "xlzeruslx"))

        self.entry_password.delete(0, "end")
        self.entry_password.insert(0, self.config.get("password", "trong1507"))

        if self.config.get("save_mkc2", False):
            self.check_save_mkc2.select()
            self.entry_mkc2.delete(0, "end")
            self.entry_mkc2.insert(0, self.config.get("mkc2", ""))

        self.entry_delay.delete(0, "end")
        self.entry_delay.insert(0, str(self.config.get("delay", 2.0)))

        if not self.config.get("auto_pay", True):
            self.check_auto_pay.deselect()

        self.entry_partner_id.delete(0, "end")
        self.entry_partner_id.insert(0, self.config.get("partner_id", "72232119869"))

        self.entry_partner_key.delete(0, "end")
        self.entry_partner_key.insert(0, self.config.get("partner_key", ""))

        # Cài đặt dropdown game
        game_code = self.config.get("game_code", "nr")
        for g_name in self.combo_game._values:
            if f"({game_code})" in g_name:
                self.combo_game.set(g_name)
                break
        self.on_game_changed(self.combo_game.get())

        self.log("Đã khởi tạo hệ thống Auto Topup the24h.vn!")

    def get_selected_game_code(self):
        val = self.combo_game.get()
        m = re.search(r'\(([^)]+)\)', val)
        return m.group(1) if m else "nr"

    def on_game_changed(self, choice):
        """Khi người dùng đổi game, tự động nạp lại danh sách server và gói nạp"""
        game_code = self.get_selected_game_code()
        game_data = self.catalog.get(game_code, {})

        # Cập nhật Servers
        servers = game_data.get("servers", [])
        server_names = [s["name"] for s in servers] if servers else ["Mặc định"]
        self.combo_server.configure(values=server_names)
        if server_names:
            self.combo_server.set(server_names[0])

        # Cập nhật Items/Prices
        items = game_data.get("items", [])
        item_labels = [f"{it['label']} (CK: {it['discount']}%)" for it in items] if items else ["10,000 đ"]
        self.combo_item.configure(values=item_labels)
        if item_labels:
            self.combo_item.set(item_labels[0])
            self.on_item_changed(item_labels[0])

    def on_item_changed(self, choice):
        """Cập nhật thông tin giá thực tế sau chiết khấu"""
        game_code = self.get_selected_game_code()
        game_data = self.catalog.get(game_code, {})
        items = game_data.get("items", [])
        idx = self.combo_item._values.index(choice) if choice in self.combo_item._values else 0
        if 0 <= idx < len(items):
            it = items[idx]
            price = int(it["price"])
            discount = int(it["discount"])
            final_price = int(price * (100 - discount) / 100)
            self.lbl_price_info.configure(
                text=f"Giá gốc: {price:,.0f} đ | Chiết khấu: {discount}% | Thanh toán: {final_price:,.0f} đ"
            )

    def handle_login_threaded(self):
        """Đăng nhập the24h trong luồng riêng để không bị đơ UI"""
        u = self.entry_username.get().strip()
        p = self.entry_password.get().strip()
        if not u or not p:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập tên đăng nhập và mật khẩu!")
            return

        self.btn_login.configure(state="disabled", text="ĐANG ĐĂNG NHẬP...")
        self.lbl_status_badge.configure(text="🟡 Đang kết nối...", text_color="#ffb74d")
        self.log(f"Đang gửi yêu cầu đăng nhập tài khoản '{u}'...")

        def _worker():
            res = self.web_client.login(u, p)
            self.after(0, lambda: self._on_login_result(res))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_login_result(self, res):
        self.btn_login.configure(state="normal", text="ĐĂNG NHẬP THE24H")
        if res.get("success"):
            user = self.web_client.user_name or self.entry_username.get().strip()
            balance = self.web_client.balance or "0đ"
            self.lbl_status_badge.configure(text="🟢 Đã kết nối", text_color="#00e676")
            self.lbl_user_name.configure(text=f"Tài khoản: {user}")
            self.lbl_balance.configure(text=f"Số dư ví: {balance}")
            self.log(f"Đăng nhập thành công! Chủ tài khoản: {user} | Số dư ví: {balance}")
            messagebox.showinfo("Thành công", f"Đăng nhập thành công!\nChủ tài khoản: {user}\nSố dư ví VND: {balance}")
            self.save_config()
        else:
            self.lbl_status_badge.configure(text="🔴 Đăng nhập thất bại", text_color="#ff5252")
            self.log(f"Đăng nhập thất bại: {res.get('message')}")
            messagebox.showerror("Đăng nhập thất bại", res.get("message"))

    def refresh_user_info(self):
        """Làm mới số dư ví từ the24h.vn"""
        if not self.web_client.logged_in:
            self.handle_login_threaded()
            return
        
        self.log("Đang làm mới số dư ví VND...")
        def _worker():
            info = self.web_client.update_user_info()
            self.after(0, lambda: self._on_refresh_result(info))
        threading.Thread(target=_worker, daemon=True).start()

    def _on_refresh_result(self, info):
        balance = info.get("balance", "") or self.web_client.balance or "0đ"
        self.lbl_balance.configure(text=f"Số dư ví: {balance}")
        self.log(f"Cập nhật số dư thành công: {balance}")

    def fill_sample_accounts(self):
        sample = "acc_game_01\nacc_game_02\nacc_game_03\nacc_game_04|1|10000\nacc_game_05|2|20000"
        self.txt_accounts.delete("1.0", "end")
        self.txt_accounts.insert("1.0", sample)

    def import_from_txt(self):
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.txt_accounts.delete("1.0", "end")
                self.txt_accounts.insert("1.0", content)
                self.log(f"Đã nạp file danh sách: {path}")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không đọc được file: {e}")

    def load_accounts_to_table(self):
        """Phân tích danh sách tài khoản từ ô text và đưa vào Bảng Quản Lý"""
        raw_text = self.txt_accounts.get("1.0", "end").strip()
        if not raw_text:
            messagebox.showwarning("Trống", "Vui lòng nhập danh sách tài khoản vào ô văn bản!")
            return

        lines = [line.strip() for line in raw_text.splitlines() if line.strip() and not line.strip().startswith("#")]
        if not lines:
            messagebox.showwarning("Trống", "Không tìm thấy tài khoản hợp lệ nào!")
            return

        # Lấy cấu hình chung hiện tại
        current_game_code = self.get_selected_game_code()
        game_data = self.catalog.get(current_game_code, {})
        game_name = game_data.get("name", current_game_code)

        # Server
        servers = game_data.get("servers", [])
        cur_server_name = self.combo_server.get()
        cur_server_id = "1"
        for s in servers:
            if s["name"] == cur_server_name:
                cur_server_id = s["id"]
                break

        # Item / Package
        items = game_data.get("items", [])
        cur_item_idx = self.combo_item._values.index(self.combo_item.get()) if self.combo_item.get() in self.combo_item._values else 0
        cur_item = items[cur_item_idx] if 0 <= cur_item_idx < len(items) else {"id": "384", "discount": "19", "price": "10000", "label": "10,000 đ"}
        cur_price = int(cur_item["price"])
        cur_discount = int(cur_item["discount"])
        cur_pay_amount = int(cur_price * (100 - cur_discount) / 100)

        # Xóa bảng cũ và nạp mới
        for row in self.tree.get_children():
            self.tree.delete(row)
        self.task_list.clear()

        for idx, line in enumerate(lines, 1):
            parts = [p.strip() for p in line.split("|")]
            acc_name = parts[0]
            server_id = cur_server_id
            server_name = cur_server_name
            item_id = cur_item["id"]
            package_label = cur_item["label"]
            pay_amount = cur_pay_amount

            # Nếu dòng có định dạng: acc|server|menhgia
            if len(parts) >= 2 and parts[1]:
                # Tìm server theo tên hoặc id
                custom_server = parts[1]
                for s in servers:
                    if s["id"] == custom_server or s["name"].lower() == custom_server.lower():
                        server_id = s["id"]
                        server_name = s["name"]
                        break

            if len(parts) >= 3 and parts[2]:
                custom_amount = parts[2].replace(",", "").replace(".", "").replace("đ", "").strip()
                for it in items:
                    if it["price"] == custom_amount:
                        item_id = it["id"]
                        package_label = it["label"]
                        d = int(it["discount"])
                        pay_amount = int(int(it["price"]) * (100 - d) / 100)
                        break

            item_data = {
                "id": idx,
                "account": acc_name,
                "game": current_game_code,
                "game_name": game_name,
                "server": server_id,
                "server_name": server_name,
                "item": item_id,
                "package": package_label,
                "price": pay_amount,
                "status": "Chờ nạp",
                "order_code": "",
                "message": ""
            }
            self.task_list.append(item_data)

            self.tree.insert("", "end", iid=str(idx), values=(
                idx,
                acc_name,
                game_name,
                server_name,
                package_label,
                f"{pay_amount:,.0f} đ",
                "Chờ nạp",
                "",
                ""
            ), tags=("pending",))

        self.update_stats()
        self.progress_bar.set(0)
        self.log(f"Đã nạp {len(self.task_list)} tài khoản vào hàng đợi nạp tiền!")

    def clear_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        self.task_list.clear()
        self.update_stats()
        self.progress_bar.set(0)
        self.log("Đã xóa sạch bảng danh sách tài khoản.")

    def update_stats(self):
        total = len(self.task_list)
        pending = sum(1 for t in self.task_list if t["status"] == "Chờ nạp")
        completed = sum(1 for t in self.task_list if t["status"] == "Thành công")
        failed = sum(1 for t in self.task_list if t["status"] == "Thất bại")
        total_money = sum(t["price"] for t in self.task_list if t["status"] == "Thành công")

        self.lbl_stats.configure(
            text=f"Tổng tài khoản: {total}  |  Chờ: {pending}  |  Thành công: {completed}  |  Thất bại: {failed}  |  Đã chi: {total_money:,.0f} đ"
        )

    def start_recharge_batch(self):
        """Bắt đầu chạy tiến trình nạp hàng loạt"""
        if not self.task_list:
            messagebox.showwarning("Chưa có danh sách", "Vui lòng nhập tài khoản và bấm 'NẠP VÀO BẢNG DANH SÁCH' trước!")
            return

        if not self.web_client.logged_in:
            ans = messagebox.askyesno("Chưa đăng nhập", "Bạn chưa đăng nhập the24h.vn!\nBạn có muốn đăng nhập ngay bây giờ không?")
            if ans:
                self.handle_login_threaded()
            return

        mkc2 = self.entry_mkc2.get().strip()
        auto_pay = self.check_auto_pay.get()
        if auto_pay and not mkc2:
            ans = messagebox.askyesno(
                "Chưa nhập MKC2",
                "Bạn đang bật 'Tự động thanh toán ngay bằng Quỹ VND' nhưng chưa điền Mật khẩu cấp 2 (MKC2)!\n"
                "Nếu không có MKC2, hệ thống chỉ tạo đơn chờ trên web mà chưa thanh toán.\n\n"
                "Bạn có muốn tiếp tục tạo đơn không?"
            )
            if not ans:
                self.entry_mkc2.focus()
                return

        self.is_running = True
        self.stop_requested = False
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.lbl_running_status.configure(text="Đang xử lý nạp danh sách...", text_color="#00d2ff")

        self.save_config()
        self.log("=== BẮT ĐẦU TIẾN TRÌNH NẠP THẺ HÀNG LOẠT ===")

        # Khởi chạy Worker Thread
        self.current_worker = threading.Thread(target=self._batch_worker, daemon=True)
        self.current_worker.start()

    def stop_recharge_batch(self):
        """Yêu cầu dừng tiến trình"""
        self.stop_requested = True
        self.lbl_running_status.configure(text="Đang dừng lại sau đơn hiện tại...", text_color="#ff5252")
        self.log("Đã bấm DỪNG! Đang hoàn tất đơn hiện tại...")

    def _batch_worker(self):
        """Vòng lặp nạp từng tài khoản game trong danh sách"""
        mkc2 = self.entry_mkc2.get().strip()
        auto_pay = self.check_auto_pay.get()
        try:
            delay = float(self.entry_delay.get().strip() or "2.0")
        except Exception:
            delay = 2.0

        total = len(self.task_list)

        for idx, task in enumerate(self.task_list):
            if self.stop_requested:
                self.log("Tiến trình đã được dừng bởi người dùng.")
                break

            # Bỏ qua những nick đã nạp thành công
            if task["status"] == "Thành công":
                continue

            item_id = str(task["id"])
            acc = task["account"]
            game = task["game"]
            server = task["server"]
            item_pkg = task["item"]

            # Cập nhật trạng thái 'Đang nạp'
            self.after(0, lambda i=item_id, a=acc: self._update_row_status(i, "Đang nạp", "", f"Đang gửi yêu cầu nạp cho {a}...", "running"))
            self.log(f"[{idx+1}/{total}] Bắt đầu nạp cho tài khoản: {acc} (Game: {task['game_name']}, Server: {task['server_name']}, Gói: {task['package']})...")

            # Gọi client nạp
            pass_mkc2 = mkc2 if auto_pay else ""
            res = self.web_client.recharge_account(
                game_key=game,
                item_id=item_pkg,
                server_id=server,
                game_account=acc,
                qty=1,
                mkc2=pass_mkc2
            )

            # Xử lý kết quả trả về
            if res.get("success"):
                order_code = res.get("order_code", "")
                status_txt = "Thành công" if auto_pay and res.get("status") == "completed" else "Đã tạo đơn"
                tag = "completed" if status_txt == "Thành công" else "running"
                msg = res.get("message", "Thành công")

                task["status"] = status_txt
                task["order_code"] = order_code
                task["message"] = msg

                self.after(0, lambda i=item_id, s=status_txt, oc=order_code, m=msg, t=tag: self._update_row_status(i, s, oc, m, t))
                self.log(f"-> [OK] Tài khoản {acc}: {msg}")
            else:
                err_msg = res.get("message", "Lỗi không xác định")
                task["status"] = "Thất bại"
                task["message"] = err_msg

                self.after(0, lambda i=item_id, m=err_msg: self._update_row_status(i, "Thất bại", "", m, "failed"))
                self.log(f"-> [THẤT BẠI] Tài khoản {acc}: {err_msg}")

            # Cập nhật thanh tiến trình và thống kê
            progress = (idx + 1) / total
            self.after(0, lambda p=progress: self.progress_bar.set(p))
            self.after(0, self.update_stats)

            # Nghỉ theo độ trễ giữa các đơn
            if idx < total - 1 and not self.stop_requested:
                time.sleep(delay)

        self.after(0, self._on_batch_finished)

    def _update_row_status(self, item_id: str, status: str, order_code: str, message: str, tag: str):
        """Cập nhật dữ liệu hàng trong Treeview"""
        if self.tree.exists(item_id):
            cur_vals = list(self.tree.item(item_id, "values"))
            cur_vals[6] = status
            if order_code:
                cur_vals[7] = order_code
            cur_vals[8] = message
            self.tree.item(item_id, values=cur_vals, tags=(tag,))

    def _on_batch_finished(self):
        self.is_running = False
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.lbl_running_status.configure(text="Đã hoàn tất tiến trình nạp!", text_color="#00e676")
        self.log("=== HOÀN TẤT TOÀN BỘ TIẾN TRÌNH NẠP THẺ ===")
        self.refresh_user_info()
        messagebox.showinfo("Hoàn tất", "Đã hoàn tất tiến trình nạp thẻ danh sách tài khoản!")

    def export_results(self):
        """Xuất kết quả danh sách nạp ra file CSV hoặc TXT"""
        if not self.task_list:
            messagebox.showwarning("Trống", "Chưa có dữ liệu để xuất!")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("Text files", "*.txt")]
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8-sig") as f:
                f.write("STT,TaiKhoan,Game,MayChu,GoiNap,ThucTra,TrangThai,MaDon,ChiTiet\n")
                for t in self.task_list:
                    f.write(f'"{t["id"]}","{t["account"]}","{t["game_name"]}","{t["server_name"]}","{t["package"]}","{t["price"]}","{t["status"]}","{t["order_code"]}","{t["message"]}"\n')
            messagebox.showinfo("Thành công", f"Đã xuất báo cáo thành công ra:\n{file_path}")
            self.log(f"Đã xuất kết quả ra file: {file_path}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không ghi được file: {e}")


if __name__ == "__main__":
    app = The24hAutoTopupApp()
    app.mainloop()
