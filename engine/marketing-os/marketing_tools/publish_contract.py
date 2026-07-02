"""PUB-04: Publishing provider contract.

Interface that all platform providers must satisfy.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol


class PublishProvider(Protocol):
    """Every platform publish provider must implement these."""

    def prepare(self, asset: dict[str, Any]) -> dict[str, Any]: ...
    def validate(self, asset: dict[str, Any]) -> dict[str, Any]: ...
    def publish(self, asset: dict[str, Any]) -> dict[str, Any]: ...
    def query_status(self, post_id: str) -> dict[str, Any]: ...
    def delete_post(self, post_id: str) -> dict[str, Any]: ...
    def collect_metrics(self, post_id: str) -> dict[str, Any]: ...


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "errors": self.errors, "warnings": self.warnings}


def validate_publish_asset(asset: dict[str, Any], platform: str) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    if not asset.get("title"):
        errors.append("missing title")
    if not asset.get("platform"):
        errors.append("missing platform")
    elif asset["platform"] != platform:
        errors.append(f"platform mismatch: {asset['platform']} != {platform}")
    if asset.get("status") not in ("approved", "review"):
        errors.append(f"asset status {asset.get('status')!r} not publishable")
    content = asset.get("content")
    if isinstance(content, dict):
        if not content:
            errors.append("empty content")
    elif not content:
        warnings.append("no content body")
    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)
