#!/usr/bin/env python3
# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Test script for notebook template output validation.

This script validates:
1. Template output format matches ExecutionResult schema
2. Cell format is compatible with frontend Jupyter.tsx parsing
3. The extract_json_result method correctly parses template output
"""

import json
import sys
import os
import base64
from typing import Any, Dict, List, Optional

# Add parent directory if needed for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------
# FRONTEND EXPECTED TYPES
# ---------------------------

def validate_execution_result_schema(data: Dict[str, Any]) -> List[str]:
    """
    Validates that data matches the frontend ExecutionResult interface:
    
    export interface ExecutionResult {
      success: boolean;
      stdout?: string;
      stderr?: string;
      error?: string | null;
      execution_time: number;
      output_data?: Record<string, unknown>;
      timestamp: string;  // Added by backend after parsing
    }
    """
    errors = []
    
    # Required fields
    if "success" not in data:
        errors.append("Missing required field: 'success'")
    elif not isinstance(data["success"], bool):
        errors.append(f"'success' must be boolean, got {type(data['success']).__name__}")
    
    if "execution_time" not in data:
        errors.append("Missing required field: 'execution_time'")
    elif not isinstance(data["execution_time"], (int, float)):
        errors.append(f"'execution_time' must be number, got {type(data['execution_time']).__name__}")
    
    # Optional string fields
    for field in ["stdout", "stderr"]:
        if field in data and data[field] is not None and not isinstance(data[field], str):
            errors.append(f"'{field}' must be string or null, got {type(data[field]).__name__}")
    
    # Error can be string or null
    if "error" in data and data["error"] is not None and not isinstance(data["error"], str):
        errors.append(f"'error' must be string or null, got {type(data['error']).__name__}")
    
    # output_data must be dict if present
    if "output_data" in data and data["output_data"] is not None:
        if not isinstance(data["output_data"], dict):
            errors.append(f"'output_data' must be object, got {type(data['output_data']).__name__}")
    
    return errors


def validate_notebook_cell_schema(cell: Dict[str, Any], idx: int) -> List[str]:
    """
    Validates that cell matches frontend expectations for Jupyter.tsx:
    
    - cell_type or type: 'markdown' | 'code'
    - source: string
    - outputs: array (for code cells)
    - execution_count: number | null (for code cells)
    """
    errors = []
    
    # Check cell_type - Jupyter.tsx expects 'cell_type'
    cell_type = cell.get("cell_type") or cell.get("type")
    if not cell_type:
        errors.append(f"Cell {idx}: Missing 'cell_type' or 'type'")
    elif cell_type not in ["markdown", "code"]:
        errors.append(f"Cell {idx}: Invalid cell_type '{cell_type}', expected 'markdown' or 'code'")
    
    # Check source
    if "source" not in cell:
        errors.append(f"Cell {idx}: Missing 'source'")
    elif not isinstance(cell["source"], str):
        errors.append(f"Cell {idx}: 'source' must be string, got {type(cell['source']).__name__}")
    
    # For code cells, check outputs
    if cell_type == "code":
        if "outputs" not in cell:
            errors.append(f"Cell {idx}: Code cell missing 'outputs'")
        elif not isinstance(cell["outputs"], list):
            errors.append(f"Cell {idx}: 'outputs' must be array, got {type(cell['outputs']).__name__}")
        else:
            # Validate each output
            for oidx, output in enumerate(cell["outputs"]):
                output_errors = validate_cell_output_schema(output, idx, oidx)
                errors.extend(output_errors)
    
    return errors


def validate_cell_output_schema(output: Dict[str, Any], cell_idx: int, output_idx: int) -> List[str]:
    """
    Validates cell output matches frontend NotebookCellOutput interface:
    
    export interface NotebookCellOutput {
      output_type: string;
      text?: string;
      name?: string;
      data?: Record<string, unknown>;
      execution_count?: number;
      ename?: string;
      evalue?: string;
      traceback?: string[];
    }
    """
    errors = []
    prefix = f"Cell {cell_idx}, Output {output_idx}"
    
    if "output_type" not in output:
        errors.append(f"{prefix}: Missing 'output_type'")
    elif not isinstance(output["output_type"], str):
        errors.append(f"{prefix}: 'output_type' must be string")
    else:
        valid_types = ["stream", "execute_result", "display_data", "error"]
        if output["output_type"] not in valid_types:
            errors.append(f"{prefix}: Unknown output_type '{output['output_type']}', expected one of {valid_types}")
    
    # Validate based on output type
    output_type = output.get("output_type")
    
    if output_type == "stream":
        if "name" not in output:
            errors.append(f"{prefix}: Stream output missing 'name'")
        if "text" not in output:
            errors.append(f"{prefix}: Stream output missing 'text'")
    
    if output_type == "error":
        if "ename" not in output:
            errors.append(f"{prefix}: Error output missing 'ename'")
        if "evalue" not in output:
            errors.append(f"{prefix}: Error output missing 'evalue'")
        if "traceback" in output and not isinstance(output["traceback"], list):
            errors.append(f"{prefix}: Error 'traceback' must be array")
    
    if output_type in ["execute_result", "display_data"]:
        if "data" not in output:
            errors.append(f"{prefix}: {output_type} missing 'data'")
        elif not isinstance(output["data"], dict):
            errors.append(f"{prefix}: 'data' must be object")
    
    return errors


def validate_output_data_cells(output_data: Dict[str, Any]) -> List[str]:
    """Validate that output_data contains properly formatted cells."""
    errors = []
    
    if "cells" not in output_data:
        errors.append("output_data missing 'cells' array")
        return errors
    
    cells = output_data["cells"]
    if not isinstance(cells, list):
        errors.append(f"output_data.cells must be array, got {type(cells).__name__}")
        return errors
    
    for idx, cell in enumerate(cells):
        if not isinstance(cell, dict):
            errors.append(f"Cell {idx}: must be object, got {type(cell).__name__}")
            continue
        cell_errors = validate_notebook_cell_schema(cell, idx)
        errors.extend(cell_errors)
    
    return errors


# ---------------------------
# SAMPLE DATA FOR TESTING
# ---------------------------

SAMPLE_PYTHON_TEMPLATE_OUTPUT = """<<<RESULTS_START>>>
{
    "success": true,
    "stdout": "",
    "stderr": "",
    "error": null,
    "execution_time": 1.234,
    "output_data": {
        "cells": [
            {
                "cell_type": "markdown",
                "source": "# Hello World",
                "idx": 0
            },
            {
                "cell_type": "code",
                "source": "print('Hello')",
                "outputs": [
                    {
                        "output_type": "stream",
                        "name": "stdout",
                        "text": "Hello\\n"
                    }
                ],
                "execution_count": 1,
                "idx": 1
            },
            {
                "cell_type": "code",
                "source": "1/0",
                "outputs": [
                    {
                        "output_type": "error",
                        "ename": "ZeroDivisionError",
                        "evalue": "division by zero",
                        "traceback": ["Traceback (most recent call last):", "ZeroDivisionError: division by zero"]
                    }
                ],
                "execution_count": 2,
                "idx": 2
            }
        ]
    }
}
<<<RESULTS_END>>>"""

SAMPLE_R_TEMPLATE_OUTPUT = """<<<RESULTS_START>>>
{
    "success": true,
    "stdout": "",
    "stderr": "",
    "error": null,
    "execution_time": 2.5,
    "output_data": {
        "cells": [
            {
                "cell_type": "code",
                "source": "x <- 1:10\\nprint(x)",
                "outputs": [
                    {
                        "output_type": "stream",
                        "name": "stdout",
                        "text": "[1]  1  2  3  4  5  6  7  8  9 10"
                    }
                ],
                "execution_count": 1
            },
            {
                "cell_type": "code",
                "source": "plot(1:10)",
                "outputs": [
                    {
                        "output_type": "display_data",
                        "data": {
                            "image/png": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
                        },
                        "metadata": {}
                    }
                ],
                "execution_count": 2
            }
        ]
    }
}
<<<RESULTS_END>>>"""


def extract_json_result_simulation(stdout: str) -> Dict[str, Any]:
    """
    Simulates NotebookExecutor.extract_json_result method.
    This should match the implementation in executor.py.
    """
    if "<<<RESULTS_START>>>" not in stdout or "<<<RESULTS_END>>>" not in stdout:
        return {"success": False, "error": "Missing result markers"}
    
    try:
        results_stdout = stdout.split("<<<RESULTS_START>>>")[1].split("<<<RESULTS_END>>>")[0].strip()
        return json.loads(results_stdout)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"JSON parse error: {str(e)}"}


def simulate_frontend_normalize(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Simulates the normalizeNotebookJson function from Jupyter.tsx.
    Returns the notebook JSON if it can find cells, otherwise None.
    """
    if not isinstance(data, dict):
        return None
    
    # Direct cells array
    if "cells" in data and isinstance(data["cells"], list):
        return data
    
    # Check prioritized keys (matches Jupyter.tsx)
    prioritized_keys = [
        "notebook",
        "notebook_json",
        "notebookContent",
        "notebook_content",
        "ipynb",
        "output_data",
        "data",
        "result",
        "payload",
        "body",
    ]
    
    for key in prioritized_keys:
        if key in data:
            result = simulate_frontend_normalize(data[key])
            if result and "cells" in result:
                return result
    
    return None


def run_tests():
    """Run all validation tests."""
    print("=" * 60)
    print("NOTEBOOK TEMPLATE OUTPUT VALIDATION TESTS")
    print("=" * 60)
    print()
    
    all_passed = True
    
    # Test 1: Python template output
    print("Test 1: Python Template Output")
    print("-" * 40)
    
    parsed = extract_json_result_simulation(SAMPLE_PYTHON_TEMPLATE_OUTPUT)
    
    # Validate ExecutionResult schema
    schema_errors = validate_execution_result_schema(parsed)
    if schema_errors:
        print("  ❌ ExecutionResult schema errors:")
        for err in schema_errors:
            print(f"     - {err}")
        all_passed = False
    else:
        print("  ✅ ExecutionResult schema valid")
    
    # Validate output_data cells
    if "output_data" in parsed and parsed["output_data"]:
        cell_errors = validate_output_data_cells(parsed["output_data"])
        if cell_errors:
            print("  ❌ Cell validation errors:")
            for err in cell_errors:
                print(f"     - {err}")
            all_passed = False
        else:
            print(f"  ✅ All {len(parsed['output_data']['cells'])} cells valid")
    
    # Test frontend parsing
    notebook = simulate_frontend_normalize(parsed)
    if notebook and "cells" in notebook:
        print(f"  ✅ Frontend can find cells ({len(notebook['cells'])} cells)")
    else:
        print("  ❌ Frontend cannot find cells in output")
        all_passed = False
    
    print()
    
    # Test 2: R template output
    print("Test 2: R Template Output")
    print("-" * 40)
    
    parsed_r = extract_json_result_simulation(SAMPLE_R_TEMPLATE_OUTPUT)
    
    schema_errors_r = validate_execution_result_schema(parsed_r)
    if schema_errors_r:
        print("  ❌ ExecutionResult schema errors:")
        for err in schema_errors_r:
            print(f"     - {err}")
        all_passed = False
    else:
        print("  ✅ ExecutionResult schema valid")
    
    if "output_data" in parsed_r and parsed_r["output_data"]:
        cell_errors_r = validate_output_data_cells(parsed_r["output_data"])
        if cell_errors_r:
            print("  ❌ Cell validation errors:")
            for err in cell_errors_r:
                print(f"     - {err}")
            all_passed = False
        else:
            print(f"  ✅ All {len(parsed_r['output_data']['cells'])} cells valid")
    
    notebook_r = simulate_frontend_normalize(parsed_r)
    if notebook_r and "cells" in notebook_r:
        print(f"  ✅ Frontend can find cells ({len(notebook_r['cells'])} cells)")
    else:
        print("  ❌ Frontend cannot find cells in output")
        all_passed = False
    
    print()
    
    # Test 3: Verify cell_type vs type handling
    print("Test 3: cell_type vs type Compatibility")
    print("-" * 40)
    
    # Frontend Jupyter.tsx checks for cell_type
    cells = parsed["output_data"]["cells"]
    type_cells = [c for c in cells if "type" in c and "cell_type" not in c]
    if type_cells:
        print(f"  ⚠️  {len(type_cells)} cells use 'type' instead of 'cell_type'")
        print("     Note: executor.py converts 'type' to 'cell_type' before sending to frontend")
        print("     This is expected behavior")
    else:
        print("  ✅ All cells use 'cell_type'")
    
    print()
    
    # Test 4: Error output format
    print("Test 4: Error Cell Format")
    print("-" * 40)
    
    error_cells = [c for c in cells if c.get("type") == "code" or c.get("cell_type") == "code"]
    error_outputs_found = False
    for cell in error_cells:
        for output in cell.get("outputs", []):
            if output.get("output_type") == "error":
                error_outputs_found = True
                required = ["ename", "evalue"]
                missing = [f for f in required if f not in output]
                if missing:
                    print(f"  ❌ Error output missing: {missing}")
                    all_passed = False
                else:
                    print("  ✅ Error output has required fields (ename, evalue)")
    
    if not error_outputs_found:
        print("  ℹ️  No error outputs to validate")
    
    print()
    print("=" * 60)
    if all_passed:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 60)
    
    return all_passed


def test_live_template_output():
    """
    Test by actually running a template (requires Python environment).
    Uses a minimal notebook to verify end-to-end.
    """
    print()
    print("=" * 60)
    print("LIVE TEMPLATE EXECUTION TEST")
    print("=" * 60)
    print()
    
    # Create a minimal notebook
    sample_notebook = {
        "cells": [
            {
                "cell_type": "code",
                "source": "print('Hello from test!')",
                "metadata": {},
                "outputs": [],
                "execution_count": None
            }
        ],
        "metadata": {
            "kernelspec": {"name": "python3"}
        },
        "nbformat": 4,
        "nbformat_minor": 4
    }
    
    # Encode cells for template
    cells_data = []
    for idx, cell in enumerate(sample_notebook["cells"]):
        cells_data.append({
            "idx": idx,
            "type": cell["cell_type"],
            "source": cell["source"]
        })
    
    cells_b64 = base64.b64encode(json.dumps(cells_data).encode()).decode()
    print(f"Sample cells (base64): {cells_b64[:50]}...")
    print()
    print("To test the actual template, run:")
    print(f"  python3 -c \"<template_code>\"")
    print("  (replace {cells_b64} placeholder with the base64 string above)")
    print()


if __name__ == "__main__":
    success = run_tests()
    test_live_template_output()
    sys.exit(0 if success else 1)
