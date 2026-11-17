from energy_monitor_app.db.store import Store
from energy_monitor_app.services.simulator import SimulatorService


class MonitorBackend:
    """供界面调用的后端门面；数据库连接不暴露给 UI。"""

    _API_METHODS = {
        "acknowledge_alert",
        "add_user",
        "audit",
        "authenticate",
        "ingest_json",
        "latest_aggregate",
        "latest_events",
        "list_alerts",
        "list_audit",
        "list_devices",
        "list_dlq",
        "list_metrics",
        "list_rules",
        "list_users",
        "process_event",
        "query_history",
        "reset_telemetry",
        "save_device",
        "save_rule",
        "set_device_enabled",
        "set_user_enabled",
        "stats",
        "toggle_rule",
    }

    def __init__(self, store=None):
        self._store = store or Store()
        self.simulator = SimulatorService(self._store)

    @property
    def database_path(self):
        return self._store.path

    def close(self):
        self._store.close()

    def __getattr__(self, name):
        if name not in self._API_METHODS:
            raise AttributeError(name)
        return getattr(self._store, name)
