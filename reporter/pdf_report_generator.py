"""
reporter/pdf_report_generator.py

Generates a PDF summary report of all format checker violations.
Uses fpdf2 to build a structured, multi-page document.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime

from fpdf import FPDF

from utils.error_model import ViolationCollector
from utils.constants import Severity

# Define colors (R, G, B)
COLOR_ERROR = (220, 53, 69)     # Red
COLOR_WARNING = (255, 193, 7)   # Amber/Yellow
COLOR_INFO = (23, 162, 184)     # Info Blue
COLOR_HEADER = (31, 56, 100)    # Dark Navy
COLOR_TEXT = (50, 50, 50)       # Dark Gray


class PDFReport(FPDF):
    def header(self):
        # Header for every page
        self.set_font("helvetica", "B", 12)
        self.set_text_color(*COLOR_HEADER)
        self.cell(0, 10, "PDF Format Checker - Summary Report", border=False, ln=True, align="C")
        self.ln(5)

    def footer(self):
        # Footer for every page
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")


def generate_pdf_report(
    collector: ViolationCollector,
    original_pdf_name: str,
    output_path: str | Path
) -> Path:
    """
    Generate a PDF summary report from the collector's violations.
    """
    out_path = Path(output_path)
    
    pdf = PDFReport()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # ── Title & Meta ──────────────────────────────────────────────────────────
    pdf.set_font("helvetica", "B", 16)
    pdf.set_text_color(*COLOR_TEXT)
    pdf.cell(0, 10, f"Report for: {original_pdf_name}", ln=True, align="L")
    
    pdf.set_font("helvetica", "I", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True, align="L")
    pdf.ln(10)
    
    # ── Summary Stats ─────────────────────────────────────────────────────────
    summary = collector.summary()
    
    pdf.set_font("helvetica", "B", 14)
    pdf.set_text_color(*COLOR_HEADER)
    pdf.cell(0, 10, "Overall Summary", ln=True)
    
    pdf.set_font("helvetica", "", 11)
    pdf.set_text_color(*COLOR_TEXT)
    pdf.cell(0, 8, f"Score: 100", ln=True) # Static score or compute one if needed
    
    pdf.cell(0, 8, f"Total Findings: {summary.get('total', 0)}", ln=True)
    pdf.set_text_color(*COLOR_ERROR)
    pdf.cell(0, 8, f"Errors: {summary.get('errors', 0)}", ln=True)
    pdf.set_text_color(200, 150, 0) # Darker yellow for text
    pdf.cell(0, 8, f"Warnings: {summary.get('warnings', 0)}", ln=True)
    pdf.set_text_color(*COLOR_INFO)
    pdf.cell(0, 8, f"Info: {summary.get('info', 0)}", ln=True)
    pdf.ln(10)
    
    # ── Detailed Violations ───────────────────────────────────────────────────
    pdf.set_font("helvetica", "B", 14)
    pdf.set_text_color(*COLOR_HEADER)
    pdf.cell(0, 10, "Detailed Findings", ln=True)
    pdf.ln(2)
    
    by_page = collector.by_page()
    
    # If no violations
    if not by_page:
        pdf.set_font("helvetica", "I", 11)
        pdf.set_text_color(*COLOR_TEXT)
        pdf.cell(0, 10, "No format violations found. Perfect score!", ln=True)
        pdf.output(str(out_path))
        return out_path

    # Iterate through pages
    for page_num, violations in sorted(by_page.items()):
        # Page header
        pdf.set_font("helvetica", "B", 12)
        pdf.set_text_color(255, 255, 255)
        pdf.set_fill_color(*COLOR_HEADER)
        
        page_label = f"Page {page_num}" if page_num > 0 else "Document-Level"
        pdf.cell(0, 8, f"  {page_label}", ln=True, fill=True)
        pdf.ln(2)
        
        # Sort violations: ERROR -> WARNING -> INFO
        def sev_order(v):
            if v.severity == Severity.ERROR: return 0
            if v.severity == Severity.WARNING: return 1
            return 2
            
        sorted_viols = sorted(violations, key=sev_order)
        
        for v in sorted_viols:
            # Severity Label
            pdf.set_font("helvetica", "B", 10)
            if v.severity == Severity.ERROR:
                pdf.set_text_color(*COLOR_ERROR)
            elif v.severity == Severity.WARNING:
                pdf.set_text_color(200, 150, 0)
            else:
                pdf.set_text_color(*COLOR_INFO)
                
            pdf.cell(25, 6, f"[{v.severity}]", ln=False)
            
            # Category & Description
            pdf.set_text_color(*COLOR_TEXT)
            pdf.set_font("helvetica", "B", 10)
            pdf.cell(0, 6, f"{v.category}: {v.description}", ln=True)
            
            # Detail
            if v.detail:
                pdf.set_font("helvetica", "", 10)
                pdf.set_text_color(100, 100, 100)
                pdf.set_x(35) # indent
                # replace smart quotes and invalid chars for latin-1 which fpdf expects by default
                try:
                    safe_detail = v.detail.encode('latin-1', 'replace').decode('latin-1')
                except:
                    safe_detail = v.detail
                pdf.multi_cell(0, 6, f"Detail: {safe_detail}")
                
            # Location
            if v.location:
                pdf.set_font("helvetica", "I", 9)
                pdf.set_text_color(150, 150, 150)
                pdf.set_x(35)
                # Ensure no invalid chars for simple pdf
                loc_text = v.location.replace('\n', ' ').strip()[:100]
                try:
                    loc_text = loc_text.encode('latin-1', 'replace').decode('latin-1')
                except:
                    pass
                pdf.multi_cell(0, 5, f"Location: \"{loc_text}\"")
                
            pdf.ln(2)
            
        pdf.ln(5)

    pdf.output(str(out_path))
    return out_path
