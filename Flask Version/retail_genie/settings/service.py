"""Business rules for company-scoped settings with full audit history."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import delete, select

from ..auth.tenant_context import current_tenant_container_id
from ..extensions import db
from ..models import (
    AuditEvent,
    AttendanceSetting,
    CommissionSetting,
    Company,
    GlobalDiscountSetting,
    TaxSetting,
    TenantContainer,
    User,
)


class SettingsRuleError(ValueError):
    def __init__(self, message: str, status_code: int = 400, code: str = "invalid_request"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _active_company(actor: User, company_id: str | None, tenant_container_id: str | None = None) -> Company:
    active_container = current_tenant_container_id(actor)
    requested_container = tenant_container_id or active_container
    if not requested_container or requested_container != active_container:
        raise SettingsRuleError("Select an active tenant container first.", 403, "tenant_forbidden")
    container = db.session.get(TenantContainer, requested_container)
    if container is None or not container.is_active:
        raise SettingsRuleError("Tenant container not found.", 404, "not_found")
    if actor.is_super_admin:
        company = db.session.get(Company, company_id) if company_id else None
    else:
        from ..auth.tenant_context import current_membership

        membership = current_membership(actor, tenant_container_id=requested_container)
        if membership is None or not membership.company_id or (company_id and company_id != membership.company_id):
            raise SettingsRuleError("Company not found.", 404, "not_found")
        company = db.session.get(Company, membership.company_id)
    if company is None or company.tenant_container_id != requested_container or not company.is_active:
        raise SettingsRuleError("Company not found.", 404, "not_found")
    return company


def _require_manage_settings(actor: User) -> None:
    if not actor.is_authenticated:
        raise SettingsRuleError("Sign in to manage settings.", 401, "authentication_required")
    if not actor.is_admin:
        raise SettingsRuleError("Only administrators can change settings.", 403, "permission_denied")


def _record(
    actor: User,
    company: Company,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict | None,
    after: dict,
) -> None:
    db.session.add(
        AuditEvent(
            tenant_container_id=company.tenant_container_id,
            company_id=company.id,
            actor_user_id=actor.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_data=before,
            after_data=after,
        )
    )


def _as_bool(value, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in {"true", "1", "yes", "on"}:
            return True
        if cleaned in {"false", "0", "no", "off", ""}:
            return False
    raise SettingsRuleError(f"{field} must be a boolean value.")


def _as_percentage(value, field: str) -> Decimal:
    try:
        rate = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise SettingsRuleError(f"{field} must be a number.") from None
    if rate < 0 or rate > 100:
        raise SettingsRuleError(f"{field} must be between 0 and 100.")
    return rate.quantize(Decimal("0.00000001"))


def _as_money(value, field: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise SettingsRuleError(f"{field} must be a number.") from None
    if amount < 0:
        raise SettingsRuleError(f"{field} cannot be negative.")
    return amount.quantize(Decimal("0.001"))


# ---------------------------------------------------------------- tax settings

def list_tax_settings(actor: User, company_id: str) -> list[TaxSetting]:
    company = _active_company(actor, company_id)
    return list(
        db.session.execute(
            select(TaxSetting)
            .where(TaxSetting.tenant_container_id == company.tenant_container_id, TaxSetting.company_id == company.id)
            .order_by(TaxSetting.name.asc())
        )
        .scalars()
    )


def update_tax_settings(actor: User, company_id: str, taxes: list[dict]) -> list[TaxSetting]:
    """Replace the company's tax table in one audited transaction."""
    _require_manage_settings(actor)
    company = _active_company(actor, company_id)
    if not isinstance(taxes, list) or len(taxes) > 20:
        raise SettingsRuleError("Provide up to 20 tax rates.")
    seen_names: set[str] = set()
    payload: list[dict] = []
    for raw in taxes:
        if not isinstance(raw, dict):
            raise SettingsRuleError("Each tax entry must be an object.")
        name = str(raw.get("name", "")).strip()
        if not name or len(name) > 120:
            raise SettingsRuleError("Each tax needs a name of 1-120 characters.")
        if name.casefold() in seen_names:
            raise SettingsRuleError(f"Duplicate tax name: {name}")
        seen_names.add(name.casefold())
        payload.append(
            {
                "name": name,
                "rate": _as_percentage(raw.get("rate"), "Tax rate"),
                "is_enabled": _as_bool(raw.get("is_enabled", True), "Tax enabled"),
            }
        )
    before = [
        {"name": tax.name, "rate": str(tax.rate), "is_enabled": tax.is_enabled}
        for tax in list_tax_settings(actor, company.id)
    ]
    db.session.execute(
        delete(TaxSetting).where(
            TaxSetting.tenant_container_id == company.tenant_container_id,
            TaxSetting.company_id == company.id,
        )
    )
    rows: list[TaxSetting] = []
    for entry in payload:
        tax = TaxSetting(
            tenant_container_id=company.tenant_container_id,
            company_id=company.id,
            name=entry["name"],
            rate=entry["rate"],
            is_enabled=entry["is_enabled"],
            created_by_id=actor.id,
        )
        db.session.add(tax)
        rows.append(tax)
    db.session.flush()
    after = [{"name": entry["name"], "rate": str(entry["rate"]), "is_enabled": entry["is_enabled"]} for entry in payload]
    _record(actor, company, action="settings.tax.updated", entity_type="TaxSetting", entity_id=company.id, before={"taxes": before}, after={"taxes": after})
    return rows


def effective_tax_settings(company: Company) -> list[TaxSetting]:
    return list(
        db.session.execute(
            select(TaxSetting)
            .where(
                TaxSetting.tenant_container_id == company.tenant_container_id,
                TaxSetting.company_id == company.id,
                TaxSetting.is_enabled.is_(True),
            )
            .order_by(TaxSetting.name.asc())
        )
        .scalars()
    )


# ---------------------------------------------------------- commission rules

def get_commission_setting(actor: User, company_id: str) -> CommissionSetting | None:
    company = _active_company(actor, company_id)
    return db.session.execute(
        select(CommissionSetting).where(
            CommissionSetting.tenant_container_id == company.tenant_container_id,
            CommissionSetting.company_id == company.id,
        )
    ).scalar_one_or_none()


def update_commission_settings(
    actor: User,
    company_id: str,
    *,
    sales_target,
    commission_interval: str,
    commission_percentage,
    is_active: bool,
) -> CommissionSetting:
    _require_manage_settings(actor)
    company = _active_company(actor, company_id)
    if commission_interval not in {"daily", "weekly", "monthly"}:
        raise SettingsRuleError("Commission interval must be daily, weekly, or monthly.")
    target = _as_money(sales_target, "Sales target")
    percentage = _as_percentage(commission_percentage, "Commission percentage")
    existing = get_commission_setting(actor, company.id)
    before = (
        {
            "sales_target": str(existing.sales_target),
            "commission_interval": existing.commission_interval,
            "commission_percentage": str(existing.commission_percentage),
            "is_active": existing.is_active,
        }
        if existing
        else None
    )
    if existing is None:
        setting = CommissionSetting(
            tenant_container_id=company.tenant_container_id,
            company_id=company.id,
            sales_target=target,
            commission_interval=commission_interval,
            commission_percentage=percentage,
            is_active=_as_bool(is_active, "Commission active"),
            created_by_id=actor.id,
        )
        db.session.add(setting)
        db.session.flush()
    else:
        existing.sales_target = target
        existing.commission_interval = commission_interval
        existing.commission_percentage = percentage
        existing.is_active = _as_bool(is_active, "Commission active")
        db.session.flush()
        setting = existing
    _record(
        actor,
        company,
        action="settings.commission.updated",
        entity_type="CommissionSetting",
        entity_id=setting.id,
        before=before,
        after={
            "sales_target": str(setting.sales_target),
            "commission_interval": setting.commission_interval,
            "commission_percentage": str(setting.commission_percentage),
            "is_active": setting.is_active,
        },
    )
    return setting


def effective_commission_setting(company: Company) -> CommissionSetting | None:
    setting = db.session.execute(
        select(CommissionSetting).where(
            CommissionSetting.tenant_container_id == company.tenant_container_id,
            CommissionSetting.company_id == company.id,
        )
    ).scalar_one_or_none()
    return setting if setting is not None and setting.is_active else None


def salesperson_commission(
    company: Company,
    gross_sales: Decimal,
    *,
    on: date | None = None,
) -> Decimal:
    """Commission accrues once interval sales meet the configured target."""
    setting = effective_commission_setting(company)
    if setting is None or gross_sales <= 0:
        return Decimal("0.000")
    if gross_sales < setting.sales_target:
        return Decimal("0.000")
    earned = (gross_sales * Decimal(str(setting.commission_percentage)) / Decimal("100")).quantize(Decimal("0.001"))
    return earned


# ------------------------------------------------------- global discount rule

def list_global_discounts(actor: User, company_id: str) -> list[GlobalDiscountSetting]:
    company = _active_company(actor, company_id)
    return list(
        db.session.execute(
            select(GlobalDiscountSetting)
            .where(
                GlobalDiscountSetting.tenant_container_id == company.tenant_container_id,
                GlobalDiscountSetting.company_id == company.id,
            )
            .order_by(GlobalDiscountSetting.created_at.desc())
        )
        .scalars()
    )


def update_global_discount_settings(
    actor: User,
    company_id: str,
    *,
    percentage,
    start_date: date | None,
    end_date: date | None,
    is_active: bool,
    description: str | None,
) -> GlobalDiscountSetting:
    _require_manage_settings(actor)
    company = _active_company(actor, company_id)
    rate = _as_percentage(percentage, "Global discount percentage")
    if start_date and end_date and end_date < start_date:
        raise SettingsRuleError("The end date cannot be before the start date.")
    existing = db.session.execute(
        select(GlobalDiscountSetting).where(
            GlobalDiscountSetting.tenant_container_id == company.tenant_container_id,
            GlobalDiscountSetting.company_id == company.id,
        )
    ).scalar_one_or_none()
    before = (
        {
            "percentage": str(existing.percentage),
            "start_date": existing.start_date.isoformat() if existing.start_date else None,
            "end_date": existing.end_date.isoformat() if existing.end_date else None,
            "is_active": existing.is_active,
            "description": existing.description,
        }
        if existing
        else None
    )
    if existing is None:
        setting = GlobalDiscountSetting(
            tenant_container_id=company.tenant_container_id,
            company_id=company.id,
            percentage=rate,
            start_date=start_date,
            end_date=end_date,
            is_active=_as_bool(is_active, "Global discount active"),
            description=(description or "").strip()[:500] or None,
            created_by_id=actor.id,
        )
        db.session.add(setting)
        db.session.flush()
    else:
        existing.percentage = rate
        existing.start_date = start_date
        existing.end_date = end_date
        existing.is_active = _as_bool(is_active, "Global discount active")
        existing.description = (description or "").strip()[:500] or None
        db.session.flush()
        setting = existing
    _record(
        actor,
        company,
        action="settings.global_discount.updated",
        entity_type="GlobalDiscountSetting",
        entity_id=setting.id,
        before=before,
        after={
            "percentage": str(setting.percentage),
            "start_date": setting.start_date.isoformat() if setting.start_date else None,
            "end_date": setting.end_date.isoformat() if setting.end_date else None,
            "is_active": setting.is_active,
            "description": setting.description,
        },
    )
    return setting


def company_today(company: Company) -> date:
    try:
        zone = ZoneInfo(company.timezone)
    except ZoneInfoNotFoundError:
        raise SettingsRuleError("The company timezone is not configured correctly.", 500, "invalid_company_timezone") from None
    return datetime.now(ZoneInfo("UTC")).astimezone(zone).date()


def effective_global_discount_percentage(company: Company, *, on: date | None = None) -> Decimal:
    """Return the active dated global discount, or zero when none applies."""
    setting = db.session.execute(
        select(GlobalDiscountSetting).where(
            GlobalDiscountSetting.tenant_container_id == company.tenant_container_id,
            GlobalDiscountSetting.company_id == company.id,
        )
    ).scalar_one_or_none()
    if setting is None or not setting.is_active:
        return Decimal("0")
    day = on or company_today(company)
    if setting.start_date and day < setting.start_date:
        return Decimal("0")
    if setting.end_date and day > setting.end_date:
        return Decimal("0")
    return Decimal(str(setting.percentage))


# -------------------------------------------------------- attendance settings

def get_attendance_setting(actor: User, company_id: str) -> AttendanceSetting | None:
    company = _active_company(actor, company_id)
    return db.session.execute(
        select(AttendanceSetting).where(
            AttendanceSetting.tenant_container_id == company.tenant_container_id,
            AttendanceSetting.company_id == company.id,
        )
    ).scalar_one_or_none()


def update_attendance_settings(
    actor: User,
    company_id: str,
    *,
    mandatory_attendance_time: str | None,
    is_mandatory_attendance_active: bool,
    max_concurrent_breaks: int,
) -> AttendanceSetting:
    _require_manage_settings(actor)
    company = _active_company(actor, company_id)
    if mandatory_attendance_time:
        if len(mandatory_attendance_time) != 5 or mandatory_attendance_time[2:3] != ":":
            raise SettingsRuleError("Mandatory attendance time must use HH:MM format.")
        try:
            hour, minute = mandatory_attendance_time.split(":")
            if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
                raise ValueError
        except ValueError:
            raise SettingsRuleError("Mandatory attendance time must use HH:MM format.") from None
    else:
        mandatory_attendance_time = None
    try:
        breaks = int(max_concurrent_breaks)
    except (TypeError, ValueError):
        raise SettingsRuleError("Maximum concurrent breaks must be a whole number.") from None
    if breaks < 1 or breaks > 10:
        raise SettingsRuleError("Maximum concurrent breaks must be between 1 and 10.")
    existing = get_attendance_setting(actor, company.id)
    before = (
        {
            "mandatory_attendance_time": existing.mandatory_attendance_time,
            "is_mandatory_attendance_active": existing.is_mandatory_attendance_active,
            "max_concurrent_breaks": existing.max_concurrent_breaks,
        }
        if existing
        else None
    )
    if existing is None:
        setting = AttendanceSetting(
            tenant_container_id=company.tenant_container_id,
            company_id=company.id,
            mandatory_attendance_time=mandatory_attendance_time,
            is_mandatory_attendance_active=_as_bool(is_mandatory_attendance_active, "Mandatory attendance active"),
            max_concurrent_breaks=breaks,
            created_by_id=actor.id,
        )
        db.session.add(setting)
        db.session.flush()
    else:
        existing.mandatory_attendance_time = mandatory_attendance_time
        existing.is_mandatory_attendance_active = _as_bool(is_mandatory_attendance_active, "Mandatory attendance active")
        existing.max_concurrent_breaks = breaks
        db.session.flush()
        setting = existing
    _record(
        actor,
        company,
        action="settings.attendance.updated",
        entity_type="AttendanceSetting",
        entity_id=setting.id,
        before=before,
        after={
            "mandatory_attendance_time": setting.mandatory_attendance_time,
            "is_mandatory_attendance_active": setting.is_mandatory_attendance_active,
            "max_concurrent_breaks": setting.max_concurrent_breaks,
        },
    )
    return setting


def settings_summary(actor: User, company_id: str) -> dict:
    company = _active_company(actor, company_id)
    taxes = list_tax_settings(actor, company.id)
    commission = get_commission_setting(actor, company.id)
    discounts = list_global_discounts(actor, company.id)
    attendance = get_attendance_setting(actor, company.id)
    return {
        "company_id": company.id,
        "taxes": [
            {"name": tax.name, "rate": str(tax.rate), "is_enabled": tax.is_enabled} for tax in taxes
        ],
        "commission": (
            {
                "sales_target": str(commission.sales_target),
                "commission_interval": commission.commission_interval,
                "commission_percentage": str(commission.commission_percentage),
                "is_active": commission.is_active,
            }
            if commission
            else None
        ),
        "global_discount": (
            {
                "percentage": str(discounts[0].percentage),
                "start_date": discounts[0].start_date.isoformat() if discounts[0].start_date else None,
                "end_date": discounts[0].end_date.isoformat() if discounts[0].end_date else None,
                "is_active": discounts[0].is_active,
                "description": discounts[0].description,
            }
            if discounts
            else None
        ),
        "attendance": (
            {
                "mandatory_attendance_time": attendance.mandatory_attendance_time,
                "is_mandatory_attendance_active": attendance.is_mandatory_attendance_active,
                "max_concurrent_breaks": attendance.max_concurrent_breaks,
            }
            if attendance
            else None
        ),
    }
