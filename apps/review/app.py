"""CallScope Call Review console (Streamlit).

Run: ``make review`` or ``uv run streamlit run apps/review/app.py``
Talks only to the CallScope API via ``ReviewApiClient``.
"""

from __future__ import annotations

import os
from typing import Any

import streamlit as st

from apps.api.review_store import ROOT_CAUSE_CODES
from apps.review.api_client import ReviewApiClient
from apps.review.helpers import escape_text, reference_diff, scrub_tool_args, timeline_lanes
from callscope.review.seed_demo import attribution_agreement, root_cause_distribution

st.set_page_config(page_title="CallScope Review", layout="wide")

API_URL = os.environ.get("CALLSCOPE_API_URL", "http://127.0.0.1:8000")
SERVICE_TOKEN = os.environ.get("CALLSCOPE_SERVICE_TOKEN", "changeme-service-token")


def _client() -> ReviewApiClient:
    if "review_api" not in st.session_state:
        st.session_state["review_api"] = ReviewApiClient(API_URL, SERVICE_TOKEN)
    return st.session_state["review_api"]  # type: ignore[no-any-return]


def _inbox() -> None:
    st.header("Inbox")
    c1, c2, c3, c4 = st.columns(4)
    flagged = c1.selectbox("Flagged", ["any", "yes", "no"])
    root_cause = c2.selectbox("Root cause", ["(all)", *sorted(ROOT_CAUSE_CODES)])
    channel = c3.selectbox("Channel", ["(all)", "browser", "sip", "sim", "replay"])
    limit = c4.number_input("Limit", min_value=1, max_value=200, value=50)
    params: dict[str, Any] = {"limit": int(limit)}
    if flagged == "yes":
        params["flagged"] = True
    elif flagged == "no":
        params["flagged"] = False
    if root_cause != "(all)":
        params["root_cause"] = root_cause
    if channel != "(all)":
        params["channel"] = channel
    try:
        page = _client().list_calls(**params)
    except Exception as exc:
        st.error(f"API error: {exc}")
        return
    items = page.get("items") or []
    st.caption(
        f"{len(items)} calls"
        + (f" · next={page.get('next_cursor')}" if page.get("next_cursor") else "")
    )
    if not items:
        st.info("No calls. Run `callscope review seed-demo` or click Seed below.")
        if st.button("Seed 40 demo calls"):
            res = _client().seed_demo(40)
            st.success(f"Created {res['created']} ({res['labelled']} labelled)")
            st.rerun()
        return
    for row in items:
        cols = st.columns([3, 2, 2, 1])
        cols[0].write(escape_text(str(row["call_id"])))
        cols[1].write(escape_text(row.get("stack_label") or ""))
        cols[2].write(", ".join(escape_text(x) for x in row.get("flag_reasons") or []))
        if cols[3].button("Open", key=f"open-{row['call_id']}"):
            st.session_state["call_id"] = row["call_id"]
            st.session_state["page"] = "Detail"
            st.rerun()


def _detail() -> None:
    st.header("Call detail")
    call_id = st.session_state.get("call_id") or st.text_input("call_id")
    if not call_id:
        st.info("Select a call from Inbox.")
        return
    try:
        detail = _client().call_detail(call_id)
    except Exception as exc:
        st.error(f"API error: {exc}")
        return
    st.subheader(escape_text(str(detail["call_id"])))
    st.write(
        f"channel={escape_text(detail.get('channel', ''))} · "
        f"flagged={detail.get('flagged')} · "
        f"RCs={', '.join(escape_text(x) for x in detail.get('root_causes') or [])}"
    )
    try:
        audio = _client().audio_url(call_id)
        st.audio(audio["url"])
        st.caption(f"expires {audio.get('expires_at')}")
    except Exception:
        st.caption("No audio URL (recording missing or auth).")

    events = detail.get("events") or []
    lanes = timeline_lanes(events)
    if lanes:
        try:
            import altair as alt
            import pandas as pd

            df = pd.DataFrame(lanes)
            chart = (
                alt.Chart(df)
                .mark_bar()
                .encode(
                    x="t_ms:Q",
                    x2="t_end_ms:Q",
                    y=alt.Y("lane:N", sort=None),
                    color="type:N",
                    tooltip=["lane", "type", "label", "t_ms"],
                )
                .properties(height=280)
            )
            st.altair_chart(chart, use_container_width=True)
        except Exception:
            st.dataframe(lanes, use_container_width=True)

    st.subheader("Transcript (escaped)")
    for ev in events:
        if ev.get("type") in {"stt.final", "brain.first_token"}:
            role = "caller" if ev["type"] == "stt.final" else "agent"
            text = escape_text(str((ev.get("payload") or {}).get("text") or ""))
            st.text(f"{role}: {text}")

    caller = next(
        (
            str((e.get("payload") or {}).get("text") or "")
            for e in events
            if e.get("type") == "stt.final"
        ),
        "",
    )
    agent = next(
        (
            str((e.get("payload") or {}).get("text") or "")
            for e in events
            if e.get("type") == "brain.first_token"
        ),
        "",
    )
    if caller and agent:
        st.subheader("Reference diff (caller vs agent text)")
        st.json(reference_diff(agent, caller))

    st.subheader("Tool calls (scrubbed)")
    for tc in detail.get("tool_calls") or []:
        args = (tc.get("payload") or {}).get("args") or {}
        if isinstance(args, dict):
            st.json({"type": tc.get("type"), "args": scrub_tool_args(args)})

    st.subheader("Label")
    with st.form("label_form"):
        code = st.selectbox("Root cause", sorted(ROOT_CAUSE_CODES))
        severity = st.slider("Severity", 1, 4, 2)
        notes = st.text_input("Notes")
        add_ds = st.selectbox("Add to dataset", ["(none)", "train", "dev"])
        reviewer = st.text_input("Reviewer", value=os.environ.get("USER", "reviewer"))
        submitted = st.form_submit_button("Save label")
        if submitted:
            body: dict[str, Any] = {
                "root_cause_code": code,
                "severity": severity,
                "reviewer": reviewer,
                "notes": notes,
            }
            if add_ds != "(none)":
                body["add_to_dataset"] = add_ds
            try:
                lab = _client().add_label(call_id, body)
                st.success(f"Saved {lab.get('label_id')}")
            except Exception as exc:
                st.error(str(exc))

    st.subheader("Existing labels")
    for lab in detail.get("labels") or []:
        st.write(
            f"{escape_text(lab.get('root_cause_code', ''))} "
            f"sev={lab.get('severity')} by {escape_text(lab.get('reviewer', ''))}"
        )


def _export() -> None:
    st.header("Export labelled failures")
    name = st.text_input("Dataset name", value="labelled-failures")
    version = st.text_input("Version", value="v1")
    if st.button("Export"):
        try:
            res = _client().export_labelled(name, version)
            st.success(f"dataset_id={res.get('dataset_id')}")
        except Exception as exc:
            st.error(str(exc))


def _compare() -> None:
    st.header("Compare eval runs")
    try:
        runs = _client().list_eval_runs()
    except Exception as exc:
        st.error(str(exc))
        return
    if len(runs) < 2:
        st.info("Need at least two eval runs in the API.")
        return
    ids = [str(r["run_id"]) for r in runs]
    a = st.selectbox("Run A", ids)
    b = st.selectbox("Run B", ids, index=min(1, len(ids) - 1))
    if st.button("Compare"):
        deltas = _client().compare_runs(a, b)
        st.dataframe(deltas, use_container_width=True)


def _distribution() -> None:
    st.header("Root-cause distribution & attribution agreement")
    try:
        page = _client().list_calls(limit=200, flagged=True)
    except Exception as exc:
        st.error(str(exc))
        return
    all_labels: list[dict[str, Any]] = []
    human_codes: list[str] = []
    auto_codes: list[str] = []
    for row in page.get("items") or []:
        detail = _client().call_detail(row["call_id"])
        labs = detail.get("labels") or []
        all_labels.extend(labs)
        human_codes.extend(str(x.get("root_cause_code")) for x in labs)
        auto_codes.extend(str(x) for x in detail.get("root_causes") or [])
    dist = root_cause_distribution(all_labels)
    st.bar_chart(dist)
    st.json(attribution_agreement(human_codes, auto_codes))
    st.caption(f"{len(all_labels)} labels across {len(page.get('items') or [])} flagged calls")


def main() -> None:
    st.title("CallScope Review")
    st.caption("Transcripts and tool args are escaped/scrubbed; no unsafe HTML.")
    page = st.sidebar.radio(
        "Page",
        ["Inbox", "Detail", "Export", "Compare", "Distribution"],
        key="page",
    )
    if page == "Inbox":
        _inbox()
    elif page == "Detail":
        _detail()
    elif page == "Export":
        _export()
    elif page == "Compare":
        _compare()
    else:
        _distribution()


if __name__ == "__main__":
    main()
