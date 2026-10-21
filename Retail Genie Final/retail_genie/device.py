"""Small request-device helpers used only for presentation decisions."""

import re

_MOBILE_PHONE = re.compile(r"(?:iphone|ipod|windows phone|iemobile|blackberry|bb10)", re.IGNORECASE)


def is_mobile_phone(user_agent: str | None, mobile_hint: str | None = None) -> bool:
    """Identify phones, while leaving tablet and desktop user agents eligible."""
    if (mobile_hint or "").strip() == "?1":
        return True
    value = user_agent or ""
    lowered = value.lower()
    return bool(_MOBILE_PHONE.search(value)) or ("android" in lowered and "mobile" in lowered)
