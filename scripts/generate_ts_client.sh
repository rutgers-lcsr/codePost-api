#!/bin/bash
# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
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

# Clean stale generated files from previous runs.
# The generator only writes files for endpoints in the current schema,
# so removed endpoints leave orphan files that break auto-generated clients.ts.
echo "Cleaning stale generated files..."
rm -rf "$OUTPUT_DIR/apis" "$OUTPUT_DIR/models" "$OUTPUT_DIR/docs"

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
echo "3. Post-Processing: Fixing Export Conflicts"
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
echo "4. Generating clients.ts"
echo "=========================================="

CLIENTS_FILE="$OUTPUT_DIR/clients.ts"
APIS_DIR="$OUTPUT_DIR/apis"

# Discover all *Api classes from the generated apis/ directory.
# Each file like CoursesApi.ts exports a class named CoursesApi.
API_CLASSES=()
while IFS= read -r api_file; do
    BASENAME=$(basename "$api_file" .ts)
    # Skip index.ts and non-Api files
    if [[ "$BASENAME" == "index" ]] || [[ ! "$BASENAME" =~ Api$ ]]; then
        continue
    fi
    API_CLASSES+=("$BASENAME")
done < <(find "$APIS_DIR" -maxdepth 1 -name '*.ts' -type f | sort)

if [ ${#API_CLASSES[@]} -eq 0 ]; then
    echo "Error: No API classes found in $APIS_DIR"
    exit 1
fi

echo "Found ${#API_CLASSES[@]} API classes, generating clients.ts..."

# Build the file
TMP_CLIENTS=$(mktemp)
cat > "$TMP_CLIENTS" << 'HEADER'
// @ts-nocheck
// Auto-generated by scripts/generate_ts_client.sh — do not edit manually.
// Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import { Configuration, type Middleware } from './runtime';
import { getAuthToken, handleUnauthorized, isTokenExpired, tryRefreshToken } from '../utils/auth';
HEADER

# Import block
echo "import {" >> "$TMP_CLIENTS"
for CLASS in "${API_CLASSES[@]}"; do
    echo "  $CLASS," >> "$TMP_CLIENTS"
done
echo "} from './apis';" >> "$TMP_CLIENTS"
echo "" >> "$TMP_CLIENTS"

# Middleware + Configuration
cat >> "$TMP_CLIENTS" << 'CONFIG'
// Proactively refresh an expired/near-expiry access token BEFORE the request is
// sent, then stamp the (possibly refreshed) token onto the outgoing request.
// This is what keeps an idle/backgrounded tab from 401-ing on return: a wall-clock
// timer can be throttled while the tab is asleep, but this pre-hook always runs on
// the next request, so a dead access token is refreshed instead of rejected.
const authRefreshMiddleware: Middleware = {
  pre: async ({ url, init }) => {
    if (getAuthToken() && isTokenExpired()) {
      await tryRefreshToken();
    }
    const token = getAuthToken();
    if (token && init.headers) {
      (init.headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
    }
    return { url, init };
  },
};

const unauthorizedMiddleware: Middleware = {
  post: async ({ response }) => {
    if (response.status === 401) {
      await handleUnauthorized();
    }
    return response;
  },
  onError: async ({ response }) => {
    if (response?.status === 401) {
      await handleUnauthorized();
    }
    return response;
  },
};

export const apiClientConfig = new Configuration({
  basePath: process.env.REACT_APP_API_URL,
  accessToken: () => Promise.resolve(getAuthToken()),
  apiKey: () => `Bearer ${getAuthToken()}`,
  middleware: [authRefreshMiddleware, unauthorizedMiddleware],
});

CONFIG

# Singleton exports: CoursesApi -> coursesApi
for CLASS in "${API_CLASSES[@]}"; do
    # Convert PascalCase to camelCase: strip "Api" suffix, lowercase first char, re-add "Api"
    NAME_WITHOUT_API="${CLASS%Api}"
    FIRST_CHAR=$(echo "${NAME_WITHOUT_API:0:1}" | tr '[:upper:]' '[:lower:]')
    CAMEL="${FIRST_CHAR}${NAME_WITHOUT_API:1}Api"
    echo "export const $CAMEL = new $CLASS(apiClientConfig);" >> "$TMP_CLIENTS"
done
echo "" >> "$TMP_CLIENTS"

command mv -f "$TMP_CLIENTS" "$CLIENTS_FILE"
echo "Generated $CLIENTS_FILE with ${#API_CLASSES[@]} API singletons."

echo "=========================================="
echo "5. Generating capabilities.generated.ts"
echo "=========================================="

# Extract the Capability enum from the Python source and generate a
# TypeScript type union.  This keeps the frontend type automatically in
# sync with the backend enum without relying on the openapi-generator's
# property-name camelization (which doesn't match the runtime response).
CAPABILITIES_FILE="$OUTPUT_DIR/capabilities.generated.ts"

"$VENV_PYTHON" -c "
import sys, os, logging
logging.disable(logging.CRITICAL)
# Suppress all Django startup output (structlog uses stdout)
import io
_real_stdout = sys.stdout
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()

sys.path.insert(0, os.path.dirname('$API_DIR'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codepost.settings')
os.environ['TESTING'] = 'True'

import django
django.setup()

# Restore stdout for our output
sys.stdout = _real_stdout

from core.permissions.capabilities import Capability, CAPABILITY_DESCRIPTIONS

caps = list(Capability)

print('// @ts-nocheck')
print('// Auto-generated from core/permissions/capabilities.py — do not edit manually.')
print('// Re-generate by running: ./scripts/generate_ts_client.sh')
print()
print('export type Capability =')
for i, cap in enumerate(caps):
    suffix = ';' if i == len(caps) - 1 else ''
    print(f\"  | '{cap.value}'{suffix}\")
print()
print('export type Capabilities = Partial<Record<Capability, boolean>>;')
print()
print('export const CAPABILITY_DESCRIPTIONS: Record<Capability, string> = {')
for cap in caps:
    desc = CAPABILITY_DESCRIPTIONS.get(cap, '')
    escaped = desc.replace(\"'\", \"\\\\'\")
    print(f\"  '{cap.value}': '{escaped}',\")
print('};')
" > "$CAPABILITIES_FILE"

echo "Generated $CAPABILITIES_FILE"

echo "=========================================="
echo "6. Formatting with Prettier..."
echo "=========================================="

if command -v npx &> /dev/null; then
    npx prettier --write "$OUTPUT_DIR"
else
    echo "Warning: Prettier not found, skipping formatting."
fi

echo "=========================================="
echo "7. Summary"
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
echo "Client Generation Complete!"
echo "Output: $OUTPUT_DIR"
echo "=========================================="
