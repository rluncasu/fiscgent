"""
RAG hook — automatically injects relevant Cod Fiscal context before each LLM call.

This is the pre_llm_call hook that fires before every LLM turn.
It analyzes the user's message for fiscal/legal intent, searches the
Cod Fiscal knowledge store, and injects relevant article excerpts
as context alongside the user's message.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Keywords that suggest a fiscal/legal query (Romanian + English)
_FISCAL_KEYWORDS_RO = [
    "impozit", "taxă", "tva", "contribuți", "fiscal", "profit", "venit",
    "salariu", "salarii", "dividend", "microîntreprindere", "acciz",
    "deducere", "deductibil", "scutire", "scutit", "cotă", "bază de calcul",
    "norme metodologice", "cod fiscal", "codul fiscal", "ANAF", "buget",
    "declarație", "factur", "plătitor", "contribuabil", "rezident",
    "nerezident", "avans", "amortizare", "leasing", "fiducie",
    "articol", "art.", "alineat", "alin.", "lege", "ordonanță",
    "cheltuieli deductibile", "cheltuieli nedeductibile", "pierderi fiscale",
    "consolidare fiscală", "sediu permanent", "dubla impunere",
    "redevență", "dobând", "capital social", "asociere", "PFA",
    "venituri din", "impozitul pe", "taxa pe", "contribuția de",
    "CASS", "CAS", "CAM", "asigurări sociale", "asigurări de sănătate",
    "pensie", "pensii", "șomaj", "fond de garantare",
    "proprietate intelectuală", "drepturi de autor",
    "jocuri de noroc", "premii", "proprietăți imobiliare",
    "activități independente", "activități agricole",
    "cedarea folosinței", "închiriere", "arendare",
    "investiții", "titluri de valoare", "instrumente financiare",
    "operațiuni scutite", "operațiuni impozabile",
    "regim special", "grup fiscal", "transfer pricing",
    "prețuri de transfer", "entități afiliate",
]

_FISCAL_KEYWORDS_EN = [
    "tax", "fiscal", "vat", "income tax", "profit tax", "dividend",
    "social contribution", "deduction", "deductible", "exemption",
    "tax rate", "tax base", "fiscal code", "ANAF", "budget",
    "invoice", "taxpayer", "resident", "non-resident",
    "depreciation", "amortization", "transfer pricing",
    "permanent establishment", "double taxation",
    "Romanian tax", "Romanian fiscal",
]


def _is_fiscal_query(message: str) -> bool:
    """Check if a message appears to be about fiscal/legal topics."""
    if not message:
        return False
    
    msg_lower = message.lower()
    
    # Check for article references
    if re.search(r'art(?:icol)?\.?\s*\d+', msg_lower):
        return True
    
    # Check keywords
    for kw in _FISCAL_KEYWORDS_RO + _FISCAL_KEYWORDS_EN:
        if kw.lower() in msg_lower:
            return True
    
    return False


def inject_fiscal_context(session_id, user_message, is_first_turn=False, **kwargs):
    """
    pre_llm_call hook: Auto-inject relevant Cod Fiscal context.
    
    Called before each LLM turn. Returns context dict if the query
    appears to be fiscal-related, None otherwise.
    """
    if not user_message:
        return None
    
    if not _is_fiscal_query(user_message):
        return None
    
    try:
        from .tools import search_fiscal_code
        
        results = search_fiscal_code(user_message, top_k=3)
        
        if not results:
            return None
        
        context_parts = [
            "📜 **Context relevant din Codul Fiscal (extras ANAF; injectat automat — "
            "folosește cod_fiscal_lookup pentru text complet):**\n"
        ]
        
        for r in results:
            section = r.get("section_path", "")
            art_num = r.get("article_number", "")
            text_preview = r.get("text", "")[:400]
            doc_type = r.get("type", "articol")
            
            type_label = "📋 Normă" if doc_type == "norma" else "⚖️ Articol"
            
            context_parts.append(
                f"{type_label} | **{section}**\n"
                f"{text_preview}...\n"
            )
        
        context_parts.append(
            "\n*Folosește `cod_fiscal_lookup` pentru textul complet al oricărui articol.*"
        )
        
        context = "\n".join(context_parts)
        
        logger.debug(
            "Injecting fiscal context: %d results for query: %s",
            len(results), user_message[:50]
        )
        
        return {"context": context}
    
    except Exception as e:
        logger.debug("Failed to inject fiscal context: %s", e)
        return None  # Fail silently, don't break the agent
