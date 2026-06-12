# Data Dictionary — Industrial IoT Data Platform

## Overview

This document describes all datasets generated and processed by the platform.

---

## Raw / Bronze Layer

### sensor_readings

One row per production line per minute. Core operational telemetry.

| Field | Type | Description | Valid Range |
|-------|------|-------------|------------|
| `timestamp` | datetime | UTC minute-resolution reading time | — |
| `line_id` | string | Production line identifier | Line-A, Line-B, Line-C |
| `machine_state` | string | Current operational state | See machine states |
| `temperature_c` | float | Equipment temperature (°C) | 0–200 |
| `pressure_bar` | float | System pressure (bar) | 0–15 |
| `vibration_mm_s` | float | Vibration velocity (mm/s) | 0–30 |
| `power_kw` | float | Electrical power draw (kW) | 0–400 |
| `throughput_units_hr` | float | Units produced per hour | 0–200 |
| `is_anomaly_flag` | bool | Deliberate anomaly injected by simulator | — |

### machine_states

Event log of state transitions. One row per state period.

| Field | Type | Description |
|-------|------|-------------|
| `event_id` | string | Unique event identifier |
| `line_id` | string | Production line |
| `machine_state` | string | State during this period |
| `event_timestamp` | datetime | State start time |
| `end_timestamp` | datetime | State end time |
| `duration_min` | float | Duration in minutes |

**Valid machine states:**

| State | Meaning |
|-------|---------|
| `Running` | Normal production |
| `Idle` | Powered but not producing |
| `Planned Downtime` | Scheduled maintenance window |
| `Unplanned Downtime` | Unexpected failure / stop |
| `Maintenance Mode` | Active maintenance in progress |

### quality_inspections

30-minute aggregated inspection records per line.

| Field | Type | Description |
|-------|------|-------------|
| `inspection_id` | string | Unique inspection batch ID |
| `timestamp` | datetime | Inspection period start |
| `line_id` | string | Production line |
| `shift` | string | Day / Evening / Night |
| `total_inspected` | int | Units inspected |
| `passed` | int | Units passing inspection |
| `failed` | int | Units failing inspection |
| `scrap_count` | int | Failed units scrapped |
| `rework_count` | int | Failed units sent for rework |
| `first_pass_yield` | float | passed / total_inspected |
| `scrap_rate` | float | scrap_count / total_inspected |
| `defect_category` | string | Primary defect type (null if no failures) |

**Defect categories:** Surface Scratch, Dimensional Out of Tolerance, Weld Defect, Assembly Error, Material Defect

### maintenance_records

Individual work orders for corrective and preventive maintenance.

| Field | Type | Description |
|-------|------|-------------|
| `work_order_id` | string | Unique work order ID |
| `line_id` | string | Production line |
| `maintenance_type` | string | Corrective / Preventive |
| `failure_category` | string | Failure type (null for Preventive) |
| `start_timestamp` | datetime | Work start time |
| `end_timestamp` | datetime | Work completion time |
| `duration_hr` | float | Duration in hours |
| `technicians` | int | Technician count |
| `parts_replaced` | bool | Whether parts were replaced |
| `resolution_note` | string | Free-text resolution description |
| `downtime_caused` | bool | Whether this WO caused production downtime |

**Failure categories:** Electrical, Mechanical, Pneumatic, Software, Operator Error

### erp_production_orders

Daily production orders from ERP/MES.

| Field | Type | Description |
|-------|------|-------------|
| `order_id` | string | Unique order ID |
| `line_id` | string | Production line |
| `order_date` | date | Production date |
| `product_type` | string | Product-Alpha / Product-Beta / Product-Gamma |
| `batch_id` | string | Batch identifier |
| `planned_units` | int | Planned production quantity |
| `actual_units` | int | Actual units produced |
| `attainment_pct` | float | actual / planned × 100 |

---

## Gold Layer — KPI Datasets

### oee_daily

Daily OEE components per line.

| Field | Description |
|-------|-------------|
| `line_id` | Production line |
| `date` | Date |
| `availability` | Running time / (Running + Unplanned Downtime) |
| `performance` | Avg throughput / Ideal throughput (95 units/hr) |
| `quality` | Baseline quality factor (0.948) |
| `oee` | Availability × Performance × Quality |

### reliability_kpis

Period-level reliability metrics per line.

| Field | Description |
|-------|-------------|
| `line_id` | Production line |
| `n_failure_events` | Total unplanned downtime events |
| `total_running_hr` | Total running time (hours) |
| `total_repair_hr` | Total repair time (hours) |
| `mtbf_hr` | Mean Time Between Failures (hours) |
| `mttr_hr` | Mean Time To Repair (hours) |
| `availability` | MTBF / (MTBF + MTTR) |

### quality_scores

Data quality assessment results per domain.

| Field | Description |
|-------|-------------|
| `domain` | Data domain (sensor, machine_state, quality, maintenance, erp) |
| `row_count` | Number of rows assessed |
| `composite_score` | Weighted average of 5 dimension scores (0–100) |
| `score_completeness` | % of required fields non-null |
| `score_validity` | % of records with values in valid range |
| `score_consistency` | % of records internally consistent |
| `score_uniqueness` | % of records without duplicates |
| `score_freshness` | % of records with valid timestamps |
| `assessed_at` | Assessment timestamp |

---

## Simulation Parameters

| Parameter | Value |
|-----------|-------|
| Random seed | 42 |
| Simulation period | 90 days |
| Start date | 2025-01-01 06:00 UTC |
| Production lines | Line-A, Line-B, Line-C |
| Sensor frequency | 1-minute intervals |
| Inspection frequency | 30-minute intervals |
| Ideal throughput | 95 units/hr |
| Sensor NaN injection rate | 0.5% per field |
| Anomaly injection rate | 0.3% of sensor readings |
| Base pass rate by line | Line-A: 95.5%, Line-B: 93.0%, Line-C: 94.4% |
