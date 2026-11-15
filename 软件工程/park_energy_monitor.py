"""兼容入口；具体实现位于 energy_monitor_app 包中。"""

from energy_monitor_app.app.main import main
from energy_monitor_app.app.monitor_app import MonitorApp
from energy_monitor_app.config.constants import (
    OPERATOR_LABELS,
    OPERATOR_REVERSE,
    ROLE_LABELS,
    SEVERITY_LABELS,
)
from energy_monitor_app.core.security import hash_password, verify_password
from energy_monitor_app.core.time_utils import display_time, parse_iso, utc_iso, utc_now
from energy_monitor_app.db.store import DB_PATH, Store
from energy_monitor_app.ui.dialogs import (
    DeviceDialog,
    LoginDialog,
    RuleDialog,
    UserDialog,
)
from energy_monitor_app.ui.widgets import make_tree

__all__ = [
    "DB_PATH",
    "DeviceDialog",
    "LoginDialog",
    "MonitorApp",
    "OPERATOR_LABELS",
    "OPERATOR_REVERSE",
    "ROLE_LABELS",
    "RuleDialog",
    "SEVERITY_LABELS",
    "Store",
    "UserDialog",
    "display_time",
    "hash_password",
    "main",
    "make_tree",
    "parse_iso",
    "utc_iso",
    "utc_now",
    "verify_password",
]


if __name__ == "__main__":
    main()
