"""Data models for the Bactopia linter."""

from dataclasses import dataclass


@dataclass
class LintResult:
    """A single lint check result."""

    rule_id: str
    severity: str  # "PASS", "WARN", "FAIL"
    component: str
    message: str

    def is_fail(self) -> bool:
        return self.severity == "FAIL"

    def is_warn(self) -> bool:
        return self.severity == "WARN"

    def is_pass(self) -> bool:
        return self.severity == "PASS"

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "component": self.component,
            "message": self.message,
        }
