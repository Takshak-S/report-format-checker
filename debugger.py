import json
import fitz
from pathlib import Path
from ingestion.pdf_loader import load_pdf
from nlp.classifier import LayoutAnalyzer
from checker import run_checks
from checks.font_validator import FontValidator
from checks.margin_validator import MarginValidator
import statistics

def build_debugger():
    pdf_path = "sample_report.pdf"
    debug_dir = Path("debug")
    debug_dir.mkdir(exist_ok=True)
    
    print("Loading PDF...")
    doc = load_pdf(pdf_path)
    
    print("Classifying layout...")
    analyzer = LayoutAnalyzer()
    analyzer.classify(doc)
    
    print("Running Margin Validator...")
    margin_val = MarginValidator()
    margin_violations = margin_val.validate(doc)
    
    print("Running Font Validator...")
    font_val = FontValidator()
    font_violations = font_val.validate(doc)
    
    violations = margin_violations + font_violations
    
    print(f"Total Violations: {len(violations)} (Margins: {len(margin_violations)}, Fonts: {len(font_violations)})")
    
    # Dump Font Histograms
    font_histograms = {}
    for p in doc.get_all_paragraphs():
        size_counts = {}
        for l in p.get_lines():
            for w in l.get_words():
                length = len(w.text.strip()) or 1
                sz = round(w.font_size, 2)
                size_counts[sz] = size_counts.get(sz, 0) + length
        
        total_chars = sum(size_counts.values())
        if total_chars > 0:
            hist = {k: v/total_chars for k, v in size_counts.items()}
            font_histograms[p.id] = hist
            
    with open(debug_dir / "font_histograms.json", "w") as f:
        json.dump(font_histograms, f, indent=2)
        
    # Margin Data
    margin_data = []
    for p in doc.get_all_paragraphs():
        if p.block_type.value in ['BODY_TEXT', 'HEADING_1', 'HEADING_2', 'HEADING_3', 'CHAPTER_TITLE', 'LIST', 'REFERENCE', 'APPENDIX']:
            lines = p.get_lines()
            if not lines: continue
            
            left_edges = []
            right_edges = []
            for l in lines:
                words = l.get_words()
                if not words: continue
                left_edges.append(words[0].bbox.x0)
                right_edges.append(words[-1].bbox.x1)
            
            if not right_edges: continue
            margin_data.append({
                "page": p.page_num,
                "id": p.id,
                "type": p.block_type.value,
                "median_left": statistics.median(left_edges),
                "median_right": statistics.median(right_edges),
                "left_edges": left_edges,
                "right_edges": right_edges,
                "text": p.text[:50]
            })
            
    with open(debug_dir / "margin_data.json", "w") as f:
        json.dump(margin_data, f, indent=2)
        
    print("Generating violation crops...")
    pdf_doc = fitz.open(pdf_path)
    violation_details = []
    
    for i, v in enumerate(violations):
        page = pdf_doc[v.page - 1]
        
        # Expand bbox a bit for context
        rect = fitz.Rect(max(0, v.bbox[0]-50), max(0, v.bbox[1]-50), min(page.rect.width, v.bbox[2]+50), min(page.rect.height, v.bbox[3]+50))
        
        annot = page.add_rect_annot(fitz.Rect(*v.bbox))
        annot.set_colors(stroke=(1, 0, 0))
        annot.update()
        
        prefix = "F" if "font" in v.description.lower() else "M"
        img_filename = f"{prefix}{i:03d}_p{v.page}.png"
        img_path = debug_dir / img_filename
        
        pix = page.get_pixmap(clip=rect, matrix=fitz.Matrix(2, 2))
        pix.save(str(img_path))
        
        # Find DOM object ID
        dom_id = None
        for page_node in doc.pages:
            if page_node.page_num == v.page:
                for p in page_node.get_paragraphs():
                    if (abs(p.bbox.x0 - v.bbox[0]) < 2.0 and abs(p.bbox.y0 - v.bbox[1]) < 2.0):
                        dom_id = p.id
                        break
        
        violation_details.append({
            "id": f"{prefix}{i:03d}",
            "page": v.page,
            "rule": v.description,
            "bbox": v.bbox,
            "dom_id": dom_id,
            "confidence": v.confidence,
            "expected": v.expected,
            "detected": v.detected,
            "reason": v.reason,
            "image": str(img_path)
        })
        
    pdf_doc.close()
    
    with open(debug_dir / "violations.json", "w") as f:
        json.dump(violation_details, f, indent=2)
        
    print("Debugger pipeline complete. Data saved to debug/")

if __name__ == "__main__":
    build_debugger()
