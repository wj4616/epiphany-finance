#!/usr/bin/env bash
# epiphany-finance — Codex variant installer.
# Deploys the Codex/gpt-5.5 entry point into ~/.codex/skills/ (where Codex discovers
# skills) WITHOUT duplicating the graph/modules/wrapper — the deployed SKILL.md points
# back at the canonical epiphany-finance install. The existing skill is not modified.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing the epiphany-finance Codex variant…"

# 1. Locate the canonical skill artifacts (graph.json + wrapper). Prefer the standard
#    Claude skills install; fall back to this script's own directory.
if [ -f "${HOME}/.claude/skills/epiphany-finance/graph.json" ]; then
  CANON="${HOME}/.claude/skills/epiphany-finance"
elif [ -f "${HERE}/graph.json" ]; then
  CANON="${HERE}"
else
  echo "  ✗ Couldn't find the epiphany-finance skill (no graph.json)."
  echo "    Run ./install.sh first to deploy the skill, then re-run this."
  exit 1
fi
echo "  ✓ Skill artifacts: ${CANON}"

# 2. Source SKILL doc to deploy as the Codex skill's SKILL.md.
if [ ! -f "${HERE}/SKILL-CODEX.md" ]; then
  echo "  ✗ SKILL-CODEX.md not found next to this script."
  exit 1
fi

# 3. Preflight (warn, don't fail — Codex can still be wired up and deps added later).
command -v codex >/dev/null 2>&1 \
  && echo "  ✓ codex CLI: $(codex --version 2>&1 | head -1)" \
  || echo "  ! codex CLI not on PATH — install Codex CLI before running the skill."

if python3 -c "import goatcs_harness" >/dev/null 2>&1; then
  echo "  ✓ goatcs-harness importable."
else
  echo "  ! goatcs-harness not importable — install the runtime:"
  echo "      pip install -e ~/projects/goatcs-harness"
fi

# The codex provider imports langchain-core at load (the harness [providers] extra).
echo "  • Ensuring the codex provider deps (langchain-core, langchain)…"
if python3 -m pip install --quiet "langchain-core>=0.3" "langchain>=0.3"; then
  echo "  ✓ Provider deps present."
else
  echo "  ! Couldn't auto-install provider deps. Try:"
  echo "      pip install -e '~/projects/goatcs-harness[providers]'"
fi

# 4. Deploy into the Codex skills directory.
DEST="${HOME}/.codex/skills/epiphany-finance"
mkdir -p "$DEST"
# Write SKILL.md from SKILL-CODEX.md, pointing the run commands at the canonical install.
sed "s|~/.claude/skills/epiphany-finance|${CANON}|g" "${HERE}/SKILL-CODEX.md" > "${DEST}/SKILL.md"
echo "  ✓ Deployed Codex skill to ${DEST}/SKILL.md"

echo ""
echo "Done. From Codex, ask for finance help (\"help me with my budget\") — it will drive"
echo "the existing graph with gpt-5.5. Or run directly:"
echo "    cd \"${CANON}\" && python3 -m wrapper.run --both --provider codex"
