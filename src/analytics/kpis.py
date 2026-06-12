"""
Analytics KPI Engine
=====================
Computes and surfaces operational KPIs from the Gold-layer datasets.

KPI families:

    Reliability  — MTBF, MTTR, Availability by asset
    Production   — OEE, Throughput, Planned Attainment, Downtime breakdown
    Quality      — First Pass Yield, Scrap Rate, Defect category trends
    Maintenance  — Work order volume, corrective vs preventive ratio,
                   average repair time, failure category distribution

All KPIs are returned as structured DataFrames and can be consumed
directly by the Streamlit dashboard or exported to CSV/Parquet.

Usage
-----
    from src.analytics.kpis import KPIEngine
    engine = KPIEngine()
    kpis = engine.compute_all()
    print(kpis["reliability"])
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR     = PROJECT_ROOT / "data" / "gold"
SILVER_DIR   = PROJECT_ROOT / "data" / "silver"


class KPIEngine:
    """Loads Gold-layer data and computes structured operational KPIs."""

    def __init__(
        self,
        gold_dir: Path = GOLD_DIR,
        silver_dir: Path = SILVER_DIR,
    ) -> None:
        self.gold_dir = gold_dir
        self.silver_dir = silver_dir
        self._cache: dict[str, pd.DataFrame] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_all(self) -> dict[str, pd.DataFrame | dict]:
        """Compute and return all KPI families."""
        return {
            "reliability":   self.reliability_kpis(),
            "oee_daily":     self.oee_kpis(),
            "quality_daily": self.quality_kpis(),
            "maintenance":   self.maintenance_kpis(),
            "production":    self.production_kpis(),
            "downtime":      self.downtime_breakdown(),
            "quality_scores": self.quality_scores(),
        }

    # ------------------------------------------------------------------
    # Reliability
    # ------------------------------------------------------------------

    def reliability_kpis(self) -> pd.DataFrame:
        """
        MTBF, MTTR, and Availability per line.

        Returns a DataFrame with one row per production line.
        """
        df = self._load("reliability_kpis")
        if df is None:
            df = self._compute_reliability_from_silver()
        return df

    def _compute_reliability_from_silver(self) -> pd.DataFrame:
        state_df = self._load_silver("machine_state")
        if state_df is None:
            return pd.DataFrame()

        rows = []
        for line, grp in state_df.groupby("line_id"):
            failures = grp[grp["machine_state"] == "Unplanned Downtime"]
            repairs = grp[grp["machine_state"] == "Maintenance Mode"]
            running = grp[grp["machine_state"] == "Running"]

            n_failures = len(failures)
            run_hr = running["duration_min"].sum() / 60.0
            repair_hr = repairs["duration_min"].sum() / 60.0

            mtbf = run_hr / n_failures if n_failures else run_hr
            mttr = repair_hr / n_failures if n_failures else 0.0
            avail = mtbf / (mtbf + mttr) if (mtbf + mttr) > 0 else 1.0

            rows.append({
                "line_id": line,
                "n_failure_events": n_failures,
                "total_running_hr": round(run_hr, 2),
                "total_repair_hr": round(repair_hr, 2),
                "mtbf_hr": round(mtbf, 2),
                "mttr_hr": round(mttr, 2),
                "availability": round(avail, 4),
            })
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # OEE
    # ------------------------------------------------------------------

    def oee_kpis(self) -> pd.DataFrame:
        """Daily OEE per line with availability, performance, quality components."""
        df = self._load("oee_daily")
        if df is None:
            return pd.DataFrame()
        df["date"] = pd.to_datetime(df["date"])
        return df

    def oee_summary(self) -> pd.DataFrame:
        """Average OEE per line over the full simulation period."""
        daily = self.oee_kpis()
        if daily.empty:
            return pd.DataFrame()
        return (
            daily.groupby("line_id")
            .agg(
                avg_oee=("oee", "mean"),
                avg_availability=("availability", "mean"),
                avg_performance=("performance", "mean"),
                avg_quality=("quality", "mean"),
            )
            .round(4)
            .reset_index()
        )

    # ------------------------------------------------------------------
    # Quality
    # ------------------------------------------------------------------

    def quality_kpis(self) -> pd.DataFrame:
        """Daily quality KPIs per line."""
        df = self._load("quality_kpis")
        if df is None:
            return pd.DataFrame()
        df["date"] = pd.to_datetime(df["date"])
        return df

    def quality_summary(self) -> pd.DataFrame:
        """Average quality metrics per line."""
        daily = self.quality_kpis()
        if daily.empty:
            return pd.DataFrame()
        return (
            daily.groupby("line_id")
            .agg(
                avg_fpy=("first_pass_yield", "mean"),
                avg_scrap_rate=("scrap_rate", "mean"),
                total_scrap=("total_scrap", "sum"),
                total_rework=("total_rework", "sum"),
                total_inspected=("total_inspected", "sum"),
            )
            .round(4)
            .reset_index()
        )

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def maintenance_kpis(self) -> pd.DataFrame:
        """Work order summary by line and maintenance type."""
        df = self._load("maintenance_summary")
        if df is None:
            return pd.DataFrame()
        return df

    def corrective_vs_preventive(self) -> pd.DataFrame:
        """Ratio of corrective to preventive work orders per line."""
        maint = self.maintenance_kpis()
        if maint.empty:
            return pd.DataFrame()

        pivot = maint.pivot_table(
            index="line_id",
            columns="maintenance_type",
            values="work_order_count",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()
        pivot.columns.name = None

        corrective = pivot.get("Corrective", 0)
        preventive = pivot.get("Preventive", 0)
        total = corrective + preventive
        pivot["corrective_pct"] = (corrective / total * 100).round(2)
        pivot["preventive_pct"] = (preventive / total * 100).round(2)
        return pivot

    # ------------------------------------------------------------------
    # Production
    # ------------------------------------------------------------------

    def production_kpis(self) -> pd.DataFrame:
        """Weekly production attainment per line."""
        df = self._load("production_attainment")
        if df is None:
            return pd.DataFrame()
        return df

    def production_summary(self) -> pd.DataFrame:
        """Overall planned vs actual per line."""
        df = self.production_kpis()
        if df.empty:
            return pd.DataFrame()
        return (
            df.groupby("line_id")
            .agg(
                total_planned=("planned_units", "sum"),
                total_actual=("actual_units", "sum"),
                avg_attainment_pct=("attainment_pct", "mean"),
            )
            .round(2)
            .reset_index()
        )

    # ------------------------------------------------------------------
    # Downtime breakdown
    # ------------------------------------------------------------------

    def downtime_breakdown(self) -> pd.DataFrame:
        """Downtime minutes per state and line for the full period."""
        state_df = self._load_silver("machine_state")
        if state_df is None:
            return pd.DataFrame()

        downtime_states = ["Idle", "Planned Downtime", "Unplanned Downtime", "Maintenance Mode"]
        df = state_df[state_df["machine_state"].isin(downtime_states)]
        return (
            df.groupby(["line_id", "machine_state"])["duration_min"]
            .sum()
            .reset_index()
            .rename(columns={"duration_min": "total_downtime_min"})
        )

    # ------------------------------------------------------------------
    # Quality scores (from quality checker)
    # ------------------------------------------------------------------

    def quality_scores(self) -> pd.DataFrame:
        df = self._load("quality_scores")
        if df is None:
            return pd.DataFrame()
        return df

    # ------------------------------------------------------------------
    # Print summary
    # ------------------------------------------------------------------

    def print_summary(self) -> None:
        """Print a concise executive summary of all KPI families."""
        print("\n" + "=" * 60)
        print("KPI Summary")
        print("=" * 60)

        rel = self.reliability_kpis()
        if not rel.empty:
            print("\nReliability")
            print(rel[["line_id", "mtbf_hr", "mttr_hr", "availability"]].to_string(index=False))

        oee_sum = self.oee_summary()
        if not oee_sum.empty:
            print("\nOEE (average over period)")
            print(oee_sum.to_string(index=False))

        q_sum = self.quality_summary()
        if not q_sum.empty:
            print("\nQuality")
            print(q_sum[["line_id", "avg_fpy", "avg_scrap_rate"]].to_string(index=False))

        cv = self.corrective_vs_preventive()
        if not cv.empty:
            print("\nMaintenance — Corrective vs Preventive")
            print(cv.to_string(index=False))

    # ------------------------------------------------------------------
    # Loader helpers
    # ------------------------------------------------------------------

    def _load(self, name: str) -> Optional[pd.DataFrame]:
        if name in self._cache:
            return self._cache[name]
        path = self.gold_dir / f"{name}.parquet"
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        self._cache[name] = df
        return df

    def _load_silver(self, name: str) -> Optional[pd.DataFrame]:
        key = f"_silver_{name}"
        if key in self._cache:
            return self._cache[key]
        path = SILVER_DIR / f"{name}.parquet"
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        self._cache[key] = df
        return df


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    engine = KPIEngine()
    engine.print_summary()
