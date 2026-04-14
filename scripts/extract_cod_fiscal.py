#!/usr/bin/env python3
"""
Extract Cod Fiscal + Norme metodologice from the ANAF markdown export (current static publication; URL may contain «2023»).

Parses the downloaded markdown (converted from HTML) into structured JSON,
preserving the legal hierarchy: Titlu → Capitol → Secțiune → Articol + Norme.

Each article is stored as a complete, verbatim unit — no chunking.
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional


# --- Regex patterns for legal document structure ---

# TITLUL I - Dispoziții generale  or  TITLUL II1 \- Impozit suplimentar
RE_TITLU = re.compile(
    r'^TITLUL\s+([IVX\d]+(?:\d*)?)\s*\\?-?\s*(.+)$'
)

# CAPITOLUL I - Scopul și sfera de cuprindere
RE_CAPITOL = re.compile(
    r'^CAPITOLUL\s+([IVX\d]+(?:\d*)?)\s*\\?-?\s*(.+)$'
)

# SECȚIUNEA 1 - ... or SECȚIUNEA a 2-a - ...
RE_SECTIUNE = re.compile(
    r'^(?:\[)?SECȚIUNEA\s+(.+?)(?:\].*)?$', re.IGNORECASE
)

# ART. 291 - Cotele de taxă  or  ART. 81 \- Locul conducerii
# Also handles ART. 401 \- , ART. 221 etc
RE_ARTICOL = re.compile(
    r'^ART\.\s+(\d+(?:\d+)?)\s*\\?-?\s*(.*)$'
)

# Cross-references: art. 291, art. 7 alin. (1), art. 316
RE_CROSS_REF = re.compile(
    r'(?:art\.\s*|ART\.\s*)(\d+(?:\d+)?)', re.IGNORECASE
)

# Norme metodologice inline links
RE_NORME_LINK = re.compile(
    r'\[Norme metodologice\]\(.*?\)'
)

# Abrogated articles
RE_ABROGAT = re.compile(r'A\s*B\s*R\s*O\s*G\s*A\s*T')


def clean_text(text: str) -> str:
    """Clean up markdown artifacts from the text."""
    # Remove markdown link syntax but keep text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # Remove escaped characters
    text = text.replace('\\-', '-').replace('\\*', '*')
    # Collapse multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_cross_references(text: str, own_article: str) -> list[str]:
    """Extract cross-referenced article numbers from text."""
    refs = set()
    for match in RE_CROSS_REF.finditer(text):
        ref_num = match.group(1)
        if ref_num != own_article:
            refs.add(f"art. {ref_num}")
    return sorted(refs)


def parse_cod_fiscal(filepath: str) -> dict:
    """
    Parse the Cod Fiscal markdown file into a structured dictionary.
    
    Returns:
        {
            "metadata": {...},
            "titluri": [...],
            "articles": {
                "291": {article_dict},
                ...
            }
        }
    """
    path = Path(filepath)
    if not path.exists():
        print(f"Error: File not found: {filepath}")
        sys.exit(1)
    
    lines = path.read_text(encoding='utf-8').splitlines()
    print(f"Read {len(lines)} lines from {filepath}")
    
    # Find where body content starts (after ToC)
    body_start = 0
    for i, line in enumerate(lines):
        # The body starts when we see "TITLUL I" without a preceding link format
        if line.strip() == 'TITLUL I - Dispoziții generale' and i > 500:
            body_start = i
            break
    
    if body_start == 0:
        # Fallback: look for first ART. that's not inside a link
        for i, line in enumerate(lines):
            if line.startswith('ART. 1 - ') and i > 500:
                body_start = i
                break
    
    print(f"Body content starts at line {body_start + 1}")
    
    # Parse metadata from first few lines
    metadata = {
        "source": "https://static.anaf.ro/static/10/Anaf/legislatie/Cod_fiscal_norme_2023.htm",
        "title": "Legea nr. 227/2015 privind Codul fiscal",
        "header_lines": []
    }
    for line in lines[:10]:
        stripped = line.strip().strip('*').strip('_').strip()
        if stripped:
            metadata["header_lines"].append(stripped)
    
    # Parse body content
    articles = {}
    titluri = []
    
    current_titlu = None
    current_titlu_name = ""
    current_capitol = None
    current_capitol_name = ""
    current_sectiune = None
    current_sectiune_name = ""
    current_article_num = None
    current_article_title = ""
    current_article_lines = []
    current_is_norme = False
    current_norme_lines = []
    
    def flush_article():
        """Save the current article to the articles dict."""
        nonlocal current_article_num, current_article_lines, current_norme_lines
        if current_article_num is None:
            return
        
        article_text = clean_text('\n'.join(current_article_lines))
        norme_text = clean_text('\n'.join(current_norme_lines))
        
        is_abrogated = bool(RE_ABROGAT.search(article_text)) or bool(RE_ABROGAT.search(current_article_title))
        
        cross_refs = extract_cross_references(
            article_text + '\n' + norme_text, 
            current_article_num
        )
        
        # Build section path
        parts = []
        if current_titlu:
            parts.append(f"Titlul {current_titlu}")
        if current_capitol:
            parts.append(f"Cap. {current_capitol}")
        if current_sectiune:
            parts.append(f"Secț. {current_sectiune}")
        parts.append(f"Art. {current_article_num}")
        section_path = " > ".join(parts)
        
        article = {
            "articol": current_article_num,
            "articol_title": current_article_title,
            "titlu_id": current_titlu or "",
            "titlu_name": current_titlu_name,
            "capitol_id": current_capitol or "",
            "capitol_name": current_capitol_name,
            "sectiune_id": current_sectiune or "",
            "sectiune_name": current_sectiune_name,
            "section_path": section_path,
            "text": article_text,
            "norme_text": norme_text,
            "cross_references": cross_refs,
            "is_abrogated": is_abrogated,
        }
        
        articles[current_article_num] = article
        current_article_lines = []
        current_norme_lines = []
    
    # Track if we're inside norme section for an article
    norme_for_article = None
    
    for i in range(body_start, len(lines)):
        line = lines[i]
        stripped = line.strip()
        
        if not stripped:
            # Blank line — add to current buffer
            if current_article_num:
                if current_is_norme:
                    current_norme_lines.append('')
                else:
                    current_article_lines.append('')
            continue
        
        # Check for TITLU
        m = RE_TITLU.match(stripped)
        if m:
            flush_article()
            current_article_num = None
            current_titlu = m.group(1).strip()
            current_titlu_name = f"Titlul {current_titlu} - {m.group(2).strip()}"
            current_capitol = None
            current_capitol_name = ""
            current_sectiune = None
            current_sectiune_name = ""
            current_is_norme = False
            
            # Track titluri for structure
            titluri.append({
                "id": current_titlu,
                "name": current_titlu_name,
                "capitole": []
            })
            continue
        
        # Check for CAPITOL
        m = RE_CAPITOL.match(stripped)
        if m:
            flush_article()
            current_article_num = None
            current_capitol = m.group(1).strip()
            current_capitol_name = f"Capitolul {current_capitol} - {m.group(2).strip()}"
            current_sectiune = None
            current_sectiune_name = ""
            current_is_norme = False
            
            if titluri:
                titluri[-1]["capitole"].append({
                    "id": current_capitol,
                    "name": current_capitol_name
                })
            continue
        
        # Check for SECȚIUNE
        m = RE_SECTIUNE.match(stripped)
        if m:
            flush_article()
            current_article_num = None
            current_sectiune = m.group(1).strip()
            current_sectiune_name = stripped
            current_is_norme = False
            continue
        
        # Check for ART.
        m = RE_ARTICOL.match(stripped)
        if m:
            flush_article()
            current_article_num = m.group(1).strip()
            current_article_title = m.group(2).strip().rstrip('\\').strip()
            current_article_lines = []
            current_norme_lines = []
            current_is_norme = False
            continue
        
        # Check for "ACTE NORMATIVE" section headers
        if stripped == 'ACTE NORMATIVE':
            # These are supplementary normative act references
            if current_article_num:
                current_article_lines.append(line)
            continue
        
        # Check for Norme metodologice content
        # The norms are typically inline, appearing after the article they reference
        # They're marked with [Norme metodologice](url) links
        if '[Norme metodologice]' in stripped or 'Norme metodologice' == stripped:
            if current_article_num:
                current_is_norme = True
                current_norme_lines.append(stripped)
            continue
        
        # Regular content line — add to current article
        if current_article_num:
            if current_is_norme:
                current_norme_lines.append(line)
            else:
                current_article_lines.append(line)
    
    # Flush last article
    flush_article()
    
    print(f"Extracted {len(articles)} articles across {len(titluri)} titles")
    
    return {
        "metadata": metadata,
        "titluri": titluri,
        "articles": articles,
    }


def save_results(data: dict, output_dir: str):
    """Save extraction results to JSON files."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    
    # Save full data
    full_path = out / "cod_fiscal_full.json"
    with open(full_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved full data to {full_path} ({full_path.stat().st_size / 1024 / 1024:.1f} MB)")
    
    # Save structure (without article text, for quick reference)
    structure = {
        "metadata": data["metadata"],
        "titluri": data["titluri"],
        "article_index": {
            num: {
                "articol": a["articol"],
                "articol_title": a["articol_title"],
                "section_path": a["section_path"],
                "is_abrogated": a["is_abrogated"],
                "has_norme": bool(a["norme_text"]),
                "cross_references": a["cross_references"],
                "text_length": len(a["text"]),
            }
            for num, a in data["articles"].items()
        }
    }
    struct_path = out / "cod_fiscal_structure.json"
    with open(struct_path, 'w', encoding='utf-8') as f:
        json.dump(structure, f, ensure_ascii=False, indent=2)
    print(f"Saved structure index to {struct_path}")
    
    # Save individual articles for easy access
    articles_dir = out / "articles"
    articles_dir.mkdir(exist_ok=True)
    for num, article in data["articles"].items():
        art_path = articles_dir / f"art_{num}.json"
        with open(art_path, 'w', encoding='utf-8') as f:
            json.dump(article, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(data['articles'])} individual article files to {articles_dir}")
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"EXTRACTION SUMMARY")
    print(f"{'='*60}")
    print(f"Total articles: {len(data['articles'])}")
    print(f"Total titles: {len(data['titluri'])}")
    abrogated = sum(1 for a in data['articles'].values() if a['is_abrogated'])
    print(f"Abrogated articles: {abrogated}")
    with_norme = sum(1 for a in data['articles'].values() if a['norme_text'])
    print(f"Articles with norme: {with_norme}")
    total_refs = sum(len(a['cross_references']) for a in data['articles'].values())
    print(f"Total cross-references: {total_refs}")
    print(f"\nTitles:")
    for t in data['titluri']:
        art_count = sum(
            1 for a in data['articles'].values() 
            if a['titlu_id'] == t['id']
        )
        print(f"  {t['name']}: {art_count} articles, {len(t['capitole'])} chapters")


def main():
    # Default input path — the downloaded file
    default_input = str(Path.home() / "Downloads" / 
        "static.anaf.ro_static_10_Anaf_legislatie_Cod_fiscal_norme_2023.htm.2026-04-14T10_45_31.391Z.md")
    
    input_file = sys.argv[1] if len(sys.argv) > 1 else default_input
    output_dir = sys.argv[2] if len(sys.argv) > 2 else str(
        Path(__file__).parent.parent / "data" / "extracted"
    )
    
    print(f"Extracting Cod Fiscal from: {input_file}")
    print(f"Output directory: {output_dir}")
    print()
    
    data = parse_cod_fiscal(input_file)
    save_results(data, output_dir)


if __name__ == '__main__':
    main()
