#!/bin/bash
# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
set -e

# Configuration
API_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEMA_FILE="$API_DIR/schema.yaml"
# Output directory relative to API_DIR (defaults to Python SDK workspace).
# Override during migration by setting CODEPOST_SDK_OUT.
SDK_OUTPUT_DIR_DEFAULT="$API_DIR/../codepost-python"
SDK_OUTPUT_DIR="${CODEPOST_SDK_OUT:-$SDK_OUTPUT_DIR_DEFAULT}"
VENV_PYTHON="$API_DIR/.venv/bin/python"

# Ensure we are in the API directory
cd "$API_DIR"

echo "=========================================="
echo "Generating OpenAPI Schema..."
echo "=========================================="

if [ ! -f "$VENV_PYTHON" ]; then
    echo "Error: Virtual environment not found at $VENV_PYTHON"
    exit 1
fi

"$VENV_PYTHON" manage.py spectacular --file "$SCHEMA_FILE"

echo "Schema generated at $SCHEMA_FILE"

echo "=========================================="
echo "Generating Python SDK..."
echo "=========================================="

# Check if openapi-generator-cli is installed
if ! command -v npx &> /dev/null; then
    echo "Error: npx is not installed. Please install Node.js and npm."
    exit 1
fi

# Generate SDK
npx @openapitools/openapi-generator-cli generate \
    -i "$SCHEMA_FILE" \
    -g python \
    -o "$SDK_OUTPUT_DIR" \
    --additional-properties=packageName=codepost_api_client

echo "=========================================="
echo "SDK Generation Complete!"
echo "Output: $SDK_OUTPUT_DIR"
echo "=========================================="
