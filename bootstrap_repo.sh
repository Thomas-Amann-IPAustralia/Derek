#!/usr/bin/env bash
# Promote this Derek/ tree to a standalone git repository.
#
# Derek was scaffolded inside the Octavius repository because the automation
# session that built it could not create a GitHub repository (the GitHub App
# lacks repo-creation scope). Everything here is self-contained; this script
# just moves it out.
#
# Derek is a CLEAN repository, not a git fork of Octavius (ADR-018): a fork
# would inherit 18 MB of dead code and a history dominated by fifteen
# identical pipeline commits, none of which can be removed once forked.
#
#   ./bootstrap_repo.sh /path/to/Derek
#
set -euo pipefail

DEST="${1:-}"
if [ -z "$DEST" ]; then
  echo "usage: $0 /path/to/new/Derek" >&2
  exit 64
fi
if [ -e "$DEST" ]; then
  echo "error: $DEST already exists" >&2
  exit 1
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Copying $SRC -> $DEST"
mkdir -p "$DEST"
tar -C "$SRC" \
    --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='.pytest_cache' --exclude='*.tmp' \
    -cf - . | tar -C "$DEST" -xf -

cd "$DEST"
git init -q
git add -A
git -c user.name="$(git config --global user.name || echo Derek)" \
    -c user.email="$(git config --global user.email || echo derek@localhost)" \
    commit -q -m "Derek: initial commit

Successor to Octavius. Carries over the offline Style Manual snapshot and
the scraper transport; everything above that layer is rebuilt.

See docs/00-postmortem-octavius.md for why."

cat <<'NEXT'

Done. Next:

  cd <your Derek path>
  pip install -r requirements.txt -r requirements-dev.txt
  pytest tests/ -v
  python tools/review/server.py        # start triage

Then create an empty GitHub repository named Derek and:

  git remote add origin git@github.com:<you>/Derek.git
  git push -u origin main

Repository variables/secrets used by .github/workflows/snapshot.yml
(all optional — the scraper works without them):
  PROXY_HOST  PROXY_PORT  PROXY_USER  PROXY_PASS
NEXT
