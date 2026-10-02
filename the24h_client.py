import re
import json
import hashlib
import time
import urllib.parse

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request
    import http.cookiejar


class The24hWebClient:
    """Client tương tác với giao diện the24h.vn qua Session Cookie"""
    def __init__(self):
        self.logged_in = False
        self.user_name = ""
        self.balance = ""

        if HAS_REQUESTS:
            self.session = requests.Session()
            self.session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            })
        else:
            self.cookie_jar = http.cookiejar.CookieJar()
            self.opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(self.cookie_jar)
            )

    def _request(self, method: str, url: str, data: dict = None, headers: dict = None, allow_redirects: bool = True):
        default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        if headers:
            default_headers.update(headers)

        if HAS_REQUESTS:
            if method.upper() == "GET":
                res = self.session.get(url, headers=default_headers, allow_redirects=allow_redirects, timeout=20)
            else:
                res = self.session.post(url, data=data, headers=default_headers, allow_redirects=allow_redirects, timeout=20)
            return {
                "status_code": res.status_code,
                "text": res.text,
                "headers": res.headers,
                "url": res.url
            }
        else:
            req_data = urllib.parse.urlencode(data).encode('utf-8') if data else None
            req = urllib.request.Request(url, data=req_data, headers=default_headers, method=method.upper())
            try:
                with self.opener.open(req, timeout=20) as resp:
                    return {
                        "status_code": resp.getcode(),
                        "text": resp.read().decode('utf-8', errors='ignore'),
                        "headers": dict(resp.headers),
                        "url": resp.geturl()
                    }
            except urllib.error.HTTPError as e:
                return {
                    "status_code": e.code,
                    "text": e.read().decode('utf-8', errors='ignore'),
                    "headers": dict(e.headers),
                    "url": e.geturl()
                }

    def get_csrf_token(self, url: str) -> str:
        res = self._request("GET", url)
        text = res["text"]
        m = re.search(r'name="_token"\s+value="([^"]+)"', text)
        if not m:
            m = re.search(r'<meta name="csrf-token"\s+content="([^"]+)"', text)
        if not m:
            m = re.search(r'content="([^"]+)"\s+name="csrf-token"', text)
        return m.group(1) if m else ""

    def login(self, username: str, password: str) -> dict:
        """Đăng nhập the24h.vn"""
        try:
            login_url = "https://the24h.vn/account/login"
            csrf = self.get_csrf_token(login_url)
            if not csrf:
                return {"success": False, "message": "Không lấy được CSRF token từ trang đăng nhập"}

            payload = {
                "_token": csrf,
                "phoneOrEmail": username,
                "password": password,
                "recaptcha_token": ""
            }

            headers = {
                "Origin": "https://the24h.vn",
                "Referer": login_url
            }

            res = self._request("POST", login_url, data=payload, headers=headers, allow_redirects=False)

            loc = res["headers"].get("Location", "") or res["headers"].get("location", "")
            if res["status_code"] in [301, 302] and ("the24h.vn" in loc or loc == "/" or "dashboard" in loc):
                self.logged_in = True
                self.update_user_info()
                return {"success": True, "message": "Đăng nhập thành công", "user": self.user_name, "balance": self.balance}
            else:
                err_match = re.search(r'<div[^>]*class="[^"]*alert-danger[^"]*"[^>]*>([\s\S]*?)</div>', res["text"])
                err_msg = re.sub(r'<[^>]+>', ' ', err_match.group(1)).strip() if err_match else "Sai tài khoản hoặc mật khẩu"
                return {"success": False, "message": err_msg}
        except Exception as e:
            return {"success": False, "message": f"Lỗi kết nối khi đăng nhập: {str(e)}"}

    def update_user_info(self) -> dict:
        """Cập nhật tên tài khoản và số dư ví VND"""
        try:
            res = self._request("GET", "https://the24h.vn")
            text = res["text"]
            bal_match = re.search(r'Số dư quỹ:\s*<b>([^<]+)</b>', text)
            if not bal_match:
                bal_match = re.search(r'Số dư quỹ:\s*<strong>([^<]+)</strong>', text)
            if not bal_match:
                bal_match = re.search(r'Số dư quỹ:\s*([0-9.,]+đ?)', text)
            if bal_match:
                self.balance = bal_match.group(1).strip()
            
            name_match = re.search(r'<span[^>]*class="[^"]*user-name[^"]*"[^>]*>([^<]+)</span>', text)
            if not name_match:
                name_match = re.search(r'<i class="fas fa-user[^"]*"></i>\s*([^<\n]+)', text)
            if name_match:
                self.user_name = name_match.group(1).strip()

            return {"user": self.user_name, "balance": self.balance}
        except Exception:
            return {"user": self.user_name, "balance": self.balance}

    def fetch_live_game_info(self, game_key: str) -> dict:
        """Lấy danh sách máy chủ và gói nạp trực tiếp từ web/API the24h.vn theo thời gian thực"""
        try:
            page_url = f"https://the24h.vn/recharge/nap-carot/{game_key}"
            res = self._request("GET", page_url)
            html = res["text"]

            # Parse items / gói nạp
            items = []
            items_match = re.search(r'<select[^>]*name="item"[^>]*>([\s\S]*?)</select>', html, re.I)
            if items_match:
                opt_matches = re.finditer(r'<option\s+[^>]*value="(\d+)"[^>]*>([\s\S]*?)</option>', items_match.group(1), re.I)
                for m in opt_matches:
                    opt_tag = m.group(0)
                    val = m.group(1)
                    label = re.sub(r'<[^>]+>', '', m.group(2)).strip()
                    disc_m = re.search(r'discount="([^"]+)"', opt_tag)
                    price_m = re.search(r'price="([^"]+)"', opt_tag)
                    items.append({
                        "id": val,
                        "discount": disc_m.group(1) if disc_m else "0",
                        "price": price_m.group(1) if price_m else "0",
                        "label": label
                    })

            # Parse servers / máy chủ
            servers = []
            servers_match = re.search(r'<select[^>]*name="account\[server\]"[^>]*>([\s\S]*?)</select>', html, re.I)
            if servers_match:
                s_matches = re.finditer(r'<option\s+[^>]*value="([^"]+)"[^>]*>([\s\S]*?)</option>', servers_match.group(1), re.I)
                for m in s_matches:
                    val = m.group(1)
                    name = re.sub(r'<[^>]+>', '', m.group(2)).strip()
                    if val:
                        servers.append({"id": val, "name": name})

            return {"success": True, "items": items, "servers": servers}
        except Exception as e:
            return {"success": False, "message": str(e), "items": [], "servers": []}

    @staticmethod
    def _decode_cf_email(html_snippet: str) -> str:
        """Giải mã email bị Cloudflare mã hóa qua data-cfemail"""
        def _repl(m):
            try:
                hex_str = m.group(1)
                k = int(hex_str[:2], 16)
                return "".join([chr(int(hex_str[i:i+2], 16) ^ k) for i in range(2, len(hex_str), 2)])
            except Exception:
                return ""
        # Thay thế các thẻ chứa data-cfemail
        return re.sub(r'<[^>]*data-cfemail=["\']([0-9a-fA-F]+)["\'][^>]*>[\s\S]*?</[^>]+>', _repl, html_snippet)

    def _fetch_recharge_history_page(self, page: int = 1) -> list:
        """Tải dữ liệu 1 trang lịch sử nạp cụ thể từ the24h.vn"""
        try:
            url = f"https://the24h.vn/history/recharge?page={page}"
            res = self._request("GET", url)
            html = res["text"]
            table_match = re.search(r'<table[^>]*>([\s\S]*?)</table>', html, re.I)
            if not table_match:
                return []
            
            rows = re.findall(r'<tr[^>]*>([\s\S]*?)</tr>', table_match.group(1), re.I)
            history = []
            for r in rows:
                cols = re.findall(r'<td[^>]*>([\s\S]*?)</td>', r, re.I)
                if len(cols) >= 8:
                    clean = []
                    for c in cols:
                        c_decoded = self._decode_cf_email(c)
                        c_clean = re.sub(r'<[^>]+>', ' ', c_decoded).strip()
                        clean.append(c_clean)

                    acc_info = re.sub(r'\s+', ' ', clean[2]).strip()
                    parts = acc_info.split(None, 1)
                    server_id = parts[0] if len(parts) >= 2 else ""
                    game_username = parts[1] if len(parts) >= 2 else acc_info

                    history.append({
                        "order_code": clean[0],
                        "service": clean[1],
                        "account_info": acc_info,
                        "server_id": server_id,
                        "game_username": game_username,
                        "amount": clean[3],
                        "charged": clean[4],
                        "status": clean[5],
                        "pay_amount": clean[6],
                        "created_at": clean[7]
                    })
            return history
        except Exception:
            return []

    def get_recharge_history(self, page: int = 0, progress_callback=None) -> list:
        """
        Lấy danh sách lịch sử nạp topup trực tiếp từ the24h.vn
        Nếu page == 0: Tự động tải TẤT CẢ các trang (toàn bộ lịch sử giao dịch từ trước tới nay)
        Nếu page > 0: Tải 1 trang cụ thể được chỉ định
        """
        if page > 0:
            return self._fetch_recharge_history_page(page)

        all_history = []
        seen_order_codes = set()
        p = 1
        max_pages = 100  # Giới hạn an toàn tối đa 100 trang

        while p <= max_pages:
            items = self._fetch_recharge_history_page(p)
            if not items:
                break

            new_items = []
            for it in items:
                code = it.get("order_code", "")
                if code and code in seen_order_codes:
                    continue
                if code:
                    seen_order_codes.add(code)
                new_items.append(it)

            if not new_items:
                break

            all_history.extend(new_items)
            if progress_callback:
                try:
                    progress_callback(p, len(all_history))
                except Exception:
                    pass

            if len(items) < 20:
                # Trang cuối cùng (the24h mặc định 20 dòng/trang)
                break

            p += 1

        return all_history

    def recharge_account(self, game_key: str, item_id: str, server_id: str, game_account: str, qty: int = 1, mkc2: str = "") -> dict:
        """
        Nạp tiền vào tài khoản game
        """
        try:
            page_url = f"https://the24h.vn/recharge/nap-carot/{game_key}"
            csrf = self.get_csrf_token(page_url)
            if not csrf:
                return {"success": False, "message": "Không lấy được CSRF token từ trang nạp"}

            recharge_payload = {
                "_token": csrf,
                "key": game_key,
                "item": item_id,
                "account[server]": server_id,
                "account[username]": game_account,
                "qty": str(qty),
                "paygate_code": "Wallet_VND"
            }

            headers = {
                "Origin": "https://the24h.vn",
                "Referer": page_url
            }

            res = self._request("POST", "https://the24h.vn/recharge", data=recharge_payload, headers=headers, allow_redirects=False)

            redirect_url = res["headers"].get("Location", "") or res["headers"].get("location", "")
            if not redirect_url:
                err_match = re.search(r'<div[^>]*class="[^"]*alert-danger[^"]*"[^>]*>([\s\S]*?)</div>', res["text"])
                err_msg = re.sub(r'<[^>]+>', ' ', err_match.group(1)).strip() if err_match else "Không tạo được đơn nạp"
                return {"success": False, "message": err_msg}

            order_match = re.search(r'/order/([A-Za-z0-9]+)', redirect_url)
            if not order_match:
                redir_page = self._request("GET", redirect_url)
                err_match = re.search(r'<div[^>]*class="[^"]*alert-danger[^"]*"[^>]*>([\s\S]*?)</div>', redir_page["text"])
                err_msg = re.sub(r'<[^>]+>', ' ', err_match.group(1)).strip() if err_match else f"Lỗi tạo đơn: {redirect_url}"
                return {"success": False, "message": err_msg}

            order_code = order_match.group(1)
            order_url = redirect_url if redirect_url.startswith("http") else f"https://the24h.vn{redirect_url}"

            order_res = self._request("GET", order_url)
            order_html = order_res["text"]

            order_token_match = re.search(r'action="https://the24h\.vn/wallet/pay"[\s\S]*?name="_token"\s+value="([^"]+)"', order_html)
            if not order_token_match:
                order_token_match = re.search(r'name="_token"\s+value="([^"]+)"', order_html)
            order_sign_match = re.search(r'name="order_sign"\s+value="([^"]+)"', order_html)

            order_token = order_token_match.group(1) if order_token_match else csrf
            order_sign = order_sign_match.group(1) if order_sign_match else ""

            if not mkc2:
                return {
                    "success": True,
                    "order_code": order_code,
                    "status": "pending_payment",
                    "message": f"Tạo đơn {order_code} thành công (Chưa thanh toán - Cần MKC2)"
                }

            pay_payload = {
                "_token": order_token,
                "action": "doPayment",
                "order_code": order_code,
                "order_sign": order_sign,
                "secret": mkc2
            }

            pay_headers = {
                "Origin": "https://the24h.vn",
                "Referer": order_url
            }

            pay_res = self._request("POST", "https://the24h.vn/wallet/pay", data=pay_payload, headers=pay_headers, allow_redirects=True)
            pay_html = pay_res["text"]

            if "Giao dịch thành công" in pay_html or "thành công" in pay_html.lower() or "Đã thanh toán" in pay_html:
                self.update_user_info()
                return {
                    "success": True,
                    "order_code": order_code,
                    "status": "completed",
                    "message": f"Nạp thành công! Mã đơn: {order_code}"
                }

            alert_match = re.search(r'<div[^>]*class="[^"]*alert-danger[^"]*"[^>]*>([\s\S]*?)</div>', pay_html)
            if alert_match:
                err_text = re.sub(r'<[^>]+>', ' ', alert_match.group(1)).strip()
                return {
                    "success": False,
                    "order_code": order_code,
                    "status": "pay_failed",
                    "message": f"Lỗi thanh toán: {err_text}"
                }

            status_match = re.search(r'TT hóa đơn:\s*([^<\n]+)', pay_html)
            order_status = status_match.group(1).strip() if status_match else "Đã xử lý"

            self.update_user_info()
            return {
                "success": True,
                "order_code": order_code,
                "status": order_status,
                "message": f"Đã gửi đơn {order_code}: {order_status}"
            }
        except Exception as e:
            return {"success": False, "message": f"Lỗi: {str(e)}"}

    def get_deposit_info(self, amount: int = 0) -> dict:
        """
        Lấy thông tin nạp quỹ VND bằng cách tạo đơn nạp trực tiếp trên the24h.vn
        để lấy chính xác: Ngân hàng, Số tài khoản (hoặc VA BIDV), Chủ tài khoản, Cú pháp nạp tự động
        """
        try:
            amt = max(10000, int(amount)) if amount > 0 else 50000
            deposit_url = "https://the24h.vn/wallet/deposit/vnd"
            res = self._request("GET", deposit_url)
            html = res.get("text", "")

            # 1. Trích xuất CSRF, Wallet ID, Paygate từ form /wallet/deposit/vnd
            csrf_m = re.search(r'name="_token"\s+value="([^"]+)"', html)
            if not csrf_m:
                csrf_m = re.search(r'<meta name="csrf-token"\s+content="([^"]+)"', html)
            csrf = csrf_m.group(1) if csrf_m else ""

            wallet_m = re.search(r'name="wallet"\s+(?:type="hidden"\s+)?value="([^"]+)"', html)
            if not wallet_m:
                wallet_m = re.search(r'value="([^"]+)"\s+name="wallet"', html)
            wallet = wallet_m.group(1) if wallet_m else ""

            paygate = "Localbank_BIDV"
            pg_match = re.search(r'<option[^>]*value="([^"]*(?:bidv|local|bank)[^"]*)"', html, re.I)
            if pg_match:
                paygate = pg_match.group(1)

            form_action_m = re.search(r'<form[^>]*action="([^"]*deposit/post[^"]*)"', html, re.I)
            post_url = form_action_m.group(1) if form_action_m else "https://the24h.vn/wallet/deposit/post"
            if not post_url.startswith("http"):
                post_url = "https://the24h.vn" + (post_url if post_url.startswith("/") else f"/{post_url}")

            order_html = ""
            order_url = ""
            if csrf and wallet:
                post_data = {
                    "_token": csrf,
                    "net_amount": str(amt),
                    "wallet": wallet,
                    "paygate_code": paygate
                }
                order_res = self._request(
                    "POST",
                    post_url,
                    data=post_data,
                    headers={"Referer": deposit_url},
                    allow_redirects=True
                )
                order_html = order_res.get("text", "")
                order_url = order_res.get("url", "")

            target_html = order_html if order_html else html

            # 2. Trích xuất Số tài khoản (hỗ trợ cả chữ và số cho BIDV Virtual Account như 963IOTBKH0055800451)
            account_no = ""
            stk_match = re.search(r'Số tài khoản:?</td>\s*<td[^>]*>([\s\S]*?)</td>', target_html, re.I)
            if stk_match:
                account_no = re.sub(r'<[^>]+>', ' ', stk_match.group(1)).strip()
            if not account_no:
                clip_stk = re.search(r'class="[^"]*copyaccnum[^"]*"[^>]*data-clipboard-text="([^"]+)"', target_html, re.I)
                if clip_stk:
                    account_no = clip_stk.group(1).strip()
            if not account_no:
                clip_stk2 = re.search(r'data-clipboard-text="([A-Za-z0-9]{8,25})"', target_html)
                if clip_stk2:
                    account_no = clip_stk2.group(1).strip()
            if not account_no:
                stk_match2 = re.search(r'(?:Số tài khoản|STK|Account Number|Số TK)[:\s]*<[^>]*>([A-Za-z0-9\s]+)<', target_html, re.I)
                if stk_match2:
                    account_no = stk_match2.group(1).strip()
            account_no = re.sub(r'\s+', '', account_no)

            # 3. Trích xuất Tên chủ tài khoản
            account_name = ""
            holder_match = re.search(r'Tên tài khoản:?</td>\s*<td[^>]*>([\s\S]*?)</td>', target_html, re.I)
            if holder_match:
                account_name = re.sub(r'<[^>]+>', ' ', holder_match.group(1)).strip()
            if not account_name:
                holder_m2 = re.search(r'(?:Tên tài khoản|Chủ tài khoản|Người thụ hưởng)[:\s]*<[^>]*>([A-Z\s]{3,35})<', target_html, re.I)
                if holder_m2:
                    account_name = holder_m2.group(1).strip()
            if not account_name:
                account_name = "THE24H"

            # 4. Trích xuất Ngân hàng
            bank_name = "BIDV"
            bank_match = re.search(r'Ngân hàng:?</td>\s*<td[^>]*>([\s\S]*?)</td>', target_html, re.I)
            if bank_match:
                b_text = re.sub(r'<[^>]+>', ' ', bank_match.group(1)).strip()
                if "BIDV" in b_text.upper():
                    bank_name = "BIDV"
                elif "VIETCOMBANK" in b_text.upper() or "VCB" in b_text.upper():
                    bank_name = "Vietcombank"
                elif "MB" in b_text.upper():
                    bank_name = "MBBank"
                else:
                    bank_name = b_text
            else:
                if "BIDV" in target_html:
                    bank_name = "BIDV"

            # 5. Trích xuất Cú pháp / Nội dung nạp tiền
            syntax = ""
            syntax_match = re.search(r'Nội dung thanh toán:?</td>\s*<td[^>]*>([\s\S]*?)</td>', target_html, re.I)
            if syntax_match:
                syntax = re.sub(r'<[^>]+>', ' ', syntax_match.group(1)).strip()
            if not syntax:
                clip_mes = re.search(r'class="[^"]*copymes[^"]*"[^>]*data-clipboard-text="([^"]+)"', target_html, re.I)
                if clip_mes:
                    syntax = clip_mes.group(1).strip()
            if not syntax:
                uname = self.user_name or "THE24H"
                syntax = f"THE24H {uname}"

            # 6. Trích xuất số tiền thực ghi trên hóa đơn
            order_amt = amt
            clip_amt = re.search(r'class="[^"]*copyamount[^"]*"[^>]*data-clipboard-text="([^"]+)"', target_html, re.I)
            if clip_amt:
                try:
                    order_amt = int(float(clip_amt.group(1).strip()))
                except Exception:
                    order_amt = amt

            return {
                "success": bool(account_no),
                "bank_name": bank_name,
                "account_no": account_no,
                "account_name": account_name,
                "syntax": syntax,
                "amount": order_amt,
                "order_url": order_url,
                "direct_qr_url": ""
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Không lấy được thông tin nạp quỹ: {str(e)}",
                "bank_name": "BIDV",
                "account_no": "",
                "account_name": "THE24H",
                "syntax": f"THE24H {self.user_name or ''}".strip(),
                "amount": amount,
                "order_url": "",
                "direct_qr_url": ""
            }

    @staticmethod
    def generate_vietqr_url(bank_code: str, account_no: str, account_name: str, amount: int, memo: str) -> str:
        """Tạo link mã QR VietQR chuẩn ngân hàng 24/7 theo số tiền và nội dung"""
        import urllib.parse
        b = (bank_code or "bidv").lower().strip()
        bank_mapping = {
            "bidv": "bidv",
            "vietcombank": "vietcombank",
            "vcb": "vietcombank",
            "mbbank": "mb",
            "mb": "mb",
            "mb bank": "mb",
            "techcombank": "techcombank",
            "tcb": "techcombank",
            "vietinbank": "vietinbank",
            "icb": "vietinbank",
            "acb": "acb",
            "tpbank": "tpbank",
            "vpbank": "vpbank"
        }
        b_clean = bank_mapping.get(b, b)
        acc = re.sub(r'\s+', '', account_no.strip())
        amt = max(0, int(amount))
        q_memo = urllib.parse.quote(memo.strip())
        q_name = urllib.parse.quote(account_name.strip())
        return f"https://img.vietqr.io/image/{b_clean}-{acc}-compact2.png?amount={amt}&addInfo={q_memo}&accountName={q_name}"


class The24hPartnerApiClient:
    """Client gọi API chính thức the24h.vn"""
    API_URL = "https://the24h.vn/api/rechargews"

    def __init__(self, partner_id: str = "", partner_key: str = ""):
        self.partner_id = partner_id
        self.partner_key = partner_key

    def md5_hash(self, text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def _post_json(self, payload: dict) -> dict:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
        if HAS_REQUESTS:
            try:
                res = requests.post(self.API_URL, json=payload, headers=headers, timeout=25)
                return res.json()
            except Exception as e:
                return {"status": "error", "message": str(e)}
        else:
            req_body = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(self.API_URL, data=req_body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=25) as resp:
                    return json.loads(resp.read().decode('utf-8'))
            except Exception as e:
                return {"status": "error", "message": str(e)}

    def get_balance(self) -> dict:
        cmd = "getbalance"
        sign = self.md5_hash(self.partner_key + self.partner_id + cmd)
        return self._post_json({"partner_id": self.partner_id, "command": cmd, "sign": sign})

    def topup(self, service_code: str, amount: str, account_info: dict, request_id: str = None) -> dict:
        cmd = "topup"
        if not request_id:
            request_id = str(int(time.time() * 1000))
        sign = self.md5_hash(self.partner_key + self.partner_id + cmd + request_id)
        payload = {
            "partner_id": self.partner_id,
            "command": cmd,
            "request_id": request_id,
            "service_code": service_code,
            "amount": str(amount),
            "qty": "1",
            "account_info": account_info,
            "sign": sign
        }
        return self._post_json(payload)

    def get_status(self, order_code: str, request_id: str = None) -> dict:
        cmd = "getstatus"
        if not request_id:
            request_id = str(int(time.time() * 1000))
        sign = self.md5_hash(self.partner_key + self.partner_id + cmd + request_id)
        payload = {
            "partner_id": self.partner_id,
            "command": cmd,
            "request_id": request_id,
            "order_code": order_code,
            "sign": sign
        }
        return self._post_json(payload)
