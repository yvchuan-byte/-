import sqlite3

from energy_monitor_app.core.app_paths import app_directory
from energy_monitor_app.db.schema import SchemaMixin
from energy_monitor_app.services.user_service import UserServiceMixin
from energy_monitor_app.services.device_service import DeviceServiceMixin
from energy_monitor_app.services.telemetry_service import TelemetryServiceMixin
from energy_monitor_app.services.query_service import QueryServiceMixin

DB_PATH = app_directory() / "energy_monitor.db"


class Store(SchemaMixin, UserServiceMixin, DeviceServiceMixin, TelemetryServiceMixin, QueryServiceMixin):
    def __init__(self, path=DB_PATH):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._create_schema()
        self._seed_data()
