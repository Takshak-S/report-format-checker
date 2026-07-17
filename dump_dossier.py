import json
import fitz
from pathlib import Path
from checker import run_checks
import os

def main():
    pdf_path = "student-project-report.pdf"
    doc, collector = run_checks(pdf_path, skip_grammar=True)
    
    viols = collector.all
    print(f"Total violations found: {len(viols)}")
    
    output_dir = Path("/home/takshak/.gemini/antigravity-ide/brain/883bcc7e-7818-498a-a661-f341299e1b90/scratch")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    dossier_data = []
    
    # We want to dump all violations
    for i, v in enumerate(viols):
        if "Page Layout" not in v.category:
            continue
            
        print(f"Processing violation: {v.category} on page {v.page}")
        
        # Get confidence and block type from the DOM
        confidence = 0.0
        block_type = "UNKNOWN"
        # Since we don't have the exact DOM node directly mapped in Violation (we only have bbox), 
        # let's search the DOM for a paragraph matching the bbox.
        for page_node in doc.pages:
            if page_node.page_num == v.page:
                for p in page_node.get_paragraphs():
                    if (abs(p.bbox.x0 - v.bbox[0]) < 1.0 and abs(p.bbox.y0 - v.bbox[1]) < 1.0):
                        block_type = p.block_type.value
                        confidence = p.classification_confidence
                        break
        
        # Extract Image Snippet
        img_filename = f"violation_{i}_p{v.page}.png"
        img_path = output_dir / img_filename
        
        if v.bbox:
            pdf_doc = fitz.open(pdf_path)
            page = pdf_doc[v.page - 1]
            # Expand bbox a bit for context
            rect = fitz.Rect(max(0, v.bbox[0]-20), max(0, v.bbox[1]-20), min(page.rect.width, v.bbox[2]+20), min(page.rect.height, v.bbox[3]+20))
            
            # Draw red rect on it for annotation
            annot = page.add_rect_annot(fitz.Rect(*v.bbox))
            annot.set_colors(stroke=(1, 0, 0))
            annot.update()
            
            pix = page.get_pixmap(clip=rect, matrix=fitz.Matrix(2, 2))
            pix.save(str(img_path))
            pdf_doc.close()
            
        dossier_data.append({
            "page": v.page,
            "rule": v.description,
            "bbox": v.bbox,
            "expected": v.detail.split(", ")[0].replace("Expected ", "") if v.detail else "",
            "detected": v.detail.split(", ")[1].replace("found ", "") if v.detail and "," in v.detail else "",
            "confidence": confidence,
            "block_type": block_type,
            "image": str(img_path)
        })
        
    with open(output_dir / "dossier_data.json", "w") as f:
        json.dump(dossier_data, f, indent=2)
        
    print("Dossier extraction complete.")

if __name__ == "__main__":
    main()
