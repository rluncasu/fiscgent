#!/usr/bin/env python3
"""
Ingest structured Cod Fiscal data into MemPalace.

Creates a palace structure:
  Wings  = Titluri (Titles)
  Rooms  = Capitole (Chapters) 
  Drawers = Articole (Articles) + Norme (Methodological norms)

Also builds a Knowledge Graph with cross-references and key facts.
"""

import json
import re
import sys
import subprocess
from pathlib import Path
from typing import Optional


def slugify(text: str) -> str:
    """Convert a title to a wing/room slug."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s_]', '', text)
    text = re.sub(r'\s+', '_', text.strip())
    # Truncate to reasonable length
    if len(text) > 60:
        text = text[:60].rsplit('_', 1)[0]
    return text


def make_wing_name(titlu_id: str, titlu_name: str) -> str:
    """Create a wing name from a title."""
    return f"wing_{slugify(titlu_name)}"


def make_room_name(capitol_name: str) -> str:
    """Create a room name from a chapter."""
    return slugify(capitol_name)


def run_mempalace_cmd(args: list[str], check: bool = True) -> str:
    """Run a mempalace CLI command."""
    cmd = ["mempalace"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  Warning: mempalace {' '.join(args)} failed: {result.stderr}")
    return result.stdout


def ingest_with_python_api(data: dict, palace_path: str):
    """Ingest articles into a ChromaDB-backed palace (MemPalace-compatible)."""
    try:
        import chromadb
    except ImportError:
        print("Error: chromadb not installed. Run: pip install chromadb")
        sys.exit(1)
    
    palace = Path(palace_path)
    palace.mkdir(parents=True, exist_ok=True)
    
    # Initialize ChromaDB
    chroma_dir = palace / "chroma"
    chroma_dir.mkdir(exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_dir))
    
    # Create the collection for drawers
    collection = client.get_or_create_collection(
        name="mempalace_drawers",
        metadata={"hnsw:space": "cosine"}
    )
    
    print(f"Initialized ChromaDB at {chroma_dir}")
    
    articles = data["articles"]
    titluri = data["titluri"]
    
    # Deduplicate titles (the file has law text + norms with same title structure)
    seen_titles = set()
    unique_titluri = []
    for t in titluri:
        key = t["id"]
        if key not in seen_titles:
            seen_titles.add(key)
            unique_titluri.append(t)
    
    print(f"\nIngesting {len(articles)} articles into {len(unique_titluri)} wings...")
    
    # Build wing and room metadata
    wing_map = {}  # titlu_id -> wing_name
    for t in unique_titluri:
        wing_name = make_wing_name(t["id"], t["name"])
        wing_map[t["id"]] = wing_name
    
    # Ingest each article as a drawer
    batch_ids = []
    batch_documents = []
    batch_metadatas = []
    
    ingested = 0
    for art_num, article in articles.items():
        titlu_id = article["titlu_id"]
        wing = wing_map.get(titlu_id, "wing_general")
        room = make_room_name(article["capitol_name"]) if article["capitol_name"] else "general"
        
        # Create drawer for the article text
        doc_id = f"art_{art_num}"
        content = f"Art. {art_num} - {article['articol_title']}\n\n{article['text']}"
        
        metadata = {
            "type": "articol",
            "article_number": art_num,
            "article_title": article["articol_title"],
            "wing": wing,
            "room": room,
            "section_path": article["section_path"],
            "titlu_id": titlu_id,
            "titlu_name": article["titlu_name"],
            "capitol_name": article["capitol_name"],
            "is_abrogated": str(article["is_abrogated"]),
            "has_norme": str(bool(article["norme_text"])),
            "cross_references": ",".join(article["cross_references"]),
        }
        
        batch_ids.append(doc_id)
        batch_documents.append(content)
        batch_metadatas.append(metadata)
        
        # Create drawer for norme if present
        if article["norme_text"]:
            norme_id = f"norme_art_{art_num}"
            norme_content = f"Norme metodologice pentru Art. {art_num} - {article['articol_title']}\n\n{article['norme_text']}"
            
            norme_metadata = {
                "type": "norma",
                "article_number": art_num,
                "article_title": article["articol_title"],
                "wing": wing,
                "room": room,
                "section_path": f"{article['section_path']} > Norme",
                "titlu_id": titlu_id,
                "titlu_name": article["titlu_name"],
                "capitol_name": article["capitol_name"],
                "is_abrogated": str(article["is_abrogated"]),
                "for_article": art_num,
            }
            
            batch_ids.append(norme_id)
            batch_documents.append(norme_content)
            batch_metadatas.append(norme_metadata)
        
        ingested += 1
        
        # Batch upsert every 100 items
        if len(batch_ids) >= 100:
            collection.upsert(
                ids=batch_ids,
                documents=batch_documents,
                metadatas=batch_metadatas,
            )
            print(f"  Ingested {ingested}/{len(articles)} articles...")
            batch_ids = []
            batch_documents = []
            batch_metadatas = []
    
    # Flush remaining
    if batch_ids:
        collection.upsert(
            ids=batch_ids,
            documents=batch_documents,
            metadatas=batch_metadatas,
        )
    
    total_drawers = collection.count()
    print(f"\nIngestion complete: {total_drawers} drawers in ChromaDB")
    
    # Save palace metadata
    palace_meta = {
        "name": "Cod Fiscal ANAF",
        "description": "Codul Fiscal al României (Legea 227/2015) cu Norme metodologice — extras publicație statică ANAF",
        "wings": {},
        "stats": {
            "total_articles": len(articles),
            "total_drawers": total_drawers,
            "abrogated": sum(1 for a in articles.values() if a["is_abrogated"]),
            "with_norme": sum(1 for a in articles.values() if a["norme_text"]),
        }
    }
    for t in unique_titluri:
        wing = wing_map[t["id"]]
        palace_meta["wings"][wing] = {
            "titlu_id": t["id"],
            "name": t["name"],
            "capitole": t.get("capitole", []),
        }
    
    meta_path = palace / "palace_metadata.json"
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(palace_meta, f, ensure_ascii=False, indent=2)
    print(f"Saved palace metadata to {meta_path}")
    
    # Build knowledge graph triples
    build_knowledge_graph(articles, palace)
    
    return palace_meta


def build_knowledge_graph(articles: dict, palace_path: Path):
    """Build a knowledge graph with cross-references and key facts."""
    print("\nBuilding knowledge graph...")
    
    triples = []
    
    for art_num, article in articles.items():
        # Cross-references
        for ref in article["cross_references"]:
            ref_num = ref.replace("art. ", "")
            triples.append({
                "subject": f"art_{art_num}",
                "predicate": "references",
                "object": f"art_{ref_num}",
            })
        
        # Subject categorization
        titlu = article.get("titlu_name", "")
        if "profit" in titlu.lower():
            triples.append({
                "subject": f"art_{art_num}",
                "predicate": "belongs_to",
                "object": "impozit_pe_profit",
            })
        elif "venit" in titlu.lower() and "microîntreprinderi" not in titlu.lower():
            triples.append({
                "subject": f"art_{art_num}",
                "predicate": "belongs_to",
                "object": "impozit_pe_venit",
            })
        elif "microîntreprinderi" in titlu.lower():
            triples.append({
                "subject": f"art_{art_num}",
                "predicate": "belongs_to",
                "object": "impozit_microintreprinderi",
            })
        elif "TVA" in titlu or "valoare" in titlu.lower():
            triples.append({
                "subject": f"art_{art_num}",
                "predicate": "belongs_to",
                "object": "tva",
            })
        elif "contribuții" in titlu.lower():
            triples.append({
                "subject": f"art_{art_num}",
                "predicate": "belongs_to",
                "object": "contributii_sociale",
            })
        elif "accize" in titlu.lower():
            triples.append({
                "subject": f"art_{art_num}",
                "predicate": "belongs_to",
                "object": "accize",
            })
        elif "locale" in titlu.lower():
            triples.append({
                "subject": f"art_{art_num}",
                "predicate": "belongs_to",
                "object": "impozite_locale",
            })
        
        # Extract known tax rates from text
        text = article["text"]
        rate_matches = re.findall(r'(\d{1,2})%', text)
        for rate in rate_matches:
            rate_int = int(rate)
            if rate_int in [1, 3, 5, 9, 10, 11, 16, 19, 21, 25]:  # Common fiscal rates
                triples.append({
                    "subject": f"art_{art_num}",
                    "predicate": "defines_rate",
                    "object": f"{rate}%",
                })
    
    # Save triples
    kg_path = palace_path / "knowledge_graph.json"
    with open(kg_path, 'w', encoding='utf-8') as f:
        json.dump(triples, f, ensure_ascii=False, indent=2)
    
    print(f"  Created {len(triples)} knowledge graph triples")
    print(f"  Saved to {kg_path}")


def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).parent.parent / "data" / "extracted" / "cod_fiscal_full.json"
    )
    palace_path = sys.argv[2] if len(sys.argv) > 2 else str(
        Path(__file__).parent.parent / "data" / "palace"
    )
    
    print(f"Loading extracted data from: {input_file}")
    print(f"Palace path: {palace_path}")
    print()
    
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Loaded {len(data['articles'])} articles")
    
    ingest_with_python_api(data, palace_path)
    
    print(f"\n✅ Ingestion complete! Palace is ready at: {palace_path}")


if __name__ == '__main__':
    main()
