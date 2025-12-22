# This is a template for running code

# to use this template, replace packages_to_install = [] with the list of packages you want to install
# then add the script to the bottom of the file



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


def template_log(message: str, level:str) -> None:
    # Write to stderr with a prefix/format that can be tracked if needed, 
    # but primarily just dumping logs to stderr as requested.
    print(f"[{level}] {message}", file=sys.stderr)



# Packages to install
packages_to_install = []

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
            [sys.executable, '-m', 'pip', 'install', '--user', '-v', package],
            capture_output=True,
            text=True
        )
        elapsed = time.time() - start_time
        
        # Check if pip used cache (look for cache-related messages)
        used_cache = 'Using cached' in result.stdout or 'from cache' in result.stdout.lower()
        cache_indicator = '(cached)' if used_cache else '(downloaded)'
        
        if result.returncode == 0:
            template_log(f"[{i}/{len(needs_install)}] ✓ {package} installed {cache_indicator} ({elapsed:.1f}s)", "INFO")
            # Log to stderr so Converger picks it up
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

# START OF USER SCRIPT TEMPLATE

try:
    # Attempt to setup plot capture if matplotlib is available
    import matplotlib
    import matplotlib.pyplot as plt
    import io
    import base64
    import atexit

    def _codepost_show_hook(*args, **kwargs):
        try:
            # Capture the current figure
            if plt.get_fignums():
                fig = plt.gcf()
                buf = io.BytesIO()
                fig.savefig(buf, format='png')
                buf.seek(0)
                img_data = base64.b64encode(buf.read()).decode('utf-8')
                # Print delimiter to stdout for the Executor to capture
                print(f"\n<<<CODEPOST_PLOT:{img_data}>>>\n") 
                plt.close(fig)
        except Exception as e:
            print(f"Error capturing plot: {e}", file=sys.stderr)

    # Monkeypatch plt.show
    plt.show = _codepost_show_hook

    # Handler to capture any remaining plots at exit (auto-print behavior)
    def _codepost_plot_atexit():
        try:
            # Capture all remaining open figures
            fignums = plt.get_fignums()
            for i in fignums:
                plt.figure(i)
                _codepost_show_hook()
        except:
            pass
            
    atexit.register(_codepost_plot_atexit)

except ImportError:
    # Matplotlib not installed, skip capture setup
    pass
except Exception as e:
    print(f"Warning: Failed to setup plot capture: {e}", file=sys.stderr)

print("<<<RESULT>>>", file=sys.stderr)

#{FILLER_CODE}
