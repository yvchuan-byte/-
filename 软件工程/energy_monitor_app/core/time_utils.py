from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc)


def utc_iso(value=None):
    value = value or utc_now()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(value):
    dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(timezone.utc)


def display_time(value):
    if not value:
        return "-"
    try:
        return parse_iso(value).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)
