"""
services/image_service.py

Provides functions for extracting image bytes, generating thumbnails,
and compiling image metadata from the DOM.
"""
import io
import fitz
from PIL import Image
import hashlib

from nlp.dom import DocumentModel, ImageNode, BlockType
from utils.constants import FIGURE_CAPTION_PATTERN

def extract_image_bytes(pdf_bytes: bytes, page_num: int, xref: int, bbox: tuple) -> bytes:
    """
    Extracts the image bytes from the PDF.
    First tries to extract the exact embedded image using xref.
    If that fails or no xref is present, crops the page at the given bounding box.
    """
    try:
        doc = fitz.open("pdf", pdf_bytes)
        
        # 1. Try extracting exact original image via xref
        if xref > 0:
            try:
                base_image = doc.extract_image(xref)
                if base_image and "image" in base_image:
                    return base_image["image"]
            except Exception:
                pass
                
        # 2. Fallback: Crop page region
        page = doc[page_num - 1]
        x0, y0, x1, y1 = bbox
        
        # Expand slightly to ensure we capture the whole image
        rect = fitz.Rect(x0, y0, x1, y1)
        pix = page.get_pixmap(clip=rect, dpi=150)
        return pix.tobytes("png")
        
    except Exception as e:
        print(f"Error extracting image bytes: {e}")
        return b""

def generate_thumbnail(image_bytes: bytes, max_size: tuple[int, int] = (256, 256)) -> bytes:
    """Generates a thumbnail for gallery view."""
    if not image_bytes:
        return b""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Convert to RGB if necessary (e.g. CMYK or RGBA)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
            
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return b""

def _find_caption_for_image(img_node: ImageNode, doc: DocumentModel) -> tuple[str, str]:
    """
    Find the closest caption paragraph below the image on the same page.
    Returns (figure_number, full_caption_text)
    """
    page = next((p for p in doc.pages if p.page_num == img_node.page_num), None)
    if not page:
        return "", ""
        
    paragraphs = page.get_paragraphs()
    # Find paragraphs below the image (y0 > image.y1)
    below_paras = [p for p in paragraphs if p.bbox.y0 >= img_node.bbox.y1 - 30] # 30pt tolerance
    below_paras.sort(key=lambda p: p.bbox.y0)
    
    for p in below_paras:
        text = p.text.strip()
        if FIGURE_CAPTION_PATTERN.match(text):
            # Extract number
            import re
            m = re.search(r"(\d+\.\d+)", text)
            num = m.group(1) if m else ""
            return num, text
            
        # If we hit a non-caption paragraph that is very close, it might not be a figure
        if p.bbox.y0 - img_node.bbox.y1 > 100:
            break
            
    return "", ""

def get_image_metadata(doc: DocumentModel) -> list[dict]:
    """
    Extracts all images and their metadata from the DOM.
    Finds cross-references in the body text.
    """
    results = []
    
    # 1. Collect all images and their captions
    for page in doc.pages:
        for img in page.get_images():
            fig_num, caption = _find_caption_for_image(img, doc)
            
            # Simple hash for unique ID
            img_id = f"img_p{img.page_num}_{int(img.bbox.x0)}_{int(img.bbox.y0)}"
            
            results.append({
                "id": img_id,
                "node": img,
                "page": img.page_num,
                "bbox": (img.bbox.x0, img.bbox.y0, img.bbox.x1, img.bbox.y1),
                "xref": img.xref,
                "width": img.width_px,
                "height": img.height_px,
                "dpi_x": img.dpi_x,
                "dpi_y": img.dpi_y,
                "colorspace": img.colorspace,
                "figure_number": fig_num,
                "caption": caption,
                "referenced_pages": [],
                "is_referenced": False
            })
            
    # 2. Cross-reference in body text
    # Map figure number to result index
    fig_map = {res["figure_number"]: idx for idx, res in enumerate(results) if res["figure_number"]}
    
    if not fig_map:
        return results
        
    import re
    for page in doc.pages:
        text = "\n".join(p.text for p in page.get_paragraphs())
        for fig_num, idx in fig_map.items():
            # Look for "Figure X.Y" or "Fig. X.Y"
            pattern = re.compile(rf"(?:Figure|Fig\.?)\s+{fig_num}", re.IGNORECASE)
            
            # If the figure is ON this page, the caption counts as 1. 
            # We want to see if it's referenced elsewhere, or referenced multiple times here.
            matches = pattern.findall(text)
            
            if matches:
                # If this page has the caption itself, subtract 1 from the count
                is_caption_page = (results[idx]["page"] == page.page_num)
                count = len(matches) - (1 if is_caption_page else 0)
                
                if count > 0:
                    results[idx]["referenced_pages"].append(page.page_num)
                    results[idx]["is_referenced"] = True
                    
    return results
