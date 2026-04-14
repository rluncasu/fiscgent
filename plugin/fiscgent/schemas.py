"""Tool schemas — what the LLM sees for the cod_fiscal_lookup tool."""

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
                "description": (
                    "Article number to look up (e.g., '291', '76', '7'). "
                    "Can also include superscript notation like '401' for Art. 40^1."
                ),
            },
            "include_norms": {
                "type": "boolean",
                "description": "Include methodological norms (default: true)",
                "default": True,
            },
            "resolve_references": {
                "type": "boolean",
                "description": (
                    "Also fetch cross-referenced articles and include their "
                    "titles and first paragraph (default: false)"
                ),
                "default": False,
            },
        },
        "required": ["article_number"],
    },
}
