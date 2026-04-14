#!/usr/bin/env bash
set -e

# Repo root (directory containing this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== FiscGent → Hermes (Codul Fiscal) ===${NC}"

# Check Hermes
if ! command -v hermes &> /dev/null; then
    echo "Eroare: hermes nu este instalat sau nu este în PATH."
    echo "Instalează Hermes Agent mai întâi de la: https://github.com/nousresearch/hermes-agent"
    exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Eroare: python3 nu este instalat."
    exit 1
fi

echo "1. Instalare dependențe Python..."
pip3 install -r requirements.txt || true # don't fail if already installed or conflicts

echo "2. Conectare plugin FiscGent la Hermes..."
HERMES_HOME="${HOME}/.hermes"
PLUGIN_DIR="${HERMES_HOME}/plugins/fiscgent"

mkdir -p "$PLUGIN_DIR"
cp -R "${SCRIPT_DIR}/plugin/fiscgent/"* "$PLUGIN_DIR/"

echo "2b. Date cod fiscal (palace + articole)..."
DATA_DIR="${SCRIPT_DIR}/data"
if [[ -d "${DATA_DIR}/palace/chroma" ]]; then
  mkdir -p "${PLUGIN_DIR}/data"
  rm -rf "${PLUGIN_DIR}/data/palace" "${PLUGIN_DIR}/data/extracted"
  cp -R "${DATA_DIR}/palace" "${PLUGIN_DIR}/data/"
  if [[ -d "${DATA_DIR}/extracted" ]]; then
    cp -R "${DATA_DIR}/extracted" "${PLUGIN_DIR}/data/"
  fi
  echo "    Copiate în ${PLUGIN_DIR}/data/ (lookup + RAG hook)."
else
  echo "    Lipsește ${DATA_DIR}/palace/chroma — rulează din repo:"
  echo "      pip3 install -r requirements.txt"
  echo "      python3 scripts/extract_cod_fiscal.py /cale/către/export-anaf.md"
  echo "      python3 scripts/ingest_to_mempalace.py"
  echo "    Apoi rulează din nou ./install.sh"
fi

echo "3. Configurare MCP MemPalace în Hermes..."
# Check if config.yaml exists
if [ -f "$HERMES_HOME/config.yaml" ]; then
    # Simple check if mempalace is already in config
    if ! grep -q "mempalace:" "$HERMES_HOME/config.yaml"; then
        echo "Adaug MCP server mempalace în config.yaml..."
        # Backup config
        cp "$HERMES_HOME/config.yaml" "$HERMES_HOME/config.yaml.bak"
        # Append naive block if mcp section is missing or just append to servers
        # We'll use hermes CLI to add it if possible, else just give instructions.
        echo "Rulati comanda: hermes mcp add mempalace -- python3 -m mempalace.mcp_server"
        hermes mcp add mempalace -- python3 -m mempalace.mcp_server || echo "Ignorați eroarea dacă este deja configurat."
    else
        echo "MemPalace MCP deja configurat in config.yaml."
    fi
else
    echo "Nu exista config.yaml în $HERMES_HOME. Rulați hermes setup mai întâi."
fi

PALACE_FOR_MCP="${PLUGIN_DIR}/data/palace"
echo ""
echo -e "${GREEN}Instalare plugin completă.${NC}"
echo "Pornire:  hermes run"
echo ""
echo "MCP MemPalace trebuie să vadă aceeași bază Chroma ca pluginul. Dacă serverul"
echo "caută implicit ~/.mempalace/palace, fie copiază datele:"
echo "  mkdir -p ~/.mempalace && cp -R \"${PALACE_FOR_MCP}\" ~/.mempalace/"
echo "fie configurează în Hermes env pentru serverul mempalace, ex.:"
echo "  MEMPALACE_PATH=${PALACE_FOR_MCP}"
echo "(exact cheia depinde de versiunea MemPalace — vezi docs)."
echo ""
echo "Configurează un furnizor LLM în Hermes (OpenRouter, OpenAI, etc.)."
