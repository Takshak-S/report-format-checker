"""
cli.py — Command-line interface for the PDF Format Checker

Usage:
    python cli.py report.pdf
    python cli.py report.pdf --skip-grammar
    python cli.py report.pdf --output /path/to/report.xlsx
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

from checker import run_checks
from reporter.report_generator import generate_report
from reporter.pdf_report_generator import generate_pdf_report
from reporter.pdf_annotator import generate_annotated_pdf
from utils.constants import Severity

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init()
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False


def _color(text: str, color_code: str) -> str:
    if HAS_COLOR:
        return f"{color_code}{text}{Style.RESET_ALL}"
    return text


def _red(t):    return _color(t, Fore.RED)
def _yellow(t): return _color(t, Fore.YELLOW)
def _cyan(t):   return _color(t, Fore.CYAN)
def _green(t):  return _color(t, Fore.GREEN)
def _bold(t):   return _color(t, Style.BRIGHT)


def main():
    parser = argparse.ArgumentParser(
        description="PDF Format Checker — validates project report formatting."
    )
    parser.add_argument("pdf", help="Path to the PDF file to check")
    parser.add_argument(
        "--skip-grammar", action="store_true",
        help="Skip grammar/spelling check (much faster)",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output path for Excel report (default: same dir as PDF)",
    )
    parser.add_argument(
        "--no-report", action="store_true",
        help="Print results to console only, skip Excel generation",
    )
    parser.add_argument(
        "--no-annotated-pdf", action="store_true",
        help="Skip generating the highlighted/annotated PDF",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(_red(f"Error: File not found: {pdf_path}"), file=sys.stderr)
        sys.exit(1)

    # ── Progress callback ─────────────────────────────────────────────────────
    def progress(label: str, current: int, total: int):
        pct = int((current / total) * 100) if total else 0
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"\r  [{bar}] {pct:3d}%  {label:<35}", end="", flush=True)

    print(_bold(f"\n📄 PDF Format Checker"))
    print(f"   File: {pdf_path}")
    print(f"   Grammar check: {'disabled' if args.skip_grammar else 'enabled'}\n")

    # ── Run checks ────────────────────────────────────────────────────────────
    try:
        doc, collector = run_checks(
            pdf_path,
            progress_callback=progress,
            skip_grammar=args.skip_grammar,
        )
    except Exception as e:
        print(f"\n{_red('Error:')} {e}", file=sys.stderr)
        sys.exit(1)

    print("\n")  # newline after progress bar

    # ── Print summary ─────────────────────────────────────────────────────────
    summary = collector.summary()
    print(_bold("─" * 60))
    print(_bold("RESULTS SUMMARY"))
    print(_bold("─" * 60))
    print(f"  Total issues : {summary['total']}")
    print(f"  {_red('Errors')}   : {summary['errors']}")
    print(f"  {_yellow('Warnings')} : {summary['warnings']}")
    print(f"  {_cyan('Info')}     : {summary['info']}")
    print()

    overall = _green("✓ PASS") if summary["errors"] == 0 else _red("✗ FAIL")
    print(f"  Overall: {_bold(overall)}")
    print(_bold("─" * 60))

    # ── Print violations grouped by category ─────────────────────────────────
    by_cat = collector.by_category()
    if by_cat:
        print()
        print(_bold("VIOLATIONS BY CATEGORY"))
        print()

        severity_fmt = {
            Severity.ERROR:   _red,
            Severity.WARNING: _yellow,
            Severity.INFO:    _cyan,
        }

        for cat in sorted(by_cat.keys()):
            viols = by_cat[cat]
            print(f"  {_bold(cat)} ({len(viols)} issue(s))")
            for v in sorted(viols, key=lambda x: x.page):
                fmt = severity_fmt.get(v.severity, str)
                page = f"p.{v.page}" if v.page > 0 else "doc"
                line = f"    [{fmt(v.severity[:4])}] ({page}) {v.description}"
                if v.detail:
                    line += f"\n           → {v.detail}"
                print(line)
            print()

    # ── Generate Excel and PDF reports ────────────────────────────────────────
    if not args.no_report:
        report_path = generate_report(collector, str(pdf_path), args.output)
        pdf_report_out = str(Path(args.output).with_suffix('.pdf'))
        pdf_report_path = generate_pdf_report(collector, str(pdf_path), pdf_report_out)
        print(f"  {_green('✓')} Excel Report saved: {report_path}")
        print(f"  {_green('✓')} PDF Report saved: {pdf_report_path}")

    # ── Generate annotated PDF ────────────────────────────────────────────────
    if not args.no_annotated_pdf and not args.no_report:
        annotated_path = generate_annotated_pdf(
            collector,
            str(pdf_path),
        )
        print(f"  {_green('✓')} Highlighted PDF saved: {annotated_path}")

    sys.exit(0 if summary["errors"] == 0 else 1)


if __name__ == "__main__":
    main()
