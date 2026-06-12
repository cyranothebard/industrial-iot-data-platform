#!/usr/bin/env python3
"""
run_pipeline.py — Full end-to-end pipeline runner
==================================================
Executes all stages in sequence:

    1. Generate simulated industrial data (raw CSVs)
    2. Run Bronze → Silver → Gold pipeline
    3. Run data quality assessment
    4. Print KPI summary

Usage:
    python run_pipeline.py [--days N] [--seed N]
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    parser = argparse.ArgumentParser(description="Industrial IoT Data Platform pipeline runner")
    parser.add_argument("--days", type=int, default=90, help="Simulation days (default: 90)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("Industrial IoT Data Platform")
    print("BridgeOps AI — Portfolio Project #2")
    print("=" * 60)

    # Stage 1: Simulate
    print(f"\n[Stage 1] Generating {args.days}-day simulation (seed={args.seed}) …")
    from src.ingestion.simulator import Simulator
    sim = Simulator(seed=args.seed, days=args.days)
    sim.generate_all()

    # Stage 2: Pipeline
    print("\n[Stage 2] Running Medallion pipeline …")
    from src.processing.pipeline import Pipeline
    pipeline = Pipeline()
    pipeline.run()

    # Stage 3: Quality
    print("\n[Stage 3] Running data quality assessment …")
    from src.quality.checks import DataQualityChecker
    checker = DataQualityChecker()
    checker.run_all()

    # Stage 4: KPI summary
    print("\n[Stage 4] Computing KPIs …")
    from src.analytics.kpis import KPIEngine
    engine = KPIEngine()
    engine.print_summary()

    print("\n" + "=" * 60)
    print("Pipeline complete.")
    print("To launch the dashboard: streamlit run src/dashboard/app.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
