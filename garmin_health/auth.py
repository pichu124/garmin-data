"""Mật khẩu web + cookie phiên — bắt buộc khi mở app qua tên miền (Caddy/HTTPS).

auth.json (trong thư mục dữ liệu, quyền 600): băm PBKDF2 của mật khẩu + khoá ký cookie.
Cookie = "<hạn epoch>.<HMAC-SHA256(khoá, hạn)>": server không lưu phiên; đổi mật khẩu
⇒ khoá mới ⇒ mọi phiên cũ (kể cả điện thoại bị mất) hết hiệu lực.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import deque

from .config import Paths, read_json, write_json

ITERATIONS = 600_000      # PBKDF2-SHA256 theo khuyến nghị OWASP; ~0,3 s/lần trên 1 OCPU
MIN_PASSWORD = 10
COOKIE = "gh_session"
SESSION_DAYS = 90
MAX_FAILURES = 10         # sai quá 10 lần trong 10 phút ⇒ khoá đăng nhập (mọi nguồn) tới hết cửa sổ
FAIL_WINDOW_S = 600


def hash_password(password: str, *, iterations: int = ITERATIONS, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, dk = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        got = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(got.hex(), dk)


def set_password(paths: Paths, password: str, *, iterations: int = ITERATIONS) -> None:
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"Mật khẩu cần ít nhất {MIN_PASSWORD} ký tự")
    write_json(paths.auth, {"password": hash_password(password, iterations=iterations), "secret": secrets.token_hex(32)})
    try:
        os.chmod(paths.auth, 0o600)
    except OSError:  # Windows: quyền kiểu POSIX không áp dụng
        pass


class Auth:
    def __init__(self, password_hash: str, secret: str):
        self.password_hash = password_hash
        self.key = bytes.fromhex(secret)
        self.lock = threading.Lock()
        self.failures: deque[float] = deque()

    @classmethod
    def load(cls, paths: Paths) -> Auth | None:
        """None nếu chưa đặt mật khẩu (dùng cục bộ như trước, không cần đăng nhập)."""
        data = read_json(paths.auth) or {}
        if not data.get("password") or not data.get("secret"):
            return None
        return cls(data["password"], data["secret"])

    def _sign(self, expires: int) -> str:
        return hmac.new(self.key, str(expires).encode(), hashlib.sha256).hexdigest()

    def make_cookie(self, now: float | None = None) -> str:
        expires = int(now if now is not None else time.time()) + SESSION_DAYS * 86400
        return f"{expires}.{self._sign(expires)}"

    def valid(self, value: str | None, now: float | None = None) -> bool:
        expires, _, sig = (value or "").partition(".")
        if not expires.isdigit() or not sig:
            return False
        if int(expires) <= (now if now is not None else time.time()):
            return False
        return hmac.compare_digest(sig, self._sign(int(expires)))

    def login(self, password: str, now: float | None = None) -> str:
        """"ok" | "bad" | "locked". Khoá giữ suốt lúc băm: dồn 100 yêu cầu cùng lúc
        thì chỉ 10 lần đầu được băm thử, phần còn lại trả "locked" ngay."""
        with self.lock:
            now = now if now is not None else time.monotonic()
            while self.failures and self.failures[0] <= now - FAIL_WINDOW_S:
                self.failures.popleft()
            if len(self.failures) >= MAX_FAILURES:
                return "locked"
            if check_password(password, self.password_hash):
                self.failures.clear()
                return "ok"
            self.failures.append(now)
            return "bad"


def cookie_value(header: str | None, name: str = COOKIE) -> str | None:
    for part in (header or "").split(";"):
        key, sep, value = part.strip().partition("=")
        if sep and key == name:
            return value
    return None
