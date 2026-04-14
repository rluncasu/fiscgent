# FiscGent - Expert Fiscal Român (Hermes Agent)

FiscGent este un agent autonom construit deasupra [Hermes Agent](https://github.com/nousresearch/hermes-agent), specializat în legislația fiscală din România (**Codul Fiscal + Norme metodologice**, extras ANAF; denumirile URL pot include «2023» fără să însemne text depășit).

Folosește **MemPalace** și **ChromaDB** pentru retenția structurată a textului legii (fără chunking distructiv), oferind acces precis la articole prin plugin-ul Hermes și căutare semantică avansată via MCP.

## FiscGent trebuie pornit separat?

**Nu.** Nu există un serviciu `fiscgent` pe care să-l rulezi cu `systemctl` sau într-un terminal separat.

- **Pluginul** este cod Python în `~/.hermes/plugins/fiscgent/`. **Hermes îl încarcă automat** când rulezi `hermes run` (dacă pluginul este activat în Hermes — vezi `hermes plugins list` / setările agentului).
- **MemPalace MCP** nu îl „pornești” manual în mod normal: Hermes pornește el procesul MCP (`python3 -m mempalace.mcp_server`) când serverul este înregistrat în config. Singura ta grijă este ca **datele** (`data/palace`) să fie unde le așteaptă pluginul și MemPalace (vezi pașii de instalare).

**Pe scurt:** după `./install.sh` și configurarea MCP + LLM, deschizi un singur lucru: **`hermes run`**.

## Componente

1. **Baza de date Palace (ChromaDB)**
   Conține 595 de articole și norme metodologice (838 de intrări), structurate pe Titluri, Capitole și Secțiuni.
   Include un graf cu referințele încrucișate (1930 de relații și cote).

2. **MemPalace MCP Server**
   Server MCP (Model Context Protocol) cu 29 de unelte pentru navigare, căutare semantică, interogare a graficului și a "tunelelor" (referințe).

3. **Hermes Plugin (`fiscgent`)**
   - **Tool `cod_fiscal_lookup`**: Permite extragerea exactă a unui articol complet cu tot cu norme, imediat ce inteligența artificială realizează că are nevoie de textul specific.
   - **Hook `pre_llm_call`**: Injectare automată RAG. De fiecare dată când puneți o întrebare despre taxe, impozite sau Codul Fiscal, uneltele fac o căutare și injectează articolele relevante automat, înainte ca LLM-ul să răspundă.
   - **Personality (SOUL.md/SKILL.md)**: Agentul este setat să acționeze ca un expert contabil și fiscal.

## Instalare în Hermes (rezumat)

1. **Hermes** — instalat și în `PATH` (`hermes --version`). Dacă nu există `~/.hermes/config.yaml`, rulați `hermes setup` și configurați un LLM.
2. **Python 3** — același mediu unde rulați `pip3` trebuie să aibă `chromadb` (și opțional `mempalace`) ca să funcționeze pluginul și MCP-ul.
3. **Datele codului fiscal** — fie le aveți deja în repo (`data/palace/chroma` + `data/extracted/`), fie le generați o dată:
   ```bash
   pip3 install -r requirements.txt
   python3 scripts/extract_cod_fiscal.py /cale/către/export-anaf.md
   python3 scripts/ingest_to_mempalace.py
   ```
4. **Din rădăcina repo-ului** rulați:
   ```bash
   ./install.sh
   ```
   Scriptul copiază `plugin/fiscgent/*` în `~/.hermes/plugins/fiscgent/` și, dacă există, **`data/palace` și `data/extracted`** în `~/.hermes/plugins/fiscgent/data/`, astfel încât `cod_fiscal_lookup` și hook-ul RAG găsesc indexul fără să depindă de calea repo-ului.

5. **MemPalace MCP** — Hermes trebuie să pornească serverul MCP MemPalace cu aceeași bază Chroma. Variante uzuale:
   - copiere la calea implicită MemPalace:
     ```bash
     mkdir -p ~/.mempalace
     cp -R ~/.hermes/plugins/fiscgent/data/palace ~/.mempalace/
     ```
   - sau adăugați serverul MCP și setați în config variabila de mediu pe care o cere versiunea voastră de MemPalace (ex. `MEMPALACE_PATH`) spre `~/.hermes/plugins/fiscgent/data/palace`.
   - înregistrare server (exemplu):
     ```bash
     hermes mcp add mempalace -- python3 -m mempalace.mcp_server
     ```

6. Porniți: `hermes run` și activați pluginul **`fiscgent`** dacă Hermes cere selectarea pluginurilor.

## Reinstalare / actualizare

După `git pull` sau modificări locale la plugin sau la date, rulați din nou `./install.sh` din rădăcina repo-ului (suprascrie fișierele din `~/.hermes/plugins/fiscgent/`).

## Cum se folosește

Rulați pur și simplu Hermes:

```bash
hermes run
```

Și puneți întrebări precum:
- "Care este cota standard de TVA și care sunt excepțiile?"
- "În ce caz pot deduce cheltuielile cu autoturismele la calculul impozitului pe profit?"
- "Cum se impozitează veniturile din activități independente (PFA)?"
- "Vorbește-mi despre regimul microîntreprinderilor (Art. 47)."
