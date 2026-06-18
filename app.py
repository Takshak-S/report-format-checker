"""
app.py — Streamlit web UI for the PDF Format Checker
"""
import sys
import os
import tempfile
from pathlib import Path

import streamlit as st

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

from checker import run_checks
from reporter.report_generator import generate_report
from utils.constants import Severity, Category


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PDF Format Checker",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Settings")
    skip_grammar = st.checkbox(
        "Skip grammar check (faster)",
        value=False,
        help="Grammar checking via LanguageTool can take 30–90 seconds. Disable for quick runs.",
    )
    st.divider()
    st.markdown("""
    **Format Specification:**
    - A4 page, TNR font
    - Left 1.5\", other margins 1\"
    - 12 pt body, 14 pt L1 headings, 16 pt chapter titles
    - 1.5× line spacing, fully justified
    - Images ≥ 600 DPI
    - 8 mandatory chapters
    - APA 7th edition citations
    """)


# ── Main UI ───────────────────────────────────────────────────────────────────
st.title("📄 PDF Format Checker")
st.caption("Upload a project report PDF to check it against the standardization template.")

uploaded = st.file_uploader("Upload PDF", type=["pdf"], label_visibility="collapsed")

if not uploaded:
    st.info("👆 Upload a PDF report to begin the format check.")
    st.stop()

# Save to temp file
with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
    tmp.write(uploaded.read())
    tmp_path = tmp.name

st.success(f"Loaded: **{uploaded.name}** ({uploaded.size / 1024:.1f} KB)")

if st.button("▶ Run Format Check", type="primary", use_container_width=True):
    progress_bar  = st.progress(0, text="Starting…")
    status_text   = st.empty()

    def update_progress(label: str, current: int, total: int):
        pct = int((current / total) * 100) if total else 0
        progress_bar.progress(pct, text=f"Running: {label}…")
        status_text.caption(f"Step {current + 1} of {total}: {label}")

    with st.spinner("Checking…"):
        try:
            doc, collector = run_checks(
                tmp_path,
                progress_callback=update_progress,
                skip_grammar=skip_grammar,
            )
        except FileNotFoundError as e:
            st.error(str(e))
            st.stop()
        except Exception as e:
            st.error(f"Error loading PDF: {e}")
            st.stop()

    progress_bar.progress(100, text="Complete ✓")
    status_text.empty()

    summary = collector.summary()

    # ── Summary metrics ───────────────────────────────────────────────────────
    st.divider()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Issues", summary["total"])
    col2.metric("🔴 Errors",    summary["errors"])
    col3.metric("🟡 Warnings",  summary["warnings"])
    col4.metric("🔵 Info",      summary["info"])

    overall = "✅ PASS" if summary["errors"] == 0 else "❌ FAIL"
    color   = "success" if summary["errors"] == 0 else "error"
    getattr(st, color)(f"**Overall Status: {overall}**")

    # ── Generate & download report ────────────────────────────────────────────
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as out_tmp:
        out_path = out_tmp.name

    report_path = generate_report(collector, uploaded.name, out_path)
    with open(report_path, "rb") as f:
        st.download_button(
            label="⬇ Download Excel Report",
            data=f.read(),
            file_name=f"{Path(uploaded.name).stem}_format_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    # ── Per-category accordion ────────────────────────────────────────────────
    st.divider()
    st.subheader("Findings by Category")

    by_cat = collector.by_category()
    severity_icon = {Severity.ERROR: "🔴", Severity.WARNING: "🟡", Severity.INFO: "🔵"}

    for cat in sorted(by_cat.keys()):
        viols = by_cat[cat]
        errors   = sum(1 for v in viols if v.severity == Severity.ERROR)
        warnings = sum(1 for v in viols if v.severity == Severity.WARNING)
        badge    = f"🔴 {errors} error(s)" if errors else (f"🟡 {len(viols)} warning(s)" if warnings else f"🔵 {len(viols)} info")

        with st.expander(f"**{cat}** — {badge}", expanded=(errors > 0)):
            for v in sorted(viols, key=lambda x: (x.page if x.page > 0 else 9999)):
                icon = severity_icon.get(v.severity, "⚪")
                page_label = f"p.{v.page}" if v.page > 0 else "doc-level"
                st.markdown(f"{icon} **[{page_label}]** {v.description}")
                if v.detail:
                    st.caption(f"↳ {v.detail}")
                if v.location:
                    st.caption(f"📍 Near: *{v.location}*")
                st.markdown("---")

    # ── Document info ─────────────────────────────────────────────────────────
    with st.expander("📋 Document Info"):
        st.write(f"**Pages:** {doc.page_count}")
        st.write(f"**Has text layer:** {'Yes' if doc.has_text_layer else 'No (scanned)'}")
        st.write(f"**Images found:** {len(doc.images)}")
        st.write(f"**Tables found:** {len(doc.tables)}")
        if doc.toc:
            st.write(f"**TOC entries:** {len(doc.toc)}")

# Cleanup
try:
    os.unlink(tmp_path)
except Exception:
    pass
