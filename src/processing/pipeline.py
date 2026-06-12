"""
Medallion Architecture Pipeline  (Bronze → Silver → Gold)
===========================================================
Transforms raw industrial data through three logical quality tiers:

    Bronze  — raw ingested data, preserved as-is with load metadata
    Silver  — validated, deduplicated, and standardised data
    Gold    — business-ready aggregated datasets for analytics and dashboards

Each layer writes Parquet files to data/{bronze,silver,gold}/.

Usage
-----
    python -m src.processing.pipeline            # run full pipeline
    from src.processing.pipeline import Pipeline
    p = Pipeline()
    p.run()
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR      = PROJECT_ROOT / "data" / "raw"
BRONZE_DIR   = PROJECT_ROOT / "data" / "bronze"
SILVER_DIR   = PROJECT_ROOT / "data" / "silver"
GOLD_DIR     = PROJECT_ROOT / "data" / "gold"

# Sensor valid operating ranges (min, max) — values outside are flagged
SENSOR_VALID_RANGES = {
    "temperature_c":       (0.0,   200.0),
    "pressure_bar":        (0.0,    15.0),
    "vibration_mm_s":      (0.0,    30.0),
    "power_kw":            (0.0,   400.0),
    "throughput_units_hr": (0.0,   200.0),
}

VALID_MACHINE_STATES = {
    "Running", "Idle", "Planned Downtime", "Unplanned Downtime", "Maintenance Mode"
}


class Pipeline:
    """End-to-end Medallion pipeline for the industrial IoT platform."""

    def __init__(self, raw_dir: Path = RAW_DIR) -> None:
        self.raw_dir = raw_dir
        for d in (BRONZE_DIR, SILVER_DIR, GOLD_DIR):
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Orchestrator
    # ------------------------------------------------------------------

    def run(self) -> dict[str, pd.DataFrame]:
        """Run the full Bronze → Silver → Gold pipeline."""
        print("\n" + "=" * 60)
        print("Pipeline: Bronze → Silver → Gold")
        print("=" * 60)

        print("\n[1/3] Bronze layer — ingest raw data …")
        bronze = self._build_bronze()

        print("\n[2/3] Silver layer — validate and standardise …")
        silver = self._build_silver(bronze)

        print("\n[3/3] Gold layer — aggregate KPIs …")
        gold = self._build_gold(silver)

        print("\nPipeline complete.")
        return {"bronze": bronze, "silver": silver, "gold": gold}

    # ------------------------------------------------------------------
    # Bronze — preserve raw data with load metadata
    # ------------------------------------------------------------------

    def _build_bronze(self) -> dict[str, pd.DataFrame]:
        bronze: dict[str, pd.DataFrame] = {}
        files = {
            "sensor":         "sensor_readings.csv",
            "machine_state":  "machine_states.csv",
            "quality":        "quality_inspections.csv",
            "maintenance":    "maintenance_records.csv",
            "erp":            "erp_production_orders.csv",
        }

        for name, fname in files.items():
            path = self.raw_dir / fname
            if not path.exists():
                print(f"  ⚠ {fname} not found — run simulator first")
                continue

            df = pd.read_csv(path, low_memory=False)
            df["_loaded_at"] = datetime.utcnow().isoformat()
            df["_source_file"] = fname
            df["_row_hash"] = df.apply(
                lambda r: hashlib.md5(str(r.values).encode()).hexdigest(), axis=1
            )

            out_path = BRONZE_DIR / f"{name}.parquet"
            df.to_parquet(out_path, index=False)
            bronze[name] = df
            print(f"  ✓ {name}: {len(df):,} rows → {out_path.name}")

        return bronze

    # ------------------------------------------------------------------
    # Silver — clean, validate, deduplicate, enrich
    # ------------------------------------------------------------------

    def _build_silver(self, bronze: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        silver: dict[str, pd.DataFrame] = {}

        if "sensor" in bronze:
            silver["sensor"] = self._clean_sensor(bronze["sensor"].copy())
        if "machine_state" in bronze:
            silver["machine_state"] = self._clean_machine_states(bronze["machine_state"].copy())
        if "quality" in bronze:
            silver["quality"] = self._clean_quality(bronze["quality"].copy())
        if "maintenance" in bronze:
            silver["maintenance"] = self._clean_maintenance(bronze["maintenance"].copy())
        if "erp" in bronze:
            silver["erp"] = self._clean_erp(bronze["erp"].copy())

        for name, df in silver.items():
            out_path = SILVER_DIR / f"{name}.parquet"
            df.to_parquet(out_path, index=False)
            valid_mask = df.get("_is_valid", pd.Series([True] * len(df)))
            print(f"  ✓ {name}: {len(df):,} rows, {valid_mask.sum():,} valid → {out_path.name}")

        return silver

    # ------------------------------------------------------------------
    # Silver helpers — domain-specific cleaning
    # ------------------------------------------------------------------

    def _clean_sensor(self, df: pd.DataFrame) -> pd.DataFrame:
        # Parse timestamps
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        # Drop true duplicates (same timestamp + line)
        before = len(df)
        df = df.drop_duplicates(subset=["timestamp", "line_id"], keep="first")
        df["_duplicate_dropped"] = before - len(df)

        # Validate machine state
        df["_state_valid"] = df["machine_state"].isin(VALID_MACHINE_STATES)

        # Validate sensor ranges
        range_flags: list[pd.Series] = []
        for col, (lo, hi) in SENSOR_VALID_RANGES.items():
            flag = df[col].notna() & df[col].between(lo, hi)
            range_flags.append(flag)
            df[f"_{col}_valid"] = flag

        # Impute missing sensor values with forward-fill then median fallback
        sensor_cols = list(SENSOR_VALID_RANGES.keys())
        df[sensor_cols] = (
            df.sort_values(["line_id", "timestamp"])
            .groupby("line_id")[sensor_cols]
            .transform(lambda x: x.ffill().fillna(x.median()))
        )

        # Mark rows that passed all range checks and state validation
        all_valid = pd.concat(range_flags, axis=1).all(axis=1) & df["_state_valid"]
        df["_is_valid"] = all_valid

        # Add derived fields
        df["date"] = df["timestamp"].dt.floor("D")
        df["hour"] = df["timestamp"].dt.hour
        df["shift"] = df["timestamp"].apply(self._get_shift)
        df["week"] = df["timestamp"].dt.isocalendar().week.astype(int)

        return df

    def _clean_machine_states(self, df: pd.DataFrame) -> pd.DataFrame:
        df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])
        df["end_timestamp"] = pd.to_datetime(df["end_timestamp"])

        # Validate state labels
        df["_state_valid"] = df["machine_state"].isin(VALID_MACHINE_STATES)

        # Flag overlapping state records for the same line (rare but possible)
        df = df.sort_values(["line_id", "event_timestamp"])
        df["_prev_end"] = df.groupby("line_id")["end_timestamp"].shift(1)
        df["_overlap"] = df["event_timestamp"] < df["_prev_end"].fillna(
            df["event_timestamp"]
        )

        df["_is_valid"] = df["_state_valid"] & ~df["_overlap"]
        return df.drop(columns=["_prev_end"])

    def _clean_quality(self, df: pd.DataFrame) -> pd.DataFrame:
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        # Validate numeric consistency
        df["_totals_consistent"] = (
            (df["passed"] + df["failed"] == df["total_inspected"])
            & (df["scrap_count"] + df["rework_count"] == df["failed"])
        )
        df["_fpy_valid"] = df["first_pass_yield"].between(0.0, 1.0)
        df["_is_valid"] = df["_totals_consistent"] & df["_fpy_valid"]

        df["date"] = df["timestamp"].dt.floor("D")
        df["week"] = df["timestamp"].dt.isocalendar().week.astype(int)
        return df

    def _clean_maintenance(self, df: pd.DataFrame) -> pd.DataFrame:
        df["start_timestamp"] = pd.to_datetime(df["start_timestamp"])
        df["end_timestamp"] = pd.to_datetime(df["end_timestamp"])
        df["_duration_valid"] = df["duration_hr"] > 0
        df["_is_valid"] = df["_duration_valid"]
        return df

    def _clean_erp(self, df: pd.DataFrame) -> pd.DataFrame:
        df["order_date"] = pd.to_datetime(df["order_date"])
        df["_attainment_valid"] = df["attainment_pct"].between(0, 150)
        df["_is_valid"] = df["_attainment_valid"]
        return df

    # ------------------------------------------------------------------
    # Gold — business-ready aggregated datasets
    # ------------------------------------------------------------------

    def _build_gold(self, silver: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        gold: dict[str, pd.DataFrame] = {}

        if "sensor" in silver and "machine_state" in silver:
            gold["oee_daily"] = self._compute_oee_daily(
                silver["sensor"], silver["machine_state"]
            )
        if "machine_state" in silver:
            gold["reliability_kpis"] = self._compute_reliability_kpis(silver["machine_state"])
        if "quality" in silver:
            gold["quality_kpis"] = self._compute_quality_kpis_daily(silver["quality"])
        if "maintenance" in silver:
            gold["maintenance_summary"] = self._compute_maintenance_summary(silver["maintenance"])
        if "erp" in silver:
            gold["production_attainment"] = self._compute_production_attainment(silver["erp"])

        for name, df in gold.items():
            out_path = GOLD_DIR / f"{name}.parquet"
            df.to_parquet(out_path, index=False)
            print(f"  ✓ {name}: {len(df):,} rows → {out_path.name}")

        return gold

    # ------------------------------------------------------------------
    # Gold helpers — KPI computations
    # ------------------------------------------------------------------

    def _compute_oee_daily(
        self, sensor_df: pd.DataFrame, state_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Compute daily OEE per line.

        OEE = Availability × Performance × Quality

        Availability  = Running time / (Running + Unplanned Downtime) time
        Performance   = Actual throughput / Ideal throughput (95 units/hr)
        Quality       = (ideally from quality layer; approximated here)
        """
        state_df = state_df[state_df["_is_valid"]].copy()
        state_df["date"] = state_df["event_timestamp"].dt.floor("D")

        # Availability from state durations
        avail_rows = []
        for (line, date), grp in state_df.groupby(["line_id", "date"]):
            total_min = grp["duration_min"].sum()
            running_min = grp.loc[grp["machine_state"] == "Running", "duration_min"].sum()
            downtime_min = grp.loc[
                grp["machine_state"] == "Unplanned Downtime", "duration_min"
            ].sum()
            avail = running_min / (running_min + downtime_min) if (running_min + downtime_min) > 0 else 1.0
            avail_rows.append({"line_id": line, "date": date, "availability": round(avail, 4)})

        avail_df = pd.DataFrame(avail_rows)

        # Performance from sensor throughput
        sensor_df["date"] = pd.to_datetime(sensor_df["timestamp"]).dt.floor("D")
        perf_df = (
            sensor_df[sensor_df["machine_state"] == "Running"]
            .groupby(["line_id", "date"])["throughput_units_hr"]
            .mean()
            .reset_index()
            .rename(columns={"throughput_units_hr": "avg_throughput"})
        )
        IDEAL_THROUGHPUT = 95.0
        perf_df["performance"] = (
            perf_df["avg_throughput"] / IDEAL_THROUGHPUT
        ).clip(upper=1.0).round(4)

        # Quality approximation (constant; replaced by actual quality layer in Gold v2)
        BASELINE_QUALITY = 0.948

        oee_df = avail_df.merge(perf_df[["line_id", "date", "performance"]], on=["line_id", "date"], how="left")
        oee_df["performance"] = oee_df["performance"].fillna(0.0)
        oee_df["quality"] = BASELINE_QUALITY
        oee_df["oee"] = (oee_df["availability"] * oee_df["performance"] * oee_df["quality"]).round(4)
        oee_df["date"] = pd.to_datetime(oee_df["date"])
        return oee_df.sort_values(["line_id", "date"]).reset_index(drop=True)

    def _compute_reliability_kpis(self, state_df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute MTBF, MTTR, and Availability per line.

        MTBF = total running time / number of failure events
        MTTR = total repair time / number of failure events
        Availability = MTBF / (MTBF + MTTR)
        """
        rows = []
        for line, grp in state_df[state_df["_is_valid"]].groupby("line_id"):
            failures = grp[grp["machine_state"] == "Unplanned Downtime"]
            repairs = grp[grp["machine_state"] == "Maintenance Mode"]
            running = grp[grp["machine_state"] == "Running"]

            n_failures = len(failures)
            total_run_hr = running["duration_min"].sum() / 60.0
            total_repair_hr = repairs["duration_min"].sum() / 60.0

            mtbf = total_run_hr / n_failures if n_failures > 0 else total_run_hr
            mttr = total_repair_hr / n_failures if n_failures > 0 else 0.0
            availability = mtbf / (mtbf + mttr) if (mtbf + mttr) > 0 else 1.0

            rows.append({
                "line_id": line,
                "n_failure_events": n_failures,
                "total_running_hr": round(total_run_hr, 2),
                "total_repair_hr": round(total_repair_hr, 2),
                "mtbf_hr": round(mtbf, 2),
                "mttr_hr": round(mttr, 2),
                "availability": round(availability, 4),
            })

        return pd.DataFrame(rows)

    def _compute_quality_kpis_daily(self, quality_df: pd.DataFrame) -> pd.DataFrame:
        """Aggregate quality metrics to daily level per line."""
        daily = (
            quality_df[quality_df["_is_valid"]]
            .groupby(["line_id", "date"])
            .agg(
                total_inspected=("total_inspected", "sum"),
                total_passed=("passed", "sum"),
                total_failed=("failed", "sum"),
                total_scrap=("scrap_count", "sum"),
                total_rework=("rework_count", "sum"),
            )
            .reset_index()
        )
        daily["first_pass_yield"] = (
            daily["total_passed"] / daily["total_inspected"]
        ).round(4)
        daily["scrap_rate"] = (
            daily["total_scrap"] / daily["total_inspected"]
        ).round(4)
        daily["date"] = pd.to_datetime(daily["date"])
        return daily.sort_values(["line_id", "date"]).reset_index(drop=True)

    def _compute_maintenance_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """Summarise work orders by line and type."""
        summary = (
            df[df["_is_valid"]]
            .groupby(["line_id", "maintenance_type"])
            .agg(
                work_order_count=("work_order_id", "count"),
                avg_duration_hr=("duration_hr", "mean"),
                total_duration_hr=("duration_hr", "sum"),
                parts_replaced_count=("parts_replaced", "sum"),
            )
            .reset_index()
        )
        summary["avg_duration_hr"] = summary["avg_duration_hr"].round(2)
        summary["total_duration_hr"] = summary["total_duration_hr"].round(2)
        return summary

    def _compute_production_attainment(self, df: pd.DataFrame) -> pd.DataFrame:
        """Weekly production attainment per line."""
        df = df[df["_is_valid"]].copy()
        df["week"] = pd.to_datetime(df["order_date"]).dt.isocalendar().week.astype(int)
        df["year"] = pd.to_datetime(df["order_date"]).dt.year
        weekly = (
            df.groupby(["line_id", "year", "week"])
            .agg(
                planned_units=("planned_units", "sum"),
                actual_units=("actual_units", "sum"),
            )
            .reset_index()
        )
        weekly["attainment_pct"] = (
            weekly["actual_units"] / weekly["planned_units"] * 100
        ).round(2)
        return weekly.sort_values(["line_id", "year", "week"]).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_shift(ts: datetime) -> str:
        hour = ts.hour
        if 6 <= hour < 14:
            return "Day"
        elif 14 <= hour < 22:
            return "Evening"
        return "Night"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pipeline = Pipeline()
    pipeline.run()
