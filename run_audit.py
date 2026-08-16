#!/usr/bin/env python3
import sys
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent))

from ingestion.pdf_loader import load_pdf
from nlp.classifier import LayoutAnalyzer
from utils.profile import build_profile
from checks.font_validator import FontValidator
from checks.margin_validator import MarginValidator
from checks.heading_validator import HeadingValidator
from checks.caption_validator import CaptionValidator
from checks.image_validator import ImageValidator
from checks.spacing_validator import SpacingValidator
from utils.error_model import ViolationCollector
from utils.noise_filter import apply_noise_filter
from utils.scoring import compute_score
from nlp.dom import BlockType

def run_full(pdf_path):
    doc = load_pdf(pdf_path)
    analyzer = LayoutAnalyzer()
    analyzer.classify(doc)
    profile = build_profile(doc)

    validators = [
        FontValidator(),
        MarginValidator(),
        HeadingValidator(),
        CaptionValidator(),
        ImageValidator(),
        SpacingValidator(),
    ]
    for v in validators:
        v.set_profile(profile)
        v.config = __import__('utils.config', fromlist=['get_config']).get_config()

    raw_collector = ViolationCollector()
    for v in validators:
        raw_collector.add_all(v.validate(doc))

    # raw stats
    raw_total = len(raw_collector.all)
    raw_by_cat = {}
    raw_by_sev = {}
    for viol in raw_collector.all:
        raw_by_cat[viol.category] = raw_by_cat.get(viol.category, 0) + 1
        raw_by_sev[viol.severity] = raw_by_sev.get(viol.severity, 0) + 1

    # apply noise filter
    final_collector = apply_noise_filter(raw_collector, doc)

    final_total = len(final_collector.all)
    final_by_cat = {}
    final_by_sev = {}
    for viol in final_collector.all:
        final_by_cat[viol.category] = final_by_cat.get(viol.category, 0) + 1
        final_by_sev[viol.severity] = final_by_sev.get(viol.severity, 0) + 1

    # classification counts
    block_counts = {}
    for p in doc.get_all_paragraphs():
        block_counts[p.block_type] = block_counts.get(p.block_type, 0) + 1

    # profile values
    prof = profile
    profile_vals = {
        'body_font_size': prof.body_font_size,
        'body_font_family': prof.body_font_family,
        'left_margin': prof.left_margin,
        'right_margin': prof.right_margin,
        'top_margin': prof.top_margin,
        'bottom_margin': prof.bottom_margin,
        'margin_tolerance': prof.margin_tolerance,
        'indent_tolerance': prof.indent_tolerance,
    }

    # heading sizes used by validator (config)
    from utils.config import get_config
    cfg = get_config()
    heading_sizes = {
        'L0': cfg.headings.level_0.size,
        'L1': cfg.headings.level_1.size,
        'L2': cfg.headings.level_2.size,
        'L3': cfg.headings.level_3.size,
    }

    # detailed violations list
    detailed = []
    for i, viol in enumerate(final_collector.all, 1):
        # find block type of paragraph if page>0
        block_type = None
        if viol.page > 0:
            page = doc.pages[viol.page - 1]
            for para in page.get_paragraphs():
                if para.bbox and para.bbox.x0 == viol.bbox[0] and para.bbox.y0 == viol.bbox[1]:
                    block_type = para.block_type
                    break
        detailed.append({
            'num': i,
            'category': viol.category,
            'severity': viol.severity,
            'page': viol.page,
            'description': viol.description,
            'confidence': viol.confidence,
            'block_type': block_type.value if block_type else None,
        })

    return {
        'pdf': Path(pdf_path).name,
        'pages': len(doc.pages),
        'raw_total': raw_total,
        'raw_by_cat': raw_by_cat,
        'raw_by_sev': raw_by_sev,
        'final_total': final_total,
        'final_by_cat': final_by_cat,
        'final_by_sev': final_by_sev,
        'detailed': detailed,
        'block_counts': {bt.value: cnt for bt, cnt in block_counts.items()},
        'profile': profile_vals,
        'heading_sizes': heading_sizes,
    }

if __name__ == '__main__':
    import json
    corpus_dir = Path(__file__).parent / 'test_files'
    pdfs = sorted(corpus_dir.glob('*.pdf'))
    all_results = []
    for pdf in pdfs:
        print(f'Processing {pdf.name}...', file=sys.stderr)
        res = run_full(pdf)
        all_results.append(res)
    print(json.dumps(all_results, indent=2, default=str))