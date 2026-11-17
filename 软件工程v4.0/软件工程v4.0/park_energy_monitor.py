"""兼容旧版导入路径；实现集中在 desktop_app.py 和 monitor_service.py。"""

from desktop_app import DeviceDialog, LoginDialog, MonitorApp, RuleDialog, UserDialog, main, make_tree
from monitor_service import (
    DB_PATH,
    OPERATOR_LABELS,
    OPERATOR_REVERSE,
    ROLE_LABELS,
    SEVERITY_LABELS,
    Store,
    display_time,
    hash_password,
    parse_iso,
    utc_iso,
    utc_now,
    verify_password,
)

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
