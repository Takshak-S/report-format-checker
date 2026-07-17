import time
import sys
import psutil
import os
from pathlib import Path

from nlp.dom import DocumentModel, Page, Paragraph, BlockType, BBox
from nlp.classifier import LayoutAnalyzer
from checks.margin_validator import MarginValidator
from checks.font_validator import FontValidator
from utils.config import TemplateConfig, get_config

def generate_synthetic_document(num_pages: int, paras_per_page: int) -> DocumentModel:
    doc = DocumentModel()
    doc.pages = []
    
    for i in range(num_pages):
        page = Page(id=f"p_{i}", page_num=i+1, bbox=BBox(0, 0, 595, 842), width=595, height=842)
        for j in range(paras_per_page):
            p = Paragraph(
                id=f"p_{i}_{j}",
                page_num=i+1,
                bbox=BBox(108, 100 + (j*50), 523, 130 + (j*50)),
                text="This is a generated test paragraph for benchmarking.",
                dominant_font="TimesNewRoman",
                dominant_font_size=12.0,
                dominant_bold=False,
                dominant_italic=False
            )
            # Add synthetic lines to satisfy line-aware margin detector
            from nlp.dom import Line, Word
            line = Line(id=f"l_{i}_{j}", page_num=i+1, bbox=p.bbox, text=p.text, font="TimesNewRoman", font_size=12.0, bold=False, italic=False)
            word = Word(id=f"w_{i}_{j}", page_num=i+1, bbox=p.bbox, text=p.text, font="TimesNewRoman", font_size=12.0, bold=False, italic=False)
            line.add_child(word)
            p.add_child(line)
            
            page.add_child(p)
            
        doc.pages.append(page)
    return doc

def run_benchmarks():
    print(f"{'='*50}\nPDF FORMAT CHECKER BENCHMARK SUITE\n{'='*50}")
    
    scales = [
        (10, 20),    # 200 paragraphs
        (50, 30),    # 1500 paragraphs
        (200, 40)    # 8000 paragraphs
    ]
    
    config = get_config()
    analyzer = LayoutAnalyzer()
    validators = [MarginValidator(), FontValidator()]
    
    process = psutil.Process(os.getpid())
    
    for pages, p_per_page in scales:
        total_p = pages * p_per_page
        print(f"\n[ Scale: {pages} Pages, {total_p} Paragraphs ]")
        
        # Generation time
        start_mem = process.memory_info().rss / 1024 / 1024
        t0 = time.time()
        doc = generate_synthetic_document(pages, p_per_page)
        t1 = time.time()
        gen_mem = process.memory_info().rss / 1024 / 1024
        
        print(f"  DOM Generation : {(t1-t0)*1000:.2f} ms \t (Mem: {gen_mem - start_mem:.2f} MB)")
        
        # Classification time
        t2 = time.time()
        analyzer.classify(doc)
        t3 = time.time()
        print(f"  Classification : {(t3-t2)*1000:.2f} ms \t ({((t3-t2)/total_p)*1000:.3f} ms / paragraph)")
        
        # Validation time
        t4 = time.time()
        total_viols = 0
        for val in validators:
            viols = val.validate(doc)
            total_viols += len(viols)
        t5 = time.time()
        print(f"  Validation     : {(t5-t4)*1000:.2f} ms \t ({((t5-t4)/total_p)*1000:.3f} ms / paragraph)")
        print(f"  Violations     : {total_viols}")
        print(f"  Peak Memory    : {process.memory_info().rss / 1024 / 1024:.2f} MB")
        
    print("\nBenchmark completed.")

if __name__ == "__main__":
    run_benchmarks()
