# Medallion Architecture — Bronze → Silver → Gold

```mermaid
graph LR
    subgraph Ingestion
        RAW["Raw Layer<br/>data/raw/<br/>─────────<br/>sensor_readings.csv<br/>machine_states.csv<br/>quality_inspections.csv<br/>maintenance_records.csv<br/>erp_production_orders.csv"]
    end

    subgraph Bronze["Bronze Layer  •  data/bronze/"]
        direction TB
        B1["sensor.parquet"]
        B2["machine_state.parquet"]
        B3["quality.parquet"]
        B4["maintenance.parquet"]
        B5["erp.parquet"]
        BMETA["+ _loaded_at<br/>+ _source_file<br/>+ _row_hash"]
    end

    subgraph Silver["Silver Layer  •  data/silver/"]
        direction TB
        S1["sensor.parquet<br/>─────────────────<br/>✓ Timestamps parsed<br/>✓ Duplicates removed<br/>✓ Missing values imputed<br/>✓ Range checks flagged<br/>✓ Shift/week enriched"]
        S2["machine_state.parquet<br/>─────────────────<br/>✓ State labels validated<br/>✓ Overlap detection<br/>✓ Duration checks"]
        S3["quality.parquet<br/>─────────────────<br/>✓ Totals consistency<br/>✓ FPY range validated<br/>✓ Date fields enriched"]
        S4["maintenance.parquet<br/>─────────────────<br/>✓ Duration > 0 checked<br/>✓ Type labels validated"]
        S5["erp.parquet<br/>─────────────────<br/>✓ Attainment range check<br/>✓ Date fields enriched"]
    end

    subgraph Gold["Gold Layer  •  data/gold/"]
        direction TB
        G1["oee_daily.parquet<br/>─────────────────<br/>OEE · Availability<br/>Performance · Quality<br/>per line per day"]
        G2["reliability_kpis.parquet<br/>─────────────────<br/>MTBF · MTTR<br/>Availability<br/>per line (period)"]
        G3["quality_kpis.parquet<br/>─────────────────<br/>FPY · Scrap Rate<br/>Total Scrap · Rework<br/>per line per day"]
        G4["maintenance_summary.parquet<br/>─────────────────<br/>WO count · Avg duration<br/>Corrective vs Preventive<br/>per line"]
        G5["production_attainment.parquet<br/>─────────────────<br/>Planned vs Actual<br/>Attainment %<br/>per line per week"]
        G6["quality_scores.parquet<br/>─────────────────<br/>Completeness · Validity<br/>Consistency · Uniqueness<br/>Freshness · Composite<br/>per data domain"]
    end

    RAW -->|"Load + metadata"| Bronze
    B1 -->|"Clean + validate"| S1
    B2 -->|"Clean + validate"| S2
    B3 -->|"Clean + validate"| S3
    B4 -->|"Clean + validate"| S4
    B5 -->|"Clean + validate"| S5
    S1 & S2 -->|"Aggregate"| G1
    S2 -->|"Aggregate"| G2
    S3 -->|"Aggregate"| G3
    S4 -->|"Aggregate"| G4
    S5 -->|"Aggregate"| G5
    S1 & S2 & S3 & S4 & S5 -->|"Quality checks"| G6

    classDef raw fill:#7F8C8D,color:#fff,stroke:#7F8C8D
    classDef bronze fill:#CD7F32,color:#fff,stroke:#CD7F32
    classDef silver fill:#A8A9AD,color:#fff,stroke:#A8A9AD
    classDef gold fill:#C9A227,color:#fff,stroke:#C9A227

    class RAW raw
    class B1,B2,B3,B4,B5,BMETA bronze
    class S1,S2,S3,S4,S5 silver
    class G1,G2,G3,G4,G5,G6 gold
```

## Layer Responsibilities

### Bronze — Preserve

The Bronze layer's only job is to capture what arrived and when.

- Every raw record is stored without modification
- Load timestamp (`_loaded_at`) allows replay and audit
- Row hashes (`_row_hash`) enable change-data-capture patterns
- No filtering, no transformation — exactly as received

### Silver — Trust

The Silver layer makes data reliable enough for analytics.

Key operations:

| Operation | Why it matters |
|-----------|---------------|
| Timestamp normalization | Inconsistent clock formats break joins and aggregations |
| Deduplication | Double-counted records corrupt KPIs |
| Missing value imputation | Forward-fill within line preserves temporal context |
| Range validation | Out-of-range sensor values flag potential sensor faults |
| State label validation | Invalid states indicate upstream system issues |
| Consistency checks | Totals that don't add up indicate data integrity problems |

Silver rows carry `_is_valid` flags. Downstream Gold tables use only valid rows.

### Gold — Decide

The Gold layer produces business-ready aggregates that the dashboard and KPI engine consume directly.

- Pre-computed OEE with all three components (Availability × Performance × Quality)
- Reliability metrics (MTBF, MTTR, Availability) per asset
- Daily quality KPIs (FPY, scrap rate) per line
- Weekly production attainment vs. plan
- Data quality scores per domain (consumed by the Quality Dashboard)

Gold tables are stable, small, and fast to query — optimized for Streamlit, Power BI, or SQL queries in production.
