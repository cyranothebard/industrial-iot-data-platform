"""Tests for the Bronze → Silver → Gold processing pipeline."""

import pytest
import pandas as pd
import tempfile
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.simulator import Simulator
from src.processing.pipeline import Pipeline


@pytest.fixture(scope="module")
def tmp_dirs(tmp_path_factory):
    """Generate raw data into a temp directory and run the pipeline."""
    base = tmp_path_factory.mktemp("data")
    raw = base / "raw"
    raw.mkdir()
    # Generate 3 days of data for speed
    sim = Simulator(seed=99, days=3)
    sim.generate_all(output_dir=raw)
    return base, raw


@pytest.fixture(scope="module")
def pipeline_results(tmp_dirs):
    base, raw = tmp_dirs
    # Monkey-patch dirs
    import src.processing.pipeline as pipe_module
    orig_raw    = pipe_module.RAW_DIR
    orig_bronze = pipe_module.BRONZE_DIR
    orig_silver = pipe_module.SILVER_DIR
    orig_gold   = pipe_module.GOLD_DIR

    pipe_module.RAW_DIR    = raw
    pipe_module.BRONZE_DIR = base / "bronze"
    pipe_module.SILVER_DIR = base / "silver"
    pipe_module.GOLD_DIR   = base / "gold"

    p = Pipeline(raw_dir=raw)
    results = p.run()

    pipe_module.RAW_DIR    = orig_raw
    pipe_module.BRONZE_DIR = orig_bronze
    pipe_module.SILVER_DIR = orig_silver
    pipe_module.GOLD_DIR   = orig_gold
    return results


class TestBronzeLayer:
    def test_bronze_keys_present(self, pipeline_results):
        assert "bronze" in pipeline_results
        for domain in ("sensor", "machine_state", "quality", "maintenance", "erp"):
            assert domain in pipeline_results["bronze"]

    def test_bronze_has_metadata(self, pipeline_results):
        df = pipeline_results["bronze"]["sensor"]
        assert "_loaded_at" in df.columns
        assert "_source_file" in df.columns
        assert "_row_hash" in df.columns

    def test_bronze_no_data_loss(self, pipeline_results):
        # Bronze should preserve all raw rows
        bronze_sensor = pipeline_results["bronze"]["sensor"]
        assert len(bronze_sensor) > 0


class TestSilverLayer:
    def test_silver_sensor_has_validity_flags(self, pipeline_results):
        df = pipeline_results["silver"]["sensor"]
        assert "_is_valid" in df.columns

    def test_silver_sensor_no_nulls_in_sensor_cols(self, pipeline_results):
        """After imputation, sensor columns should have no nulls."""
        df = pipeline_results["silver"]["sensor"]
        sensor_cols = [
            "temperature_c", "pressure_bar", "vibration_mm_s",
            "power_kw", "throughput_units_hr"
        ]
        for col in sensor_cols:
            null_count = df[col].isna().sum()
            assert null_count == 0, f"{col} still has {null_count} nulls after imputation"

    def test_silver_machine_states_overlap_flag(self, pipeline_results):
        df = pipeline_results["silver"]["machine_state"]
        assert "_overlap" in df.columns

    def test_silver_quality_consistency_flag(self, pipeline_results):
        df = pipeline_results["silver"]["quality"]
        assert "_totals_consistent" in df.columns
        assert df["_totals_consistent"].all()

    def test_silver_sensor_dedup(self, pipeline_results):
        df = pipeline_results["silver"]["sensor"]
        dupes = df.duplicated(subset=["timestamp", "line_id"]).sum()
        assert dupes == 0


class TestGoldLayer:
    def test_gold_oee_columns(self, pipeline_results):
        df = pipeline_results["gold"]["oee_daily"]
        for col in ("line_id", "date", "oee", "availability", "performance", "quality"):
            assert col in df.columns

    def test_gold_oee_in_range(self, pipeline_results):
        df = pipeline_results["gold"]["oee_daily"]
        assert df["oee"].between(0.0, 1.0).all()
        assert df["availability"].between(0.0, 1.0).all()

    def test_gold_reliability_kpis(self, pipeline_results):
        df = pipeline_results["gold"]["reliability_kpis"]
        for col in ("line_id", "mtbf_hr", "mttr_hr", "availability"):
            assert col in df.columns

    def test_gold_reliability_mtbf_positive(self, pipeline_results):
        df = pipeline_results["gold"]["reliability_kpis"]
        assert (df["mtbf_hr"] > 0).all()

    def test_gold_quality_kpis_fpy_range(self, pipeline_results):
        df = pipeline_results["gold"]["quality_kpis"]
        assert df["first_pass_yield"].between(0.0, 1.0).all()
