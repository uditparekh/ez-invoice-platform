"""Shared connector contracts for accounting-system integrations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class PreflightIssue:
    code: str
    message: str
    field: str = ""
    blocking: bool = True


@dataclass
class ConnectorResult:
    success: bool
    message: str
    external_id: Optional[str] = None
    issues: List[PreflightIssue] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "external_id": self.external_id,
            "issues": [issue.__dict__ for issue in self.issues],
            "raw": self.raw,
        }


class AccountingConnector(Protocol):
    """Minimum behavior required from an SiftEntry posting connector."""

    def is_connected(self) -> bool:
        ...

    def preflight(self, payload: Dict[str, Any]) -> List[PreflightIssue]:
        ...

    def post_bill(self, payload: Dict[str, Any]) -> ConnectorResult:
        ...
