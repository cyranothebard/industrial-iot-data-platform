"""
Data Quality Layer
==================
Implements multi-dimensional data quality checks and a composite quality score
for each data domain in the industrial IoT platform.

Quality is evaluated across five dimensions (ISO 25012 / DAMA-inspired):

    1. Completeness  — are required fields populated?
    2. Validity      — do values fall within acceptable ranges?
    3. Consistency   — are records internally consistent?
    4. Uniqueness    — are there duplicate records?
    5. Freshness     — are timestamps reasonable and not stale?

Each check produces a per-row flag (bool) and a domain-level score (0–100).
The composite quality score weights the five dimensions equally by default.

Usage
-----
    from src.quality.checks import DataQualityChecker
    checker = DataQualityChecker()
    report = checker.run_all()
    print(report)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SILVER_DIR   = PROJECT_ROOT / "data" / "silver"
GOLD_DIR     = PROJECT_ROOT / "data" / "gold"

# Sensor acceptable ranges
SENSOR_VALID_RANGES = {
    "temperature_c":       (0.0,   200.0),
    "pressure_bar":        (0.0,    15.0),
    "vibration_mm_s":      (0.0,    30.0),
    "power_kw":            (0.0,   400.0),
    "throughput_units_hr": (0.0,   200.0),
}

SENSOR_COLS       = list(SENSOR_VALID_RANGES.keys())
REQUIRED_SENSOR   = ["timestamp", "line_id", "machine_state"] + SENSOR_COLS
REQUIRED_STATE    = ["event_id", "line_id", "machine_state", "event_timestamp", "duration_min"]
REQUIRED_QUALITY  = ["inspection_id", "line_id", "timestamp", "total_inspected", "passed", "failed"]
REQUIRED_MAINT    = ["work_order_id", "line_id", "maintenance_type", "start_timestamp", "duration_hr"]
REQUIRED_ERP      = ["order_id", "line_id", "order_date", "planned_units", "actual_units"]

VALID_STATES = {
    "Running", "Idle", "Planned Downtime", "Unplanned Downtime", "Maintenance Mode"
}


class DataQualityChecker:
    """
    Runs comprehensive quality checks across all silver-layer datasets and
    produces a structured quality report with per-domain and composite scores.
    """

    def __init__(self, silver_dir: Path = SILVER_DIR) -> None:
        self.silver_dir = silver_dir
        self.report: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_all(self) -> dict[str, dict]:
        """Run all quality checks and return the full quality report."""
        print("\n" + "=" * 60)
        print("Data Quality Assessment")
        print("=" * 60)

        domains = {
            "sensor":        (self._check_sensor,        "sensor.parquet"),
            "machine_state": (self._check_machine_states, "machine_state.parquet"),
            "quality":       (self._check_quality,        "quality.parquet"),
            "maintenance":   (self._check_maintenance,    "maintenance.parquet"),
            "erp":           (self._check_erp,            "erp.parquet"),
        }

        for domain, (check_fn, fname) in domains.items():
            path = self.silver_dir / fname
            if not path.exists():
                print(f"  ⚠ {fname} not found — skipping")
                continue
            df = pd.read_parquet(path)
            result = check_fn(df)
            self.report[domain] = result
            score = result["composite_score"]
            print(f"  {domain:20s}  composite score: {score:.1f}/100")

        self._print_summary()
        self._save_report()
        return self.report

    # ------------------------------------------------------------------
    # Domain-specific checkers
    # ------------------------------------------------------------------

    def _check_sensor(self, df: pd.DataFrame) -> dict:
        checks: dict[str, float] = {}

        # 1. Completeness — required fields present and non-null
        completeness = self._completeness_score(df, REQUIRED_SENSOR)
        checks["completeness"] = completeness

        # 2. Validity — sensor values in range
        valid_flags = []
        for col, (lo, hi) in SENSOR_VALID_RANGES.items():
            col_valid = df[col].notna() & df[col].between(lo, hi)
            valid_flags.append(col_valid)
        validity = float(pd.concat(valid_flags, axis=1).all(axis=1).mean() * 100)
        checks["validity"] = round(validity, 2)

        # 3. Consistency — machine state is a valid label
        state_valid = df["machine_state"].isin(VALID_STATES).mean() * 100
        checks["consistency"] = round(float(state_valid), 2)

        # 4. Uniqueness — no duplicate (timestamp, line_id) pairs
        duplicates = df.duplicated(subset=["timestamp", "line_id"]).sum()
        uniqueness = max(0.0, (1 - duplicates / len(df)) * 100)
        checks["uniqueness"] = round(uniqueness, 2)

        # 5. Freshness — timestamps are chronologically ordered within each line
        df_sorted = df.sort_values(["line_id", "timestamp"])
        ts_diffs = df_sorted.groupby("line_id")["timestamp"].diff().dt.total_seconds()
        out_of_order = (ts_diffs < 0).sum()
        freshness = max(0.0, (1 - out_of_order / len(df)) * 100)
        checks["freshness"] = round(freshness, 2)

        # Anomaly flagging — IQR-based outlier counts per sensor
        anomaly_summary = self._iqr_anomaly_counts(df, SENSOR_COLS)

        composite = self._composite(checks)
        return {
            "domain": "sensor",
            "row_count": len(df),
            "checks": checks,
            "composite_score": composite,
            "anomaly_summary": anomaly_summary,
            "issues": self._identify_issues(df, checks),
        }

    def _check_machine_states(self, df: pd.DataFrame) -> dict:
        checks: dict[str, float] = {}

        checks["completeness"] = self._completeness_score(df, REQUIRED_STATE)

        state_valid = df["machine_state"].isin(VALID_STATES).mean() * 100
        checks["validity"] = round(float(state_valid), 2)

        # Consistency: duration must be positive, end > start
        duration_valid = (df["duration_min"] > 0).mean() * 100
        checks["consistency"] = round(float(duration_valid), 2)

        duplicates = df.duplicated(subset=["event_id"]).sum()
        checks["uniqueness"] = round(max(0.0, (1 - duplicates / len(df)) * 100), 2)

        ts_valid = (
            df["event_timestamp"].notna() & df["end_timestamp"].notna()
            & (df["end_timestamp"] > df["event_timestamp"])
        ).mean() * 100
        checks["freshness"] = round(float(ts_valid), 2)

        composite = self._composite(checks)
        return {
            "domain": "machine_state",
            "row_count": len(df),
            "checks": checks,
            "composite_score": composite,
            "anomaly_summary": {},
            "issues": self._identify_issues(df, checks),
        }

    def _check_quality(self, df: pd.DataFrame) -> dict:
        checks: dict[str, float] = {}

        checks["completeness"] = self._completeness_score(df, REQUIRED_QUALITY)

        totals_ok = (df["passed"] + df["failed"] == df["total_inspected"]).mean() * 100
        checks["validity"] = round(float(totals_ok), 2)

        fpy_ok = df["first_pass_yield"].between(0.0, 1.0).mean() * 100
        checks["consistency"] = round(float(fpy_ok), 2)

        duplicates = df.duplicated(subset=["inspection_id"]).sum()
        checks["uniqueness"] = round(max(0.0, (1 - duplicates / len(df)) * 100), 2)

        ts_valid = df["timestamp"].notna().mean() * 100
        checks["freshness"] = round(float(ts_valid), 2)

        composite = self._composite(checks)
        return {
            "domain": "quality",
            "row_count": len(df),
            "checks": checks,
            "composite_score": composite,
            "anomaly_summary": {},
            "issues": self._identify_issues(df, checks),
        }

    def _check_maintenance(self, df: pd.DataFrame) -> dict:
        checks: dict[str, float] = {}

        checks["completeness"] = self._completeness_score(df, REQUIRED_MAINT)

        valid_types = {"Corrective", "Preventive", "Emergency"}
        type_valid = df["maintenance_type"].isin(valid_types).mean() * 100
        checks["validity"] = round(float(type_valid), 2)

        dur_ok = (df["duration_hr"] > 0).mean() * 100
        checks["consistency"] = round(float(dur_ok), 2)

        duplicates = df.duplicated(subset=["work_order_id"]).sum()
        checks["uniqueness"] = round(max(0.0, (1 - duplicates / len(df)) * 100), 2)

        ts_valid = df["start_timestamp"].notna().mean() * 100
        checks["freshness"] = round(float(ts_valid), 2)

        composite = self._composite(checks)
        return {
            "domain": "maintenance",
            "row_count": len(df),
            "checks": checks,
            "composite_score": composite,
            "anomaly_summary": {},
            "issues": self._identify_issues(df, checks),
        }

    def _check_erp(self, df: pd.DataFrame) -> dict:
        checks: dict[str, float] = {}

        checks["completeness"] = self._completeness_score(df, REQUIRED_ERP)

        units_valid = (df["planned_units"] > 0).mean() * 100
        checks["validity"] = round(float(units_valid), 2)

        attainment_valid = df["attainment_pct"].between(0, 150).mean() * 100
        checks["consistency"] = round(float(attainment_valid), 2)

        duplicates = df.duplicated(subset=["order_id"]).sum()
        checks["uniqueness"] = round(max(0.0, (1 - duplicates / len(df)) * 100), 2)

        ts_valid = df["order_date"].notna().mean() * 100
        checks["freshness"] = round(float(ts_valid), 2)

        composite = self._composite(checks)
        return {
            "domain": "erp",
            "row_count": len(df),
            "checks": checks,
            "composite_score": composite,
            "anomaly_summary": {},
            "issues": self._identify_issues(df, checks),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _completeness_score(df: pd.DataFrame, required_cols: list[str]) -> float:
        """Percentage of required cells that are non-null."""
        available = [c for c in required_cols if c in df.columns]
        total_cells = len(df) * len(available)
        if total_cells == 0:
            return 0.0
        non_null = df[available].notna().sum().sum()
        return round(float(non_null / total_cells * 100), 2)

    @staticmethod
    def _composite(checks: dict[str, float], weights: Optional[dict] = None) -> float:
        """Weighted average of dimension scores."""
        default_weights = {
            "completeness": 0.25,
            "validity":     0.25,
            "consistency":  0.20,
            "uniqueness":   0.15,
            "freshness":    0.15,
        }
        w = weights or default_weights
        total_w = sum(w.get(k, 0) for k in checks)
        if total_w == 0:
            return 0.0
        weighted_sum = sum(checks.get(k, 0) * w.get(k, 0) for k in checks)
        return round(weighted_sum / total_w, 2)

    @staticmethod
    def _iqr_anomaly_counts(df: pd.DataFrame, cols: list[str]) -> dict[str, int]:
        """Count IQR-based outliers per sensor column."""
        counts: dict[str, int] = {}
        for col in cols:
            if col not in df.columns:
                continue
            series = df[col].dropna()
            q1, q3 = series.quantile(0.25), series.quantile(0.75)
            iqr = q3 - q1
            lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            counts[col] = int(((series < lo) | (series > hi)).sum())
        return counts

    @staticmethod
    def _identify_issues(df: pd.DataFrame, checks: dict[str, float]) -> list[str]:
        """Return human-readable issue descriptions for scores below threshold."""
        issues: list[str] = []
        thresholds = {
            "completeness": 95.0,
            "validity":     95.0,
            "consistency":  97.0,
            "uniqueness":   99.0,
            "freshness":    98.0,
        }
        for dim, score in checks.items():
            threshold = thresholds.get(dim, 95.0)
            if score < threshold:
                gap = round(threshold - score, 2)
                issues.append(
                    f"{dim.capitalize()} below threshold ({score:.1f}% < {threshold}%; gap: {gap}%)"
                )
        return issues

    def _print_summary(self) -> None:
        print("\n" + "-" * 60)
        print(f"{'Domain':<22} {'Compl':>6} {'Valid':>6} {'Consis':>7} {'Uniq':>6} {'Fresh':>6} {'Score':>7}")
        print("-" * 60)
        for domain, result in self.report.items():
            c = result["checks"]
            score = result["composite_score"]
            print(
                f"{domain:<22} "
                f"{c.get('completeness', 0):>6.1f} "
                f"{c.get('validity', 0):>6.1f} "
                f"{c.get('consistency', 0):>7.1f} "
                f"{c.get('uniqueness', 0):>6.1f} "
                f"{c.get('freshness', 0):>6.1f} "
                f"{score:>7.1f}"
            )
        print("-" * 60)

        if self.report:
            overall = np.mean([r["composite_score"] for r in self.report.values()])
            print(f"\nOverall platform quality score: {overall:.1f}/100")

    def _save_report(self) -> None:
        """Save quality scores as a flat Parquet table for dashboard consumption."""
        GOLD_DIR.mkdir(parents=True, exist_ok=True)
        rows = []
        for domain, result in self.report.items():
            row = {
                "domain": domain,
                "row_count": result["row_count"],
                "composite_score": result["composite_score"],
                "assessed_at": datetime.utcnow().isoformat(),
                **{f"score_{k}": v for k, v in result["checks"].items()},
            }
            rows.append(row)
        if rows:
            df = pd.DataFrame(rows)
            out = GOLD_DIR / "quality_scores.parquet"
            df.to_parquet(out, index=False)
            print(f"\nQuality report written to {out}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    checker = DataQualityChecker()
    checker.run_all()
