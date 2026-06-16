#!/usr/bin/env bash
# One-command rebuild — grow + fix descriptions + translate + apply + push.
# ZERO LLM tokens: pure Python/GitHub-API/free-MT. Notifies nothing; just runs.
#
# Usage:
#   ./rebuild.sh                  # add up to EXPAND_MAX (default 8000) new skills, then publish
#   EXPAND_MAX=0 ./rebuild.sh     # refresh only (no growth)
#   EXPAND_MAX=15000 ./rebuild.sh # grow harder
#
set -uo pipefail
cd "$(dirname "$0")"
export GITHUB_TOKEN="$(gh auth token 2>/dev/null)"
[ -z "$GITHUB_TOKEN" ] && { echo "ERROR: run 'gh auth login' first"; exit 1; }
EXPAND_MAX="${EXPAND_MAX:-8000}"
MT_MAX="${MT_MAX:-9000}"

echo "[1/5] expand (EXPAND_MAX=$EXPAND_MAX) — Git Trees, no code-search ..."
EXPAND_MAX="$EXPAND_MAX" python3 scraper/expand_skills.py || { echo "expand failed"; exit 1; }

echo "[2/5] refix broken (block-scalar) descriptions ..."
python3 scraper/refix_desc.py || true

echo "[3/5] translate new descriptions (free Google MT) ..."
MT_MAX="$MT_MAX" python3 scraper/translate_mt.py || true

echo "[4/5] apply translations + fix star total ..."
USE_CACHE=1 python3 scraper/build_data.py || true
python3 - <<'PY'
import json
d = json.load(open("data/skills.json")); m = json.load(open("data/meta.json"))
m["total_stars"] = sum({r["repo"]: r.get("stars", 0) for r in d}.values())
m["granularity"] = "skill"
json.dump(m, open("data/meta.json", "w"), ensure_ascii=False)
print(f"  {len(d)} skills | {sum(1 for s in d if s.get('desc_zh'))} zh | {m['total_stars']:,} stars")
PY

echo "[5/5] commit + push (Pages auto-rebuilds) ..."
git add -A
N=$(python3 -c "import json;print(len(json.load(open('data/skills.json'))))")
git -c user.name="LINKIN" -c user.email="animeglade@gmail.com" \
    commit -q -m "data: rebuild $(date -u +%F) ($N skills)" || { echo "  no changes; done"; exit 0; }
for try in 1 2 3; do
  git push origin HEAD:main && break || { echo "  push retry $try (transient GitHub error)"; sleep 6; }
done
echo "DONE → live in ~1 min: https://linkin2009.github.io/skillhub/"
