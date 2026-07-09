from __future__ import annotations

from datetime import datetime, timedelta, timezone

from config import MAX_EXPIRY_DAYS, MIN_EXPIRY_MINUTES

EXPIRY_UNITS = ("minutes", "hours", "days")

UNIT_LABELS = {
    "minutes": "Minutes",
    "hours": "Hours",
    "days": "Days",
}


class ExpiryError(ValueError):
    pass


def expiry_limits(unit: str) -> tuple[int, int]:
    if unit == "minutes":
        return MIN_EXPIRY_MINUTES, MAX_EXPIRY_DAYS * 24 * 60
    if unit == "hours":
        return 1, MAX_EXPIRY_DAYS * 24
    if unit == "days":
        return 1, MAX_EXPIRY_DAYS
    raise ExpiryError(f"Unknown expiry unit: {unit}")


def normalize_unit(unit: str) -> str:
    raw = (unit or "days").strip().lower()
    if raw.endswith("s"):
        raw = raw[:-1]
    if raw == "minute":
        return "minutes"
    if raw == "hour":
        return "hours"
    if raw == "day":
        return "days"
    if raw in EXPIRY_UNITS:
        return raw
    raise ExpiryError("Expiry unit must be minutes, hours, or days.")


def expiry_to_timedelta(value: int, unit: str) -> timedelta:
    unit = normalize_unit(unit)
    if unit == "minutes":
        return timedelta(minutes=value)
    if unit == "hours":
        return timedelta(hours=value)
    return timedelta(days=value)


def validate_expiry(value: int, unit: str) -> timedelta:
    unit = normalize_unit(unit)
    minimum, maximum = expiry_limits(unit)
    if value < minimum or value > maximum:
        unit_label = UNIT_LABELS[unit].lower()
        raise ExpiryError(
            f"Expiry must be between {minimum} and {maximum} {unit_label}."
        )
    return expiry_to_timedelta(value, unit)


def parse_expiry_form(form, *, prefix: str = "expiry") -> timedelta:
    value_key = f"{prefix}_value" if prefix else "value"
    unit_key = f"{prefix}_unit" if prefix else "unit"

    legacy_days = form.get("expiry_days") or form.get("default_expiry_days")
    raw_value = form.get(value_key)
    raw_unit = form.get(unit_key)

    if raw_value is None or not str(raw_value).strip():
        if legacy_days is not None and str(legacy_days).strip():
            try:
                return validate_expiry(int(legacy_days), "days")
            except ValueError as exc:
                raise ExpiryError("Enter a valid expiry number.") from exc
        raise ExpiryError("Enter how long the share link should stay active.")

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ExpiryError("Enter a valid expiry number.") from exc

    return validate_expiry(value, raw_unit or "days")


def format_duration(value: int, unit: str) -> str:
    unit = normalize_unit(unit)
    label = UNIT_LABELS[unit].lower()
    if value == 1:
        label = label[:-1]
    return f"{value} {label}"


def format_expiry_duration(expires_at: datetime, *, now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    delta = expires_at - current.astimezone(timezone.utc)
    total_seconds = int(delta.total_seconds())
    if total_seconds <= 0:
        return "Expired"

    total_minutes = total_seconds // 60
    if total_minutes < 60:
        return f"{total_minutes} minute{'s' if total_minutes != 1 else ''} left"

    total_hours = total_minutes // 60
    if total_hours < 24:
        minutes = total_minutes % 60
        if minutes:
            return f"{total_hours} hour{'s' if total_hours != 1 else ''} {minutes}m left"
        return f"{total_hours} hour{'s' if total_hours != 1 else ''} left"

    days = delta.days
    hours = (total_minutes % (24 * 60)) // 60
    if hours:
        return f"{days} day{'s' if days != 1 else ''} {hours}h left"
    return f"{days} day{'s' if days != 1 else ''} left"
