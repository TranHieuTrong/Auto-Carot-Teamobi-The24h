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

import io
import urllib.parse
import requests
from PIL import Image, ImageTk

from the24h_client import The24hWebClient, The24hPartnerApiClient

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CATALOG_FILE = "games_catalog.json"

# Bảng quy đổi ngọc / lượng / xu tham khảo chuẩn Teamobi / Carot
GEM_RATES = {
    "10000": {"base": 13, "x3": 32, "unit": "Ngọc"},
    "20000": {"base": 32, "x3": 82, "unit": "Ngọc"},
    "50000": {"base": 91, "x3": 231, "unit": "Ngọc"},
    "100000": {"base": 195, "x3": 495, "unit": "Ngọc"},
    "200000": {"base": 455, "x3": 1155, "unit": "Ngọc"},
    "500000": {"base": 1430, "x3": 3630, "unit": "Ngọc"},
    "1000000": {"base": 3250, "x3": 8250, "unit": "Ngọc"},
}


class TopupQRDialog(ctk.CTkToplevel):
    """Cửa sổ Nạp Tiền Quỹ the24h.vn qua mã QR VietQR tự động 24/7"""
    def __init__(self, parent, web_client, default_amount: int = 0, on_topup_success=None):
        super().__init__(parent)
        self.parent = parent
        self.web_client = web_client
        self.default_amount = max(10000, int(default_amount)) if int(default_amount) > 0 else 50000
        self.current_amount = self.default_amount
        self.on_topup_success = on_topup_success

        self.title("⚡ NẠP TIỀN VÀO QUỸ THE24H.VN - QUÉT MÃ QR VIETQR")
        self.geometry("860x700")
        self.minsize(800, 640)
        self.configure(fg_color="#14171f")
        self.transient(parent)
        self.grab_set()

        self.initial_balance_val = self.parent._parse_money_val(self.web_client.balance)
        self.is_closed = False
        self.poll_active = True
        self.poll_timer = None
        self.deposit_data = {}
        self.qr_image_tk = None

        self.setup_ui()
        self.fetch_deposit_info_async()
        self.start_balance_polling()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def is_alive(self):
        try:
            return not getattr(self, "is_closed", False) and bool(self.winfo_exists())
        except Exception:
            return False

    def on_close(self):
        self.is_closed = True
        self.poll_active = False
        if self.poll_timer is not None:
            try:
                self.after_cancel(self.poll_timer)
            except Exception:
                pass
            self.poll_timer = None
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header banner
        header = ctk.CTkFrame(self, fg_color="#1e222d", corner_radius=0, height=60)
        header.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 10))
        header.grid_columnconfigure(0, weight=1)

        lbl_t = ctk.CTkLabel(
            header, 
            text="⚡ NẠP TIỀN QUỸ THE24H.VN QUA MÃ QR NGÂN HÀNG (VIETQR 24/7)",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#00d2ff"
        )
        lbl_t.pack(anchor="w", padx=16, pady=(10, 2))

        lbl_sub = ctk.CTkLabel(
            header,
            text="Hệ thống the24h.vn sẽ tự động nhận diện và cộng số dư vào ví trong 10-30 giây sau khi chuyển khoản",
            font=ctk.CTkFont(size=11),
            text_color="#9aa0a6"
        )
        lbl_sub.pack(anchor="w", padx=16, pady=(0, 10))

        # Main Body (2 Columns)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=0)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # ----------------- CỘT TRÁI: MÃ QR -----------------
        card_left = ctk.CTkFrame(body, fg_color="#1e222d", corner_radius=10, border_width=1, border_color="#262c3b")
        card_left.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=0)
        card_left.grid_columnconfigure(0, weight=1)

        lbl_card_qr = ctk.CTkLabel(card_left, text="📱 MÃ QR CHUYỂN KHOẢN TỰ ĐỘNG", font=ctk.CTkFont(size=13, weight="bold"), text_color="#00e676")
        lbl_card_qr.pack(anchor="w", padx=14, pady=(12, 6))

        # Khung hiển thị QR
        self.frame_qr = ctk.CTkFrame(card_left, fg_color="#ffffff", corner_radius=8, width=270, height=270)
        self.frame_qr.pack(padx=14, pady=6)
        self.frame_qr.pack_propagate(False)

        self.lbl_qr_img = ctk.CTkLabel(self.frame_qr, text="⏳ Đang tạo hóa đơn & mã VietQR...", font=ctk.CTkFont(size=12, weight="bold"), text_color="#1e222d", wraplength=240, justify="center")
        self.lbl_qr_img.pack(expand=True, fill="both")

        lbl_qr_hint = ctk.CTkLabel(
            card_left,
            text="📲 Mở App Ngân hàng bất kỳ (VCB, BIDV, MB, Tech, Momo...)\nchọn Quét QR để tự điền số tiền & nội dung",
            font=ctk.CTkFont(size=11),
            text_color="#9aa0a6",
            justify="center"
        )
        lbl_qr_hint.pack(padx=10, pady=(6, 8))

        # Chọn nhanh số tiền nạp
        lbl_quick = ctk.CTkLabel(card_left, text="⚡ Chọn nhanh số tiền nạp:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#ffd54f")
        lbl_quick.pack(anchor="w", padx=14, pady=(4, 4))

        quick_frame = ctk.CTkFrame(card_left, fg_color="transparent")
        quick_frame.pack(fill="x", padx=10, pady=(0, 10))

        amounts_to_show = []
        if self.default_amount > 0 and self.default_amount not in [20000, 50000, 100000, 200000, 500000]:
            amounts_to_show.append((f"Thiếu ({self.default_amount:,}đ)", self.default_amount))
        amounts_to_show.extend([
            ("20k", 20000),
            ("50k", 50000),
            ("100k", 100000),
            ("200k", 200000),
            ("500k", 500000)
        ])

        for txt, val in amounts_to_show:
            btn = ctk.CTkButton(
                quick_frame,
                text=txt,
                width=65,
                height=26,
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color="#262c3b",
                hover_color="#0284c7",
                command=lambda v=val: self.set_amount(v)
            )
            btn.pack(side="left", padx=3, pady=2)

        # ----------------- CỘT PHẢI: THÔNG TIN & CÚ PHÁP -----------------
        card_right = ctk.CTkFrame(body, fg_color="#1e222d", corner_radius=10, border_width=1, border_color="#262c3b")
        card_right.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=0)
        card_right.grid_columnconfigure(0, weight=1)

        lbl_card_info = ctk.CTkLabel(card_right, text="📋 THÔNG TIN THỤ HƯỞNG & CÚ PHÁP", font=ctk.CTkFont(size=13, weight="bold"), text_color="#00d2ff")
        lbl_card_info.pack(anchor="w", padx=14, pady=(12, 6))

        # Nhập số tiền tùy chỉnh
        box_amt = ctk.CTkFrame(card_right, fg_color="#262c3b", corner_radius=6)
        box_amt.pack(fill="x", padx=12, pady=(0, 8))
        
        lbl_a = ctk.CTkLabel(box_amt, text="Số tiền muốn nạp (VNĐ):", font=ctk.CTkFont(size=11, weight="bold"), text_color="#ffd54f")
        lbl_a.pack(anchor="w", padx=10, pady=(6, 2))

        amt_input_row = ctk.CTkFrame(box_amt, fg_color="transparent")
        amt_input_row.pack(fill="x", padx=10, pady=(0, 8))

        self.entry_amount = ctk.CTkEntry(amt_input_row, height=32, font=ctk.CTkFont(size=13, weight="bold"))
        self.entry_amount.insert(0, str(self.current_amount))
        self.entry_amount.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_apply_amt = ctk.CTkButton(
            amt_input_row,
            text="🔄 Tạo lại QR",
            width=95,
            height=32,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self.on_amount_submitted
        )
        btn_apply_amt.pack(side="right")

        # Bảng chi tiết chuyển khoản
        box_details = ctk.CTkFrame(card_right, fg_color="#262c3b", corner_radius=6)
        box_details.pack(fill="x", padx=12, pady=(0, 8))

        self.row_bank = self._build_info_row(box_details, "🏦 Ngân hàng:", "BIDV")
        self.row_stk = self._build_info_row(box_details, "🔢 Số tài khoản:", "Đang tải...", has_copy=True)
        self.row_holder = self._build_info_row(box_details, "👤 Chủ tài khoản:", "THE24H", has_copy=True)
        self.row_money = self._build_info_row(box_details, "💵 Số tiền nạp:", f"{self.current_amount:,} đ", has_copy=True)
        self.row_memo = self._build_info_row(box_details, "📝 Nội dung (BẮT BUỘC):", "Đang tải...", has_copy=True, highlight=True)

        # Cảnh báo lưu ý
        warn_box = ctk.CTkFrame(card_right, fg_color="#312217", border_width=1, border_color="#f59e0b", corner_radius=6)
        warn_box.pack(fill="x", padx=12, pady=(4, 10))

        lbl_w1 = ctk.CTkLabel(
            warn_box,
            text="⚠️ QUAN TRỌNG: Quét mã QR sẽ tự động điền đúng Số tiền & Nội dung.\nNếu nhập tay trong App Ngân Hàng, BẮT BUỘC ghi đúng Nội dung chuyển khoản ở trên để hệ thống tự động cộng số dư vào ví!",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#fcd34d",
            justify="left"
        )
        lbl_w1.pack(padx=10, pady=8)

        # ----------------- FOOTER ACTIONS & STATUS -----------------
        footer = ctk.CTkFrame(self, fg_color="#181a20", height=65, corner_radius=0)
        footer.grid(row=2, column=0, sticky="ew", padx=0, pady=0)
        footer.grid_columnconfigure(0, weight=1)

        foot_bar = ctk.CTkFrame(footer, fg_color="transparent")
        foot_bar.pack(fill="x", padx=16, pady=10)

        left_stat = ctk.CTkFrame(foot_bar, fg_color="transparent")
        left_stat.pack(side="left")

        self.lbl_wallet_now = ctk.CTkLabel(
            left_stat,
            text=f"Số dư ví the24h: {self.web_client.balance or '0đ'}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#00e5ff"
        )
        self.lbl_wallet_now.pack(anchor="w")

        self.lbl_status = ctk.CTkLabel(
            left_stat,
            text="🟢 Đang theo dõi số dư ví (tự động kiểm tra mỗi 4s)...",
            font=ctk.CTkFont(size=11),
            text_color="#9aa0a6"
        )
        self.lbl_status.pack(anchor="w")

        btn_close = ctk.CTkButton(
            foot_bar,
            text="Đóng",
            width=90,
            height=36,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self.on_close
        )
        btn_close.pack(side="right", padx=(8, 0))

        self.btn_start_topup = ctk.CTkButton(
            foot_bar,
            text="🚀 Bắt đầu nạp danh sách",
            width=180,
            height=36,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#374151",
            hover_color="#4b5563",
            state="disabled",
            command=self.on_start_batch_clicked
        )
        self.btn_start_topup.pack(side="right", padx=(8, 0))

        btn_manual_check = ctk.CTkButton(
            foot_bar,
            text="🔄 Kiểm tra số dư ví ngay",
            width=170,
            height=36,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=lambda: self._check_balance_once(silent=False)
        )
        btn_manual_check.pack(side="right")

    def _build_info_row(self, parent, label_text, default_val, has_copy=False, highlight=False):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=3)

        lbl = ctk.CTkLabel(row, text=label_text, width=150, anchor="w", font=ctk.CTkFont(size=11))
        lbl.pack(side="left")

        color = "#ffd54f" if highlight else "#ffffff"
        font = ctk.CTkFont(size=11, weight="bold")

        val_entry = ctk.CTkEntry(row, height=26, font=font, text_color=color)
        val_entry.insert(0, default_val)
        val_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        if has_copy:
            btn_copy = ctk.CTkButton(
                row,
                text="📋 Chép",
                width=60,
                height=26,
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color="#374151",
                hover_color="#0284c7",
                command=lambda e=val_entry, n=label_text: self.copy_value(e.get(), n)
            )
            btn_copy.pack(side="right")

        return val_entry

    def copy_value(self, text, field_name):
        try:
            self.clipboard_clear()
            self.clipboard_append(text.strip())
            self.update()
            clean_name = re.sub(r'[^a-zA-Z0-9\s\u00C0-\u1EF9]', '', field_name).strip()
            self.lbl_status.configure(text=f"✅ Đã sao chép {clean_name}: {text.strip()}", text_color="#00e676")
        except Exception:
            pass

    def fetch_deposit_info_async(self):
        if not self.is_alive():
            return
        try:
            self.lbl_qr_img.configure(image=None, text="⏳ Đang tạo hóa đơn nạp the24h.vn & tải VietQR...", wraplength=240, justify="center")
        except Exception:
            pass

        def _worker():
            if not self.is_alive():
                return
            data = self.web_client.get_deposit_info(self.current_amount)
            if not self.is_alive():
                return
            try:
                self.after(0, lambda: self._on_deposit_info_ready(data))
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _on_deposit_info_ready(self, data):
        if not self.is_alive():
            return
        try:
            self.deposit_data = data
            bank_name = data.get("bank_name", "BIDV")
            stk = data.get("account_no", "").strip()
            holder = data.get("account_name", "THE24H").strip()
            syntax = data.get("syntax", f"THE24H {self.web_client.user_name or ''}").strip()

            self.row_bank.delete(0, "end")
            self.row_bank.insert(0, bank_name)

            self.row_stk.delete(0, "end")
            if stk:
                self.row_stk.insert(0, stk)
            else:
                self.row_stk.insert(0, "Chưa lấy được STK (Vui lòng điền)")

            self.row_holder.delete(0, "end")
            self.row_holder.insert(0, holder)

            self.row_memo.delete(0, "end")
            self.row_memo.insert(0, syntax)

            self.update_qr_image()
        except Exception:
            pass

    def set_amount(self, val: int):
        if not self.is_alive():
            return
        try:
            self.current_amount = max(10000, int(val))
            self.entry_amount.delete(0, "end")
            self.entry_amount.insert(0, str(self.current_amount))
            self.fetch_deposit_info_async()
        except Exception:
            pass

    def on_amount_submitted(self):
        if not self.is_alive():
            return
        try:
            val_str = re.sub(r'[^\d]', '', self.entry_amount.get().strip())
            val = int(val_str) if val_str else 0
            if val < 10000:
                messagebox.showwarning("Số tiền không hợp lệ", "the24h.vn yêu cầu nạp tối thiểu từ 10,000 đ trở lên!")
                return
            self.current_amount = val
            self.fetch_deposit_info_async()
        except Exception:
            pass

    def update_qr_image(self):
        if not self.is_alive():
            return
        try:
            amt = self.current_amount
            stk = self.row_stk.get().strip()
            holder = self.row_holder.get().strip()
            memo = self.row_memo.get().strip()
            bank = self.row_bank.get().strip().lower() or "bidv"

            self.row_money.delete(0, "end")
            self.row_money.insert(0, f"{amt:,} đ")

            if not stk or "đang tải" in stk.lower() or "chưa lấy" in stk.lower():
                self.lbl_qr_img.configure(image=None, text="⚠️ Vui lòng nhập Số tài khoản nhận tiền", wraplength=240, justify="center")
                return

            direct_url = self.deposit_data.get("direct_qr_url", "")
            if direct_url and direct_url.startswith("http") and amt == self.default_amount:
                qr_url = direct_url
            else:
                qr_url = The24hWebClient.generate_vietqr_url(bank, stk, holder, amt, memo)

            self.lbl_qr_img.configure(image=None, text="⏳ Đang tải mã VietQR...", wraplength=240, justify="center")

            def _fetch_qr():
                if not self.is_alive():
                    return
                try:
                    r = requests.get(qr_url, timeout=12)
                    if not self.is_alive():
                        return
                    if r.status_code == 200:
                        pil_img = Image.open(io.BytesIO(r.content))
                        if self.is_alive():
                            self.after(0, lambda: self._display_qr(pil_img))
                    else:
                        if self.is_alive():
                            self.after(0, lambda: self.lbl_qr_img.configure(text="❌ Lỗi tải QR từ ngân hàng", wraplength=240, justify="center"))
                except Exception:
                    if self.is_alive():
                        try:
                            self.after(0, lambda: self.lbl_qr_img.configure(text="❌ Không thể kết nối VietQR", wraplength=240, justify="center"))
                        except Exception:
                            pass

            threading.Thread(target=_fetch_qr, daemon=True).start()
        except Exception:
            pass

    def _display_qr(self, pil_img):
        if not self.is_alive():
            return
        try:
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(250, 250))
            self.lbl_qr_img.configure(image=ctk_img, text="")
            self.qr_image_tk = ctk_img
        except Exception:
            pass

    def start_balance_polling(self):
        if not self.poll_active or not self.is_alive():
            return
        self._check_balance_once(silent=True)
        try:
            self.poll_timer = self.after(4000, self.start_balance_polling)
        except Exception:
            pass

    def _check_balance_once(self, silent=False):
        if not self.is_alive():
            return

        def _worker():
            if not self.is_alive():
                return
            info = self.web_client.update_user_info()
            if not self.is_alive():
                return
            try:
                self.after(0, lambda: self._on_balance_polled(info, silent))
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _on_balance_polled(self, info, silent=False):
        if not self.is_alive():
            return
        try:
            new_bal_str = info.get("balance", "") or self.web_client.balance or "0đ"
            new_bal_val = self.parent._parse_money_val(new_bal_str)
            self.lbl_wallet_now.configure(text=f"Số dư ví the24h: {new_bal_str}")

            if new_bal_val > self.initial_balance_val:
                diff_added = new_bal_val - self.initial_balance_val
                self.lbl_status.configure(
                    text=f"🎉 ĐÃ NHẬN TIỀN THÀNH CÔNG! (+{diff_added:,}đ) | Số dư mới: {new_bal_str}",
                    text_color="#00e676"
                )
                self.btn_start_topup.configure(
                    state="normal",
                    fg_color="#00c853",
                    hover_color="#00a844",
                    text="🚀 ĐỦ TIỀN RỒI - BẮT ĐẦU NẠP NGAY"
                )
                self.parent.lbl_balance.configure(text=f"Số dư ví: {new_bal_str}")
                self.parent.recalculate_and_sync_table()
            else:
                if not silent:
                    self.lbl_status.configure(
                        text=f"Số dư ví chưa thay đổi ({new_bal_str}). Đang tiếp tục theo dõi...",
                        text_color="#ffd54f"
                    )
        except Exception:
            pass

    def on_start_batch_clicked(self):
        self.on_close()
        if self.on_topup_success:
            self.on_topup_success()


class The24hAutoTopupApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("THE24H AUTO TOPUP - TỰ ĐỘNG NẠP CAROT / TEAMOBI HÀNG LOẠT")
        self.geometry("1280x850")
        self.minsize(1050, 720)

        # Clients & State
        self.web_client = The24hWebClient()
        self.partner_client = The24hPartnerApiClient()
        self.catalog = self.load_catalog()
        # Cấu hình chỉ lưu trên RAM trong suốt phiên chạy (KHÔNG LƯU Ổ CỨNG)
        self.config = {
            "game_code": "nr",
            "delay": 2.0,
            "auto_pay": True
        }

        self.is_running = False
        self.stop_requested = False
        self.current_worker = None

        self.task_list = []
        self.history_list = []

        self.setup_ui()
        self.apply_config()

        # Tải dữ liệu live ban đầu
        self.after(500, self.fetch_live_game_data)

    def load_catalog(self):
        if os.path.exists(CATALOG_FILE):
            try:
                with open(CATALOG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
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
        # Cấu hình mặc định trong RAM (Không đọc/ghi file đĩa - an toàn 100% khi public)
        return {
            "game_code": "nr",
            "delay": 2.0,
            "auto_pay": True
        }

    def save_config(self):
        # Không lưu thông tin ra file ổ cứng
        pass

    def setup_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # =========================================================================
        # 1. TOP HEADER BAR
        # =========================================================================
        header_frame = ctk.CTkFrame(self, height=65, corner_radius=0, fg_color="#181a20")
        header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header_frame.grid_columnconfigure(1, weight=1)

        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.grid(row=0, column=0, padx=20, pady=8, sticky="w")

        lbl_title = ctk.CTkLabel(
            title_box, 
            text="⚡ THE24H AUTO TOPUP", 
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#00d2ff"
        )
        lbl_title.pack(anchor="w")

        lbl_sub = ctk.CTkLabel(
            title_box, 
            text="Nạp Carot / Teamobi Tự Động Hàng Loạt & Tra Cứu Lịch Sử the24h.vn", 
            font=ctk.CTkFont(size=12),
            text_color="#9aa0a6"
        )
        lbl_sub.pack(anchor="w")

        user_info_frame = ctk.CTkFrame(header_frame, fg_color="#242834", corner_radius=8)
        user_info_frame.grid(row=0, column=2, padx=20, pady=8, sticky="e")

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
            text="🔄 Làm mới ví", 
            width=90, 
            height=28,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self.refresh_user_info
        )
        btn_reload_balance.pack(side="left", padx=(5, 10))

        # =========================================================================
        # 2. MAIN BODY
        # =========================================================================
        body_frame = ctk.CTkFrame(self, fg_color="transparent")
        body_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=8)
        body_frame.grid_columnconfigure(1, weight=1)
        body_frame.grid_rowconfigure(0, weight=1)

        # -------------------------------------------------------------
        # 2.1 LEFT PANEL: CẤU HÌNH & TÀI KHOẢN (Gọn gàng 320px)
        # -------------------------------------------------------------
        left_panel = ctk.CTkScrollableFrame(body_frame, width=320, corner_radius=10, fg_color="#1e222d")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=0)

        # Card 1: Tài khoản Web the24h.vn
        card_acc_lbl = ctk.CTkLabel(left_panel, text="🔑 1. TÀI KHOẢN THE24H.VN", font=ctk.CTkFont(size=13, weight="bold"), text_color="#00d2ff")
        card_acc_lbl.pack(anchor="w", padx=8, pady=(8, 4))

        box_acc = ctk.CTkFrame(left_panel, fg_color="#262c3b", corner_radius=8)
        box_acc.pack(fill="x", padx=4, pady=(0, 10))

        lbl_u = ctk.CTkLabel(box_acc, text="Email / SĐT đăng nhập:", font=ctk.CTkFont(size=11))
        lbl_u.pack(anchor="w", padx=10, pady=(8, 2))
        self.entry_username = ctk.CTkEntry(box_acc, height=30, placeholder_text="Tài khoản the24h.vn")
        self.entry_username.pack(fill="x", padx=10, pady=(0, 6))

        lbl_p = ctk.CTkLabel(box_acc, text="Mật khẩu:", font=ctk.CTkFont(size=11))
        lbl_p.pack(anchor="w", padx=10, pady=(0, 2))
        self.entry_password = ctk.CTkEntry(box_acc, height=30, placeholder_text="Mật khẩu", show="*")
        self.entry_password.pack(fill="x", padx=10, pady=(0, 6))

        lbl_m = ctk.CTkLabel(box_acc, text="Mật khẩu cấp 2 (MKC2 - Thanh toán):", font=ctk.CTkFont(size=11, weight="bold"), text_color="#ffb74d")
        lbl_m.pack(anchor="w", padx=10, pady=(0, 2))
        self.entry_mkc2 = ctk.CTkEntry(box_acc, height=30, placeholder_text="Nhập MKC2 để tự thanh toán", show="*")
        self.entry_mkc2.pack(fill="x", padx=10, pady=(0, 4))

        mkc2_opts = ctk.CTkFrame(box_acc, fg_color="transparent")
        mkc2_opts.pack(fill="x", padx=10, pady=(0, 6))
        self.check_show_mkc2 = ctk.CTkCheckBox(mkc2_opts, text="Hiện MKC2", font=ctk.CTkFont(size=10), command=self.toggle_show_mkc2)
        self.check_show_mkc2.pack(side="left")
        lbl_ram_only = ctk.CTkLabel(mkc2_opts, text="🔒 RAM Only (Tắt là xóa)", font=ctk.CTkFont(size=10, weight="bold"), text_color="#10b981")
        lbl_ram_only.pack(side="right")

        self.btn_login = ctk.CTkButton(
            box_acc, 
            text="ĐĂNG NHẬP THE24H", 
            height=32,
            fg_color="#0284c7", 
            hover_color="#0369a1",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.handle_login_threaded
        )
        self.btn_login.pack(fill="x", padx=10, pady=(2, 10))

        # Card 2: Cấu hình Game & Máy chủ & Gói nạp (LIVE API)
        card_game_lbl = ctk.CTkFrame(left_panel, fg_color="transparent")
        card_game_lbl.pack(fill="x", padx=8, pady=(2, 4))
        
        lbl_g_title = ctk.CTkLabel(card_game_lbl, text="🎮 2. CHỌN GAME & GÓI", font=ctk.CTkFont(size=13, weight="bold"), text_color="#00d2ff")
        lbl_g_title.pack(side="left")

        btn_live_reload = ctk.CTkButton(
            card_game_lbl, 
            text="🔄 Tải lại API", 
            width=75, 
            height=22,
            font=ctk.CTkFont(size=10),
            fg_color="#374151",
            hover_color="#4b5563",
            command=self.fetch_live_game_data
        )
        btn_live_reload.pack(side="right")

        box_game = ctk.CTkFrame(left_panel, fg_color="#262c3b", corner_radius=8)
        box_game.pack(fill="x", padx=4, pady=(0, 10))

        lbl_g = ctk.CTkLabel(box_game, text="Sản phẩm / Game:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_g.pack(anchor="w", padx=10, pady=(8, 2))
        game_names = [f"{v['name']} ({k})" for k, v in self.catalog.items()]
        self.combo_game = ctk.CTkComboBox(box_game, height=30, values=game_names, command=self.on_game_changed)
        self.combo_game.pack(fill="x", padx=10, pady=(0, 6))

        lbl_s = ctk.CTkLabel(box_game, text="Máy chủ (Server):", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_s.pack(anchor="w", padx=10, pady=(0, 2))
        self.combo_server = ctk.CTkComboBox(box_game, height=30, values=["Chọn máy chủ"], command=self.on_server_changed)
        self.combo_server.pack(fill="x", padx=10, pady=(0, 6))

        lbl_i = ctk.CTkLabel(box_game, text="Số tiền / Mệnh giá:", font=ctk.CTkFont(size=11, weight="bold"))
        lbl_i.pack(anchor="w", padx=10, pady=(0, 2))
        self.combo_item = ctk.CTkComboBox(box_game, height=30, values=["Chọn gói nạp"], command=self.on_item_changed)
        self.combo_item.pack(fill="x", padx=10, pady=(0, 8))

        # Card 3: Cài đặt nạp
        card_opt_lbl = ctk.CTkLabel(left_panel, text="⚙️ 3. CÀI ĐẶT NẠP", font=ctk.CTkFont(size=13, weight="bold"), text_color="#00d2ff")
        card_opt_lbl.pack(anchor="w", padx=8, pady=(2, 4))

        box_opt = ctk.CTkFrame(left_panel, fg_color="#262c3b", corner_radius=8)
        box_opt.pack(fill="x", padx=4, pady=(0, 8))

        delay_frame = ctk.CTkFrame(box_opt, fg_color="transparent")
        delay_frame.pack(fill="x", padx=10, pady=(8, 4))
        lbl_d = ctk.CTkLabel(delay_frame, text="Nghỉ giữa mỗi nick (giây):", font=ctk.CTkFont(size=11))
        lbl_d.pack(side="left")
        self.entry_delay = ctk.CTkEntry(delay_frame, width=50, height=28)
        self.entry_delay.insert(0, "2.0")
        self.entry_delay.pack(side="right")

        self.check_auto_pay = ctk.CTkCheckBox(
            box_opt, 
            text="Tự động thanh toán ngay Quỹ VND", 
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#00e676"
        )
        self.check_auto_pay.select()
        self.check_auto_pay.pack(anchor="w", padx=10, pady=(4, 8))

        btn_open_deposit = ctk.CTkButton(
            box_opt,
            text="⚡ Nạp Quỹ / Quét QR VietQR",
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self.open_topup_qr_dialog
        )
        btn_open_deposit.pack(fill="x", padx=10, pady=(0, 10))

        # -------------------------------------------------------------
        # 2.2 RIGHT PANEL: TABS (NẠP TIỀN & LỊCH SỬ NẠP)
        # -------------------------------------------------------------
        self.main_tabs = ctk.CTkTabview(body_frame, fg_color="#1e222d")
        self.main_tabs.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)

        tab_topup = self.main_tabs.add("🚀 NẠP TIỀN HÀNG LOẠT")
        tab_history = self.main_tabs.add("📜 LỊCH SỬ NẠP THE24H")
        tab_log = self.main_tabs.add("📝 NHẬT KÝ (LOG)")

        # =============================================================
        # TAB 1: NẠP TIỀN HÀNG LOẠT
        # =============================================================
        tab_topup.grid_columnconfigure(0, weight=1)
        tab_topup.grid_rowconfigure(2, weight=1)

        # BOX A: NHẬP FILE / NICK
        box_input = ctk.CTkFrame(tab_topup, fg_color="#262c3b", corner_radius=8)
        box_input.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 6))
        box_input.grid_columnconfigure(0, weight=1)

        input_toolbar = ctk.CTkFrame(box_input, fg_color="transparent")
        input_toolbar.grid(row=0, column=0, sticky="ew", padx=10, pady=(6, 4))

        lbl_input_title = ctk.CTkLabel(
            input_toolbar, 
            text="📁 DANH SÁCH TÀI KHOẢN (Mỗi dòng 1 nick: SĐT, Email hoặc Username)", 
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#00d2ff"
        )
        lbl_input_title.pack(side="left")

        btn_import_file = ctk.CTkButton(
            input_toolbar, 
            text="📂 CHỌN FILE .TXT", 
            width=130, 
            height=28,
            font=ctk.CTkFont(weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self.import_from_txt
        )
        btn_import_file.pack(side="right", padx=(6, 0))

        btn_sample = ctk.CTkButton(
            input_toolbar, 
            text="Mẫu thử", 
            width=70, 
            height=28,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self.fill_sample_accounts
        )
        btn_sample.pack(side="right", padx=6)

        btn_clear_input = ctk.CTkButton(
            input_toolbar, 
            text="Xóa", 
            width=50, 
            height=28,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self.clear_input_text
        )
        btn_clear_input.pack(side="right")

        self.txt_accounts = ctk.CTkTextbox(box_input, height=85, font=ctk.CTkFont(family="Consolas", size=12))
        self.txt_accounts.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        self.txt_accounts.bind("<KeyRelease>", lambda e: self.recalculate_and_sync_table())

        # BOX B: TỔNG TIỀN, CHIẾT KHẤU & QUY ĐỔI NGỌC CHI TIẾT
        card_summary = ctk.CTkFrame(tab_topup, fg_color="#262c3b", corner_radius=8, border_width=1, border_color="#0284c7")
        card_summary.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))
        card_summary.grid_columnconfigure((0, 1, 2, 3), weight=1)

        # Cột 1: Số lượng nick
        box_s1 = ctk.CTkFrame(card_summary, fg_color="transparent")
        box_s1.grid(row=0, column=0, padx=10, pady=6, sticky="w")
        ctk.CTkLabel(box_s1, text="Số lượng tài khoản:", font=ctk.CTkFont(size=11), text_color="#9aa0a6").pack(anchor="w")
        self.lbl_sum_count = ctk.CTkLabel(box_s1, text="0 tài khoản", font=ctk.CTkFont(size=15, weight="bold"), text_color="#ffffff")
        self.lbl_sum_count.pack(anchor="w")

        # Cột 2: Gói nạp & Quy đổi Ngọc
        box_s2 = ctk.CTkFrame(card_summary, fg_color="transparent")
        box_s2.grid(row=0, column=1, padx=10, pady=6, sticky="w")
        ctk.CTkLabel(box_s2, text="💎 Quy đổi Ngọc / 1 nick:", font=ctk.CTkFont(size=11), text_color="#9aa0a6").pack(anchor="w")
        self.lbl_sum_gems = ctk.CTkLabel(box_s2, text="-- Ngọc (x3: --)", font=ctk.CTkFont(size=14, weight="bold"), text_color="#00e5ff")
        self.lbl_sum_gems.pack(anchor="w")

        # Cột 3: Chiết khấu & Thực trả 1 nick
        box_s3 = ctk.CTkFrame(card_summary, fg_color="transparent")
        box_s3.grid(row=0, column=2, padx=10, pady=6, sticky="w")
        ctk.CTkLabel(box_s3, text="Chiết khấu & Thực trả/nick:", font=ctk.CTkFont(size=11), text_color="#9aa0a6").pack(anchor="w")
        self.lbl_sum_unit_pay = ctk.CTkLabel(box_s3, text="0 đ (CK: 0%)", font=ctk.CTkFont(size=14, weight="bold"), text_color="#69f0ae")
        self.lbl_sum_unit_pay.pack(anchor="w")

        # Cột 4: TỔNG TIỀN THANH TOÁN
        box_s4 = ctk.CTkFrame(card_summary, fg_color="transparent")
        box_s4.grid(row=0, column=3, padx=10, pady=6, sticky="e")
        ctk.CTkLabel(box_s4, text="TỔNG TIỀN THANH TOÁN:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#ffd54f").pack(anchor="e")
        self.lbl_sum_total_money = ctk.CTkLabel(box_s4, text="0 đ", font=ctk.CTkFont(size=19, weight="bold"), text_color="#00ff66")
        self.lbl_sum_total_money.pack(anchor="e")

        # BOX C: BẢNG TIẾN TRÌNH TREEVIEW (RỘNG RÃI, CÓ SCROLLBAR NGANG & DỌC)
        table_container = ctk.CTkFrame(tab_topup, fg_color="#262c3b", corner_radius=8)
        table_container.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 6))
        table_container.grid_columnconfigure(0, weight=1)
        table_container.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", 
                        background="#1e222d", 
                        foreground="#ffffff", 
                        fieldbackground="#1e222d", 
                        rowheight=26,
                        font=("Segoe UI", 10))
        style.configure("Treeview.Heading", 
                        background="#262c3b", 
                        foreground="#00d2ff", 
                        font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#0284c7")])

        # Các cột gọn gàng, rõ ràng, không bị co rút
        columns = ("stt", "account", "server", "package", "gems", "pay_amount", "status", "order_code", "message")
        self.tree = ttk.Treeview(table_container, columns=columns, show="headings", selectmode="browse")

        self.tree.heading("stt", text="#")
        self.tree.heading("account", text="Tài khoản Game")
        self.tree.heading("server", text="Máy chủ")
        self.tree.heading("package", text="Gói nạp")
        self.tree.heading("gems", text="💎 Nhận được")
        self.tree.heading("pay_amount", text="Thực trả")
        self.tree.heading("status", text="Trạng thái")
        self.tree.heading("order_code", text="Mã đơn")
        self.tree.heading("message", text="Chi tiết / Ghi chú")

        self.tree.column("stt", width=35, minwidth=35, stretch=False, anchor="center")
        self.tree.column("account", width=170, minwidth=130, stretch=True, anchor="w")
        self.tree.column("server", width=95, minwidth=80, stretch=False, anchor="center")
        self.tree.column("package", width=90, minwidth=80, stretch=False, anchor="center")
        self.tree.column("gems", width=140, minwidth=110, stretch=False, anchor="center")
        self.tree.column("pay_amount", width=85, minwidth=75, stretch=False, anchor="e")
        self.tree.column("status", width=105, minwidth=90, stretch=False, anchor="center")
        self.tree.column("order_code", width=135, minwidth=115, stretch=False, anchor="center")
        self.tree.column("message", width=180, minwidth=100, stretch=True, anchor="w")

        # Scrollbars (Cả Ngang và Dọc)
        tree_scroll_y = ttk.Scrollbar(table_container, orient="vertical", command=self.tree.yview)
        tree_scroll_x = ttk.Scrollbar(table_container, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)

        self.tree.grid(row=0, column=0, sticky="nsew", padx=4, pady=(4, 0))
        tree_scroll_y.grid(row=0, column=1, sticky="ns", padx=(0, 4), pady=(4, 0))
        tree_scroll_x.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 4))

        self.tree.tag_configure("pending", foreground="#b0bec5")
        self.tree.tag_configure("running", foreground="#4fc3f7", font=("Segoe UI", 10, "bold"))
        self.tree.tag_configure("completed", foreground="#69f0ae", font=("Segoe UI", 10, "bold"))
        self.tree.tag_configure("failed", foreground="#ff5252", font=("Segoe UI", 10, "bold"))

        # Progress bar & Thống kê bottom tab
        stats_frame = ctk.CTkFrame(tab_topup, fg_color="transparent")
        stats_frame.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 4))
        stats_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(stats_frame, height=10)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        stats_row = ctk.CTkFrame(stats_frame, fg_color="transparent")
        stats_row.grid(row=1, column=0, sticky="ew")

        self.lbl_stats = ctk.CTkLabel(
            stats_row, 
            text="Tổng: 0 | Chờ: 0 | Thành công: 0 | Thất bại: 0",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#ffffff"
        )
        self.lbl_stats.pack(side="left")

        btn_export = ctk.CTkButton(
            stats_row, 
            text="📊 Xuất Báo Cáo", 
            width=100, 
            height=26,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self.export_results
        )
        btn_export.pack(side="right")

        # =============================================================
        # TAB 2: LỊCH SỬ NẠP THE24H (MỚI)
        # =============================================================
        tab_history.grid_columnconfigure(0, weight=1)
        tab_history.grid_rowconfigure(2, weight=1)

        hist_toolbar = ctk.CTkFrame(tab_history, fg_color="#262c3b", corner_radius=8)
        hist_toolbar.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 4))

        lbl_hist_title = ctk.CTkLabel(
            hist_toolbar, 
            text="📜 LỊCH SỬ NẠP TOPUP TRÊN THE24H.VN", 
            font=ctk.CTkFont(size=13, weight="bold"), 
            text_color="#00d2ff"
        )
        lbl_hist_title.pack(side="left", padx=10, pady=6)

        self.lbl_hist_count = ctk.CTkLabel(
            hist_toolbar, 
            text="(Đang chờ tải...)", 
            font=ctk.CTkFont(size=11),
            text_color="#9aa0a6"
        )
        self.lbl_hist_count.pack(side="left", padx=5)

        btn_export_hist = ctk.CTkButton(
            hist_toolbar,
            text="📊 Xuất Lịch Sử CSV",
            height=28,
            width=130,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#374151",
            hover_color="#4b5563",
            command=self.export_history_csv
        )
        btn_export_hist.pack(side="right", padx=10, pady=6)

        btn_fetch_history = ctk.CTkButton(
            hist_toolbar, 
            text="🔄 TẢI TOÀN BỘ LỊCH SỬ", 
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#0284c7", 
            hover_color="#0369a1",
            command=self.load_recharge_history
        )
        btn_fetch_history.pack(side="right", padx=(0, 6), pady=6)

        # Khung thẻ Thống kê Tổng Nạp & Chiết khấu (Stats Bar)
        hist_stats_frame = ctk.CTkFrame(tab_history, fg_color="#1e222d", corner_radius=8)
        hist_stats_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))
        hist_stats_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        # Thẻ 1: Tổng gói nạp (Mệnh giá)
        box_stat1 = ctk.CTkFrame(hist_stats_frame, fg_color="#262c3b", corner_radius=6)
        box_stat1.grid(row=0, column=0, padx=5, pady=6, sticky="nsew")
        ctk.CTkLabel(box_stat1, text="💎 TỔNG GÓI NẠP (MỆNH GIÁ)", font=ctk.CTkFont(size=10, weight="bold"), text_color="#9aa0a6").pack(anchor="w", padx=10, pady=(6, 1))
        self.lbl_hist_total_face = ctk.CTkLabel(box_stat1, text="0 đ", font=ctk.CTkFont(size=15, weight="bold"), text_color="#00d2ff")
        self.lbl_hist_total_face.pack(anchor="w", padx=10, pady=(0, 6))

        # Thẻ 2: Tổng thực trừ ví
        box_stat2 = ctk.CTkFrame(hist_stats_frame, fg_color="#262c3b", corner_radius=6)
        box_stat2.grid(row=0, column=1, padx=5, pady=6, sticky="nsew")
        ctk.CTkLabel(box_stat2, text="💰 TỔNG THỰC TRỪ VÍ", font=ctk.CTkFont(size=10, weight="bold"), text_color="#9aa0a6").pack(anchor="w", padx=10, pady=(6, 1))
        self.lbl_hist_total_paid = ctk.CTkLabel(box_stat2, text="0 đ", font=ctk.CTkFont(size=15, weight="bold"), text_color="#00e676")
        self.lbl_hist_total_paid.pack(anchor="w", padx=10, pady=(0, 6))

        # Thẻ 3: Tiết kiệm chiết khấu
        box_stat3 = ctk.CTkFrame(hist_stats_frame, fg_color="#262c3b", corner_radius=6)
        box_stat3.grid(row=0, column=2, padx=5, pady=6, sticky="nsew")
        ctk.CTkLabel(box_stat3, text="🎉 TIẾT KIỆM (CHIẾT KHẤU)", font=ctk.CTkFont(size=10, weight="bold"), text_color="#9aa0a6").pack(anchor="w", padx=10, pady=(6, 1))
        self.lbl_hist_total_saved = ctk.CTkLabel(box_stat3, text="0 đ", font=ctk.CTkFont(size=15, weight="bold"), text_color="#ffd54f")
        self.lbl_hist_total_saved.pack(anchor="w", padx=10, pady=(0, 6))

        # Thẻ 4: Tổng số đơn
        box_stat4 = ctk.CTkFrame(hist_stats_frame, fg_color="#262c3b", corner_radius=6)
        box_stat4.grid(row=0, column=3, padx=5, pady=6, sticky="nsew")
        ctk.CTkLabel(box_stat4, text="📊 TỔNG SỐ ĐƠN NẠP", font=ctk.CTkFont(size=10, weight="bold"), text_color="#9aa0a6").pack(anchor="w", padx=10, pady=(6, 1))
        self.lbl_hist_order_counts = ctk.CTkLabel(box_stat4, text="0 đơn", font=ctk.CTkFont(size=14, weight="bold"), text_color="#f3f4f6")
        self.lbl_hist_order_counts.pack(anchor="w", padx=10, pady=(0, 6))

        # Bảng Lịch Sử Treeview (Row 2)
        hist_table_box = ctk.CTkFrame(tab_history, fg_color="#262c3b", corner_radius=8)
        hist_table_box.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 6))
        hist_table_box.grid_columnconfigure(0, weight=1)
        hist_table_box.grid_rowconfigure(0, weight=1)

        hist_cols = ("stt", "order_code", "service", "server_name", "account", "amount", "pay_amount", "status", "created_at")
        self.tree_history = ttk.Treeview(hist_table_box, columns=hist_cols, show="headings", selectmode="browse")

        self.tree_history.heading("stt", text="#")
        self.tree_history.heading("order_code", text="Mã đơn hàng")
        self.tree_history.heading("service", text="Dịch vụ")
        self.tree_history.heading("server_name", text="Máy chủ")
        self.tree_history.heading("account", text="Tài khoản nhận")
        self.tree_history.heading("amount", text="Gói nạp")
        self.tree_history.heading("pay_amount", text="Thực trừ ví")
        self.tree_history.heading("status", text="Trạng thái")
        self.tree_history.heading("created_at", text="Thời gian tạo")

        self.tree_history.column("stt", width=35, minwidth=35, stretch=False, anchor="center")
        self.tree_history.column("order_code", width=140, minwidth=120, stretch=False, anchor="center")
        self.tree_history.column("service", width=75, minwidth=65, stretch=False, anchor="center")
        self.tree_history.column("server_name", width=110, minwidth=90, stretch=False, anchor="center")
        self.tree_history.column("account", width=190, minwidth=150, stretch=True, anchor="w")
        self.tree_history.column("amount", width=95, minwidth=85, stretch=False, anchor="center")
        self.tree_history.column("pay_amount", width=95, minwidth=85, stretch=False, anchor="e")
        self.tree_history.column("status", width=105, minwidth=90, stretch=False, anchor="center")
        self.tree_history.column("created_at", width=135, minwidth=115, stretch=False, anchor="center")

        h_scroll_y = ttk.Scrollbar(hist_table_box, orient="vertical", command=self.tree_history.yview)
        h_scroll_x = ttk.Scrollbar(hist_table_box, orient="horizontal", command=self.tree_history.xview)
        self.tree_history.configure(yscrollcommand=h_scroll_y.set, xscrollcommand=h_scroll_x.set)

        self.tree_history.grid(row=0, column=0, sticky="nsew", padx=4, pady=(4, 0))
        h_scroll_y.grid(row=0, column=1, sticky="ns", padx=(0, 4), pady=(4, 0))
        h_scroll_x.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 4))

        self.tree_history.tag_configure("completed", foreground="#69f0ae", font=("Segoe UI", 10, "bold"))
        self.tree_history.tag_configure("pending", foreground="#ffd54f", font=("Segoe UI", 10, "bold"))
        self.tree_history.tag_configure("failed", foreground="#ff5252", font=("Segoe UI", 10, "bold"))

        # =============================================================
        # TAB 3: NHẬT KÝ (LOG)
        # =============================================================
        tab_log.grid_columnconfigure(0, weight=1)
        tab_log.grid_rowconfigure(0, weight=1)

        self.txt_log = ctk.CTkTextbox(tab_log, font=ctk.CTkFont(family="Consolas", size=11))
        self.txt_log.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        btn_clear_log = ctk.CTkButton(
            tab_log, 
            text="Xóa Nhật Ký", 
            width=90, 
            height=26,
            fg_color="#374151",
            hover_color="#4b5563",
            command=lambda: self.txt_log.delete("1.0", "end")
        )
        btn_clear_log.grid(row=1, column=0, sticky="e", padx=6, pady=(0, 6))

        # =========================================================================
        # 3. BOTTOM CONTROL BAR
        # =========================================================================
        bottom_frame = ctk.CTkFrame(self, height=65, corner_radius=0, fg_color="#181a20")
        bottom_frame.grid(row=2, column=0, sticky="ew", padx=0, pady=0)
        bottom_frame.grid_columnconfigure(0, weight=1)

        action_container = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        action_container.pack(fill="x", padx=20, pady=10)

        self.lbl_running_status = ctk.CTkLabel(
            action_container, 
            text="Sẵn sàng nạp tiền", 
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#9aa0a6"
        )
        self.lbl_running_status.pack(side="left")

        self.btn_start = ctk.CTkButton(
            action_container, 
            text="🚀 BẮT ĐẦU NẠP TẤT CẢ", 
            height=42, 
            width=210,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#00c853", 
            hover_color="#00a844",
            command=self.start_recharge_batch
        )
        self.btn_start.pack(side="right", padx=(10, 0))

        self.btn_stop = ctk.CTkButton(
            action_container, 
            text="⏹ DỪNG LẠI", 
            height=42, 
            width=100,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#d32f2f", 
            hover_color="#b71c1c",
            state="disabled",
            command=self.stop_recharge_batch
        )
        self.btn_stop.pack(side="right")

        self.btn_topup_qr = ctk.CTkButton(
            action_container,
            text="💳 NẠP TIỀN QUÉT MÃ QR",
            height=42,
            width=210,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self.open_topup_qr_dialog
        )
        self.btn_topup_qr.pack(side="right", padx=(0, 10))

    def log(self, msg: str):
        now = datetime.now().strftime("%H:%M:%S")
        self.txt_log.insert("end", f"[{now}] {msg}\n")
        self.txt_log.see("end")

    def toggle_show_mkc2(self):
        self.entry_mkc2.configure(show="" if self.check_show_mkc2.get() else "*")

    def apply_config(self):
        # Ô đăng nhập, mật khẩu, MKC2 luôn để trống ban đầu - hoàn toàn không lưu trên máy
        self.entry_username.delete(0, "end")
        self.entry_password.delete(0, "end")
        self.entry_mkc2.delete(0, "end")

        self.entry_delay.delete(0, "end")
        self.entry_delay.insert(0, str(self.config.get("delay", 2.0)))

        if not self.config.get("auto_pay", True):
            self.check_auto_pay.deselect()

        game_code = self.config.get("game_code", "nr")
        for g_name in self.combo_game._values:
            if f"({game_code})" in g_name:
                self.combo_game.set(g_name)
                break

    def auto_initial_login(self):
        pass

    def get_selected_game_code(self):
        val = self.combo_game.get()
        m = re.search(r'\(([^)]+)\)', val)
        return m.group(1) if m else "nr"

    def fetch_live_game_data(self):
        """Lấy danh sách máy chủ và bảng giá trực tiếp từ web/API the24h.vn"""
        game_code = self.get_selected_game_code()
        game_title = self.catalog.get(game_code, {}).get("name", game_code)
        self.log(f"Đang kết nối lấy dữ liệu API trực tiếp cho game '{game_title}' ({game_code})...")

        def _worker():
            live_data = self.web_client.fetch_live_game_info(game_code)
            self.after(0, lambda: self._on_live_data_fetched(game_code, live_data))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_live_data_fetched(self, game_code, live_data):
        if live_data.get("success") and (live_data.get("items") or live_data.get("servers")):
            if game_code not in self.catalog:
                self.catalog[game_code] = {"name": game_code}
            if live_data.get("items"):
                self.catalog[game_code]["items"] = live_data["items"]
            if live_data.get("servers"):
                self.catalog[game_code]["servers"] = live_data["servers"]
            self.log(f"✅ Đã tải dữ liệu trực tiếp: {len(live_data.get('servers', []))} máy chủ, {len(live_data.get('items', []))} gói nạp.")
        else:
            self.log("⚠️ Sử dụng cấu hình có sẵn cho game.")

        self.update_game_ui_options()

    def on_game_changed(self, choice):
        self.fetch_live_game_data()

    def update_game_ui_options(self):
        game_code = self.get_selected_game_code()
        game_data = self.catalog.get(game_code, {})

        servers = game_data.get("servers", [])
        server_names = [s["name"] for s in servers] if servers else ["Mặc định"]
        self.combo_server.configure(values=server_names)
        if server_names:
            self.combo_server.set(server_names[0])

        items = game_data.get("items", [])
        item_labels = []
        for it in items:
            price_str = str(it.get("price", "0"))
            gem_info = GEM_RATES.get(price_str, None)
            gem_text = f" (~{gem_info['base']} {gem_info['unit']})" if gem_info else ""
            item_labels.append(f"{it['label']} - CK: {it['discount']}%{gem_text}")

        if not item_labels:
            item_labels = ["10,000 đ"]

        self.combo_item.configure(values=item_labels)
        if item_labels:
            self.combo_item.set(item_labels[0])

        self.recalculate_and_sync_table()

    def on_server_changed(self, choice):
        self.recalculate_and_sync_table()

    def on_item_changed(self, choice):
        self.recalculate_and_sync_table()

    def get_current_item_info(self):
        game_code = self.get_selected_game_code()
        game_data = self.catalog.get(game_code, {})
        items = game_data.get("items", [])
        cur_choice = self.combo_item.get()
        idx = self.combo_item._values.index(cur_choice) if cur_choice in self.combo_item._values else 0
        if 0 <= idx < len(items):
            it = items[idx]
            price = int(it.get("price", 10000))
            discount = int(it.get("discount", 0))
            final_price = int(price * (100 - discount) / 100)
            price_key = str(price)
            gem_info = GEM_RATES.get(price_key, {"base": "--", "x3": "--", "unit": "Ngọc"})
            return {
                "id": it.get("id", ""),
                "price": price,
                "discount": discount,
                "final_price": final_price,
                "label": it.get("label", f"{price:,} đ"),
                "gem_base": gem_info["base"],
                "gem_x3": gem_info["x3"],
                "gem_unit": gem_info["unit"]
            }
        return {"id": "", "price": 10000, "discount": 0, "final_price": 10000, "label": "10,000 đ", "gem_base": 13, "gem_x3": 32, "gem_unit": "Ngọc"}

    def get_current_server_info(self):
        game_code = self.get_selected_game_code()
        game_data = self.catalog.get(game_code, {})
        servers = game_data.get("servers", [])
        cur_s_name = self.combo_server.get()
        for s in servers:
            if s["name"] == cur_s_name:
                return s
        return {"id": "1", "name": cur_s_name}

    def parse_input_accounts(self):
        raw_text = self.txt_accounts.get("1.0", "end").strip()
        if not raw_text:
            return []
        lines = []
        for line in raw_text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                lines.append(line)
        return lines

    def recalculate_and_sync_table(self):
        """Tính toán tổng tiền, chiết khấu, số ngọc và cập nhật bảng Treeview"""
        accounts = self.parse_input_accounts()
        item_info = self.get_current_item_info()
        server_info = self.get_current_server_info()
        game_code = self.get_selected_game_code()
        game_name = self.catalog.get(game_code, {}).get("name", game_code)

        num_acc = len(accounts)
        unit_price = item_info["price"]
        discount = item_info["discount"]
        unit_pay = item_info["final_price"]
        total_pay = unit_pay * num_acc

        gem_base = item_info["gem_base"]
        gem_x3 = item_info["gem_x3"]
        unit_str = item_info["gem_unit"]

        # Chuỗi quy đổi ngọc
        gem_display = f"💎 ~{gem_base} {unit_str} (x3: {gem_x3})" if isinstance(gem_base, int) else "--"

        # 1. Cập nhật thẻ tóm tắt
        self.lbl_sum_count.configure(text=f"{num_acc} tài khoản")
        self.lbl_sum_gems.configure(text=gem_display)
        self.lbl_sum_unit_pay.configure(text=f"{unit_pay:,.0f} đ (CK: {discount}%)")
        self.lbl_sum_total_money.configure(text=f"{total_pay:,.0f} đ")

        # So sánh số dư ví
        current_wallet = 0
        try:
            val_str = re.sub(r'[^0-9]', '', self.web_client.balance or "0")
            current_wallet = int(val_str) if val_str else 0
        except Exception:
            current_wallet = 0

        if total_pay > 0:
            if current_wallet >= total_pay:
                self.lbl_running_status.configure(
                    text=f"✅ Số dư ví {current_wallet:,.0f}đ đủ thanh toán cho {num_acc} tài khoản (Tổng: {total_pay:,.0f}đ)",
                    text_color="#00e676"
                )
                self.btn_topup_qr.configure(
                    text="⚡ Nạp Thêm Quỹ / QR",
                    fg_color="#374151",
                    hover_color="#4b5563"
                )
            else:
                diff = total_pay - current_wallet
                self.lbl_running_status.configure(
                    text=f"⚠️ Cần: {total_pay:,.0f}đ | Số dư ví: {current_wallet:,.0f}đ (Thiếu: {diff:,.0f}đ)",
                    text_color="#ffd54f"
                )
                self.btn_topup_qr.configure(
                    text=f"💳 Quét QR Nạp Thiếu: {diff:,.0f}đ",
                    fg_color="#0284c7",
                    hover_color="#0369a1"
                )

        # 2. Cập nhật Treeview bảng tiến trình
        old_status_map = {t["account"]: (t.get("status"), t.get("order_code"), t.get("message")) for t in self.task_list}

        for row in self.tree.get_children():
            self.tree.delete(row)
        self.task_list.clear()

        for idx, acc in enumerate(accounts, 1):
            old_s = old_status_map.get(acc)
            status = old_s[0] if old_s else "Chờ nạp"
            order_code = old_s[1] if old_s else ""
            msg = old_s[2] if old_s else ""
            tag = "completed" if status == "Thành công" else ("failed" if status == "Thất bại" else "pending")

            task_item = {
                "id": idx,
                "account": acc,
                "game": game_code,
                "game_name": game_name,
                "server": server_info["id"],
                "server_name": server_info["name"],
                "item": item_info["id"],
                "package": item_info["label"],
                "gems": gem_display,
                "price": unit_pay,
                "status": status,
                "order_code": order_code,
                "message": msg
            }
            self.task_list.append(task_item)

            acc_disp = f"\u200b{acc}" if (acc and acc.startswith("0")) else acc
            self.tree.insert("", "end", iid=str(idx), values=(
                idx,
                acc_disp,
                server_info["name"],
                item_info["label"],
                gem_display,
                f"{unit_pay:,.0f} đ",
                status,
                order_code,
                msg
            ), tags=(tag,))

        self.update_stats()

    def update_stats(self):
        total = len(self.task_list)
        pending = sum(1 for t in self.task_list if t["status"] == "Chờ nạp")
        completed = sum(1 for t in self.task_list if t["status"] == "Thành công")
        failed = sum(1 for t in self.task_list if t["status"] == "Thất bại")
        self.lbl_stats.configure(
            text=f"Tổng: {total} | Chờ: {pending} | Thành công: {completed} | Thất bại: {failed}"
        )

    def import_from_txt(self):
        path = filedialog.askopenfilename(
            title="Chọn file chứa danh sách tài khoản",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.txt_accounts.delete("1.0", "end")
                self.txt_accounts.insert("1.0", content)
                self.recalculate_and_sync_table()
                acc_count = len(self.parse_input_accounts())
                self.log(f"Đã nạp file: {os.path.basename(path)} ({acc_count} tài khoản)")
                messagebox.showinfo("Nạp file thành công", f"Đã nạp {acc_count} tài khoản từ file:\n{os.path.basename(path)}")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không đọc được file: {e}")

    def fill_sample_accounts(self):
        sample = "1231123123\nhhuahua@gmail.com\nabc@gmail.com\n823748234"
        self.txt_accounts.delete("1.0", "end")
        self.txt_accounts.insert("1.0", sample)
        self.recalculate_and_sync_table()

    def clear_input_text(self):
        self.txt_accounts.delete("1.0", "end")
        self.recalculate_and_sync_table()

    def handle_login_threaded(self, silent=False):
        u = self.entry_username.get().strip()
        p = self.entry_password.get().strip()
        if not u or not p:
            if not silent:
                messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập tên đăng nhập và mật khẩu the24h.vn!")
            return

        self.btn_login.configure(state="disabled", text="ĐANG ĐĂNG NHẬP...")
        self.lbl_status_badge.configure(text="🟡 Đang kết nối...", text_color="#ffb74d")
        if not silent:
            self.log(f"Đang gửi yêu cầu đăng nhập tài khoản '{u}'...")

        def _worker():
            res = self.web_client.login(u, p)
            self.after(0, lambda: self._on_login_result(res, silent))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_login_result(self, res, silent=False):
        self.btn_login.configure(state="normal", text="ĐĂNG NHẬP THE24H")
        if res.get("success"):
            user = self.web_client.user_name or self.entry_username.get().strip()
            balance = self.web_client.balance or "0đ"
            self.lbl_status_badge.configure(text="🟢 Đã kết nối", text_color="#00e676")
            self.lbl_user_name.configure(text=f"Tài khoản: {user}")
            self.lbl_balance.configure(text=f"Số dư ví: {balance}")
            self.log(f"Đăng nhập thành công! Chủ tài khoản: {user} | Số dư ví: {balance}")
            self.recalculate_and_sync_table()
            # Tự động tải lịch sử nạp
            self.load_recharge_history()
            if not silent:
                messagebox.showinfo("Thành công", f"Đăng nhập thành công!\nChủ tài khoản: {user}\nSố dư ví: {balance}")
        else:
            self.lbl_status_badge.configure(text="🔴 Đăng nhập thất bại", text_color="#ff5252")
            self.log(f"Đăng nhập thất bại: {res.get('message')}")
            if not silent:
                messagebox.showerror("Đăng nhập thất bại", res.get("message"))

    def refresh_user_info(self):
        if not self.web_client.logged_in:
            self.handle_login_threaded()
            return
        
        self.log("Đang làm mới số dư ví...")
        def _worker():
            info = self.web_client.update_user_info()
            self.after(0, lambda: self._on_refresh_result(info))
        threading.Thread(target=_worker, daemon=True).start()

    def _on_refresh_result(self, info):
        balance = info.get("balance", "") or self.web_client.balance or "0đ"
        self.lbl_balance.configure(text=f"Số dư ví: {balance}")
        self.log(f"Cập nhật số dư ví: {balance}")
        self.recalculate_and_sync_table()

    # =========================================================================
    # LỊCH SỬ NẠP THE24H.VN
    # =========================================================================
    def load_recharge_history(self):
        if not self.web_client.logged_in:
            self.handle_login_threaded()
            return

        self.lbl_hist_count.configure(text="(Đang tải tất cả giao dịch...)")
        self.log("Đang tải toàn bộ lịch sử giao dịch từ the24h.vn...")

        def _on_progress(p, count):
            self.after(0, lambda: self.lbl_hist_count.configure(text=f"(Đang tải trang {p}: {count} đơn...)"))

        def _worker():
            history = self.web_client.get_recharge_history(page=0, progress_callback=_on_progress)
            self.after(0, lambda: self._on_history_loaded(history))

        threading.Thread(target=_worker, daemon=True).start()

    @staticmethod
    def _parse_money_val(val) -> int:
        if not val:
            return 0
        clean = re.sub(r'[^\d]', '', str(val))
        try:
            return int(clean) if clean else 0
        except Exception:
            return 0

    def resolve_server_name(self, service_code: str, server_id: str) -> str:
        """Quy đổi ID server thành tên hiển thị chuẩn (ví dụ: ID 10 -> 7 Sao, ID 22 -> 15 sao)"""
        if not server_id:
            return ""
        
        sid_str = str(server_id).strip()
        svc = str(service_code).strip().lower()

        # 1. Tra cứu trực tiếp trong catalog đã tải
        target_game = None
        for g_code, g_data in self.catalog.items():
            g_name = g_data.get("name", "").lower()
            if svc == g_code.lower() or svc in g_name or g_code.lower() in svc:
                target_game = g_data
                break
            if svc in ["nr", "ngocrong"] and g_code == "nr":
                target_game = g_data
                break
            if svc in ["nj", "ninja", "ninjaschool"] and g_code == "nj":
                target_game = g_data
                break
            if svc in ["hs", "hso", "hiepsi"] and g_code == "hs":
                target_game = g_data
                break

        if not target_game and "nr" in self.catalog:
            target_game = self.catalog["nr"]

        if target_game:
            for s in target_game.get("servers", []):
                if str(s.get("id", "")).strip() == sid_str:
                    return s.get("name", sid_str)

        # 2. Bảng mapping dự phòng chuẩn Ngọc Rồng (The24h)
        nr_mapping = {
            "1": "1 Sao", "2": "2 Sao", "3": "3 Sao", "6": "4 Sao", "7": "5 Sao", "9": "6 Sao",
            "10": "7 Sao", "11": "8 Sao", "12": "9 sao", "13": "10 Sao", "14": "11 sao (vip 1)",
            "15": "12 sao", "18": "13 sao", "20": "14 sao", "22": "15 sao", "19": "VIP 2",
            "16": "super 1", "17": "super 2", "21": "super 3"
        }
        if sid_str in nr_mapping:
            return nr_mapping[sid_str]

        return f"Sv {sid_str}"

    def _on_history_loaded(self, history):
        self.history_list = history
        for row in self.tree_history.get_children():
            self.tree_history.delete(row)

        if not history:
            self.lbl_hist_count.configure(text="(Chưa có lịch sử hoặc không lấy được)")
            self.lbl_hist_total_face.configure(text="0 đ")
            self.lbl_hist_total_paid.configure(text="0 đ")
            self.lbl_hist_total_saved.configure(text="0 đ")
            self.lbl_hist_order_counts.configure(text="0 đơn")
            self.log("Không tìm thấy đơn nạp nào trong lịch sử.")
            return

        self.lbl_hist_count.configure(text=f"(Tất cả {len(history)} giao dịch)")
        self.log(f"Đã tải thành công toàn bộ {len(history)} giao dịch từ the24h.vn!")

        total_face = 0
        total_paid = 0
        success_count = 0
        pending_count = 0
        failed_count = 0

        for idx, h in enumerate(history, 1):
            st = h.get("status", "")
            st_lower = st.lower()
            if "hoàn thành" in st_lower:
                tag = "completed"
                success_count += 1
            elif "chờ" in st_lower:
                tag = "pending"
                pending_count += 1
            else:
                tag = "failed"
                failed_count += 1

            face_val = self._parse_money_val(h.get("amount", ""))
            paid_val = self._parse_money_val(h.get("pay_amount", ""))
            total_face += face_val
            total_paid += paid_val

            amount_disp = f"{face_val:,} đ" if face_val > 0 else (h.get("amount", "") or "0 đ")
            paid_disp = f"{paid_val:,} đ" if paid_val > 0 else (h.get("pay_amount", "") or "0 đ")

            server_name = self.resolve_server_name(h.get("service", ""), h.get("server_id", ""))
            game_acc = h.get("game_username", "") or h.get("account_info", "")
            game_acc_disp = f"\u200b{game_acc}" if (game_acc and game_acc.startswith("0")) else game_acc

            self.tree_history.insert("", "end", iid=str(idx), values=(
                idx,
                h.get("order_code", ""),
                h.get("service", "").upper(),
                server_name,
                game_acc_disp,
                amount_disp,
                paid_disp,
                st,
                h.get("created_at", "")
            ), tags=(tag,))

        saved_val = max(0, total_face - total_paid)
        self.lbl_hist_total_face.configure(text=f"{total_face:,} đ")
        self.lbl_hist_total_paid.configure(text=f"{total_paid:,} đ")
        self.lbl_hist_total_saved.configure(text=f"{saved_val:,} đ")
        self.lbl_hist_order_counts.configure(text=f"{len(history)} đơn ({success_count} xong • {pending_count} chờ)")

    def export_history_csv(self):
        if not self.history_list:
            messagebox.showwarning("Chưa có dữ liệu", "Không có dữ liệu lịch sử để xuất!")
            return
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            initialfile=f"lich_su_nap_the24h_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        if not file_path:
            return

        try:
            import csv
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["STT", "Mã đơn hàng", "Dịch vụ", "Máy chủ", "Tài khoản nhận", "Gói nạp", "Thực trừ ví", "Trạng thái", "Thời gian tạo"])
                for idx, h in enumerate(self.history_list, 1):
                    s_name = self.resolve_server_name(h.get("service", ""), h.get("server_id", ""))
                    g_acc = h.get("game_username", "") or h.get("account_info", "")
                    writer.writerow([
                        idx,
                        h.get("order_code", ""),
                        h.get("service", "").upper(),
                        s_name,
                        g_acc,
                        h.get("amount", ""),
                        h.get("pay_amount", ""),
                        h.get("status", ""),
                        h.get("created_at", "")
                    ])
            messagebox.showinfo("Thành công", f"Đã xuất lịch sử ra file:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Lỗi xuất file", str(e))

    # =========================================================================
    # NẠP TIỀN QUỸ THE24H.VN / MÃ QR VIETQR
    # =========================================================================
    def open_topup_qr_dialog(self, default_amount=None):
        """Mở hộp thoại tạo mã QR VietQR nạp tiền vào quỹ the24h.vn"""
        if not self.web_client.logged_in:
            ans = messagebox.askyesno(
                "Chưa đăng nhập the24h.vn",
                "Bạn cần đăng nhập tài khoản the24h.vn để hệ thống lấy đúng Ngân hàng, STK và Cú pháp nạp tiền cá nhân của bạn.\n\n"
                "Bạn có muốn đăng nhập ngay bây giờ không?"
            )
            if ans:
                self.handle_login_threaded()
            return

        if default_amount is None:
            # Tự động tính số tiền còn thiếu từ danh sách nick đang chờ nạp
            total_needed = sum(t.get("price", 0) for t in self.task_list if t.get("status") != "Thành công")
            current_wallet = self._parse_money_val(self.web_client.balance)
            diff = total_needed - current_wallet
            default_amount = diff if diff > 0 else (total_needed if total_needed > 0 else 50000)

        TopupQRDialog(
            parent=self,
            web_client=self.web_client,
            default_amount=int(default_amount),
            on_topup_success=self._on_qr_topup_success
        )

    def _on_qr_topup_success(self):
        """Callback khi chuyển khoản thành công và số dư đã được cộng vào ví"""
        self.recalculate_and_sync_table()
        self.log("✅ Tiền nạp đã vào ví the24h.vn thành công! Bắt đầu tiến trình nạp...")
        self.start_recharge_batch()

    # =========================================================================
    # BẮT ĐẦU TIẾN TRÌNH NẠP BATCH
    # =========================================================================
    def start_recharge_batch(self):
        if not self.task_list:
            messagebox.showwarning("Chưa có tài khoản", "Vui lòng nhập danh sách tài khoản hoặc chọn file .txt trước!")
            return

        if not self.web_client.logged_in:
            ans = messagebox.askyesno("Chưa đăng nhập", "Bạn chưa đăng nhập the24h.vn!\nBạn có muốn đăng nhập ngay không?")
            if ans:
                self.handle_login_threaded()
            return

        mkc2 = self.entry_mkc2.get().strip()
        auto_pay = self.check_auto_pay.get()

        # KIỂM TRA SỐ DƯ VÍ SO VỚI TỔNG TIỀN CẦN NẠP
        total_needed = sum(t.get("price", 0) for t in self.task_list if t.get("status") != "Thành công")
        current_wallet = self._parse_money_val(self.web_client.balance)
        diff = total_needed - current_wallet

        if auto_pay and diff > 0:
            pending_count = sum(1 for t in self.task_list if t.get("status") != "Thành công")
            msg = (
                f"⚠️ SỐ DƯ VÍ KHÔNG ĐỦ ĐỂ NẠP TOÀN BỘ DANH SÁCH!\n\n"
                f"• Số tài khoản chờ nạp: {pending_count} nick\n"
                f"• Tổng tiền cần nạp: {total_needed:,.0f} đ\n"
                f"• Số dư ví the24h hiện tại: {current_wallet:,.0f} đ\n"
                f"• Số tiền còn thiếu: {diff:,.0f} đ\n\n"
                f"👉 Bạn có muốn mở MÃ QR VIETQR để chuyển khoản đúng {diff:,.0f} đ ngay không?\n"
                f"(Sau khi chuyển khoản xong, hệ thống sẽ tự động phát hiện số dư mới và tiếp tục nạp)"
            )
            ans = messagebox.askyesno("Số dư ví không đủ", msg)
            if ans:
                self.open_topup_qr_dialog(default_amount=diff)
                return
            else:
                ans_cont = messagebox.askyesno(
                    "Xác nhận nạp thiếu",
                    f"Bạn chọn không nạp thêm tiền. Hệ thống sẽ nạp các tài khoản lần lượt cho đến khi hết số dư ví ({current_wallet:,.0f} đ).\n\n"
                    f"Bạn có chắc chắn muốn chạy không?"
                )
                if not ans_cont:
                    return

        if auto_pay and not mkc2:
            ans = messagebox.askyesno(
                "Chưa nhập MKC2",
                "Bạn đang bật 'Tự động thanh toán ngay bằng Quỹ VND' nhưng chưa điền Mật khẩu cấp 2 (MKC2)!\n"
                "Nếu không có MKC2, hệ thống chỉ tạo đơn chờ thanh toán trên web.\n\n"
                "Bạn có muốn tiếp tục tạo đơn không?"
            )
            if not ans:
                self.entry_mkc2.focus()
                return

        self.is_running = True
        self.stop_requested = False
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.lbl_running_status.configure(text="Đang thực hiện nạp lần lượt...", text_color="#00d2ff")

        self.log("=== BẮT ĐẦU NẠP DANH SÁCH TÀI KHOẢN ===")

        self.current_worker = threading.Thread(target=self._batch_worker, daemon=True)
        self.current_worker.start()

    def stop_recharge_batch(self):
        self.stop_requested = True
        self.lbl_running_status.configure(text="Đang dừng lại sau đơn hiện tại...", text_color="#ff5252")
        self.log("Đã bấm DỪNG! Đang hoàn tất đơn hiện tại...")

    def _batch_worker(self):
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

            if task["status"] == "Thành công":
                continue

            item_id = str(task["id"])
            acc = task["account"]
            game = task["game"]
            server = task["server"]
            item_pkg = task["item"]

            self.after(0, lambda i=item_id, a=acc: self._update_row_status(i, "Đang nạp", "", f"Đang gửi yêu cầu cho {a}...", "running"))
            self.log(f"[{idx+1}/{total}] Đang nạp tài khoản: {acc} (Server: {task['server_name']}, Gói: {task['package']})...")

            pass_mkc2 = mkc2 if auto_pay else ""
            res = self.web_client.recharge_account(
                game_key=game,
                item_id=item_pkg,
                server_id=server,
                game_account=acc,
                qty=1,
                mkc2=pass_mkc2
            )

            if res.get("success"):
                order_code = res.get("order_code", "")
                status_txt = "Thành công" if auto_pay and res.get("status") == "completed" else "Đã tạo đơn"
                tag = "completed" if status_txt == "Thành công" else "running"
                msg = res.get("message", "Thành công")

                task["status"] = status_txt
                task["order_code"] = order_code
                task["message"] = msg

                self.after(0, lambda i=item_id, s=status_txt, oc=order_code, m=msg, t=tag: self._update_row_status(i, s, oc, m, t))
                self.log(f"-> [THÀNH CÔNG] Tài khoản {acc}: {msg}")
            else:
                err_msg = res.get("message", "Lỗi không xác định")
                task["status"] = "Thất bại"
                task["message"] = err_msg

                self.after(0, lambda i=item_id, m=err_msg: self._update_row_status(i, "Thất bại", "", m, "failed"))
                self.log(f"-> [THẤT BẠI] Tài khoản {acc}: {err_msg}")

                if "số dư" in err_msg.lower() or "không đủ" in err_msg.lower():
                    self.after(0, lambda: self.lbl_running_status.configure(
                        text="⚠️ Hết số dư ví! Bấm 'Quét QR' để nạp thêm và tiếp tục.",
                        text_color="#ff5252"
                    ))

            progress = (idx + 1) / total
            self.after(0, lambda p=progress: self.progress_bar.set(p))
            self.after(0, self.update_stats)

            if idx < total - 1 and not self.stop_requested:
                time.sleep(delay)

        self.after(0, self._on_batch_finished)

    def _update_row_status(self, item_id: str, status: str, order_code: str, message: str, tag: str):
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
        self.lbl_running_status.configure(text="Đã hoàn tất nạp danh sách!", text_color="#00e676")
        self.log("=== HOÀN TẤT TIẾN TRÌNH NẠP THẺ ===")
        self.refresh_user_info()
        self.load_recharge_history()
        messagebox.showinfo("Hoàn tất", "Đã hoàn tất tiến trình nạp thẻ cho danh sách tài khoản!")

    def export_results(self):
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
                f.write("STT,TaiKhoan,MayChu,GoiNap,QuyDoiNgoc,ThucTra,TrangThai,MaDon,ChiTiet\n")
                for t in self.task_list:
                    f.write(f'"{t["id"]}","{t["account"]}","{t["server_name"]}","{t["package"]}","{t["gems"]}","{t["price"]}","{t["status"]}","{t["order_code"]}","{t["message"]}"\n')
            messagebox.showinfo("Thành công", f"Đã xuất báo cáo ra:\n{file_path}")
            self.log(f"Đã xuất kết quả: {file_path}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không ghi được file: {e}")


if __name__ == "__main__":
    app = The24hAutoTopupApp()
    app.mainloop()
