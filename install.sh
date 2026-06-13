#!/usr/bin/env bash
# epiphany-finance installer — plain-language, friendly, idempotent.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Setting up epiphany-finance…"

# 1. Python
if ! command -v python3 >/dev/null 2>&1; then
  echo "  ✗ I couldn't find Python 3. Please install Python 3.8+ and run this again."
  echo "    (Linux: 'sudo apt install python3 python3-pip'  •  macOS: 'brew install python')"
  exit 1
fi
echo "  ✓ Python found: $(python3 --version 2>&1)"

# 2. Dependencies
echo "  • Installing required packages (this may take a minute)…"
if python3 -m pip install --quiet yfinance "plotly>=6,<7" "kaleido==0.2.1" "weasyprint>=68" PyYAML; then
  echo "  ✓ Packages installed."
else
  echo "  ! Some packages didn't install automatically. You can try:"
  echo "      python3 -m pip install yfinance plotly kaleido weasyprint PyYAML"
  echo "    (WeasyPrint also needs system libs on some Linux: 'sudo apt install libpango-1.0-0 libpangocairo-1.0-0')"
fi

# 3. Deploy to the Claude skills dir (if present)
DEST="${HOME}/.claude/skills/epiphany-finance"
if [ -d "${HOME}/.claude/skills" ]; then
  mkdir -p "$DEST"
  cp -r "$HERE"/{graph.json,SKILL.md,SKILL-CODEX.md,INSTALL.md,appendix.md,brief.md,pyproject.toml,install.sh,install-codex.sh} "$DEST"/ 2>/dev/null
  cp -r "$HERE"/{modules,wrapper,fixtures,tests} "$DEST"/ 2>/dev/null
  echo "  ✓ Deployed to $DEST"
else
  echo "  • ~/.claude/skills not found — skipping deploy (you can still run it from here)."
fi

echo ""
echo "All done! To begin:"
echo "    cd \"$HERE\" && python3 -m wrapper.run --mode intake"
echo "  then:"
echo "    python3 -m wrapper.run --both"
