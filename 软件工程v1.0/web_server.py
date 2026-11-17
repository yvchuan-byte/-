import json
import secrets
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent


class APIError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class RequestHandler(BaseHTTPRequestHandler):
    sessions = {}
    store = None

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def _send(self, status, body, content_type="application/json; charset=utf-8",
              headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, data, headers=None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send(status, body, headers=headers)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise APIError("请求长度无效") from exc
        if length < 0 or length > 1024 * 1024:
            raise APIError("请求内容过大", 413)
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise APIError("请求必须是有效的 JSON") from exc
        if not isinstance(value, dict):
            raise APIError("请求内容必须是 JSON 对象")
        return value

    def _session(self):
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        morsel = cookie.get("v1_session")
        user = self.sessions.get(morsel.value) if morsel else None
        if not user:
            raise APIError("请先登录", 401)
        return user

    @staticmethod
    def _require_operator(user):
        if user["role_code"] not in ("ADMIN", "OPERATOR"):
            raise APIError("只读账号不能修改设备", 403)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            try:
                body = (ROOT / "index.html").read_bytes()
            except OSError as exc:
                self._json(500, {"error": "无法读取原型页面：%s" % exc})
                return
            self._send(200, body, "text/html; charset=utf-8")
            return
        if parsed.path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
            return
        if parsed.path == "/api/me":
            cookie = SimpleCookie()
            cookie.load(self.headers.get("Cookie", ""))
            morsel = cookie.get("v1_session")
            user = self.sessions.get(morsel.value) if morsel else None
            self._json(200, {"user": user})
            return
        if parsed.path != "/api/data":
            self._json(404, {"error": "接口不存在"})
            return
        try:
            self._session()
            view = parse_qs(parsed.query).get("view", ["devices"])[0]
            if view != "devices":
                raise APIError("v1.0 仅提供设备和指标页面", 404)
            self._json(
                200,
                {"devices": self.store.list_devices(), "metrics": self.store.list_metrics()},
            )
        except APIError as exc:
            self._json(exc.status, {"error": str(exc)})
        except Exception as exc:
            print("GET API error:", repr(exc))
            self._json(500, {"error": "读取数据失败：%s" % exc})

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
            if parsed.path == "/api/login":
                user = self.store.authenticate(
                    str(payload.get("username", "")),
                    str(payload.get("password", "")),
                )
                if not user:
                    raise APIError("用户名或密码错误，或用户已停用", 401)
                token = secrets.token_urlsafe(32)
                self.sessions[token] = user
                self._json(
                    200,
                    {"user": user},
                    headers={
                        "Set-Cookie": (
                            "v1_session=%s; HttpOnly; SameSite=Strict; Path=/"
                        ) % token
                    },
                )
                return
            if parsed.path == "/api/logout":
                cookie = SimpleCookie()
                cookie.load(self.headers.get("Cookie", ""))
                morsel = cookie.get("v1_session")
                if morsel:
                    self.sessions.pop(morsel.value, None)
                self._json(
                    200,
                    {"ok": True},
                    headers={
                        "Set-Cookie": (
                            "v1_session=; HttpOnly; SameSite=Strict; "
                            "Path=/; Max-Age=0"
                        )
                    },
                )
                return

            user = self._session()
            self._require_operator(user)
            if parsed.path == "/api/device":
                self.store.save_device(payload)
            elif parsed.path == "/api/device/toggle":
                self.store.set_device_enabled(
                    str(payload.get("device_code", "")),
                    bool(payload.get("enabled")),
                )
            else:
                raise APIError("接口不存在", 404)
            self._json(200, {"ok": True})
        except APIError as exc:
            self._json(exc.status, {"error": str(exc)})
        except (TypeError, ValueError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            print("POST API error:", repr(exc))
            self._json(500, {"error": "操作失败：%s" % exc})
