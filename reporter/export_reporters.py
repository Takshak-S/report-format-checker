import json
import csv
from pathlib import Path
from utils.error_model import ViolationCollector
from utils.constants import Severity
from utils.scoring import compute_score

def generate_json_report(collector: ViolationCollector, pdf_name: str, output_path: str | Path = None) -> Path:
    if output_path is None:
        output_path = Path(pdf_name).with_suffix(".report.json")
        
    data = {
        "pdf_name": pdf_name,
        "summary": collector.summary(),
        "violations": [v.to_dict() for v in collector.all]
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        
    return Path(output_path)

def generate_csv_report(collector: ViolationCollector, pdf_name: str, output_path: str | Path = None) -> Path:
    if output_path is None:
        output_path = Path(pdf_name).with_suffix(".report.csv")
        
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Page", "Category", "Severity", "Description", "Detail", "Location"])
        
        for v in collector.all:
            writer.writerow([
                v.page if v.page > 0 else "Doc",
                v.category,
                v.severity,
                v.description,
                v.detail or "",
                v.location or ""
            ])
            
    return Path(output_path)

def generate_html_report(collector: ViolationCollector, pdf_name: str, output_path: str | Path = None) -> Path:
    if output_path is None:
        output_path = Path(pdf_name).with_suffix(".report.html")
        
    summary = collector.summary()
    total = summary['total']

    # Document score — single source of truth in utils/scoring.py
    score, grade = compute_score(collector)
    
    page_data = collector.by_page()
    heatmap_html = ""
    if page_data:
        max_page = max(page_data.keys())
        for p in range(1, max_page + 1):
            count = len(page_data.get(p, []))
            intensity = min(1.0, count / 10.0) if count else 0
            color = f"rgba(239, 68, 68, {intensity})" if count else "rgba(34, 197, 94, 0.1)"
            heatmap_html += f'<div class="heatmap-cell" style="background: {color};" title="Page {p}: {count} issues">{p}</div>'

    rows_html = ""
    for v in collector.all:
        sev_class = v.severity.lower()
        
        # Explainability Block
        explain_html = ""
        if v.reason or v.signals:
            explain_html += "<div class='explain-box'>"
            if v.expected:
                explain_html += f"<p><strong>Expected:</strong> {v.expected} <span>|</span> <strong>Detected:</strong> {v.detected}</p>"
            if v.confidence > 0:
                explain_html += f"<p><strong>Confidence:</strong> {round(v.confidence * 100, 1)}%</p>"
            if v.reason:
                explain_html += f"<p><strong>Reason:</strong> {v.reason}</p>"
            if v.suggested_fix:
                explain_html += f"<p><strong>Suggested Fix:</strong> <span style='color: #10b981;'>{v.suggested_fix}</span></p>"
            if v.signals:
                explain_html += "<p><strong>Signals:</strong></p><ul>"
                for s in v.signals:
                    explain_html += f"<li>{s}</li>"
                explain_html += "</ul>"
            explain_html += "</div>"
            
        rows_html += f"""
        <div class="violation-card border-{sev_class}">
            <div class="v-header">
                <span class="badge badge-{sev_class}">{v.severity}</span>
                <span class="v-category">{v.category}</span>
                <span class="v-page">Page {v.page if v.page > 0 else 'Doc'}</span>
            </div>
            <div class="v-rule">{v.description}</div>
            <div class="v-location">"{v.location or 'N/A'}"</div>
            {explain_html}
        </div>
        """
        
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Validation Dashboard - {pdf_name}</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg: #0f172a; --surface: #1e293b; --text: #f8fafc; --text-muted: #94a3b8;
                --critical: #ef4444; --major: #f97316; --minor: #eab308;
                --warning: #3b82f6; --info: #64748b; --success: #10b981;
            }}
            body {{
                font-family: 'Inter', sans-serif; background-color: var(--bg); color: var(--text);
                margin: 0; padding: 40px; box-sizing: border-box;
            }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            .header {{ text-align: center; margin-bottom: 40px; }}
            .header h1 {{ font-size: 2.5rem; font-weight: 700; margin: 0; background: -webkit-linear-gradient(45deg, #3b82f6, #10b981); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
            .header p {{ color: var(--text-muted); font-size: 1.1rem; }}
            
            /* Glassmorphism Stats */
            .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 20px; margin-bottom: 40px; }}
            .stat-card {{ background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(10px); padding: 20px; border-radius: 16px; border: 1px solid rgba(255,255,255,0.05); text-align: center; transition: transform 0.3s ease; }}
            .stat-card:hover {{ transform: translateY(-5px); }}
            .stat-card.score {{ border-bottom: 4px solid var(--success); }}
            .stat-card.critical {{ border-bottom: 4px solid var(--critical); }}
            .stat-card.major {{ border-bottom: 4px solid var(--major); }}
            .stat-value {{ font-size: 2.5rem; font-weight: 700; margin-bottom: 5px; }}
            .stat-label {{ color: var(--text-muted); font-size: 0.9rem; text-transform: uppercase; letter-spacing: 1px; }}
            
            /* Heatmap */
            .heatmap-section {{ background: var(--surface); padding: 30px; border-radius: 16px; margin-bottom: 40px; }}
            .heatmap-section h2 {{ margin-top: 0; font-size: 1.5rem; }}
            .heatmap-grid {{ display: flex; flex-wrap: wrap; gap: 8px; }}
            .heatmap-cell {{ width: 35px; height: 35px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 0.8rem; font-weight: 600; cursor: pointer; transition: transform 0.2s; }}
            .heatmap-cell:hover {{ transform: scale(1.2); }}
            
            /* Violations List */
            .violations-section {{ margin-top: 40px; }}
            .violation-card {{ background: var(--surface); padding: 25px; border-radius: 12px; margin-bottom: 20px; border-left: 5px solid var(--info); box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }}
            .border-critical {{ border-left-color: var(--critical); }}
            .border-major {{ border-left-color: var(--major); }}
            .border-minor {{ border-left-color: var(--minor); }}
            .border-warning {{ border-left-color: var(--warning); }}
            
            .v-header {{ display: flex; align-items: center; gap: 15px; margin-bottom: 15px; }}
            .badge {{ padding: 5px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; }}
            .badge-critical {{ background: rgba(239, 68, 68, 0.2); color: var(--critical); }}
            .badge-major {{ background: rgba(249, 115, 22, 0.2); color: var(--major); }}
            .badge-minor {{ background: rgba(234, 179, 8, 0.2); color: var(--minor); }}
            .badge-warning {{ background: rgba(59, 130, 246, 0.2); color: var(--warning); }}
            .v-category {{ font-weight: 600; color: #fff; }}
            .v-page {{ margin-left: auto; color: var(--text-muted); font-size: 0.9rem; }}
            
            .v-rule {{ font-size: 1.2rem; font-weight: 600; margin-bottom: 10px; }}
            .v-location {{ font-family: monospace; color: var(--warning); background: rgba(0,0,0,0.3); padding: 10px; border-radius: 6px; margin-bottom: 15px; }}
            
            /* Explainability Box */
            .explain-box {{ background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.05); padding: 20px; border-radius: 8px; font-size: 0.95rem; line-height: 1.5; }}
            .explain-box p {{ margin: 0 0 10px 0; }}
            .explain-box strong {{ color: #e2e8f0; }}
            .explain-box ul {{ margin: 0; padding-left: 20px; color: var(--text-muted); }}
            .explain-box li {{ margin-bottom: 5px; }}
            
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Validation Dashboard</h1>
                <p>{pdf_name}</p>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card score">
                    <div class="stat-value" style="color: var(--success);">{score}/100 ({grade})</div>
                    <div class="stat-label">Doc Score</div>
                </div>
                <div class="stat-card critical">
                    <div class="stat-value" style="color: var(--critical);">{summary.get('critical', 0)}</div>
                    <div class="stat-label">Critical</div>
                </div>
                <div class="stat-card major">
                    <div class="stat-value" style="color: var(--major);">{summary.get('major', 0)}</div>
                    <div class="stat-label">Major</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color: var(--minor);">{summary.get('minor', 0)}</div>
                    <div class="stat-label">Minor</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color: var(--warning);">{summary.get('warnings', 0)}</div>
                    <div class="stat-label">Warnings</div>
                </div>
            </div>
            
            <div class="heatmap-section">
                <h2>Page Heatmap (Issues per Page)</h2>
                <div class="heatmap-grid">
                    {heatmap_html}
                </div>
            </div>
            
            <div class="violations-section">
                <h2>Detailed Explainability Report</h2>
                {rows_html}
            </div>
        </div>
    </body>
    </html>
    """
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
        
    return Path(output_path)
