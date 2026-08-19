"""Evidence-aware input loading for the commodity simulation.

The simulation consumes values from one JSON ledger. Every numeric, boolean,
or categorical input used by a scenario carries a unit, definition, evidence
grade, source label, and observation date. Grade-X records are deliberately
unusable, while grade-C assumptions must expose a sensitivity interval.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterator, Literal


EvidenceGrade = Literal["A", "B", "C", "X"]
DEFAULT_LEDGER_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "commodity_simulation"
    / "evidence.json"
)


@dataclass(frozen=True)
class EvidenceRecord:
    """One traceable simulation input."""

    path: str
    value: Any
    unit: str
    definition: str
    grade: EvidenceGrade
    source: str
    as_of: str
    label: str | None = None
    sensitivity: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        if self.grade not in {"A", "B", "C", "X"}:
            raise ValueError(f"{self.path}: unsupported evidence grade {self.grade!r}")
        for name in ("unit", "definition", "source", "as_of"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{self.path}: {name} must not be blank")
        if self.grade == "C":
            if self.label not in {"assumption", "derived", "estimate"}:
                raise ValueError(
                    f"{self.path}: grade-C inputs require an explicit label"
                )
            if self.label == "assumption" and self.sensitivity is None:
                raise ValueError(
                    f"{self.path}: assumptions require a sensitivity interval"
                )
        if self.sensitivity is not None:
            low, high = self.sensitivity
            if low > high:
                raise ValueError(
                    f"{self.path}: sensitivity lower bound exceeds upper bound"
                )

    @property
    def usable(self) -> bool:
        return self.grade != "X"


class VerifiedInputLedger:
    """Read and validate the single source of scenario inputs."""

    def __init__(self, payload: dict[str, Any], *, source_path: Path) -> None:
        self.payload = payload
        self.source_path = source_path
        if payload.get("schema_version") != 1:
            raise ValueError("unsupported verified-input schema version")
        self._records = tuple(self._walk_records(payload))
        if not self._records:
            raise ValueError("verified-input ledger contains no evidence records")

    @classmethod
    def load(cls, path: str | Path = DEFAULT_LEDGER_PATH) -> "VerifiedInputLedger":
        source_path = Path(path)
        with source_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise TypeError("verified-input ledger root must be an object")
        return cls(payload, source_path=source_path)

    @property
    def records(self) -> tuple[EvidenceRecord, ...]:
        return self._records

    def record(self, dotted_path: str, *, allow_unverified: bool = False) -> EvidenceRecord:
        node: Any = self.payload
        for component in dotted_path.split("."):
            if not isinstance(node, dict) or component not in node:
                raise KeyError(f"unknown input path: {dotted_path}")
            node = node[component]
        if not self._is_record(node):
            raise TypeError(f"input path is not an evidence record: {dotted_path}")
        record = self._make_record(dotted_path, node)
        if not record.usable and not allow_unverified:
            raise ValueError(f"grade-X input cannot be used: {dotted_path}")
        return record

    def value(self, dotted_path: str) -> Any:
        return self.record(dotted_path).value

    def assert_complete(self) -> None:
        """Re-run metadata and grade checks for every ledger record."""

        for record in self._records:
            record.__post_init__()

    @classmethod
    def _walk_records(
        cls, node: Any, prefix: str = ""
    ) -> Iterator[EvidenceRecord]:
        if cls._is_record(node):
            yield cls._make_record(prefix, node)
            return
        if isinstance(node, dict):
            for key, child in node.items():
                child_path = f"{prefix}.{key}" if prefix else key
                yield from cls._walk_records(child, child_path)
        elif isinstance(node, list):
            for index, child in enumerate(node):
                child_path = f"{prefix}[{index}]"
                yield from cls._walk_records(child, child_path)

    @staticmethod
    def _is_record(node: Any) -> bool:
        return isinstance(node, dict) and "value" in node

    @staticmethod
    def _make_record(path: str, node: dict[str, Any]) -> EvidenceRecord:
        sensitivity = node.get("sensitivity")
        sensitivity_tuple = (
            (float(sensitivity[0]), float(sensitivity[1]))
            if sensitivity is not None
            else None
        )
        return EvidenceRecord(
            path=path,
            value=node["value"],
            unit=str(node.get("unit", "")),
            definition=str(node.get("definition", "")),
            grade=node.get("grade", ""),
            source=str(node.get("source", "")),
            as_of=str(node.get("as_of", "")),
            label=node.get("label"),
            sensitivity=sensitivity_tuple,
        )
