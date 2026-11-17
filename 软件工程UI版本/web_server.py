import argparse
import json
import queue
import secrets
import sys
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from energy_monitor_app.services.monitor_backend import MonitorBackend


ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
MAX_BODY_SIZE = 5 * 1024 * 1024
backend = None
sessions = {}
simulator = {"running": False, "interval": 5, "last_cycle": 0.0, "error": ""}
simulator_event_queue = queue.Queue()
simulator_error_queue = queue.Queue()
simulator_stop_event = None
simulator_thread = None


class APIError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def json_bytes(data):
    return json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")


def _stop_simulator():
    global simulator_stop_event, simulator_thread
    if simulator_stop_event:
        simulator_stop_event.set()
    if simulator_thread and simulator_thread.is_alive():
        simulator_thread.join()
    simulator_stop_event = None
    simulator_thread = None
    simulator["running"] = False


def _start_simulator(interval):
    global simulator_error_queue, simulator_stop_event, simulator_thread
    profiles = backend.simulator.profiles()
    if not profiles:
        raise APIError("没有启用的设备可供模拟")

    _stop_simulator()
    simulator_error_queue = queue.Queue()
    simulator_stop_event = threading.Event()
    simulator.update(
        running=True,
        interval=interval,
        last_cycle=0.0,
        error="",
    )
    simulator_thread = threading.Thread(
        target=backend.simulator.produce,
        args=(
            simulator_stop_event,
            simulator_event_queue,
            interval,
            simulator_error_queue,
            profiles,
        ),
        daemon=True,
    )
    simulator_thread.start()


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "EnergyMonitorWeb/1.0"

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
        self._send(status, json_bytes(data), headers=headers)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise APIError("请求长度无效") from exc
        if length < 0 or length > MAX_BODY_SIZE:
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
        morsel = cookie.get("energy_session")
        user = sessions.get(morsel.value) if morsel else None
        if not user:
            raise APIError("登录已失效，请重新登录", 401)
        return user

    def _require_operator(self, user):
        if user["role_code"] not in ("ADMIN", "OPERATOR"):
            raise APIError("当前账号没有执行此操作的权限", 403)

    def _require_admin(self, user):
        if user["role_code"] != "ADMIN":
            raise APIError("此操作仅系统管理员可用", 403)

    def _pump_simulator(self):
        processed = False
        while True:
            try:
                event = simulator_event_queue.get_nowait()
            except queue.Empty:
                break
            try:
                backend.process_event(event)
                processed = True
            except Exception as exc:
                simulator["error"] = str(exc)
                _stop_simulator()
                break

        if processed:
            simulator["last_cycle"] = time.monotonic()

        try:
            error = simulator_error_queue.get_nowait()
        except queue.Empty:
            return
        if error:
            simulator["error"] = error
            _stop_simulator()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            try:
                body = INDEX.read_bytes()
            except OSError as exc:
                self._json(500, {"error": "无法读取界面文件：%s" % exc})
                return
            self._send(200, body, "text/html; charset=utf-8")
            return
        if parsed.path == "/api/me":
            try:
                user = self._session()
            except APIError:
                self._json(200, {"user": None})
                return
            self._json(200, {"user": user})
            return
        if parsed.path != "/api/data":
            self._json(404, {"error": "没有找到请求的接口"})
            return

        try:
            user = self._session()
            self._pump_simulator()
            query = parse_qs(parsed.query)
            view = query.get("view", ["dashboard"])[0]
            if view == "dashboard":
                devices = backend.list_devices()
                profiles = backend.simulator.profiles()
                device = query.get("device", [""])[0]
                metric = query.get("metric", [""])[0]
                if not device and profiles:
                    device = profiles[0]["device_code"]
                profile = next(
                    (item for item in profiles if item["device_code"] == device),
                    None,
                )
                available = [item["metric_code"] for item in profile["metrics"]] if profile else []
                if not metric and available:
                    metric = available[0]
                if metric not in available and available:
                    metric = available[0]
                chart_rows = backend.query_history(
                    device_code=device, metric_code=metric, limit=30
                ) if device and metric else []
                data = {
                    "stats": backend.stats(),
                    "devices": devices,
                    "profiles": profiles,
                    "metrics": available,
                    "device": device,
                    "metric": metric,
                    "chart": list(reversed(chart_rows)),
                    "events": backend.latest_events(30),
                    "simulator": dict(simulator),
                }
            elif view == "devices":
                data = {"devices": backend.list_devices(), "metrics": backend.list_metrics()}
            elif view == "history":
                data = {
                    "rows": backend.query_history(
                        device_code=query.get("device", [""])[0],
                        metric_code=query.get("metric", [""])[0],
                        start=query.get("start", [""])[0],
                        end=query.get("end", [""])[0],
                        limit=5000,
                    )
                }
            elif view == "alerts":
                data = {"alerts": backend.list_alerts(), "rules": backend.list_rules()}
            elif view == "quality":
                data = {
                    "dlq": backend.list_dlq(),
                    "audit": backend.list_audit(),
                    "database": backend.database_path,
                }
            elif view == "users":
                self._require_admin(user)
                data = {"users": backend.list_users()}
            else:
                raise APIError("未知页面")
            self._json(200, data)
        except APIError as exc:
            self._json(exc.status, {"error": str(exc)})
        except Exception as exc:
            print("API GET error:", repr(exc))
            self._json(500, {"error": "读取数据失败：%s" % exc})

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
            if parsed.path == "/api/login":
                user = backend.authenticate(
                    str(payload.get("username", "")),
                    str(payload.get("password", "")),
                )
                if not user:
                    raise APIError("用户名或密码错误，或用户已停用", 401)
                token = secrets.token_urlsafe(32)
                sessions[token] = user
                self._json(
                    200,
                    {"user": user},
                    headers={
                        "Set-Cookie": (
                            "energy_session=%s; HttpOnly; SameSite=Strict; "
                            "Path=/"
                        ) % token
                    },
                )
                return

            if parsed.path == "/api/logout":
                cookie = SimpleCookie()
                cookie.load(self.headers.get("Cookie", ""))
                morsel = cookie.get("energy_session")
                if morsel:
                    sessions.pop(morsel.value, None)
                self._json(
                    200,
                    {"ok": True},
                    headers={
                        "Set-Cookie": (
                            "energy_session=; HttpOnly; SameSite=Strict; "
                            "Path=/; Max-Age=0"
                        )
                    },
                )
                return

            user = self._session()
            actor = user["username"]
            if parsed.path == "/api/device":
                self._require_operator(user)
                backend.save_device(payload, actor)
            elif parsed.path == "/api/device/toggle":
                self._require_operator(user)
                backend.set_device_enabled(
                    str(payload.get("device_code", "")),
                    bool(payload.get("enabled")),
                    actor,
                )
            elif parsed.path == "/api/alert/ack":
                self._require_operator(user)
                ok, message = backend.acknowledge_alert(
                    str(payload.get("alert_id", "")), actor
                )
                if not ok:
                    raise APIError(message)
            elif parsed.path == "/api/rule":
                self._require_operator(user)
                backend.save_rule(payload.get("rule_id"), payload, actor)
            elif parsed.path == "/api/rule/toggle":
                self._require_operator(user)
                backend.toggle_rule(int(payload.get("rule_id", 0)), actor)
            elif parsed.path == "/api/user":
                self._require_admin(user)
                backend.add_user(
                    str(payload.get("username", "")),
                    str(payload.get("password", "")),
                    str(payload.get("display_name", "")),
                    str(payload.get("role_code", "")),
                    actor,
                )
            elif parsed.path == "/api/user/toggle":
                self._require_admin(user)
                username = str(payload.get("username", ""))
                if username == actor:
                    raise APIError("不能停用当前登录用户")
                backend.set_user_enabled(
                    username, bool(payload.get("enabled")), actor
                )
            elif parsed.path == "/api/simulator":
                self._require_operator(user)
                action = payload.get("action")
                if action == "start":
                    interval = int(payload.get("interval", 5))
                    if not 1 <= interval <= 60:
                        raise APIError("采集间隔须为 1–60 秒")
                    _start_simulator(interval)
                elif action == "stop":
                    _stop_simulator()
                elif action == "cycle":
                    profiles = backend.simulator.profiles()
                    if not profiles:
                        raise APIError("没有启用的设备可供模拟")
                    count = 0
                    for event in backend.simulator.generate_cycle(profiles):
                        backend.process_event(event)
                        count += 1
                else:
                    raise APIError("未知的模拟器操作")
            elif parsed.path == "/api/import":
                self._require_operator(user)
                content = payload.get("content", "")
                if not isinstance(content, str):
                    raise APIError("文件内容必须是文本")
                results = {"ok": 0, "duplicate": 0, "invalid": 0}
                for line in content.splitlines():
                    if not line.strip():
                        continue
                    status = backend.ingest_json(line)["status"]
                    results[
                        {"OK": "ok", "DUPLICATE": "duplicate"}.get(status, "invalid")
                    ] += 1
                data = results
            elif parsed.path == "/api/reset":
                self._require_admin(user)
                backend.reset_telemetry(actor)
            else:
                raise APIError("没有找到请求的接口", 404)

            if parsed.path == "/api/simulator" and payload.get("action") == "cycle":
                self._json(200, {"ok": True, "count": count})
            elif parsed.path == "/api/import":
                self._json(200, {"ok": True, "results": data})
            else:
                self._json(200, {"ok": True, "simulator": dict(simulator)})
        except APIError as exc:
            self._json(exc.status, {"error": str(exc)})
        except (TypeError, ValueError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            print("API POST error:", repr(exc))
            self._json(500, {"error": "操作失败：%s" % exc})


def main():
    parser = argparse.ArgumentParser(description="智慧园区 Layui 桌面监测系统")
    parser.add_argument("--port", type=int, default=0, help="本地服务端口，默认自动分配")
    args = parser.parse_args()

    try:
        from PyQt5.QtCore import QUrl
        from PyQt5.QtWidgets import QApplication, QMainWindow
        from PyQt5.QtWebEngineWidgets import QWebEngineView
    except ImportError as exc:
        raise SystemExit(
            "桌面界面组件未安装，请运行：python -m pip install -r requirements.txt"
        ) from exc

    server = HTTPServer(("127.0.0.1", args.port), RequestHandler)
    address = "http://127.0.0.1:%s" % server.server_port

    def serve():
        global backend
        backend = MonitorBackend()
        try:
            server.serve_forever()
        finally:
            _stop_simulator()
            backend.close()

    server_thread = threading.Thread(target=serve, daemon=True)
    server_thread.start()

    app = QApplication([sys.argv[0]])
    window = QMainWindow()
    window.setWindowTitle("智慧园区实时能耗与环境监测系统")
    window.resize(1440, 900)
    window.setMinimumSize(980, 680)
    view = QWebEngineView(window)
    view.setUrl(QUrl(address))
    window.setCentralWidget(view)
    window.show()
    print("智慧园区实时能耗与环境监测系统已启动")
    try:
        return app.exec_()
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join()


if __name__ == "__main__":
    main()
