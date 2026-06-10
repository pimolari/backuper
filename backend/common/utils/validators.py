"""
Reusable validators for business-rule constraints.

Centralises region / storage-class checks that were previously
duplicated in multiple route handlers.
"""

from backend import config
from backend.common.exceptions import ValidationError


def validate_region(region: str) -> None:
    """Raise :class:`ValidationError` if *region* is not allowed."""
    if region not in config.ALLOWED_REGIONS:
        raise ValidationError(
            f"Invalid region. Allowed: {config.ALLOWED_REGIONS}"
        )


def validate_storage_class(storage_class: str) -> None:
    """Raise :class:`ValidationError` if *storage_class* is not allowed."""
    if storage_class not in config.ALLOWED_STORAGE_CLASSES:
        raise ValidationError(
            f"Invalid storage class. Allowed: {config.ALLOWED_STORAGE_CLASSES}"
        )
