"""Limited demo redaction. Not a general PII or secret detection service."""

import json
import re

SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "access_token",
    "refresh_token",
    "email",
    "phone",
    "phone_number",
}
SAFE_FIELDS = {
    "supplier",
    "unit_price_cents",
    "quantity",
    "total_cents",
    "budget_cents",
    "delivery_days",
    "warranty_months",
    "draft_id",
    "status",
    "quotes",
}
PATTERNS = (
    r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{16,}",
    r"(?i)\bBearer\s+[^\s\"']+",
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    r"(?<!\w)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\w)",
)


def redact(value):
    if isinstance(value, dict):
        return {
            str(k): "[REDACTED]" if str(k).lower() in SENSITIVE_KEYS else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        for pattern in PATTERNS:
            value = re.sub(pattern, "[REDACTED]", value)
    return value


def trace_summary(value, limit=2000):
    def safe(item, permitted=False):
        if isinstance(item, dict):
            return {
                str(k): safe(v, True) if k in SAFE_FIELDS else "[REDACTED]"
                for k, v in item.items()
            }
        if isinstance(item, (list, tuple)):
            return [safe(v) for v in item]
        return (
            redact(item)
            if permitted or not isinstance(item, str)
            else "[REDACTED_TEXT]"
        )

    return json.dumps(safe(value), ensure_ascii=False, allow_nan=False)[:limit]
