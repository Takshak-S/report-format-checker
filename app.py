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
from reporter.pdf_report_generator import generate_pdf_report
from reporter.pdf_annotator import generate_annotated_pdf
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

if "uploaded_filename" not in st.session_state or st.session_state.uploaded_filename != uploaded.name:
    st.session_state.uploaded_filename = uploaded.name
    st.session_state.check_results = None
    st.session_state.doc = None
    st.session_state.excel_report = None
    st.session_state.pdf_report = None
    st.session_state.annotated_pdf = None

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
            
            # Generate reports during the check phase so we don't re-run them on every UI interaction
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as out_tmp:
                out_path = out_tmp.name
            report_path = generate_report(collector, uploaded.name, out_path)
            with open(report_path, "rb") as f:
                st.session_state.excel_report = f.read()
            os.unlink(report_path)

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as out_pdf_tmp:
                out_pdf_path = out_pdf_tmp.name
            pdf_report_path = generate_pdf_report(collector, uploaded.name, out_pdf_path)
            with open(pdf_report_path, "rb") as f:
                st.session_state.pdf_report = f.read()
            os.unlink(pdf_report_path)

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as ann_tmp:
                ann_path = ann_tmp.name
            annotated_path = generate_annotated_pdf(collector, tmp_path, ann_path)
            with open(annotated_path, "rb") as f:
                st.session_state.annotated_pdf = f.read()
            os.unlink(annotated_path)

            st.session_state.check_results = collector
            st.session_state.doc = doc

        except FileNotFoundError as e:
            st.error(str(e))
            st.stop()
        except Exception as e:
            st.error(f"Error loading PDF: {e}")
            st.stop()

    progress_bar.progress(100, text="Complete ✓")
    status_text.empty()

if st.session_state.check_results is not None:
    collector = st.session_state.check_results
    doc = st.session_state.doc

    summary = collector.summary()

    # ── Summary metrics ───────────────────────────────────────────────────────
    st.divider()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Issues", summary["total"])
    col2.metric("🔴 Critical",  summary["critical"])
    col3.metric("🟡 Warnings",  summary["warnings"])
    col4.metric("🔵 Info",      summary["info"])

    overall = "✅ PASS" if summary["critical"] == 0 else "❌ FAIL"
    color   = "success" if summary["critical"] == 0 else "error"
    getattr(st, color)(f"**Overall Status: {overall}**")

    # ── Download buttons ──────────────────────────────────────────────────────
    col_dl1, col_dl2, col_dl3 = st.columns(3)
    
    with col_dl1:
        if st.session_state.excel_report:
            st.download_button(
                label="⬇ Download Excel Report",
                data=st.session_state.excel_report,
                file_name=f"{Path(uploaded.name).stem}_format_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            
    with col_dl2:
        if st.session_state.pdf_report:
            st.download_button(
                label="⬇ Download PDF Summary",
                data=st.session_state.pdf_report,
                file_name=f"{Path(uploaded.name).stem}_format_report.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
            
    with col_dl3:
        if st.session_state.annotated_pdf:
            st.download_button(
                label="⬇ Download Highlighted PDF",
                data=st.session_state.annotated_pdf,
                file_name=f"{Path(uploaded.name).stem}_highlighted.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

    # ── Per-category accordion ────────────────────────────────────────────────
    st.divider()
    st.subheader("Findings by Category")

    by_cat = collector.by_category()
    severity_icon = {
        Severity.CRITICAL: "🔴", 
        Severity.MAJOR: "🟠", 
        Severity.MINOR: "🟡", 
        Severity.WARNING: "🟡", 
        Severity.SUGGESTION: "🔵",
        Severity.INFO: "🔵"
    }

    for cat in sorted(by_cat.keys()):
        viols = by_cat[cat]
        critical = sum(1 for v in viols if v.severity == Severity.CRITICAL)
        major = sum(1 for v in viols if v.severity == Severity.MAJOR)
        minor = sum(1 for v in viols if v.severity == Severity.MINOR)
        warnings = sum(1 for v in viols if v.severity == Severity.WARNING)
        
        if critical > 0:
            badge = f"🔴 {critical} critical"
        elif major > 0:
            badge = f"🟠 {major} major"
        elif minor > 0:
            badge = f"🟡 {minor} minor"
        elif warnings > 0:
            badge = f"🟡 {warnings} warning(s)"
        else:
            badge = f"🔵 {len(viols)} info"

        with st.expander(f"**{cat}** — {badge}", expanded=(critical > 0 or major > 0)):
            for v in sorted(viols, key=lambda x: (x.page if x.page > 0 else 9999)):
                icon = severity_icon.get(v.severity, "⚪")
                page_label = f"p.{v.page}" if v.page > 0 else "doc-level"
                st.markdown(f"{icon} **[{page_label}]** {v.description}")
                if v.detail:
                    st.caption(f"↳ {v.detail}")
                if v.location:
                    bg_color = "#ffcccc" if v.severity in (Severity.CRITICAL, Severity.MAJOR) else "#fff0b3" if v.severity in (Severity.MINOR, Severity.WARNING) else "#e6f2ff"
                    st.markdown(f"<span style='font-size: 0.8em; color: gray;'>📍 Near: </span><mark style='background-color: {bg_color}; color: black; padding: 0.1em 0.3em; border-radius: 3px; font-size: 0.9em;'>{v.location}</mark>", unsafe_allow_html=True)
                st.markdown("---")

    # ── Document info ─────────────────────────────────────────────────────────
    with st.expander("📋 Document Info"):
        st.write(f"**Pages:** {len(doc.pages)}")
        st.write(f"**Has text layer:** {'Yes' if bool(doc.raw_text.strip()) else 'No (scanned)'}")
        images_count = sum(len(p.get_images()) for p in doc.pages)
        st.write(f"**Images found:** {images_count}")
        tables_count = sum(len(p.get_tables()) for p in doc.pages)
        st.write(f"**Tables found:** {tables_count}")

# Cleanup
try:
    if 'tmp_path' in locals():
        os.unlink(tmp_path)
except Exception:
    pass
