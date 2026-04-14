"""
Tool handlers — the code that runs when the LLM calls cod_fiscal_lookup.

Queries the ChromaDB palace store for exact article matches by number,
optionally including norms and cross-referenced articles.
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Palace data path — resolved at import time
_PLUGIN_DIR = Path(__file__).parent
_DEFAULT_PALACE = _PLUGIN_DIR / "data" / "palace"
_ARTICLES_CACHE = {}
_PALACE_META = None


def _find_palace_path() -> Path:
    """Find the palace path — check multiple locations."""
    # 1. Plugin-bundled data
    bundled = _PLUGIN_DIR / "data" / "palace"
    if bundled.exists():
        return bundled
    
    # 2. Project directory
    project = _PLUGIN_DIR.parent.parent / "data" / "palace"
    if project.exists():
        return project
    
    # 3. Home directory
    home = Path.home() / ".fiscgent" / "palace"
    if home.exists():
        return home
    
    # Fallback
    return bundled


def _get_chroma_collection():
    """Get the ChromaDB collection (lazy init)."""
    try:
        import chromadb
    except ImportError:
        logger.error("chromadb not installed")
        return None
    
    palace_path = _find_palace_path()
    chroma_dir = palace_path / "chroma"
    
    if not chroma_dir.exists():
        logger.error(f"ChromaDB directory not found: {chroma_dir}")
        return None
    
    client = chromadb.PersistentClient(path=str(chroma_dir))
    try:
        return client.get_collection("mempalace_drawers")
    except Exception as e:
        logger.error(f"Failed to get collection: {e}")
        return None


def _load_articles_index() -> dict:
    """Load the article index for fast lookups."""
    global _ARTICLES_CACHE
    if _ARTICLES_CACHE:
        return _ARTICLES_CACHE
    
    palace_path = _find_palace_path()
    
    # Try loading from extracted JSON first (faster than ChromaDB for exact lookups)
    extracted_dir = palace_path.parent / "extracted" if palace_path.name == "palace" else None
    if extracted_dir is None:
        extracted_dir = _PLUGIN_DIR.parent.parent / "data" / "extracted"
    
    full_json = extracted_dir / "cod_fiscal_full.json" if extracted_dir else None
    if full_json and full_json.exists():
        with open(full_json, 'r', encoding='utf-8') as f:
            data = json.load(f)
        _ARTICLES_CACHE = data.get("articles", {})
        logger.info(f"Loaded {len(_ARTICLES_CACHE)} articles from index")
        return _ARTICLES_CACHE
    
    # Fallback: load individual article files
    articles_dir = extracted_dir / "articles" if extracted_dir else None
    if articles_dir and articles_dir.exists():
        for f in articles_dir.glob("art_*.json"):
            with open(f, 'r', encoding='utf-8') as fh:
                article = json.load(fh)
            _ARTICLES_CACHE[article["articol"]] = article
        logger.info(f"Loaded {len(_ARTICLES_CACHE)} articles from individual files")
        return _ARTICLES_CACHE
    
    return {}


def cod_fiscal_lookup(args: dict, **kwargs) -> str:
    """
    Look up a specific article from the Cod Fiscal.
    
    Returns JSON with the full article text, norms, and optional cross-references.
    """
    article_number = args.get("article_number", "").strip()
    include_norms = args.get("include_norms", True)
    resolve_references = args.get("resolve_references", False)
    
    if not article_number:
        return json.dumps({"error": "No article number provided"})
    
    try:
        articles = _load_articles_index()
        
        if not articles:
            return json.dumps({
                "error": "Article index not loaded. Run the ingestion script first."
            })
        
        # Normalize article number
        art_num = article_number.replace("Art.", "").replace("art.", "").strip()
        
        if art_num not in articles:
            # Try fuzzy match
            candidates = [k for k in articles.keys() if k.startswith(art_num)]
            if candidates:
                return json.dumps({
                    "error": f"Article {art_num} not found exactly. Did you mean: {', '.join(sorted(candidates)[:5])}?"
                })
            return json.dumps({"error": f"Article {art_num} not found in Cod Fiscal"})
        
        article = articles[art_num]
        
        result = {
            "article": art_num,
            "title": article["articol_title"],
            "section_path": article["section_path"],
            "text": article["text"],
            "is_abrogated": article["is_abrogated"],
            "cross_references": article["cross_references"],
        }
        
        if include_norms and article.get("norme_text"):
            result["norms"] = article["norme_text"]
        
        if resolve_references and article["cross_references"]:
            refs = []
            for ref in article["cross_references"][:5]:  # Limit to 5
                ref_num = ref.replace("art. ", "")
                if ref_num in articles:
                    ref_art = articles[ref_num]
                    # Include title and first paragraph only
                    first_para = ref_art["text"].split("\n\n")[0][:300]
                    refs.append({
                        "article": ref_num,
                        "title": ref_art["articol_title"],
                        "section_path": ref_art["section_path"],
                        "preview": first_para,
                    })
            result["referenced_articles"] = refs
        
        return json.dumps(result, ensure_ascii=False)
    
    except Exception as e:
        logger.exception("Error in cod_fiscal_lookup")
        return json.dumps({"error": f"Lookup failed: {str(e)}"})


def search_fiscal_code(query: str, top_k: int = 5, wing: Optional[str] = None) -> list[dict]:
    """
    Semantic search across the Cod Fiscal using ChromaDB.
    Used internally by the pre_llm_call hook.
    """
    collection = _get_chroma_collection()
    if collection is None:
        return []
    
    try:
        where_filter = None
        if wing:
            where_filter = {"wing": wing}
        
        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )
        
        hits = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 0
                hits.append({
                    "text": doc[:500],
                    "section_path": meta.get("section_path", ""),
                    "article_number": meta.get("article_number", ""),
                    "type": meta.get("type", ""),
                    "distance": distance,
                })
        
        return hits
    
    except Exception as e:
        logger.exception("Error in search_fiscal_code")
        return []
