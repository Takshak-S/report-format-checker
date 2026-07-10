# Project Report: Automated PDF Format Checker

## 1. Abstract
The Automated PDF Format Checker is an intelligent validation tool designed to assist students, researchers, and academic departments in ensuring that project reports conform strictly to specified formatting guidelines. By automating the tedious process of manual format checking, the system reduces the administrative burden on evaluators and ensures uniformity in academic submissions. The tool provides a user-friendly Streamlit web interface and a robust Command-Line Interface (CLI) to cater to different user preferences.

---

## 2. Problem Statement
Academic institutions and corporate departments often have strict guidelines for document formatting, encompassing rules for page margins, font styles, line spacing, heading hierarchies, figure and table captions, citation formats, and more. 
Traditionally, verifying adherence to these rules has been a manual, time-consuming, and error-prone process. Reviewers spend a significant amount of time checking margins or font sizes rather than focusing on the actual content of the report. There is a pressing need for a software solution that can parse PDF documents, automatically check for these formatting constraints, and generate a comprehensive violation report for the authors to rectify before final submission.

---

## 3. Proposed Solution
We propose the **PDF Format Checker**, a Python-based software tool that programmatically inspects PDF files against a predefined departmental standardization template. 

### Key Features:
- **Comprehensive Document Parsing**: Leverages advanced PDF parsing and OCR libraries to extract text, fonts, layout coordinates, and embedded images.
- **Automated Rule Validation**: Implements discrete checking modules for layout, typography, structure, grammar, and citations.
- **Detailed Reporting**: Generates an Excel-based report outlining exactly where violations occurred, making it easy for the user to fix their document.
- **Dual Interfaces**: Offers both a visual Web UI for individual users and a CLI for automated batch processing.

---

## 4. System Architecture
The system follows a modular architecture designed for high cohesion and loose coupling. This allows individual checks to be added or modified without affecting the rest of the application.

### 4.1 High-Level Flow
1. **Input Stage**: The user uploads a PDF file via the Web UI or passes the file path via the CLI.
2. **Ingestion Layer**: The PDF is parsed to extract metadata, text blocks (with font and size details), images, and page geometries.
3. **Orchestration Layer**: The `checker.py` module sequences the parsed document through an array of independent formatting checks.
4. **Processing Layer**: Individual modules evaluate specific rules (e.g., `font_checks.py`, `spacing_checks.py`). If a rule is violated, a `Violation` object is instantiated and collected.
5. **Output Stage**: The `reporter` module compiles the collected `Violation` objects into a structured Excel file and presents a summary to the user.

### 4.2 Module Directory Structure
- `ingestion/`: Handles document loading (`pdf_loader.py`), combining `pdfplumber` and `PyMuPDF` for accurate text and element extraction.
- `checks/`: The core business logic containing independent rule validators.
- `reporter/`: Responsible for formatting and saving the output into an `.xlsx` report (`report_generator.py`).
- `utils/`: Contains constants for rule definitions (`constants.py`) and error modeling structures (`error_model.py`).

---

## 5. Implementation Details

### 5.1 Formatting & Layout Checks
- **Page Geometry (`layout_checks.py`)**: Validates that all pages conform to the A4 size standard (210×297 mm) and enforces strict margins (Left 1.5″; Right, Top, and Bottom 1″).
- **Typography (`font_checks.py`)**: Ensures that "Times New Roman" is used exclusively throughout the document and validates the body text font size is exactly 12 pt.
- **Spacing & Alignment (`spacing_checks.py`)**: Analyzes line spacing to ensure a 1.5× multiplier and verifies that paragraphs are fully justified.

### 5.2 Structural Checks
- **Headings (`heading_checks.py`)**: Verifies the hierarchy and styling of headings.
  - Level 0 (Chapter Title): 16 pt, UPPERCASE, starts on a new page.
  - Level 1: 14 pt, Bold, UPPERCASE, decimal prefix.
  - Level 2: 12 pt, Title Case.
  - Level 3: 12 pt, Bold + Italic.
- **Document Flow (`chapter_checks.py`)**: Ensures the presence of all 8 mandatory chapters in the correct sequence.

### 5.3 Multimedia & Technical Checks
- **Images (`image_checks.py`)**: Checks image resolution to ensure it meets the ≥ 600 DPI standard. Utilizes Tesseract OCR to verify the presence of X and Y axis labels on graphs.
- **Captions (`caption_checks.py`)**: Ensures figure captions are positioned *below* images and table titles are positioned *above* tables, conforming to the `Figure X.Y` and `Table X.Y` numbering formats.
- **Equations (`equation_checks.py`)**: Checks that mathematical equations are right-aligned and numbered chapter-wise `(X.Y)`.

### 5.4 Language & Citations
- **Grammar (`grammar_checks.py`)**: Integrates `LanguageTool` to check for grammatical errors, while skipping false positives using a custom Computer Science domain dictionary (`CS_DICTIONARY`).
- **Citations (`citation_checks.py`)**: Validates adherence to APA 7th edition formatting and performs a bidirectional cross-check to ensure all in-text citations appear in the bibliography and vice versa.

---

## 6. Technology Stack
The project is built on a robust Python ecosystem:
- **Core Processing**: 
  - `pdfplumber`, `PyMuPDF`, `pypdf`, `pdfminer.six` (PDF parsing and layout analysis)
  - `Pillow` (Image extraction and processing)
- **Optical Character Recognition**: 
  - `pytesseract` (Graph label detection)
- **Natural Language Processing**: 
  - `language-tool-python` (Grammar and spell checking)
  - `regex` (Advanced pattern matching)
- **User Interface**: 
  - `streamlit` (Web framework)
  - `colorama` (Terminal styling)
- **Data Export**: 
  - `openpyxl` (Excel report generation)

---

## 7. User Manual & Deployment

### System Requirements
The system requires system-level dependencies for PDF rendering and OCR:
```bash
# Ubuntu / Debian
sudo apt-get install -y poppler-utils tesseract-ocr
# macOS
brew install poppler tesseract
```

### Running the Application
Users can choose between a graphical or command-line interface depending on their workflow.

**Web UI (Recommended for Individual Users):**
Provides an intuitive drag-and-drop interface for uploading PDFs and downloading the resulting Excel report.
```bash
streamlit run app.py
```

**Command-Line Interface (Recommended for Batch/CI Pipelines):**
Allows for quick validation and pipeline integration.
```bash
# Run a full check
python cli.py report.pdf

# Run check but skip grammar validation to increase speed
python cli.py report.pdf --skip-grammar
```

---

## 8. Conclusion and Future Scope
The Automated PDF Format Checker successfully bridges the gap between strict formatting requirements and the manual effort required to enforce them. By providing immediate, detailed feedback, it allows authors to easily rectify their documents before final submission.

**Future Enhancements:**
- **Auto-Correction**: Generating a fixed PDF/Word document where possible.
- **Customizable Templates**: Allowing users to upload JSON configuration files to define their own formatting rules dynamically.
- **Cloud Deployment**: Hosting the Streamlit application on cloud platforms (e.g., AWS, Heroku) as a centralized service for the entire institution.
