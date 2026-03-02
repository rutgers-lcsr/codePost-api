#!/bin/bash
# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
set -euo pipefail

# Configuration
API_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEMA_FILE="$API_DIR/schema.yaml"
# Output directory relative to API_DIR (defaults to UI workspace).
# Override during migration by setting CODEPOST_TS_CLIENT_OUT.
OUTPUT_DIR_DEFAULT="$API_DIR/../codePost-ui/src/api-client"
OUTPUT_DIR="${CODEPOST_TS_CLIENT_OUT:-$OUTPUT_DIR_DEFAULT}"
VENV_PYTHON="$API_DIR/.venv/bin/python"

# Ensure we are in the API directory
cd "$API_DIR"

echo "=========================================="
echo "1. Generating OpenAPI Schema..."
echo "=========================================="

if [ ! -f "$VENV_PYTHON" ]; then
    echo "Error: Virtual environment not found at $VENV_PYTHON"
    echo "Please ensure the backend venv is set up."
    exit 1
fi

# Regenerate schema to ensure it's up to date
"$VENV_PYTHON" manage.py spectacular --file "$SCHEMA_FILE"

echo "Schema generated at $SCHEMA_FILE"

echo "=========================================="
echo "2. Generating TypeScript Client..."
echo "=========================================="

# Ensure output directory exists (create parent as needed)
mkdir -p "$OUTPUT_DIR"

if [ ! -d "$OUTPUT_DIR" ]; then
    echo "Error: Output directory is not a directory: $OUTPUT_DIR"
    exit 1
fi

# Quick write-permission check
if [ ! -w "$OUTPUT_DIR" ]; then
    echo "Error: Output directory is not writable: $OUTPUT_DIR"
    exit 1
fi

# Check if npx is available
if ! command -v npx &> /dev/null; then
    echo "Error: npx is not installed. Please install Node.js."
    exit 1
fi

# Generate generic TypeScript Fetch client
# We use typescript-fetch because it's standard and works well with modern React
npx @openapitools/openapi-generator-cli generate \
    -i "$SCHEMA_FILE" \
    -g typescript-fetch \
    -o "$OUTPUT_DIR" \
    --additional-properties=typescriptThreePlus=true \
    --additional-properties=supportsES6=true \
    --additional-properties=nullSafeAdditionalProps=true \
    --additional-properties=withoutRuntimeChecks=true \
    --additional-properties=removeOperationIdPrefix=true \
    --additional-properties=stringEnums=true

echo "=========================================="
echo "3. Formatting Client with Prettier..."
echo "=========================================="

if command -v npx &> /dev/null; then
    npx prettier --write "$OUTPUT_DIR"
else
    echo "Warning: Prettier not found, skipping formatting."
fi

echo "=========================================="
echo "4. Post-run Summary"
echo "=========================================="

FILE_COUNT=$(find "$OUTPUT_DIR" -type f 2>/dev/null | wc -l | tr -d ' ')
echo "Generated files: $FILE_COUNT"

# If the output dir is inside a git repo, show a focused status summary.
if command -v git &> /dev/null; then
    if GIT_TOPLEVEL=$(git -C "$OUTPUT_DIR" rev-parse --show-toplevel 2>/dev/null); then
        if command -v realpath &> /dev/null; then
            OUTPUT_REL=$(realpath --relative-to="$GIT_TOPLEVEL" "$OUTPUT_DIR")
        else
            OUTPUT_REL="$OUTPUT_DIR"
        fi

        echo "Git repo: $GIT_TOPLEVEL"
        echo "Path: $OUTPUT_REL"
        git -C "$GIT_TOPLEVEL" status --porcelain=v1 "$OUTPUT_REL" | head -n 200 || true

        # Optional: stage generated output (useful when the dir is tracked/untracked intentionally)
        if [ "${CODEPOST_TS_CLIENT_GIT_ADD:-0}" = "1" ]; then
            git -C "$GIT_TOPLEVEL" add "$OUTPUT_REL"
            echo "Staged changes under: $OUTPUT_REL"
        fi
    else
        echo "Note: Output directory is not inside a git repo (no status summary)."
    fi
fi


echo "=========================================="
echo "3.5. Post-Processing: Fixing Export Conflicts"
echo "=========================================="

# Add // @ts-nocheck to all generated .ts files.
# This suppresses TypeScript strict-mode errors (e.g. noUnusedLocals) on
# auto-generated code without needing to exclude the directory from tsconfig.
# ESLint's ban-ts-comment rule does NOT apply here because eslint.config.mjs
# already ignores src/api-client/**.
echo "Adding // @ts-nocheck to generated .ts files..."
while IFS= read -r tsfile; do
    if ! head -1 "$tsfile" | grep -qF '@ts-nocheck'; then
        TMP_TS=$(mktemp)
        { echo '// @ts-nocheck'; cat "$tsfile"; } > "$TMP_TS"
        command mv -f "$TMP_TS" "$tsfile"
    fi
done < <(find "$OUTPUT_DIR" -name '*.ts' -type f)
echo "Done."

# Fix conflicting exports in apis/index.ts
# Original: export * from './SomeApi';
# New:      export { SomeApi } from './SomeApi';
# This prevents 'UpdateRequest' collision errors.

INDEX_FILE="$OUTPUT_DIR/apis/index.ts"

if [ -f "$INDEX_FILE" ]; then
    echo "Patching $INDEX_FILE to use named exports..."
    
    # Create a temporary file
    TMP_INDEX=$(mktemp)
    
    # Process the file
    # We strip single quotes, take the filename part, and use it as the class name
    # Assumption: The file './SomeApi' contains a class named 'SomeApi'
    while IFS= read -r line; do
        if [[ "$line" =~ export\ \*\ from\ \'(.*)\'\; ]]; then
            MODULE_PATH="${BASH_REMATCH[1]}" # e.g. ./SomeApi
            BASENAME=$(basename "$MODULE_PATH") # SomeApi
            echo "export { $BASENAME } from '$MODULE_PATH';" >> "$TMP_INDEX"
        else
            echo "$line" >> "$TMP_INDEX"
        fi
    done < "$INDEX_FILE"
    
    command mv -f "$TMP_INDEX" "$INDEX_FILE"
    echo "Patch complete."
else
    echo "Warning: $INDEX_FILE not found, skipping patch."
fi

echo "=========================================="
echo "Client Generation Complete!"
echo "Output: $OUTPUT_DIR"
echo "=========================================="
