"""Tests for the data quality checking layer."""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.quality.checks import DataQualityChecker


class TestDataQualityChecker:
    """Unit tests for individual quality dimension methods."""

    def setup_method(self):
        self.checker = DataQualityChecker()

    # ------------------------------------------------------------------
    # Completeness
    # ------------------------------------------------------------------

    def test_completeness_all_present(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        score = self.checker._completeness_score(df, ["a", "b"])
        assert score == 100.0

    def test_completeness_with_nulls(self):
        df = pd.DataFrame({"a": [1, None, 3], "b": [4, 5, None]})
        score = self.checker._completeness_score(df, ["a", "b"])
        # 4 out of 6 cells non-null
        assert abs(score - 66.67) < 0.1

    def test_completeness_empty_df(self):
        df = pd.DataFrame({"a": []})
        score = self.checker._completeness_score(df, ["a"])
        assert score == 0.0

    # ------------------------------------------------------------------
    # Composite score
    # ------------------------------------------------------------------

    def test_composite_equal_weights(self):
        checks = {
            "completeness": 100.0,
            "validity": 80.0,
            "consistency": 90.0,
            "uniqueness": 100.0,
            "freshness": 95.0,
        }
        score = self.checker._composite(checks)
        assert 80.0 <= score <= 100.0

    def test_composite_perfect_score(self):
        checks = {k: 100.0 for k in ["completeness", "validity", "consistency", "uniqueness", "freshness"]}
        assert self.checker._composite(checks) == 100.0

    # ------------------------------------------------------------------
    # IQR anomaly detection
    # ------------------------------------------------------------------

    def test_iqr_no_anomalies(self):
        df = pd.DataFrame({"temp": np.ones(100) * 80.0})
        counts = self.checker._iqr_anomaly_counts(df, ["temp"])
        assert counts["temp"] == 0

    def test_iqr_detects_outliers(self):
        vals = list(np.ones(96) * 80.0) + [200.0, 200.0, 200.0, 200.0]
        df = pd.DataFrame({"temp": vals})
        counts = self.checker._iqr_anomaly_counts(df, ["temp"])
        assert counts["temp"] >= 4

    # ------------------------------------------------------------------
    # Issue identification
    # ------------------------------------------------------------------

    def test_identify_issues_below_threshold(self):
        checks = {"completeness": 70.0, "validity": 99.0}
        issues = self.checker._identify_issues(pd.DataFrame(), checks)
        assert any("Completeness" in i for i in issues)
        assert not any("Validity" in i for i in issues)

    def test_identify_issues_all_passing(self):
        checks = {
            "completeness": 99.0,
            "validity": 99.0,
            "consistency": 99.0,
            "uniqueness": 99.5,
            "freshness": 99.0,
        }
        issues = self.checker._identify_issues(pd.DataFrame(), checks)
        assert len(issues) == 0

    # ------------------------------------------------------------------
    # Sensor check integration
    # ------------------------------------------------------------------

    def test_sensor_check_returns_required_keys(self):
        # Build minimal valid sensor DataFrame
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-01-01", periods=10, freq="1min"),
            "line_id": ["Line-A"] * 10,
            "machine_state": ["Running"] * 10,
            "temperature_c": np.full(10, 95.0),
            "pressure_bar": np.full(10, 4.0),
            "vibration_mm_s": np.full(10, 3.0),
            "power_kw": np.full(10, 120.0),
            "throughput_units_hr": np.full(10, 75.0),
        })
        result = self.checker._check_sensor(df)
        for key in ("domain", "row_count", "checks", "composite_score", "anomaly_summary", "issues"):
            assert key in result

    def test_sensor_check_perfect_data(self):
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-01-01", periods=20, freq="1min"),
            "line_id": ["Line-A"] * 20,
            "machine_state": ["Running"] * 20,
            "temperature_c": np.full(20, 95.0),
            "pressure_bar": np.full(20, 4.0),
            "vibration_mm_s": np.full(20, 3.0),
            "power_kw": np.full(20, 120.0),
            "throughput_units_hr": np.full(20, 75.0),
        })
        result = self.checker._check_sensor(df)
        assert result["composite_score"] >= 95.0

    def test_sensor_check_with_out_of_range(self):
        """Out-of-range values should lower the validity score."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-01-01", periods=10, freq="1min"),
            "line_id": ["Line-A"] * 10,
            "machine_state": ["Running"] * 10,
            "temperature_c": [95.0] * 5 + [999.0] * 5,  # 5 out of range
            "pressure_bar": np.full(10, 4.0),
            "vibration_mm_s": np.full(10, 3.0),
            "power_kw": np.full(10, 120.0),
            "throughput_units_hr": np.full(10, 75.0),
        })
        result = self.checker._check_sensor(df)
        # Validity should be below perfect
        assert result["checks"]["validity"] < 100.0
