"""
Industrial IoT Data Simulator
==============================
Generates realistic operational data streams for a multi-line manufacturing
facility. Simulates five core data domains:

    1. Production line sensor readings (temperature, pressure, vibration, power, throughput)
    2. Machine state events (running, idle, planned/unplanned downtime, maintenance)
    3. Quality inspection records (pass/fail, defect category, scrap, rework)
    4. Maintenance work orders (corrective and preventive)
    5. ERP production orders (planned vs. actual output)

The simulator is deterministic given a fixed random seed and generates 90 days
of data across three production lines (Line-A, Line-B, Line-C).

Usage
-----
    python run_pipeline.py
    python -m src.ingestion.simulator
    from src.ingestion.simulator import Simulator
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

LINES = ["Line-A", "Line-B", "Line-C"]
MACHINE_STATES = ["Running", "Idle", "Planned Downtime", "Unplanned Downtime", "Maintenance Mode"]
STATE_WEIGHTS = [0.70, 0.10, 0.10, 0.07, 0.03]

DEFECT_CATEGORIES = [
    "Surface Scratch",
    "Dimensional Out of Tolerance",
    "Weld Defect",
    "Assembly Error",
    "Material Defect",
]
FAILURE_CATEGORIES = ["Electrical", "Mechanical", "Pneumatic", "Software", "Operator Error"]
PRODUCT_TYPES = ["Product-Alpha", "Product-Beta", "Product-Gamma"]

# Valid ranges exposed for downstream quality checks
SENSOR_VALID_RANGES = {
    "temperature_c":       (0.0,   200.0),
    "pressure_bar":        (0.0,    15.0),
    "vibration_mm_s":      (0.0,    30.0),
    "power_kw":            (0.0,   400.0),
    "throughput_units_hr": (0.0,   200.0),
}

# Sensor operating distributions by machine state: (mean_lo, mean_hi, std)
SENSOR_PARAMS: dict[str, dict[str, tuple[float, float, float]]] = {
    "Running": {
        "temperature_c":       (78.0, 122.0, 2.5),
        "pressure_bar":        (2.4,    5.8, 0.2),
        "vibration_mm_s":      (0.8,    6.5, 0.4),
        "power_kw":            (75.0, 185.0, 8.0),
        "throughput_units_hr": (55.0,  95.0, 5.0),
    },
    "Idle": {
        "temperature_c":       (30.0,  55.0, 1.5),
        "pressure_bar":        (0.0,    0.5, 0.05),
        "vibration_mm_s":      (0.1,    0.8, 0.05),
        "power_kw":            (8.0,   22.0, 1.5),
        "throughput_units_hr": (0.0,    0.0, 0.0),
    },
    "Planned Downtime": {
        "temperature_c":       (20.0,  35.0, 1.0),
        "pressure_bar":        (0.0,    0.3, 0.03),
        "vibration_mm_s":      (0.0,    0.3, 0.02),
        "power_kw":            (0.0,    5.0, 0.5),
        "throughput_units_hr": (0.0,    0.0, 0.0),
    },
    "Unplanned Downtime": {
        "temperature_c":       (50.0, 140.0, 8.0),
        "pressure_bar":        (0.0,    8.0, 1.5),
        "vibration_mm_s":      (5.0,   18.0, 2.0),
        "power_kw":            (0.0,   30.0, 5.0),
        "throughput_units_hr": (0.0,    0.0, 0.0),
    },
    "Maintenance Mode": {
        "temperature_c":       (20.0,  40.0, 1.5),
        "pressure_bar":        (0.0,    1.0, 0.1),
        "vibration_mm_s":      (0.0,    2.0, 0.3),
        "power_kw":            (5.0,   35.0, 3.0),
        "throughput_units_hr": (0.0,    0.0, 0.0),
    },
}


class Simulator:
    """Deterministic industrial data simulator for a three-line production facility."""

    def __init__(
        self,
        seed: int = 42,
        days: int = 90,
        start_date: Optional[datetime] = None,
    ) -> None:
        self.seed = seed
        self.days = days
        self.start_date = start_date or datetime(2025, 1, 1, 6, 0, 0)
        self.end_date = self.start_date + timedelta(days=days)
        np.random.seed(seed)
        random.seed(seed)

    def _reset_rng(self, offset: int) -> None:
        """Reset NumPy and stdlib RNGs to deterministic per-method seeds."""
        np.random.seed(self.seed + offset)
        random.seed(self.seed + offset)

    # ------------------------------------------------------------------
    # Public orchestrator
    # ------------------------------------------------------------------

    def generate_all(self, output_dir: Path = RAW_DIR) -> dict[str, Path]:
        """Generate all data domains and write to CSV files."""
        output_dir.mkdir(parents=True, exist_ok=True)
        paths: dict[str, Path] = {}

        # Generate states first — sensor generation depends on them
        print("Generating machine state events …")
        state_df = self.generate_machine_states()
        paths["machine_state"] = output_dir / "machine_states.csv"
        state_df.to_csv(paths["machine_state"], index=False)
        print(f"  → {len(state_df):,} records written to {paths['machine_state']}")

        print("Generating sensor data …")
        sensor_df = self.generate_sensor_data(state_df=state_df)
        paths["sensor"] = output_dir / "sensor_readings.csv"
        sensor_df.to_csv(paths["sensor"], index=False)
        print(f"  → {len(sensor_df):,} records written to {paths['sensor']}")

        print("Generating quality inspection records …")
        quality_df = self.generate_quality_data()
        paths["quality"] = output_dir / "quality_inspections.csv"
        quality_df.to_csv(paths["quality"], index=False)
        print(f"  → {len(quality_df):,} records written to {paths['quality']}")

        print("Generating maintenance work orders …")
        maintenance_df = self.generate_maintenance_records()
        paths["maintenance"] = output_dir / "maintenance_records.csv"
        maintenance_df.to_csv(paths["maintenance"], index=False)
        print(f"  → {len(maintenance_df):,} records written to {paths['maintenance']}")

        print("Generating ERP production orders …")
        erp_df = self.generate_erp_data()
        paths["erp"] = output_dir / "erp_production_orders.csv"
        erp_df.to_csv(paths["erp"], index=False)
        print(f"  → {len(erp_df):,} records written to {paths['erp']}")

        manifest = {
            "generated_at": datetime.utcnow().isoformat(),
            "seed": self.seed,
            "simulation_days": self.days,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "lines": LINES,
            "files": {k: str(v) for k, v in paths.items()},
            "total_records": {
                "sensor": len(sensor_df),
                "machine_state": len(state_df),
                "quality": len(quality_df),
                "maintenance": len(maintenance_df),
                "erp": len(erp_df),
            },
        }
        manifest_path = output_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"\nManifest written to {manifest_path}")
        return paths

    # ------------------------------------------------------------------
    # Machine States
    # ------------------------------------------------------------------

    def generate_machine_states(self) -> pd.DataFrame:
        """
        Generate a time-ordered event log of machine state transitions.

        State durations are drawn from:
            Running:            Exp(mean=240 min)
            Idle:               Uniform(15–90 min)
            Planned Downtime:   Uniform(30–240 min)
            Unplanned Downtime: Exp(mean=90 min)
            Maintenance Mode:   Uniform(60–480 min)
        """
        self._reset_rng(101)
        records = []
        state_duration_params = {
            "Running":            ("exp",     240),
            "Idle":               ("uniform", (15, 90)),
            "Planned Downtime":   ("uniform", (30, 240)),
            "Unplanned Downtime": ("exp",     90),
            "Maintenance Mode":   ("uniform", (60, 480)),
        }

        for line in LINES:
            current_time = self.start_date
            state = "Running"

            while current_time < self.end_date:
                dist, param = state_duration_params[state]
                if dist == "exp":
                    duration_min = np.random.exponential(param)
                else:
                    duration_min = np.random.uniform(*param)
                duration_min = max(5.0, duration_min)

                end_time = min(current_time + timedelta(minutes=duration_min), self.end_date)

                records.append({
                    "event_id": f"{line}-{len(records):06d}",
                    "line_id": line,
                    "machine_state": state,
                    "event_timestamp": current_time,
                    "end_timestamp": end_time,
                    "duration_min": round((end_time - current_time).total_seconds() / 60, 2),
                })

                current_time = end_time
                if state == "Unplanned Downtime":
                    state = "Maintenance Mode"
                elif state == "Maintenance Mode":
                    state = "Running"
                else:
                    state = np.random.choice(MACHINE_STATES, p=STATE_WEIGHTS)

        df = pd.DataFrame(records)
        df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])
        df["end_timestamp"] = pd.to_datetime(df["end_timestamp"])
        return df.sort_values(["line_id", "event_timestamp"]).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Sensor Data  (vectorized via merge_asof — O(n))
    # ------------------------------------------------------------------

    def generate_sensor_data(
        self,
        state_df: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        Generate 1-minute interval sensor readings for each production line.

        Uses pd.merge_asof to assign machine states efficiently, then generates
        sensor values per state group with NumPy vectorization.
        """
        self._reset_rng(102)
        if state_df is None:
            state_df = self.generate_machine_states()

        timestamps = pd.date_range(self.start_date, self.end_date, freq="1min")
        all_frames = []

        for line in LINES:
            ts_df = pd.DataFrame({"timestamp": timestamps, "line_id": line})

            line_states = (
                state_df[state_df["line_id"] == line]
                .sort_values("event_timestamp")[["event_timestamp", "machine_state"]]
                .rename(columns={"event_timestamp": "timestamp"})
            )
            merged = pd.merge_asof(
                ts_df.sort_values("timestamp"),
                line_states,
                on="timestamp",
                direction="backward",
            )
            merged["machine_state"] = merged["machine_state"].fillna("Idle")

            n = len(merged)
            sensor_arrays: dict[str, np.ndarray] = {
                s: np.empty(n) for s in SENSOR_VALID_RANGES
            }

            for machine_state, params in SENSOR_PARAMS.items():
                state_mask = (merged["machine_state"] == machine_state).to_numpy()
                count = int(state_mask.sum())
                if count == 0:
                    continue
                for sensor, (lo, hi, std) in params.items():
                    mean = (lo + hi) / 2.0
                    vals = np.random.normal(mean, std, size=count)
                    vals = np.clip(vals, lo * 0.5, hi * 2.0)
                    sensor_arrays[sensor][state_mask] = vals

            # Anomaly injection (~0.3% of readings)
            anomaly_mask = np.random.random(n) < 0.003
            for sensor in ("temperature_c", "vibration_mm_s"):
                multipliers = np.random.uniform(1.4, 2.2, size=n)
                sensor_arrays[sensor] = np.where(
                    anomaly_mask,
                    sensor_arrays[sensor] * multipliers,
                    sensor_arrays[sensor],
                )

            # Sensor dropout injection (~0.5% per field)
            for sensor in sensor_arrays:
                dropout = np.random.random(n) < 0.005
                vals = sensor_arrays[sensor].astype(float)
                vals[dropout] = np.nan
                merged[sensor] = np.round(vals, 3)

            merged["is_anomaly_flag"] = anomaly_mask
            all_frames.append(merged)

        df = pd.concat(all_frames, ignore_index=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df.sort_values(["timestamp", "line_id"]).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Quality Inspections
    # ------------------------------------------------------------------

    def generate_quality_data(self) -> pd.DataFrame:
        """
        Generate 30-minute aggregated quality inspection records per line.

        Pass rate varies by shift (Day > Evening > Night) and degrades
        slightly over 90 days to simulate tool wear.
        """
        self._reset_rng(103)
        records = []
        inspection_id = 0
        base_pass_rates = {"Line-A": 0.955, "Line-B": 0.930, "Line-C": 0.944}

        for line in LINES:
            ts = self.start_date
            base = base_pass_rates[line]

            while ts < self.end_date:
                shift = self._get_shift(ts)
                shift_factor = {"Day": 1.00, "Evening": 0.983, "Night": 0.965}[shift]
                days_elapsed = (ts - self.start_date).days
                degradation = 1.0 - (days_elapsed * 0.0005 / 7.0)
                pass_rate = max(0.80, min(1.0, base * shift_factor * degradation))

                total = np.random.randint(18, 42)
                passed = int(total * pass_rate)
                failed = total - passed
                scrap = int(failed * np.random.uniform(0.3, 0.7))
                rework = failed - scrap

                records.append({
                    "inspection_id": f"QI-{inspection_id:07d}",
                    "timestamp": ts,
                    "line_id": line,
                    "shift": shift,
                    "total_inspected": total,
                    "passed": passed,
                    "failed": failed,
                    "scrap_count": scrap,
                    "rework_count": rework,
                    "first_pass_yield": round(passed / total, 4),
                    "scrap_rate": round(scrap / total, 4),
                    "defect_category": np.random.choice(DEFECT_CATEGORIES) if failed > 0 else None,
                })
                inspection_id += 1
                ts += timedelta(minutes=30)

        df = pd.DataFrame(records)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df.sort_values(["timestamp", "line_id"]).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Maintenance Records
    # ------------------------------------------------------------------

    def generate_maintenance_records(self) -> pd.DataFrame:
        """Generate corrective and preventive work orders per line."""
        self._reset_rng(104)
        records = []
        wo_id = 0
        notes_corrective = [
            "Bearing replaced on main drive",
            "Pneumatic cylinder seal replaced",
            "PLC I/O module fault cleared",
            "Conveyor belt tracking realigned",
            "Motor overheating — cooling fan replaced",
            "Sensor calibration drift corrected",
            "E-stop relay contact cleaned",
        ]
        notes_preventive = [
            "Scheduled lubrication of linear guides",
            "Filter cartridge replacement — hydraulic unit",
            "Torque check on all fasteners",
            "Electrical panel thermal inspection",
            "Calibration verification — temperature sensors",
        ]

        for line in LINES:
            # Keep a non-empty maintenance dataset even for short simulations (e.g., 3-day tests)
            corrective_count = max(1, int(self.days / 30 * np.random.uniform(2.0, 3.5)))
            for _ in range(corrective_count):
                start = self.start_date + timedelta(
                    minutes=int(np.random.randint(0, self.days * 24 * 60))
                )
                duration_hr = float(np.clip(np.random.exponential(4.0), 0.5, 24.0))
                records.append({
                    "work_order_id": f"WO-{wo_id:06d}",
                    "line_id": line,
                    "maintenance_type": "Corrective",
                    "failure_category": np.random.choice(FAILURE_CATEGORIES),
                    "start_timestamp": start,
                    "end_timestamp": start + timedelta(hours=duration_hr),
                    "duration_hr": round(duration_hr, 2),
                    "technicians": int(np.random.randint(1, 4)),
                    "parts_replaced": bool(np.random.choice([True, False], p=[0.65, 0.35])),
                    "resolution_note": np.random.choice(notes_corrective),
                    "downtime_caused": True,
                })
                wo_id += 1

            preventive_count = max(1, int(self.days / 7 * np.random.uniform(1.0, 2.0)))
            for i in range(preventive_count):
                start = self.start_date + timedelta(days=i * 7 + float(np.random.uniform(0, 2)))
                duration_hr = float(np.random.uniform(1.0, 4.0))
                records.append({
                    "work_order_id": f"WO-{wo_id:06d}",
                    "line_id": line,
                    "maintenance_type": "Preventive",
                    "failure_category": None,
                    "start_timestamp": start,
                    "end_timestamp": start + timedelta(hours=duration_hr),
                    "duration_hr": round(duration_hr, 2),
                    "technicians": 1,
                    "parts_replaced": bool(np.random.choice([True, False], p=[0.30, 0.70])),
                    "resolution_note": np.random.choice(notes_preventive),
                    "downtime_caused": False,
                })
                wo_id += 1

        df = pd.DataFrame(records)
        df["start_timestamp"] = pd.to_datetime(df["start_timestamp"])
        df["end_timestamp"] = pd.to_datetime(df["end_timestamp"])
        return df.sort_values(["line_id", "start_timestamp"]).reset_index(drop=True)

    # ------------------------------------------------------------------
    # ERP Production Orders
    # ------------------------------------------------------------------

    def generate_erp_data(self) -> pd.DataFrame:
        """Generate daily production order records (planned vs. actual) per line."""
        self._reset_rng(105)
        records = []
        order_id = 0

        for line in LINES:
            current_date = self.start_date.date()
            end_date = self.end_date.date()

            while current_date < end_date:
                product = np.random.choice(PRODUCT_TYPES, p=[0.50, 0.30, 0.20])
                planned = int(np.random.uniform(600, 900))
                loss = np.random.uniform(0.02, 0.12)
                actual = int(planned * (1.0 - loss))

                records.append({
                    "order_id": f"PO-{order_id:07d}",
                    "line_id": line,
                    "order_date": current_date,
                    "product_type": product,
                    "batch_id": f"BATCH-{line[-1]}-{current_date.strftime('%Y%m%d')}",
                    "planned_units": planned,
                    "actual_units": actual,
                    "attainment_pct": round(actual / planned * 100, 2),
                    "shift": "Day",
                })
                order_id += 1
                current_date += timedelta(days=1)

        df = pd.DataFrame(records)
        df["order_date"] = pd.to_datetime(df["order_date"])
        return df.sort_values(["line_id", "order_date"]).reset_index(drop=True)

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
    print("=" * 60)
    print("Industrial IoT Data Simulator")
    print("=" * 60)
    sim = Simulator(seed=42, days=90)
    sim.generate_all()
    print("\nSimulation complete.")
