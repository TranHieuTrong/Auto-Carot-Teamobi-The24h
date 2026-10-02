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
