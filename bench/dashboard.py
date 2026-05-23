#!/usr/bin/env python3
"""kvc benchmark dashboard.

Usage:
    streamlit run bench/dashboard.py
"""

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

PROJECT_DIR = Path(__file__).parent.parent
BENCH_DIR = PROJECT_DIR / "bench"
OUTPUT_DIR = BENCH_DIR / "output"

st.set_page_config(
    page_title="kvc benchmarks",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


@st.cache_data(ttl=30)
def load_runs() -> pd.DataFrame:
    rows = []
    for bench_path in sorted(OUTPUT_DIR.glob("**/bench.json")):
        run_dir = bench_path.parent
        try:
            bench = json.loads(bench_path.read_text())
        except Exception:
            continue

        meta: dict = {}
        meta_path = run_dir / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
            except Exception:
                pass

        duration_s = bench.get("duration_s") or 0
        total = bench.get("total") or 0
        counters = bench.get("perf", {}).get("counters", {})
        task_clock = counters.get("task-clock")
        ctx_sw = counters.get("context-switches")
        timing = bench.get("timing_us", {})
        cfg = bench.get("config") or meta.get("bench", {})
        infra = bench.get("infra", {})

        row = {
            "run_id": bench.get("run_id") or meta.get("run_id", run_dir.name),
            "version": bench.get("version")
            or meta.get("version", run_dir.parent.name)
            or "—",
            "label": bench.get("label") or run_dir.name,
            "timestamp": bench.get("timestamp") or meta.get("timestamp") or "",
            "git_commit": (bench.get("git_commit") or meta.get("git_commit") or "")[:8],
            "env": bench.get("env") or "—",
            "connections": bench.get("workers", 1),
            "total": total,
            "errors": bench.get("errors", 0),
            "duration_s": round(duration_s, 3),
            "throughput_per_s": bench.get("throughput_per_s", 0),
            "min_us": timing.get("min"),
            "p50_us": timing.get("p50"),
            "p95_us": timing.get("p95"),
            "p99_us": timing.get("p99"),
            "p999_us": timing.get("p999"),
            "max_us": timing.get("max"),
            "cpu_pct": (
                round(task_clock / 1e9 / duration_s * 100, 1)
                if task_clock and duration_s
                else None
            ),
            "ctx_sw_per_req": round(ctx_sw / total, 3) if ctx_sw and total else None,
            "task_clock_s": round(task_clock / 1e9, 3) if task_clock else None,
            "context_switches": ctx_sw,
            "page_faults": counters.get("page-faults"),
            "hostname": infra.get("hostname", ""),
            "cpu_model": infra.get("cpu_model", ""),
            "os": infra.get("os", ""),
            "cpu_count": infra.get("cpu_count"),
            "key_space": cfg.get("key_space"),
            "value_size": cfg.get("value_size"),
            "set_ratio": cfg.get("set_ratio"),
            "del_ratio": cfg.get("del_ratio"),
            "warmup": cfg.get("warmup"),
            "perf_report": bench.get("perf_report", ""),
            "flamegraph_path": str(run_dir / "flamegraph.svg")
            if (run_dir / "flamegraph.svg").exists()
            else "",
        }
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    return df.sort_values("timestamp", na_position="last").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------


def sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filters")

    versions = sorted(df["version"].dropna().unique())
    sel_versions = st.sidebar.multiselect("Version", versions, default=versions)

    envs = sorted(df["env"].dropna().unique())
    sel_envs = st.sidebar.multiselect("Environment", envs, default=envs)

    conns = sorted(df["connections"].dropna().unique())
    sel_conns = st.sidebar.multiselect("Connections", conns, default=conns)

    st.sidebar.caption(f"{len(df)} total runs")
    st.sidebar.button("Reload data", on_click=load_runs.clear)

    mask = (
        df["version"].isin(sel_versions)
        & df["env"].isin(sel_envs)
        & df["connections"].isin(sel_conns)
    )
    return df[mask].copy()


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------


def tab_overview(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No runs match the current filters.")
        return

    best = df.loc[df["throughput_per_s"].idxmax()]
    latest = df.iloc[-1]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Runs", len(df))
    c2.metric(
        "Best throughput",
        f"{best['throughput_per_s']:,.0f} req/s",
        help=f"{best['label']} · {int(best['connections'])}c",
    )
    c3.metric(
        "Latest throughput",
        f"{latest['throughput_per_s']:,.0f} req/s",
        help=latest["label"],
    )
    c4.metric(
        "Latest p99",
        f"{latest['p99_us']:,.0f} µs" if pd.notna(latest["p99_us"]) else "—",
    )
    c5.metric(
        "Latest CPU%",
        f"{latest['cpu_pct']:.1f}%" if pd.notna(latest["cpu_pct"]) else "—",
    )

    st.divider()

    # All runs table
    display = df[
        [
            "label",
            "version",
            "timestamp",
            "env",
            "connections",
            "throughput_per_s",
            "p50_us",
            "p95_us",
            "p99_us",
            "p999_us",
            "cpu_pct",
            "ctx_sw_per_req",
            "errors",
            "git_commit",
        ]
    ].copy()
    display["timestamp"] = (
        display["timestamp"].dt.strftime("%Y-%m-%d %H:%M").fillna("—")
    )
    st.dataframe(display, width="stretch", hide_index=True)

    st.divider()

    # Drill-down
    sel = st.selectbox(
        "Drill into run",
        ["—"] + list(df["label"]),
        key="drilldown_select",
    )
    if sel == "—":
        return

    run = df[df["label"] == sel].iloc[0]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.caption("**Machine**")
        st.text(f"CPU:   {run['cpu_model'] or '—'}")
        st.text(f"OS:    {run['os'] or '—'}")
        st.text(f"Host:  {run['hostname'] or '—'}")
        st.text(f"Cores: {run['cpu_count'] or '—'}")
    with col2:
        st.caption("**Config**")
        st.text(f"Key space:  {run['key_space'] or '—'}")
        st.text(f"Value size: {run['value_size'] or '—'} B")
        st.text(f"SET ratio:  {run['set_ratio'] or '—'}")
        st.text(f"DEL ratio:  {run['del_ratio'] or '—'}")
        st.text(f"Warmup:     {run['warmup'] or '—'}")
    with col3:
        st.caption("**Perf counters**")
        st.text(f"CPU time:  {run['task_clock_s'] or '—'} s")
        st.text(
            f"Ctx sw:    {int(run['context_switches']):,}"
            if pd.notna(run["context_switches"])
            else "Ctx sw:    —"
        )
        st.text(
            f"Pg faults: {int(run['page_faults']):,}"
            if pd.notna(run["page_faults"])
            else "Pg faults: —"
        )

    if run["perf_report"]:
        with st.expander("Perf report (hot functions)"):
            st.code(run["perf_report"], language=None)

    if run["flamegraph_path"]:
        with st.expander("Flamegraph", expanded=False):
            svg = Path(run["flamegraph_path"]).read_text(encoding="utf-8")
            components.html(
                f'<div style="overflow-x:auto;background:#fff;padding:8px;border-radius:6px">{svg}</div>',
                height=1000,
                scrolling=False,
            )


def tab_trends(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No runs match the current filters.")
        return

    df_t = df.dropna(subset=["timestamp"]).copy()
    df_t["label_short"] = (
        df_t["label"].str[:18] + " " + df_t["connections"].astype(str) + "c"
    )

    # ── Throughput ──────────────────────────────────────────────────────────
    fig_tp = px.line(
        df_t,
        x="timestamp",
        y="throughput_per_s",
        color="version",
        symbol="connections",
        markers=True,
        hover_data={
            "label": True,
            "env": True,
            "connections": True,
            "timestamp": False,
        },
        labels={"throughput_per_s": "req/s", "timestamp": ""},
        title="Throughput over time",
    )
    fig_tp.update_traces(marker_size=8)
    st.plotly_chart(fig_tp, width="stretch")

    # ── Latency percentiles ─────────────────────────────────────────────────
    lat_cols = ["p50_us", "p95_us", "p99_us", "p999_us"]
    lat_df = df_t.melt(
        id_vars=["timestamp", "version", "label", "connections", "env"],
        value_vars=lat_cols,
        var_name="pct",
        value_name="µs",
    ).dropna(subset=["µs"])
    lat_df["pct"] = lat_df["pct"].str.replace("_us", "").str.replace("p", "p")

    fig_lat = px.line(
        lat_df,
        x="timestamp",
        y="µs",
        color="pct",
        line_dash="version",
        markers=True,
        hover_data={
            "label": True,
            "env": True,
            "connections": True,
            "timestamp": False,
        },
        labels={"µs": "µs", "timestamp": ""},
        title="Latency percentiles over time",
        color_discrete_map={
            "p50": "#3fb950",
            "p95": "#d29922",
            "p99": "#f85149",
            "p999": "#bc8cff",
        },
    )
    fig_lat.update_traces(marker_size=7)
    st.plotly_chart(fig_lat, width="stretch")

    # ── CPU & ctx switches ──────────────────────────────────────────────────
    if df_t["cpu_pct"].notna().any():
        col1, col2 = st.columns(2)
        with col1:
            fig_cpu = px.line(
                df_t.dropna(subset=["cpu_pct"]),
                x="timestamp",
                y="cpu_pct",
                color="version",
                markers=True,
                labels={"cpu_pct": "CPU%", "timestamp": ""},
                title="Server CPU utilization",
            )
            st.plotly_chart(fig_cpu, width="stretch")
        with col2:
            if df_t["ctx_sw_per_req"].notna().any():
                fig_ctx = px.line(
                    df_t.dropna(subset=["ctx_sw_per_req"]),
                    x="timestamp",
                    y="ctx_sw_per_req",
                    color="version",
                    markers=True,
                    labels={"ctx_sw_per_req": "ctx sw / req", "timestamp": ""},
                    title="Context switches per request",
                )
                st.plotly_chart(fig_ctx, width="stretch")


def tab_compare(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No runs match the current filters.")
        return

    def run_label(r: pd.Series) -> str:
        ts = r["timestamp"].strftime("%m-%d %H:%M") if pd.notna(r["timestamp"]) else "?"
        return f"{r['label']} · {int(r['connections'])}c · {r['env']} · {ts}"

    id_to_display = {r["run_id"]: run_label(r) for _, r in df.iterrows()}
    display_to_id = {v: k for k, v in id_to_display.items()}

    default_n = min(4, len(df))
    default_sel = [id_to_display[rid] for rid in df["run_id"].iloc[-default_n:]]

    selected = st.multiselect(
        "Select runs to compare",
        options=list(display_to_id.keys()),
        default=default_sel,
    )
    if not selected:
        st.info("Select at least one run above.")
        return

    cdf = df[df["run_id"].isin([display_to_id[s] for s in selected])].copy()
    cdf["run_label"] = cdf["run_id"].map(id_to_display)

    # ── Throughput & p99 side by side ───────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(
            cdf.sort_values("throughput_per_s"),
            x="throughput_per_s",
            y="run_label",
            color="version",
            orientation="h",
            text="throughput_per_s",
            labels={"throughput_per_s": "req/s", "run_label": ""},
            title="Throughput",
        )
        fig.update_traces(texttemplate="%{x:,.0f}", textposition="outside")
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, width="stretch")

    with col2:
        lat_cols = ["min_us", "p50_us", "p95_us", "p99_us", "p999_us", "max_us"]
        lat_df = cdf.melt(
            id_vars=["run_label"],
            value_vars=lat_cols,
            var_name="pct",
            value_name="µs",
        ).dropna(subset=["µs"])
        lat_df["pct"] = lat_df["pct"].str.replace("_us", "")
        lat_df["pct"] = pd.Categorical(
            lat_df["pct"],
            categories=["min", "p50", "p95", "p99", "p999", "max"],
            ordered=True,
        )
        fig2 = px.bar(
            lat_df.sort_values("pct"),
            x="pct",
            y="µs",
            color="run_label",
            barmode="group",
            labels={"pct": "", "µs": "µs", "run_label": "Run"},
            title="Latency distribution",
        )
        st.plotly_chart(fig2, width="stretch")

    # ── CPU & ctx switches ──────────────────────────────────────────────────
    if cdf["cpu_pct"].notna().any():
        col3, col4 = st.columns(2)
        with col3:
            fig3 = px.bar(
                cdf.sort_values("cpu_pct"),
                x="cpu_pct",
                y="run_label",
                color="version",
                orientation="h",
                text="cpu_pct",
                labels={"cpu_pct": "CPU%", "run_label": ""},
                title="CPU utilization",
            )
            fig3.update_traces(texttemplate="%{x:.1f}%", textposition="outside")
            fig3.update_layout(showlegend=False)
            st.plotly_chart(fig3, width="stretch")
        with col4:
            if cdf["ctx_sw_per_req"].notna().any():
                fig4 = px.bar(
                    cdf.sort_values("ctx_sw_per_req"),
                    x="ctx_sw_per_req",
                    y="run_label",
                    color="version",
                    orientation="h",
                    text="ctx_sw_per_req",
                    labels={"ctx_sw_per_req": "ctx sw / req", "run_label": ""},
                    title="Context switches per request",
                )
                fig4.update_traces(texttemplate="%{x:.3f}", textposition="outside")
                fig4.update_layout(showlegend=False)
                st.plotly_chart(fig4, width="stretch")

    # ── Summary table ───────────────────────────────────────────────────────
    st.subheader("Comparison table")
    show_cols = [
        "run_label",
        "version",
        "env",
        "connections",
        "throughput_per_s",
        "p50_us",
        "p95_us",
        "p99_us",
        "p999_us",
        "cpu_pct",
        "ctx_sw_per_req",
        "errors",
        "duration_s",
    ]
    st.dataframe(
        cdf[show_cols].rename(columns={"run_label": "Run"}).set_index("Run"),
        width="stretch",
    )


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


def tab_about() -> None:
    st.markdown(
        """
**KVC** is an in-memory key-value store written in C. It exposes a minimal text protocol
over TCP — `GET`, `SET`, and `DEL`, one command per newline — and is designed as a
*research and learning environment* for measuring, studying, and experimenting with
performance engineering.

The goal is not to ship a production system. It is to build a reproducible, measurable
environment where the cost of every design decision can be quantified and understood.
The code is intentionally simple and unoptimized, so the bottlenecks are visible and
the impact of each change is clear. The benchmarks are designed to be rigorous and
repeatable, with a focus on isolating the effects of each change.

Each answer feeds the next implementation. This page tracks the data behind every iteration.
        """
    )

    st.divider()
    st.subheader("Versions")
    st.markdown((PROJECT_DIR / "VERSIONS.md").read_text())


def main() -> None:
    st.title("kvc — benchmark dashboard")

    with st.spinner("Loading runs…"):
        df = load_runs()

    if df.empty:
        st.error(f"No bench.json files found under `{OUTPUT_DIR}`")
        st.stop()

    filtered = sidebar_filters(df)
    st.caption(f"Showing **{len(filtered)}** of {len(df)} runs")

    t1, t2, t3, t4 = st.tabs(["About", "Overview", "Trends", "Compare"])
    with t1:
        tab_about()
    with t2:
        tab_overview(filtered)
    with t3:
        tab_trends(filtered)
    with t4:
        tab_compare(filtered)


if __name__ == "__main__":
    main()
