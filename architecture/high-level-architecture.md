# High-Level Architecture — Industrial IoT Data Platform

## Platform Overview

```mermaid
graph TB
    subgraph Sources["Industrial Data Sources"]
        PLC["PLC / SCADA<br/>Machine Sensors"]
        QI["Quality<br/>Inspection Stations"]
        MAINT["Maintenance<br/>Systems (CMMS)"]
        ERP["ERP / MES<br/>Production Planning"]
    end

    subgraph Ingestion["Ingestion Layer"]
        SIM["Python Simulator<br/>(src/ingestion/simulator.py)"]
        RAW["Raw Data<br/>CSV / JSON / Parquet<br/>data/raw/"]
    end

    subgraph Processing["Processing Layer (Medallion)"]
        BRONZE["Bronze<br/>Raw preserved data<br/>+ load metadata<br/>data/bronze/"]
        SILVER["Silver<br/>Validated · Deduplicated<br/>Timestamp-normalized<br/>data/silver/"]
        GOLD["Gold<br/>Business-ready KPIs<br/>Aggregated datasets<br/>data/gold/"]
    end

    subgraph Quality["Data Quality Layer"]
        QC["Quality Checker<br/>(src/quality/checks.py)"]
        QS["Quality Scores<br/>5 dimensions per domain<br/>data/gold/quality_scores.parquet"]
    end

    subgraph Analytics["Analytics Layer"]
        KPI["KPI Engine<br/>(src/analytics/kpis.py)"]
    end

    subgraph Dashboard["Dashboard Layer"]
        DASH["Streamlit Dashboard<br/>(src/dashboard/app.py)"]
        P1["Operations Overview<br/>OEE · Throughput · Attainment"]
        P2["Reliability Dashboard<br/>MTBF · MTTR · Availability"]
        P3["Data Quality Dashboard<br/>Quality scores · Anomalies"]
    end

    subgraph Future["Future AI Layer"]
        PdM["Predictive Maintenance<br/>ML Models"]
        CV["Computer Vision<br/>Quality Inspection"]
        LLM["Engineering Assistant<br/>Generative AI / RAG"]
    end

    PLC --> SIM
    QI --> SIM
    MAINT --> SIM
    ERP --> SIM
    SIM --> RAW
    RAW --> BRONZE
    BRONZE --> SILVER
    SILVER --> GOLD
    SILVER --> QC
    QC --> QS
    GOLD --> KPI
    QS --> KPI
    KPI --> DASH
    DASH --> P1
    DASH --> P2
    DASH --> P3
    GOLD -.->|"Feature tables (future)"| PdM
    GOLD -.->|"Image metadata (future)"| CV
    GOLD -.->|"Knowledge base (future)"| LLM

    classDef source fill:#1A3A5C,color:#fff,stroke:#1A3A5C
    classDef ingestion fill:#E87722,color:#fff,stroke:#E87722
    classDef bronze fill:#CD7F32,color:#fff,stroke:#CD7F32
    classDef silver fill:#A8A9AD,color:#fff,stroke:#A8A9AD
    classDef gold fill:#FFD700,color:#333,stroke:#FFD700
    classDef quality fill:#2ECC71,color:#fff,stroke:#2ECC71
    classDef analytics fill:#3498DB,color:#fff,stroke:#3498DB
    classDef dashboard fill:#9B59B6,color:#fff,stroke:#9B59B6
    classDef future fill:#ECF0F1,color:#999,stroke:#BDC3C7,stroke-dasharray:5 5

    class PLC,QI,MAINT,ERP source
    class SIM,RAW ingestion
    class BRONZE bronze
    class SILVER silver
    class GOLD gold
    class QC,QS quality
    class KPI analytics
    class DASH,P1,P2,P3 dashboard
    class PdM,CV,LLM future
```

## Data Flow Summary

| Stage | Input | Output | Key Operations |
|-------|-------|--------|----------------|
| **Ingestion** | Industrial systems | Raw CSV/Parquet | Simulate 5 data domains across 3 lines for 90 days |
| **Bronze** | Raw files | `data/bronze/*.parquet` | Preserve raw data + add load metadata, row hashes |
| **Silver** | Bronze Parquet | `data/silver/*.parquet` | Validate, deduplicate, impute, normalize timestamps |
| **Gold** | Silver Parquet | `data/gold/*.parquet` | Aggregate into business KPIs: OEE, MTBF, FPY etc. |
| **Quality** | Silver Parquet | `quality_scores.parquet` | Score 5 quality dimensions per domain |
| **Analytics** | Gold Parquet | DataFrames / charts | Compute reliability, production, maintenance KPIs |
| **Dashboard** | Analytics | Streamlit UI | 3-page interactive operational dashboard |

## Technology Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Ingestion | Python / NumPy | Deterministic simulation, realistic distributions |
| Processing | Pandas + PyArrow | Medallion architecture (Bronze/Silver/Gold) |
| Storage | Parquet (local) | Designed for Databricks Delta Lake in production |
| Quality | Custom checks | ISO 25012 / DAMA-inspired 5-dimension scoring |
| Analytics | Pandas | KPI computation from Gold layer |
| Dashboard | Streamlit + Plotly | 3-page interactive operational views |
| Testing | pytest | Unit + integration test coverage |
| Containers | Docker + Compose | Single-command deployment |

## Production Evolution Path

```
Current (MVP)           → Next Step              → Production Target
─────────────────────────────────────────────────────────────────────
Local Parquet files     → Delta Lake (OSS)       → Databricks Lakehouse
Pandas processing       → PySpark                → Databricks Workflows
Simulated data          → Real PLC / OPC-UA      → Industrial IoT Hub
Streamlit dashboard     → Power BI               → Power BI + Embedded
Manual pipeline run     → Scheduled jobs         → Databricks Jobs / ADF
```
