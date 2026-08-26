#!/bin/bash
# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
#
# Sync the in-app user documentation (markdown source) from codePost-ui into
# this repo, so the API can serve it to MCP agents (codepost_search_docs).
# The UI bundles these files into its JS at build time — the API is otherwise
# blind to them, hence the committed copy. Re-run after editing docs in the UI.
set -euo pipefail

SRC="${CODEPOST_UI_DOCS:-$(dirname "$0")/../../codePost-ui/src/docs/content}"
DST="$(dirname "$0")/../docs/user"

if [ ! -d "$SRC" ]; then
    echo "error: docs source not found at $SRC (set CODEPOST_UI_DOCS)" >&2
    exit 1
fi

mkdir -p "$DST"
rm -f "$DST"/*.md
cp "$SRC"/*.md "$DST"/
echo "Synced $(ls "$DST"/*.md | wc -l) docs pages into docs/user/"
