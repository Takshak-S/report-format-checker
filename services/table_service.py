"""
services/table_service.py

Provides functions for compiling table metadata and converting TableNode rows to DataFrames.
"""
import pandas as pd

from nlp.dom import DocumentModel, TableNode
from utils.constants import TABLE_CAPTION_PATTERN

def table_to_dataframe(table_node: TableNode) -> pd.DataFrame:
    """Converts a TableNode to a pandas DataFrame."""
    if not table_node.rows:
        return pd.DataFrame()
        
    # Assume first row is header for simplicity, but handle if it's not
    # pdfplumber extracts rows as list of lists.
    # Clean up None values
    clean_rows = []
    for row in table_node.rows:
        clean_row = [str(cell).strip() if cell is not None else "" for cell in row]
        if not any(clean_row):
            continue
        
        # Check if any cell contains newlines. If so, expand into multiple rows.
        max_lines = max((cell.count('\n') + 1 for cell in clean_row), default=1)
        if max_lines > 1:
            split_cells = [cell.split('\n') for cell in clean_row]
            for i in range(max_lines):
                new_row = [sc[i].strip() if i < len(sc) else "" for sc in split_cells]
                if any(new_row):  # Only add if the sub-row isn't completely empty
                    clean_rows.append(new_row)
        else:
            clean_rows.append(clean_row)
            
    if not clean_rows:
        return pd.DataFrame()
        
    df = pd.DataFrame(clean_rows)
    
    # Try to promote first row to header if it looks like one
    # Simple heuristic: if there are no empty strings in the first row
    if all(clean_rows[0]) and len(clean_rows) > 1:
        df.columns = clean_rows[0]
        df = df[1:].reset_index(drop=True)
        
    return df

def _find_caption_for_table(tbl_node: TableNode, doc: DocumentModel) -> tuple[str, str]:
    """
    Find the closest caption paragraph above the table on the same page.
    Returns (table_number, full_caption_text)
    """
    page = next((p for p in doc.pages if p.page_num == tbl_node.page_num), None)
    if not page:
        return "", ""
        
    paragraphs = page.get_paragraphs()
    # Find paragraphs above the table (y1 < table.y0)
    above_paras = [p for p in paragraphs if p.bbox.y1 <= tbl_node.bbox.y0 + 30] # 30pt tolerance
    above_paras.sort(key=lambda p: p.bbox.y1, reverse=True) # Sort bottom-up
    
    for p in above_paras:
        text = p.text.strip()
        if TABLE_CAPTION_PATTERN.match(text):
            import re
            m = re.search(r"(\d+\.\d+)", text)
            num = m.group(1) if m else ""
            return num, text
            
        # If we hit a non-caption paragraph that is very close, it might not be a table caption
        if tbl_node.bbox.y0 - p.bbox.y1 > 100:
            break
            
    return "", ""

def get_table_metadata(doc: DocumentModel) -> list[dict]:
    """
    Extracts all tables and their metadata from the DOM.
    Finds cross-references in the body text.
    """
    results = []
    
    # 1. Collect all tables and their captions
    for page in doc.pages:
        for tbl in page.get_tables():
            tbl_num, caption = _find_caption_for_table(tbl, doc)
            df = table_to_dataframe(tbl)
            
            tbl_id = f"tbl_p{tbl.page_num}_{int(tbl.bbox.x0)}_{int(tbl.bbox.y0)}"
            
            results.append({
                "id": tbl_id,
                "node": tbl,
                "page": tbl.page_num,
                "bbox": (tbl.bbox.x0, tbl.bbox.y0, tbl.bbox.x1, tbl.bbox.y1),
                "table_number": tbl_num,
                "caption": caption,
                "rows": len(df),
                "columns": len(df.columns) if not df.empty else 0,
                "dataframe": df,
                "referenced_pages": [],
                "is_referenced": False
            })
            
    # 2. Cross-reference in body text
    tbl_map = {res["table_number"]: idx for idx, res in enumerate(results) if res["table_number"]}
    
    if not tbl_map:
        return results
        
    import re
    for page in doc.pages:
        text = "\n".join(p.text for p in page.get_paragraphs())
        for tbl_num, idx in tbl_map.items():
            # Look for "Table X.Y" or "Tab. X.Y"
            pattern = re.compile(rf"(?:Table|Tab\.?)\s+{tbl_num}", re.IGNORECASE)
            
            matches = pattern.findall(text)
            
            if matches:
                is_caption_page = (results[idx]["page"] == page.page_num)
                count = len(matches) - (1 if is_caption_page else 0)
                
                if count > 0:
                    results[idx]["referenced_pages"].append(page.page_num)
                    results[idx]["is_referenced"] = True
                    
    return results
