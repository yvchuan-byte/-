import csv
import json
import math
import os
import queue
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from energy_monitor_app.config.constants import OPERATOR_REVERSE, ROLE_LABELS, SEVERITY_LABELS
from energy_monitor_app.core.time_utils import display_time, utc_iso, utc_now
from energy_monitor_app.ui.dialogs import DeviceDialog, LoginDialog, RuleDialog, UserDialog
from energy_monitor_app.ui.widgets import make_tree


class SimulatorViewMixin:
    def run_demo(self):
        if self.sim_thread and self.sim_thread.is_alive():
            self.stop_simulator()

        base = utc_now().replace(microsecond=0) - timedelta(seconds=15)
        values = [96, 108, 115, 121]
        results = []
        for i, value in enumerate(values):
            event_time = utc_iso(base + timedelta(seconds=i * 5))
            payload = {
                "eventId": str(uuid.uuid4()),
                "deviceCode": "POWER-A-01",
                "metricCode": "power",
                "value": value,
                "unit": "kW",
                "eventTime": event_time,
            }
            results.append(self.backend.process_event(payload))

        self.backend.audit(
            self.user["username"], "DEMO_DATA_INJECTED", "Telemetry",
            "POWER-A-01", "注入 96、108、115、121 kW 四点样例",
        )
        self.refresh_all()

        alert_count = sum(
            len(result.get("alertIds", []))
            for result in results
            if result["status"] == "OK"
        )
        messagebox.showinfo(
            "演示数据已注入",
            "已向 POWER-A-01 注入 96、108、115、121 kW 四条数据。\n"
            f"本次新触发告警数：{alert_count}\n\n"
            "默认规则为功率 >100 kW 连续 3 次。\n"
            "若要确保分钟样本数恰好为 4，可先点击“清空实验数据”。",
            parent=self.root,
        )

    def inject_selected_sample(self):
        device_code = self.chart_device_var.get()
        metric_code = self.chart_metric_var.get()
        try:
            self.event_queue.put(
                self.backend.simulator.generate_event(device_code, metric_code)
            )
        except ValueError as exc:
            messagebox.showerror("采样失败", str(exc), parent=self.root)
            return
        self.status_var.set(f"已生成采样：{device_code} / {metric_code}")

    def start_simulator(self):
        if not self.can_operate:
            return
        if self.sim_thread and self.sim_thread.is_alive():
            return

        try:
            interval = max(1.0, min(60.0, float(self.interval_var.get())))
        except ValueError:
            messagebox.showerror("参数错误", "采集间隔必须是数字。", parent=self.root)
            return

        profiles = self.backend.simulator.profiles()
        if not profiles:
            messagebox.showwarning("模拟器", "没有启用的设备。", parent=self.root)
            return

        stop_event = threading.Event()
        self.sim_stop_event = stop_event

        self.sim_thread = threading.Thread(
            target=self.backend.simulator.produce,
            args=(
                stop_event,
                self.event_queue,
                interval,
                self.sim_error_queue,
                profiles,
            ),
            daemon=True,
        )
        self.sim_thread.start()
        self.sim_status_label.configure(text=f"模拟器：运行中（每 {interval:g} 秒）")
        self.status_var.set("模拟器已启动")
        self.backend.audit(
            self.user["username"], "SIMULATOR_STARTED", "Simulator", "",
            f"interval={interval}",
        )

    def stop_simulator(self, audit=True):
        if self.sim_stop_event:
            self.sim_stop_event.set()
        if self.sim_thread and self.sim_thread.is_alive():
            self.sim_thread.join(timeout=0.5)
        was_running = self.sim_thread is not None
        self.sim_thread = None
        self.sim_stop_event = None

        if hasattr(self, "sim_status_label"):
            self.sim_status_label.configure(text="模拟器：已停止")
        if audit and was_running and self.user:
            self.backend.audit(
                self.user["username"], "SIMULATOR_STOPPED", "Simulator", "", ""
            )

    def pump_queue(self):
        if not self.user:
            return
        try:
            error = self.sim_error_queue.get_nowait()
        except queue.Empty:
            error = None
        if error:
            self.stop_simulator(audit=False)
            self.sim_status_label.configure(text="模拟器：发生错误")
            self.status_var.set(f"模拟器错误：{error}")

        processed = 0
        while processed < 500:
            try:
                payload = self.event_queue.get_nowait()
            except queue.Empty:
                break
            try:
                result = self.backend.process_event(payload)
                if result["status"] == "INVALID":
                    self.status_var.set(f"接入异常：{result['message']}")
            except Exception as exc:
                self.status_var.set(f"数据处理失败：{exc}")
            processed += 1

        self.root.after(250, self.pump_queue)
