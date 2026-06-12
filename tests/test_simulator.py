"""Tests for the data ingestion simulator."""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.simulator import Simulator, LINES, MACHINE_STATES, SENSOR_VALID_RANGES


class TestSimulator:
    def setup_method(self):
        self.sim = Simulator(seed=42, days=7)

    def test_sensor_data_shape(self):
        df = self.sim.generate_sensor_data()
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert "timestamp" in df.columns
        assert "line_id" in df.columns
        for line in LINES:
            assert line in df["line_id"].unique()

    def test_sensor_data_columns(self):
        df = self.sim.generate_sensor_data()
        expected_sensors = [
            "temperature_c", "pressure_bar", "vibration_mm_s",
            "power_kw", "throughput_units_hr"
        ]
        for col in expected_sensors:
            assert col in df.columns, f"Missing sensor column: {col}"

    def test_sensor_values_mostly_in_range(self):
        df = self.sim.generate_sensor_data()
        running = df[df["machine_state"] == "Running"]
        # At least 90% of running-state readings should be in valid range
        temp_valid = running["temperature_c"].dropna().between(0, 200)
        assert temp_valid.mean() >= 0.90

    def test_machine_states_valid_labels(self):
        df = self.sim.generate_machine_states()
        invalid = ~df["machine_state"].isin(MACHINE_STATES)
        assert invalid.sum() == 0

    def test_machine_state_durations_positive(self):
        df = self.sim.generate_machine_states()
        assert (df["duration_min"] > 0).all()

    def test_machine_state_end_after_start(self):
        df = self.sim.generate_machine_states()
        assert (df["end_timestamp"] > df["event_timestamp"]).all()

    def test_quality_fpy_in_range(self):
        df = self.sim.generate_quality_data()
        assert df["first_pass_yield"].between(0.0, 1.0).all()

    def test_quality_totals_consistent(self):
        df = self.sim.generate_quality_data()
        assert (df["passed"] + df["failed"] == df["total_inspected"]).all()

    def test_quality_scrap_rework_consistent(self):
        df = self.sim.generate_quality_data()
        assert (df["scrap_count"] + df["rework_count"] == df["failed"]).all()

    def test_maintenance_records_types(self):
        df = self.sim.generate_maintenance_records()
        valid_types = {"Corrective", "Preventive", "Emergency"}
        assert df["maintenance_type"].isin(valid_types).all()

    def test_maintenance_duration_positive(self):
        df = self.sim.generate_maintenance_records()
        assert (df["duration_hr"] > 0).all()

    def test_erp_attainment_realistic(self):
        df = self.sim.generate_erp_data()
        assert df["attainment_pct"].between(50, 110).all()

    def test_erp_all_lines_present(self):
        df = self.sim.generate_erp_data()
        for line in LINES:
            assert line in df["line_id"].unique()

    def test_deterministic_with_seed(self):
        sim1 = Simulator(seed=123, days=3)
        sim2 = Simulator(seed=123, days=3)
        df1 = sim1.generate_quality_data()
        df2 = sim2.generate_quality_data()
        pd.testing.assert_frame_equal(df1, df2)
