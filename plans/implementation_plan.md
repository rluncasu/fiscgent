# FiscGent — Romanian Fiscal Code Expert Agent

An autonomous Hermes Agent specialized in Romanian fiscal/accounting law, powered by MemPalace for structured knowledge storage and retrieval over the **Codul Fiscal cu Norme metodologice** published on ANAF’s static site. The canonical URL and filenames may still contain **«2023»**; in practice the **scraped export reflects the current text ANAF serves** — keep the local snapshot in sync by re-scraping when ANAF updates the page.

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│           Local scraped export (ANAF Cod + Norme)            │
│  e.g. markdown/HTML snapshot — already obtained upstream     │
└──────────────────┬───────────────────────────────────────────┘
                   │ Phase 2: Parse → JSON
                   ▼
┌──────────────────────────────────────────────────────────────┐
│              Structured Articles & Norms                     │
│  Titlu → Capitol → Secțiune → Articol + Norme Metodologice  │
└──────────────────┬───────────────────────────────────────────┘
                   │ Phase 3: Ingest
                   ▼
┌──────────────────────────────────────────────────────────────┐
│                     MemPalace                                │
│                                                              │
│  Wing: titlu_ii_impozit_profit                               │
│    Room: capitol_i_dispozitii_generale                       │
│      Drawer: Art. 13 (verbatim)                              │
│      Drawer: Norme Art. 13 (verbatim)                        │
│    Room: capitol_ii_calculul_rezultatului_fiscal              │
│      Drawer: Art. 25 (verbatim) ──tunnel──┐                  │
│  Wing: titlu_vii_tva                      │                  │
│    Room: capitol_x_cotele_de_tva          │                  │
│      Drawer: Art. 291 (verbatim)          │                  │
│      Drawer: Norme Art. 291 (verbatim)    │                  │
│  Wing: definitii_si_concepte  ◄───────────┘                  │
│    Room: art_7_definitii                                     │
│      Drawer: Art. 7 (verbatim)                               │
│                                                              │
│  Knowledge Graph:                                            │
│    Art.291 → references → Art.7                              │
│    Art.291 → defines → "cota standard TVA = 19%"             │
│    Art.76  → applies_to → "venituri din salarii"             │
└───────────┬──────────────────────────┬───────────────────────┘
            │                          │
            │ MCP Server (29 tools)    │ Python API
            ▼                          ▼
┌─────────────────────┐  ┌────────────────────────────────────┐
│ Hermes MCP          │  │ Hermes Plugin: fiscgent            │
│ Integration         │  │                                    │
│                     │  │ Tool: cod_fiscal_lookup             │
│ mempalace_search    │  │   → exact article by number        │
│ mempalace_kg_query  │  │   → article + norms together       │
│ mempalace_traverse  │  │   → cross-reference resolution     │
│ mempalace_follow_   │  │                                    │
│   tunnels           │  │ Hook: pre_llm_call                 │
│ ...27 more tools    │  │   → auto-inject relevant context   │
│                     │  │                                    │
│ Best for:           │  │ Best for:                          │
│ Semantic search,    │  │ Exact lookups, structured          │
│ exploration,        │  │ responses, provenance,             │
│ cross-references    │  │ automatic RAG injection            │
└─────────────────────┘  └────────────────────────────────────┘
            │                          │
            └──────────┬───────────────┘
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                    Hermes Agent                              │
│                                                              │
│  SOUL.md: Expert contabil & fiscal român                     │
│  Personality: Romanian fiscal law specialist                 │
│  Dual access: MCP (broad search) + Plugin (precise lookup)  │
└──────────────────────────────────────────────────────────────┘
```

## User Review Required

> [!IMPORTANT]
> **Storage: MemPalace** (not chunking, not GraphRAG).
> MemPalace stores full articles verbatim as "drawers" inside a structured palace (Wings → Rooms → Drawers). This preserves legal document integrity — no lossy chunking, no summarization. The Palace structure maps naturally to the Cod Fiscal hierarchy (Titluri=Wings, Capitole=Rooms, Articole=Drawers). Tunnels auto-link cross-referenced articles. 96.6% recall on benchmarks in raw mode.

> [!IMPORTANT]
> **Dual Access: MCP + Hermes Plugin**.
> - **MCP**: Connects MemPalace's 29-tool MCP server to Hermes natively. Gives the agent full semantic search, knowledge graph queries, tunnel traversal, and exploration capabilities.
> - **Hermes Plugin**: A custom `cod_fiscal_lookup` tool for precise article-by-number retrieval with structured response (article text + norms + cross-refs). Also provides a `pre_llm_call` hook that auto-injects relevant fiscal context before every LLM call.

> [!WARNING]
> **LLM Provider**: You'll need an API key for an LLM provider configured in Hermes. MemPalace itself needs no API — everything is local (ChromaDB + local embeddings).

## Proposed Changes

### Phase 1: Install Dependencies

#### Setup
1. Install Hermes Agent via the official installer
2. Install MemPalace (`pip install mempalace`)
3. Run `hermes setup` to configure LLM provider
4. Verify both tools work independently

---

### Phase 2: Extract & Process ANAF Fiscal Code

#### [NEW] `scripts/extract_cod_fiscal.py`
A Python script that:
1. Reads the **already-scraped** source file from disk (path configurable; typical input is **markdown** produced from the ANAF HTML export, matching line-oriented headings like `TITLUL`, `CAPITOLUL`, `ART.`).
2. Parses line-by-line (and regex / light cleanup), preserving the legal hierarchy:
   - **Titluri** (Titles) — top-level divisions (e.g., "Titlul VII - Taxa pe valoarea adăugată")
   - **Capitole** (Chapters) — within titles
   - **Secțiuni** (Sections) — within chapters
   - **Articole** (Articles) — the atomic legal units, stored individually
   - **Norme metodologice** (Methodological norms) — stored as separate entries linked to their article
3. Extracts cross-references from each article (regex for "art. N", "alin. (N)", "pct. N")
4. Outputs structured JSON: one entry per article with metadata:
   ```json
   {
     "articol": "291",
     "titlu_name": "Titlul VII - Taxa pe valoarea adăugată",
     "capitol_name": "Capitolul X - Cotele de taxă pe valoarea adăugată",
     "sectiune_name": "Secțiunea 1",
     "articol_title": "Cotele de taxă pe valoarea adăugată",
     "text": "...(full article text)...",
     "norme_text": "...(full norms text for this article)...",
     "cross_references": ["art. 7", "art. 292", "art. 331"],
     "section_path": "Titlul VII > Cap. X > Secț. 1 > Art. 291"
   }
   ```

#### [NEW] `data/extracted/` directory
Contains the structured JSON output, ready for MemPalace ingestion.

---

### Phase 3: Ingest into MemPalace

#### [NEW] `scripts/ingest_to_mempalace.py`
A Python script that uses the MemPalace Python API to:

1. **Initialize the palace** at `~/.mempalace/palace` (or project-local)
2. **Create Wings** — one per Titlu:
   ```python
   # Wing per Title
   "wing_titlu_ii_impozit_profit"
   "wing_titlu_iv_impozit_venit"
   "wing_titlu_vii_tva"
   "wing_titlu_v_contributii_sociale"
   "wing_definitii"  # Art. 1-12 (general definitions)
   ```

3. **Create Rooms** — one per Capitol within each Wing:
   ```python
   # Rooms within wing_titlu_vii_tva
   "capitol_i_definitii_tva"
   "capitol_x_cotele_de_tva"
   "capitol_xi_operatiuni_scutite"
   ```

4. **Add Drawers** — one per Article (full verbatim text), one per Norme:
   ```python
   from mempalace.mcp_server import add_drawer  # or equivalent API
   
   add_drawer(
       wing="wing_titlu_vii_tva",
       room="capitol_x_cotele_de_tva",
       content=article_291_full_text,
       metadata={
           "type": "articol",
           "number": "291",
           "title": "Cotele de taxă pe valoarea adăugată",
           "section_path": "Titlul VII > Cap. X > Art. 291"
       }
   )
   
   add_drawer(
       wing="wing_titlu_vii_tva",
       room="capitol_x_cotele_de_tva",
       content=norme_291_full_text,
       metadata={
           "type": "norma",
           "for_article": "291",
           "section_path": "Titlul VII > Cap. X > Norme Art. 291"
       }
   )
   ```

5. **Build Knowledge Graph** — entities and relationships:
   ```python
   from mempalace.knowledge_graph import KnowledgeGraph
   kg = KnowledgeGraph()
   
   # Tax rates as facts
   kg.add_triple("art_291", "defines", "cota_standard_tva_19%")
   kg.add_triple("art_291", "defines", "cota_redusa_tva_9%")
   kg.add_triple("art_291", "defines", "cota_redusa_tva_5%")
   
   # Cross-references
   kg.add_triple("art_291", "references", "art_7")
   kg.add_triple("art_291", "references", "art_292")
   
   # Subject matter links
   kg.add_triple("art_76", "applies_to", "venituri_din_salarii")
   kg.add_triple("art_43", "applies_to", "impozit_dividende")
   ```

6. **Create Tunnels** — cross-wing connections where articles reference each other across Titles

#### [NEW] `scripts/build_kg_triples.py`
Helper script that parses the extracted articles to automatically:
- Detect cross-references (regex: `art\.\s*\d+`, `alin\.\s*\(\d+\)`)
- Extract tax rates, deadlines, thresholds as facts
- Generate knowledge graph triples

---

### Phase 4: Connect MemPalace MCP to Hermes

#### Configuration
Add MemPalace as an MCP server in Hermes config:
```yaml
# ~/.hermes/config.yaml
mcp:
  servers:
    mempalace:
      command: python
      args: ["-m", "mempalace.mcp_server"]
      env:
        MEMPALACE_PATH: "~/.mempalace/palace"
```

Or via CLI:
```bash
hermes mcp add mempalace -- python -m mempalace.mcp_server
```

This gives Hermes access to all 29 MemPalace MCP tools:
- `mempalace_search` — semantic search across all fiscal law
- `mempalace_kg_query` — query the knowledge graph
- `mempalace_kg_timeline` — temporal queries
- `mempalace_traverse` — navigate Wings → Rooms → Drawers
- `mempalace_follow_tunnels` — follow cross-references
- `mempalace_list_wings` / `mempalace_list_rooms` — browse structure
- `mempalace_get_drawer` — retrieve specific drawer content

---

### Phase 5: Create Hermes Plugin (Precise Lookup + Auto-RAG)

#### [NEW] `plugin/fiscgent/plugin.yaml`
```yaml
name: fiscgent
version: 1.0.0
description: >
  Romanian Fiscal Code expert — precise article lookup, 
  automatic context injection, and structured legal responses.
  Works alongside MemPalace MCP for comprehensive fiscal law access.
provides_tools:
  - cod_fiscal_lookup
provides_hooks:
  - pre_llm_call
```

#### [NEW] `plugin/fiscgent/__init__.py`
Registration that:
1. Registers `cod_fiscal_lookup` tool
2. Registers `pre_llm_call` hook for automatic RAG context injection
3. Installs the SOUL.md personality on first load

#### [NEW] `plugin/fiscgent/schemas.py`
```python
COD_FISCAL_LOOKUP = {
    "name": "cod_fiscal_lookup",
    "description": (
        "Look up a specific article from the Romanian Fiscal Code "
        "(Codul Fiscal cu Norme metodologice — extras ANAF). Returns the full "
        "article text, associated methodological norms, and cross-references. "
        "Use this when the user asks about a specific article number, or when "
        "you need the exact legal text for a provision. "
        "For broader semantic search, use mempalace_search instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "article_number": {
                "type": "string",
                "description": "Article number (e.g., '291', '76', '7')"
            },
            "include_norms": {
                "type": "boolean",
                "description": "Include methodological norms (default: true)",
                "default": True
            },
            "resolve_references": {
                "type": "boolean",
                "description": "Also fetch cross-referenced articles (default: false)",
                "default": False
            }
        },
        "required": ["article_number"]
    }
}
```

#### [NEW] `plugin/fiscgent/tools.py`
Tool handler that:
1. Queries the MemPalace palace via Python API for the exact article drawer
2. Optionally fetches the associated Norme drawer
3. Optionally resolves cross-references (fetches referenced articles)
4. Returns structured JSON:
   ```json
   {
     "article": "291",
     "title": "Cotele de taxă pe valoarea adăugată",
     "section_path": "Titlul VII > Cap. X > Art. 291",
     "text": "...(full article)...",
     "norms": "...(full norms)...",
     "cross_references": [
       {"article": "7", "preview": "Definiții - În înțelesul prezentului cod..."},
       {"article": "292", "preview": "Scutiri pentru operațiunile din interiorul țării..."}
     ]
   }
   ```

#### [NEW] `plugin/fiscgent/rag_hook.py`
The `pre_llm_call` hook that:
1. Analyzes the user's message for fiscal/legal intent
2. Searches MemPalace for relevant articles (semantic search)
3. Returns top 3-5 relevant article excerpts as injected context
4. Includes the section_path for provenance
5. Only fires when the query appears fiscal-related (keyword detection)

```python
def inject_fiscal_context(session_id, user_message, **kwargs):
    """Auto-inject relevant Cod Fiscal context before each LLM call."""
    if not _is_fiscal_query(user_message):
        return None  # not a fiscal question, skip
    
    results = search_memories(
        user_message, 
        palace_path=PALACE_PATH,
        wing=None,  # search all wings
        top_k=5
    )
    
    if not results:
        return None
    
    context = "📜 Context relevant din Codul Fiscal (extras ANAF):\n\n"
    for r in results:
        context += f"**{r['section_path']}**\n{r['text'][:500]}...\n\n"
    
    return {"context": context}
```

#### [NEW] `plugin/fiscgent/skill.md`
Bundled skill with detailed instructions:
- Always cite the specific Article number
- Distinguish between law text and methodological norms
- Use `cod_fiscal_lookup` for exact article retrieval
- Use `mempalace_search` for broad topic search
- Use `mempalace_kg_query` for relationship queries
- Dacă întrebarea depășește textul din cod/norme (ex. interpretări punctuale ANAF, spețe), recomandă verificarea surselor oficiale sau a unui expert

---

### Phase 6: Configure Agent Personality

#### [NEW] `plugin/fiscgent/SOUL.md`
```markdown
# Expert Contabil & Fiscal Român

Ești un expert contabil și fiscal specializat pe legislația fiscală românească.
Te bazezi pe **Codul Fiscal cu Normele Metodologice** (extras ANAF — conținutul curent al publicației statice; denumirile URL pot include «2023»),
accesibil prin MemPalace și instrumentul cod_fiscal_lookup.

## Instrumente disponibile
- `cod_fiscal_lookup` — caută un articol specific după număr (include text + norme)
- `mempalace_search` — căutare semantică în tot Codul Fiscal
- `mempalace_kg_query` — întreabă graficul de cunoștințe (rate, termene, referințe)
- `mempalace_traverse` — navighează structura: Titluri → Capitole → Articole
- `mempalace_follow_tunnels` — urmărește referințele încrucișate între articole

## Comportament
- Răspunzi în limba utilizatorului (română sau engleză)
- Citezi întotdeauna articolul specific din Codul Fiscal
- Faci distincție clară între textul legii și normele metodologice
- Când un articol face referire la alt articol, folosește tunnel/lookup pentru context complet
- Oferi exemple practice pentru a clarifica prevederile complexe
- Recomanzi consultarea unui expert autorizat pentru situații specifice
- Menționezi explicit că te bazezi pe textul extras din codul fiscal și normele metodologice ANAF, pentru claritate

## Domenii de expertiză
- Impozit pe profit (Titlul II)
- Impozit pe veniturile microîntreprinderilor (Titlul III)
- Impozit pe venit (Titlul IV)
- Contribuții sociale obligatorii (Titlul V)
- Impozitul pe veniturile obținute din România de nerezidenți (Titlul VI)
- Taxa pe valoarea adăugată (Titlul VII)
- Accize și alte taxe speciale (Titlul VIII)
- Impozite și taxe locale (Titlul IX)
```

---

### Phase 7: Install Script & Documentation

#### [NEW] `install.sh`
One-click setup:
1. Create Python venv and install dependencies
2. Install Hermes Agent (if not present)
3. Install MemPalace
4. Run extraction script
5. Run ingestion script (populate MemPalace palace)
6. Copy plugin to `~/.hermes/plugins/fiscgent/`
7. Configure MCP server in Hermes config
8. Copy SOUL.md
9. Print usage instructions

#### [NEW] `README.md`
Full documentation with usage examples.

#### [NEW] `requirements.txt`
```
mempalace>=3.1.0
chromadb
# Add only what extract/ingest scripts actually import (no BeautifulSoup/lxml/httpx for downloading — scraping is out of band).
```

## Project Structure

```
fiscgent/
├── install.sh                          # One-click setup
├── requirements.txt                    # Python dependencies
├── README.md                           # Documentation
├── scripts/
│   ├── extract_cod_fiscal.py          # scraped source file → structured JSON
│   ├── ingest_to_mempalace.py         # JSON → MemPalace palace
│   └── build_kg_triples.py           # Extract KG triples from articles
├── data/
│   └── extracted/                     # Structured JSON (generated)
├── plugin/
│   └── fiscgent/
│       ├── plugin.yaml               # Hermes plugin manifest
│       ├── __init__.py                # Registration
│       ├── schemas.py                 # Tool schemas
│       ├── tools.py                   # cod_fiscal_lookup handler
│       ├── rag_hook.py               # pre_llm_call auto-injection
│       ├── skill.md                   # Bundled skill instructions
│       └── SOUL.md                    # Agent personality
└── tests/
    ├── test_extraction.py             # Verify all articles extracted
    ├── test_mempalace.py              # Verify palace structure
    └── test_plugin.py                 # Verify tool responses
```

## Open Questions

> [!IMPORTANT]
> **Do you already have Hermes Agent installed?** If yes, I skip that step and go straight to extraction + MemPalace.

> [!IMPORTANT]
> **Which LLM provider will you use?** This affects answer quality. A strong model (Claude Opus, GPT-4, etc.) will interpret romanian legal nuances far better than a small local model.

> [!IMPORTANT]
> **MemPalace palace location**: Default `~/.mempalace/palace` or project-local in `fiscgent/data/palace/`? Project-local keeps everything self-contained; global shares with any other MemPalace usage you may have.

## Verification Plan

### Automated Tests
1. **Extraction**: Verify all Titles (I-IX), all Chapters, and key articles (Art. 7, 76, 291, 292) are extracted
2. **MemPalace structure**: Verify Wings match Titles, Rooms match Chapters, Drawers contain full article text
3. **Knowledge Graph**: Query "art_291 references" → should return art. 7, art. 292
4. **Plugin tool**: `cod_fiscal_lookup(article_number="291")` → returns full text + norms
5. **MCP integration**: `mempalace_search("cota TVA")` → returns Art. 291
6. **RAG hook**: Ask "Ce taxe plătesc pe dividende?" → auto-injects Art. 43 context

### Manual Verification
- Ask complex multi-article questions that require tunnel traversal
- Verify Romanian legal terminology is handled correctly
- Test provenance: every answer should cite specific articles
- Compare agent answers against the source document directly
