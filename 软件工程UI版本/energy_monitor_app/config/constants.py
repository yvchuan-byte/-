ROLE_LABELS = {
    "ADMIN": "系统管理员",
    "OPERATOR": "运维人员",
    "VIEWER": "只读用户",
}

SEVERITY_LABELS = {
    1: "紧急",
    2: "高",
    3: "中",
    4: "低",
}

OPERATOR_LABELS = {
    ">": "GT",
    ">=": "GE",
    "<": "LT",
    "<=": "LE",
    "区间": "BETWEEN",
}

OPERATOR_REVERSE = {v: k for k, v in OPERATOR_LABELS.items()}
