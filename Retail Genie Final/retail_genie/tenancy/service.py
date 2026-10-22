"""Tenant-container provisioning helpers."""

from ..extensions import db
from ..models import DATA_DOMAINS, TenantDataPolicy

DEFAULT_SHARING_MODE = "company"


def seed_tenant_data_policies(tenant_container_id: str, *, changed_by_user_id: str | None = None) -> list[TenantDataPolicy]:
    """Create restrictive company-level defaults for every supported data domain.

    Call this in the same transaction as container creation. Company-level is a
    safe default: it preserves standalone-company use but does not silently
    share data with newly added sibling companies.
    """
    policies = [
        TenantDataPolicy(
            tenant_container_id=tenant_container_id,
            domain=domain,
            sharing_mode=DEFAULT_SHARING_MODE,
            is_enabled=True,
            policy_version=1,
            changed_by_user_id=changed_by_user_id,
        )
        for domain in DATA_DOMAINS
    ]
    db.session.add_all(policies)
    return policies
