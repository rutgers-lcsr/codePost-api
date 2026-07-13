# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.

import os
import sys
import json

# Add autograder to path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# Minimal import setup
# We assume buildHelpers does NOT depend on Django models
from autograder.testUtils.buildHelpers import createDockerFile

def verify_all_languages():
    # Load specs manually to know what to test
    with open(os.path.join(os.path.dirname(__file__), 'buildSpecs.json')) as f:
        specs = json.load(f)
    
    print(f"Testing {len(specs)} configurations...")
    
    errors = []
    
    for lang, config in specs.items():
        if lang in ['alpine', 'ubuntu', 'windows', 'default']: continue # Skip templates
        
        print(f"  Verifying {lang}...", end="")
        try:
            # Generate Dockerfile
            dockerfile = createDockerFile(lang, "default", environmentID=123)
            
            # Basic Assertions
            if "FROM" not in dockerfile:
                errors.append(f"{lang}: Missing FROM instruction")
            
            # Check for base command presence
            if config.get('install'):
                # Heuristic: install command should usually be present unless it's empty
                pass 
                
            # Language specific checks
            if lang.startswith('java') and lang != 'javascript':
                if 'openjdk' not in dockerfile and 'jdk' not in dockerfile:
                     errors.append(f"{lang}: Base image missing jdk (got {config['base'].strip()})")
            
            if 'node' in lang:
                if 'node' not in dockerfile and 'npm' not in dockerfile:
                     errors.append(f"{lang}: Base image might be wrong (got {config['base'].strip()})")
            
            if 'r-' in lang or lang == 'r':
                if 'r-base' not in dockerfile:
                     errors.append(f"{lang}: Base image missing r-base (got {config['base'].strip()})")
            
            # Check for bash (User requirement)
            if 'bash' not in dockerfile:
                 errors.append(f"{lang}: Dockerfile missing bash installation")

            print(" OK")
            
        except Exception as e:
            print(" FAILED")
            errors.append(f"{lang}: Exception during generation: {e}")

    print("\nVerification Complete.")
    if errors:
        print("\nERRORS FOUND:")
        for e in errors:
            print(f"  [X] {e}")
        sys.exit(1)
    else:
        print("\nAll languages verified successfully.")

if __name__ == "__main__":
    verify_all_languages()
