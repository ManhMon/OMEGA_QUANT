"""omega.data.data_validator - compatibility shim"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List
import pandas as pd

@dataclass
class ValidationIssue:
    field: str
    message: str
    severity: str = "error"

class DataValidator:
    def validate(self, df: pd.DataFrame) -> List[ValidationIssue]:
        issues = []
        if df.empty:
            issues.append(ValidationIssue("df", "DataFrame is empty"))
        return issues
