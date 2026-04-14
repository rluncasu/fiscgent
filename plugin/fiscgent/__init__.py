"""FiscGent plugin — registration.

Wires the cod_fiscal_lookup tool and pre_llm_call RAG hook into Hermes.
"""

import logging
import shutil
from pathlib import Path

from . import schemas, tools, rag_hook

logger = logging.getLogger(__name__)


def _install_soul():
    """Copy SOUL.md to ~/.hermes/ on first load."""
    try:
        from hermes_cli.config import get_hermes_home
        dest = get_hermes_home() / "SOUL.md"
    except Exception:
        dest = Path.home() / ".hermes" / "SOUL.md"
    
    source = Path(__file__).parent / "SOUL.md"
    
    if not source.exists():
        return
    
    if dest.exists():
        # Don't overwrite — but check if we should append
        existing = dest.read_text(encoding='utf-8')
        if 'Expert Contabil' in existing:
            return  # Already installed
        
        # Append our persona
        soul_content = source.read_text(encoding='utf-8')
        with open(dest, 'a', encoding='utf-8') as f:
            f.write('\n\n' + soul_content)
        logger.info("Appended FiscGent persona to existing SOUL.md")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        logger.info("Installed SOUL.md to %s", dest)


def _install_skill():
    """Copy skill.md to ~/.hermes/skills/fiscgent/ on first load."""
    try:
        from hermes_cli.config import get_hermes_home
        dest = get_hermes_home() / "skills" / "fiscgent" / "SKILL.md"
    except Exception:
        dest = Path.home() / ".hermes" / "skills" / "fiscgent" / "SKILL.md"
    
    if dest.exists():
        return  # Don't overwrite user edits
    
    source = Path(__file__).parent / "skill.md"
    if source.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        logger.info("Installed skill.md to %s", dest)


def register(ctx):
    """Wire schemas to handlers and register hooks."""
    # Register the cod_fiscal_lookup tool
    ctx.register_tool(
        name="cod_fiscal_lookup",
        toolset="fiscgent",
        schema=schemas.COD_FISCAL_LOOKUP,
        handler=tools.cod_fiscal_lookup,
    )
    
    # Register the pre_llm_call hook for automatic RAG injection
    ctx.register_hook("pre_llm_call", rag_hook.inject_fiscal_context)
    
    # Install personality and skill on first load
    _install_soul()
    _install_skill()
    
    logger.info("FiscGent plugin loaded: cod_fiscal_lookup tool + pre_llm_call hook")
