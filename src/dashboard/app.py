"""
Operational Dashboard — Streamlit Application
==============================================
Three-page operational dashboard built on the Industrial IoT Data Platform:

    Page 1: Operations Overview
        - Overall OEE gauge
        - Throughput trend by line
        - Production attainment (planned vs actual)
        - Downtime breakdown by category

    Page 2: Reliability Dashboard
        - MTBF / MTTR / Availability table per asset
        - Availability trend over time
        - Corrective vs Preventive maintenance ratio

    Page 3: Data Quality Dashboard
        - Composite quality score per domain
        - Dimension breakdown (completeness, validity, consistency …)
        - Sensor anomaly counts
        - IQR outlier alert table

Run with:
    streamlit run src/dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Ensure project root is on sys.path when running via streamlit
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analytics.kpis import KPIEngine
from src.quality.checks import DataQualityChecker

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Industrial IoT Data Platform | BridgeOps AI",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

BRAND_COLOR = "#1A3A5C"
ACCENT      = "#E87722"
GREEN       = "#2ECC71"
YELLOW      = "#F1C40F"
RED         = "#E74C3C"

# Streamlit compatibility: older installs expose st.cache but not st.cache_data.
cache_data = getattr(st, "cache_data", st.cache)
divider = getattr(st, "divider", lambda: st.markdown("---"))

# ---------------------------------------------------------------------------
# Load data (cached)
# ---------------------------------------------------------------------------

@cache_data(ttl=300)
def load_kpis() -> dict:
    engine = KPIEngine()
    return engine.compute_all()


@cache_data(ttl=300)
def load_quality_report() -> dict:
    checker = DataQualityChecker()
    return checker.run_all()


@cache_data(ttl=300)
def load_sensor_sample() -> pd.DataFrame:
    path = PROJECT_ROOT / "data" / "silver" / "sensor.parquet"
    if path.exists():
        df = pd.read_parquet(path)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar() -> str:
    with st.sidebar:
        st.markdown(
            f"""
            <div style='text-align:center; padding: 12px 0 8px 0;'>
                <span style='font-size:2rem;'>🏭</span>
                <h2 style='color:{BRAND_COLOR}; margin:4px 0 0 0; font-size:1.1rem;'>
                    Industrial IoT<br>Data Platform
                </h2>
                <p style='color:#888; font-size:0.78rem; margin:4px 0;'>BridgeOps AI · Portfolio Project</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        divider()
        page = st.radio(
            "Navigation",
            [
                "🏠 Operations Overview",
                "🔧 Reliability Dashboard",
                "📊 Data Quality Dashboard",
            ],
        )
        divider()
        st.caption(
            "Simulation: 3 production lines · 90 days · "
            "seed=42\n\nData flows from raw sensors through "
            "Bronze → Silver → Gold before appearing here."
        )
    return page


# ---------------------------------------------------------------------------
# Page 1 — Operations Overview
# ---------------------------------------------------------------------------

def page_operations_overview(kpis: dict) -> None:
    st.title("Operations Overview")
    st.caption("Production performance, OEE, and downtime across all lines · 90-day simulation")

    oee_daily = kpis.get("oee_daily", pd.DataFrame())
    production = kpis.get("production", pd.DataFrame())
    downtime = kpis.get("downtime", pd.DataFrame())

    # --- Top KPI tiles ---
    if not oee_daily.empty:
        overall_oee = oee_daily["oee"].mean()
        overall_avail = oee_daily["availability"].mean()
        overall_perf = oee_daily["performance"].mean()
    else:
        overall_oee = overall_avail = overall_perf = 0.0

    if not production.empty:
        avg_attainment = production["attainment_pct"].mean()
    else:
        avg_attainment = 0.0

    col1, col2, col3, col4 = st.columns(4)
    _metric(col1, "Overall OEE", f"{overall_oee * 100:.1f}%", delta="World-class ≥ 85%")
    _metric(col2, "Availability", f"{overall_avail * 100:.1f}%")
    _metric(col3, "Performance", f"{overall_perf * 100:.1f}%")
    _metric(col4, "Plan Attainment", f"{avg_attainment:.1f}%")

    divider()

    # --- OEE trend ---
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.subheader("OEE Trend by Line")
        if not oee_daily.empty:
            fig = px.line(
                oee_daily,
                x="date", y="oee", color="line_id",
                labels={"date": "Date", "oee": "OEE", "line_id": "Line"},
                color_discrete_sequence=[BRAND_COLOR, ACCENT, GREEN],
            )
            fig.update_traces(line_width=2)
            fig.add_hline(y=0.85, line_dash="dot", line_color="gray",
                          annotation_text="World-class (85%)", annotation_position="bottom right")
            fig.update_layout(
                yaxis_tickformat=".0%", height=320,
                legend=dict(orientation="h", y=-0.2),
                margin=dict(l=0, r=0, t=20, b=0),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("OEE data not available — run the pipeline first.")

    with col_right:
        st.subheader("OEE by Line (avg)")
        if not oee_daily.empty:
            oee_summary = (
                oee_daily.groupby("line_id")["oee"].mean().reset_index()
                .rename(columns={"oee": "avg_oee"})
            )
            oee_summary["avg_oee_pct"] = (oee_summary["avg_oee"] * 100).round(1)
            fig_bar = px.bar(
                oee_summary,
                x="line_id", y="avg_oee_pct", color="line_id",
                labels={"avg_oee_pct": "OEE %", "line_id": ""},
                color_discrete_sequence=[BRAND_COLOR, ACCENT, GREEN],
                text_auto=True,
            )
            fig_bar.update_layout(
                height=320, showlegend=False,
                margin=dict(l=0, r=0, t=20, b=0),
                yaxis=dict(range=[0, 100]),
            )
            st.plotly_chart(fig_bar, use_container_width=True)

    divider()

    # --- Downtime breakdown ---
    col_dl, col_dr = st.columns(2)

    with col_dl:
        st.subheader("Downtime by Category (all lines)")
        if not downtime.empty:
            total_downtime = downtime.groupby("machine_state")["total_downtime_min"].sum().reset_index()
            total_downtime["hours"] = (total_downtime["total_downtime_min"] / 60).round(1)
            fig_pie = px.pie(
                total_downtime,
                names="machine_state", values="hours",
                hole=0.45,
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            fig_pie.update_traces(textinfo="percent+label")
            fig_pie.update_layout(height=300, margin=dict(l=0, r=0, t=20, b=0), showlegend=False)
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Downtime data not available.")

    with col_dr:
        st.subheader("Weekly Production Attainment")
        if not production.empty:
            fig_att = px.line(
                production,
                x="week", y="attainment_pct", color="line_id",
                labels={"week": "Week", "attainment_pct": "Attainment %", "line_id": "Line"},
                color_discrete_sequence=[BRAND_COLOR, ACCENT, GREEN],
            )
            fig_att.add_hline(y=95.0, line_dash="dot", line_color="gray",
                              annotation_text="Target (95%)")
            fig_att.update_layout(
                height=300, legend=dict(orientation="h", y=-0.2),
                margin=dict(l=0, r=0, t=20, b=0),
            )
            st.plotly_chart(fig_att, use_container_width=True)
        else:
            st.info("Production data not available.")


# ---------------------------------------------------------------------------
# Page 2 — Reliability Dashboard
# ---------------------------------------------------------------------------

def page_reliability(kpis: dict) -> None:
    st.title("Reliability Dashboard")
    st.caption("MTBF, MTTR, asset availability, and maintenance activity · 90-day simulation")

    reliability = kpis.get("reliability", pd.DataFrame())
    maint_kpis  = kpis.get("maintenance", pd.DataFrame())
    oee_daily   = kpis.get("oee_daily", pd.DataFrame())

    # --- Reliability KPI tiles ---
    if not reliability.empty:
        avg_mtbf = reliability["mtbf_hr"].mean()
        avg_mttr = reliability["mttr_hr"].mean()
        avg_avail = reliability["availability"].mean()
        total_failures = reliability["n_failure_events"].sum()
    else:
        avg_mtbf = avg_mttr = avg_avail = total_failures = 0

    col1, col2, col3, col4 = st.columns(4)
    _metric(col1, "Avg MTBF", f"{avg_mtbf:.1f} hr", help_text="Mean Time Between Failures")
    _metric(col2, "Avg MTTR", f"{avg_mttr:.1f} hr", help_text="Mean Time To Repair")
    _metric(col3, "Avg Availability", f"{avg_avail * 100:.1f}%")
    _metric(col4, "Total Failure Events", str(int(total_failures)))

    divider()

    col_l, col_r = st.columns([3, 2])

    with col_l:
        st.subheader("Asset Reliability Summary")
        if not reliability.empty:
            display = reliability[["line_id", "mtbf_hr", "mttr_hr", "availability", "n_failure_events"]].copy()
            display["availability"] = (display["availability"] * 100).round(2).astype(str) + "%"
            display.columns = ["Line", "MTBF (hr)", "MTTR (hr)", "Availability", "Failure Events"]
            st.dataframe(display)

        st.subheader("Availability Trend")
        if not oee_daily.empty:
            fig = px.line(
                oee_daily,
                x="date", y="availability", color="line_id",
                labels={"date": "Date", "availability": "Availability", "line_id": "Line"},
                color_discrete_sequence=[BRAND_COLOR, ACCENT, GREEN],
            )
            fig.update_layout(yaxis_tickformat=".0%", height=280,
                              margin=dict(l=0, r=0, t=20, b=0),
                              legend=dict(orientation="h", y=-0.2))
            st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader("Maintenance Mix")
        if not maint_kpis.empty:
            totals = maint_kpis.groupby("maintenance_type")["work_order_count"].sum().reset_index()
            fig_donut = px.pie(
                totals, names="maintenance_type", values="work_order_count",
                hole=0.45,
                color_discrete_sequence=[RED, GREEN, YELLOW],
            )
            fig_donut.update_traces(textinfo="percent+label")
            fig_donut.update_layout(height=260, showlegend=False,
                                    margin=dict(l=0, r=0, t=20, b=0))
            st.plotly_chart(fig_donut, use_container_width=True)

            st.subheader("Work Orders by Line & Type")
            wos = maint_kpis[["line_id", "maintenance_type", "work_order_count", "avg_duration_hr"]]
            wos.columns = ["Line", "Type", "WOs", "Avg Duration (hr)"]
            st.dataframe(wos)


# ---------------------------------------------------------------------------
# Page 3 — Data Quality Dashboard
# ---------------------------------------------------------------------------

def page_data_quality(kpis: dict) -> None:
    st.title("Data Quality Dashboard")
    st.caption(
        "Composite quality scores across all data domains. "
        "This layer validates that the data foundation is reliable before AI or analytics consume it."
    )

    quality_scores_df = kpis.get("quality_scores", pd.DataFrame())

    if quality_scores_df.empty:
        st.warning("Quality scores not found — run `python -m src.quality.checks` first.")
        return

    # --- Overall score tile ---
    overall = quality_scores_df["composite_score"].mean()
    col1, col2, col3 = st.columns(3)
    col1.metric("Platform Quality Score", f"{overall:.1f}/100",
                delta=f"{'✓ Reliable' if overall >= 90 else '⚠ Needs attention'}")
    col2.metric("Domains Assessed", str(len(quality_scores_df)))
    valid_domains = (quality_scores_df["composite_score"] >= 90).sum()
    col3.metric("Domains ≥ 90", f"{valid_domains}/{len(quality_scores_df)}")

    divider()

    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Composite Score by Domain")
        fig = px.bar(
            quality_scores_df.sort_values("composite_score"),
            x="composite_score", y="domain",
            orientation="h",
            color="composite_score",
            color_continuous_scale=["#E74C3C", "#F1C40F", "#2ECC71"],
            range_color=[60, 100],
            labels={"composite_score": "Score", "domain": ""},
            text_auto=True,
        )
        fig.add_vline(x=90, line_dash="dot", line_color="gray",
                      annotation_text="Target (90)", annotation_position="top right")
        fig.update_layout(
            height=300, coloraxis_showscale=False,
            margin=dict(l=0, r=0, t=20, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader("Quality Dimensions — Sensor Domain")
        sensor_row = quality_scores_df[quality_scores_df["domain"] == "sensor"]
        if not sensor_row.empty:
            dims = ["completeness", "validity", "consistency", "uniqueness", "freshness"]
            scores = [sensor_row.iloc[0].get(f"score_{d}", 0) for d in dims]
            fig_radar = go.Figure(go.Scatterpolar(
                r=scores + [scores[0]],
                theta=dims + [dims[0]],
                fill="toself",
                fillcolor=f"rgba(26,58,92,0.25)",
                line_color=BRAND_COLOR,
                name="Sensor",
            ))
            fig_radar.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[80, 100])),
                height=300,
                margin=dict(l=20, r=20, t=20, b=20),
            )
            st.plotly_chart(fig_radar, use_container_width=True)

    divider()

    st.subheader("Full Quality Score Table")
    score_cols = [c for c in quality_scores_df.columns if c.startswith("score_")]
    display_cols = ["domain", "row_count", "composite_score"] + score_cols
    display_cols = [c for c in display_cols if c in quality_scores_df.columns]
    display = quality_scores_df[display_cols].copy()
    display.columns = [
        c.replace("score_", "").replace("_", " ").title() for c in display.columns
    ]
    st.dataframe(display)

    divider()
    st.info(
        "**Why does data quality matter before AI?**  \n"
        "Every model trained on unreliable data inherits that unreliability. "
        "This dashboard makes quality visible so it can be addressed before analytics and AI decisions are made. "
        "See [Essay #3: Why Data Foundations Come Before AI Scaling](/blog/en/2026-06-data-foundations-before-ai.html)."
    )


# ---------------------------------------------------------------------------
# Helper — metric tile
# ---------------------------------------------------------------------------

def _metric(col, label: str, value: str, delta: str = "", help_text: str = "") -> None:
    with col:
        st.metric(label=label, value=value, delta=delta or None, help=help_text or None)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    page = render_sidebar()

    # Load data once
    try:
        kpis = load_kpis()
    except Exception as e:
        st.error(f"Could not load KPI data: {e}")
        st.info("Run the full pipeline first: `python run_pipeline.py`")
        return

    if "Operations Overview" in page:
        page_operations_overview(kpis)
    elif "Reliability" in page:
        page_reliability(kpis)
    elif "Data Quality" in page:
        page_data_quality(kpis)


if __name__ == "__main__":
    main()
