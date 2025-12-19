# This is a template for running jupyter notebook code cells inside a Docker container.

# To use this template replace the placeholder {cells_b64} with a base64-encoded JSON array of cells, And packages_to_install with a list of packages to install.



# START OF PACKAGE INSTALLATION TEMPLATE
import subprocess
import sys
import os
import time
import site

# Set environment for pip
os.environ['PIP_ROOT_USER_ACTION'] = 'ignore'
if 'PIP_CACHE_DIR' not in os.environ:
    os.environ['PIP_CACHE_DIR'] = '/tmp/pip-cache'
os.environ['MPLBACKEND'] = 'Agg'  # For matplotlib headless

MAX_CELLS = 500  # Maximum number of cells allowed to prevent abuse

def template_log(message: str, level:str) -> None:
    print(f"[{level}] {message}", file=sys.stderr)



# Packages to install
packages_to_install = []

script_start_time = time.time()

# Debug: Check if pip cache is mounted
pip_cache_path = os.environ.get('PIP_CACHE_DIR', '/tmp/pip-cache')
if os.path.exists(pip_cache_path):
    template_log(f"Pip cache directory found at {pip_cache_path}", "DEBUG")
    try:
        cache_size = sum(os.path.getsize(os.path.join(dirpath, filename))
                        for dirpath, dirnames, filenames in os.walk(pip_cache_path)
                        for filename in filenames)
        template_log(f"Current cache size: {cache_size / 1024 / 1024:.2f} MB", "DEBUG")
    except Exception as e:
        template_log(f"Could not calculate cache size: {str(e)}", "DEBUG")
else:
    template_log(f"Pip cache directory NOT found - cache may not be working!", "WARNING")

template_log(f"Checking {len(packages_to_install)} package(s): {', '.join(packages_to_install)}", "INFO")

# Check which packages are already installed (from pre-built image or previous runs)
import importlib.util
already_installed = []
needs_install = []
for package in packages_to_install:
    # Try to import the package to see if it's already available
    try:
        __import__(package)
        already_installed.append(package)
    except ImportError:
        needs_install.append(package)

if already_installed:
    template_log(f"{len(already_installed)} package(s) already available: {', '.join(already_installed)}", "INFO")

if not needs_install:
    template_log("✓ All packages available, skipping installation", "INFO")

# Install packages with progress feedback
failed_packages = []
for i, package in enumerate(needs_install, 1):
    template_log(f"[{i}/{len(needs_install)}] Installing {package}...", "INFO")
    start_time = time.time()
    
    try:
        # Use pip's cache to speed up installations (cache is mounted at /root/.cache/pip)
        # Run pip with verbose output to capture cache usage
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '--user', '-v', "--only-binary", ":all:", package],
            capture_output=True,
            text=True
        )
        elapsed = time.time() - start_time
        
        # Check if pip used cache (look for cache-related messages)
        used_cache = 'Using cached' in result.stdout or 'from cache' in result.stdout.lower()
        cache_indicator = '(cached)' if used_cache else '(downloaded)'
        
        if result.returncode == 0:
            template_log(f"[{i}/{len(needs_install)}] ✓ {package} installed {cache_indicator} ({elapsed:.1f}s)", "INFO")
            print(f"CODEPOST_AUTO_INSTALL_SUCCESS: {package}", file=sys.stderr)
        else:
            raise subprocess.CalledProcessError(result.returncode, result.args)
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start_time
        template_log(f"[{i}/{len(needs_install)}] ✗ {package} failed ({elapsed:.1f}s)", "ERROR")
        failed_packages.append(package)
    
    sys.stderr.flush()

# Summary
if failed_packages:
    template_log(f"Failed to install {len(failed_packages)} package(s): {', '.join(failed_packages)}", "ERROR")
else:
    template_log("✓ All packages installed successfully", "INFO")

# Show final cache size
if needs_install and os.path.exists(pip_cache_path):
    try:
        cache_size = sum(os.path.getsize(os.path.join(dirpath, filename))
                        for dirpath, dirnames, filenames in os.walk(pip_cache_path)
                        for filename in filenames)
        template_log(f"Final cache size: {cache_size / 1024 / 1024:.2f} MB", "DEBUG")
    except Exception:
        pass

# SECURITY: Make pip cache read-only after installation to prevent notebook code from tampering
if needs_install and os.path.exists(pip_cache_path):
    try:
        import stat
        # Remove write permissions for everyone on the cache directory
        for root, dirs, files in os.walk(pip_cache_path):
            # Make directories read-only and executable (for traversal)
            for d in dirs:
                dir_path = os.path.join(root, d)
                os.chmod(dir_path, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
            # Make files read-only
            for f in files:
                file_path = os.path.join(root, f)
                os.chmod(file_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        # Make the root cache directory read-only
        os.chmod(pip_cache_path, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        template_log("Pip cache locked (read-only) after installation", "SECURITY")
    except Exception as e:
        template_log(f"Could not lock pip cache: {str(e)}", "WARNING")

sys.stderr.flush()

# Refresh sys.path to include newly installed user site-packages
if needs_install:
    try:
        from importlib import reload
        reload(site)
        # Also explicitly add the user site directory if not present
        if site.getusersitepackages() not in sys.path:
             site.addsitedir(site.getusersitepackages())
        template_log(f"Refreshed sys.path with user site packages: {site.getusersitepackages()}", "DEBUG")
    except Exception as e:
        template_log(f"Failed to refresh sys.path: {e}", "WARNING")

sys.stderr.flush()

print("", file=sys.stderr)  # Blank line for readability


# END OF PACKAGE INSTALLATION TEMPLATE

import json
import base64
import ast
import sys
import io
import os
from contextlib import redirect_stdout, redirect_stderr

# Debug: Show initial working directory and mounted files
template_log(f"Initial working directory: {os.getcwd()}", "DEBUG")
template_log(f"/work exists: {os.path.exists('/work')}", "DEBUG")
if os.path.exists('/work'):
    template_log(f"Files in /work: {os.listdir('/work')}", "DEBUG")
template_log(f"~/shared exists: {os.path.exists('/root/shared')}", "DEBUG")
if os.path.exists('/root/shared'):
    template_log(f"Files in ~/shared: {os.listdir('/root/shared')}", "DEBUG")   


# Change to /work directory where assignment files are located
# Datasets remain accessible at ~/shared/...
if os.path.exists('/work'):
    os.chdir('/work')
    template_log(f"Changed working directory to /work", "DEBUG")
    template_log(f"Changed to: {os.getcwd()}", "DEBUG")
else:
    template_log(f"/work does not exist, staying in {os.getcwd()}", "DEBUG")


# Decode cells
cells_json = base64.b64decode('{cells_b64}').decode('utf-8')
cells = json.loads(cells_json)

# Results storage
results = []

# Shared namespace for all cells (like Jupyter)
namespace = {'__name__': '__main__', '__builtins__': __builtins__}


if len(cells) > MAX_CELLS:
    template_log(f"Number of cells ({len(cells)}) exceeds maximum allowed ({MAX_CELLS})", "ERROR")
    results.append({
        'cell_type': 'markdown',
        'source': f"**Error:** Number of cells ({len(cells)}) exceeds maximum allowed ({MAX_CELLS}). Execution aborted. Please reduces the number of cells and try again. Or contact support."
    })
else:
    # Execute each code cell
    for cell_idx, cell in enumerate(cells):
        if cell['type'] == 'markdown':
            results.append({
            'cell_type': 'markdown',
            'source': cell['source'],
            'idx': cell['idx']
        })
        elif cell['type'] == 'code':
            cell_source = cell['source']
            
            # Capture stdout and stderr
            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()
            
            outputs = []
            success = True
            error_msg = None
            
            try:
                with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                    # Parse and execute with last-expression handling
                    try:
                        parsed = ast.parse(cell_source, mode='exec')
                        
                        # Check if last statement is an expression
                        if parsed.body and isinstance(parsed.body[-1], ast.Expr):
                            # Execute all-but-last
                            setup_stmts = parsed.body[:-1]
                            last_expr = parsed.body[-1].value
                            
                            if setup_stmts:
                                setup = ast.Module(body=setup_stmts, type_ignores=[])
                                exec(compile(setup, '<cell>', 'exec'), namespace)
                            
                            # Evaluate and display last expression
                            result = eval(compile(ast.Expression(body=last_expr), '<cell>', 'eval'), namespace)
                            if result is not None:
                                # Smart display for different types
                                result_type = type(result).__name__
                                result_module = type(result).__module__
                                
                                # Check for pandas DataFrame/Series
                                if 'pandas' in result_module and hasattr(result, 'to_string'):
                                    print(result.to_string())
                                # Check for numpy arrays
                                elif 'numpy' in result_module and hasattr(result, '__array__'):
                                    print(repr(result))
                                # Default: use repr
                                else:
                                    print(repr(result))
                        else:
                            # Just execute normally
                            exec(cell_source, namespace)
                    except SyntaxError as e:
                        # If parsing fails, just execute
                        exec(cell_source, namespace)
            except Exception as e:
                success = False
                error_msg = str(e)
                import traceback
                stderr_capture.write(traceback.format_exc())
            
            # Get captured output
            stdout_text = stdout_capture.getvalue()
            stderr_text = stderr_capture.getvalue()
            
            # Check for matplotlib figures and capture them
            try:
                if 'matplotlib' in sys.modules:
                    import matplotlib.pyplot as plt
                    import base64
                    from io import BytesIO
                    
                    # Get all figures
                    figs = [plt.figure(n) for n in plt.get_fignums()]
                    if len(figs) > 0:
                        for fig in figs:
                            # Save figure to bytes
                            buf = BytesIO()
                            fig.savefig(buf, format='png', bbox_inches='tight', dpi=100)
                            buf.seek(0)
                            img_base64 = base64.b64encode(buf.read()).decode('utf-8')
                            buf.close()
                            
                            # Add as display_data output
                            outputs.append({
                                'output_type': 'display_data',
                                'data': {
                                    'image/png': img_base64
                                },
                                'metadata': {}
                            })
                        
                        # Close all figures to free memory
                        plt.close('all')
            except Exception as e:
                # If matplotlib capture fails, add error to stderr for debugging
                stderr_capture.write(f"\\nMatplotlib capture error: {{str(e)}}\\n")
                pass
            
            NBS_OUTPUT_LIMIT = 10000  # Max characters in output 10kb, defined here so it cannot be changed by notebook code
            # Build outputs list
            if stdout_text:
                
                # Truncate stdout if too long
                if len(stdout_text) > NBS_OUTPUT_LIMIT:
                    stdout_text = stdout_text[:NBS_OUTPUT_LIMIT] + "\\n...[ERROR output truncated]\\n"

                outputs.append({
                    'output_type': 'stream',
                    'name': 'stdout',
                    'text': stdout_text
                })
            if stderr_text:
                
                # Truncate stderr if too long
                if len(stderr_text) > NBS_OUTPUT_LIMIT:
                    stderr_text = stderr_text[:NBS_OUTPUT_LIMIT] + "\\n...[ERROR output truncated]\\n"
                    
                outputs.append({
                    'output_type': 'stream',
                    'name': 'stderr',
                    'text': stderr_text
                })
            if not success:

                # Truncate error message if too long
                if error_msg and len(error_msg) > NBS_OUTPUT_LIMIT:
                    error_msg = error_msg[:NBS_OUTPUT_LIMIT] + "\\n...[ERROR message truncated]\\n"

                if stderr_text and len(stderr_text) > NBS_OUTPUT_LIMIT:
                    stderr_text = stderr_text[:NBS_OUTPUT_LIMIT] + "\\n...[ERROR message truncated]\\n"

                outputs.append({
                    'output_type': 'error',
                    'ename': 'ExecutionError',
                    'evalue': error_msg or stderr_text,
                    'traceback': [stderr_text]
                })

            results.append({
                'cell_type': 'code',
                'source': cell_source,
                'outputs': outputs,
                'execution_count': sum(1 for r in results if r.get('cell_type') == 'code') + 1,
                'idx': cell_idx
            })

# Output results as JSON
end_time = time.time()
execution_time = end_time - script_start_time


# Populate stdout and stderr from results allows us to give a better breakdown of each cell output in the view, Each cell will be _______cell <idx>______

stdout_cells= ""
stderr_cells =""

for cell in results:
    outputs = cell.get('outputs', [])
    
    for output in outputs:
        if output['output_type'] == 'stream' and output['name'] == 'stdout':
            stdout_cells += f"______cell {cell['idx']}______\n\n" + output['text'] + "\n"
        elif output['output_type'] == 'stream' and output['name'] == 'stderr':
            stderr_cells += f"______cell {cell['idx']}______\n\n" + output['text'] + "\n"

# Create final output_data should look like a notebook but with populated cells

final_result = {
    "success": len(failed_packages) == 0,
    "stdout": stdout_cells, 
    "stderr": stderr_cells, 
    "error": None,
    "execution_time": execution_time,
    "output_data": {
        "cells": results
    }
}

print('<<<RESULTS_START>>>')
print(json.dumps(final_result))
print('<<<RESULTS_END>>>')