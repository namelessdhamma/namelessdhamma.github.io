#!/usr/bin/env python3
"""
LTX Model Mount Probe - Read-only inspection of Kaggle model datasource
Kaggle Private Script Kernel (CPU-only, internet disabled)
No mutations: inspection only.
"""
import os
import sys
import json
import shutil
from pathlib import Path

def inspect_kaggle_input():
    """Recursively inspect /kaggle/input for mounted datasources."""
    results = {
        "mounted_paths": [],
        "discovered_models": [],
        "disk_usage": {},
        "errors": []
    }
    
    input_root = Path("/kaggle/input")
    if not input_root.exists():
        results["errors"].append(f"/kaggle/input does not exist")
        return results
    
    try:
        # Recursive walk with depth limit
        for root, dirs, files in os.walk(input_root):
            depth = root.replace(str(input_root), "").count(os.sep)
            if depth > 5:  # Reasonable depth limit
                dirs.clear()
                continue
            
            for file in files:
                fpath = Path(root) / file
                try:
                    stat = fpath.stat()
                    is_readable = os.access(fpath, os.R_OK)
                    
                    entry = {
                        "absolute_path": str(fpath.resolve()),
                        "relative_path": str(fpath.relative_to(input_root)),
                        "size_bytes": stat.st_size,
                        "readable": is_readable,
                        "size_mb": round(stat.st_size / (1024 * 1024), 2)
                    }
                    
                    results["mounted_paths"].append(entry)
                    
                    # Flag .safetensors files
                    if file.endswith(".safetensors"):
                        results["discovered_models"].append(entry)
                
                except (OSError, PermissionError) as e:
                    results["errors"].append(f"Error stat {fpath}: {str(e)[:200]}")
    
    except Exception as e:
        results["errors"].append(f"Walk error: {str(e)[:200]}")
    
    # Get /kaggle/working disk usage
    try:
        usage = shutil.disk_usage("/kaggle/working")
        results["disk_usage"] = {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "total_gb": round(usage.total / (1024**3), 2),
            "used_gb": round(usage.used / (1024**3), 2),
            "free_gb": round(usage.free / (1024**3), 2)
        }
    except Exception as e:
        results["errors"].append(f"disk_usage error: {str(e)[:200]}")
    
    return results

if __name__ == "__main__":
    results = inspect_kaggle_input()
    
    # Output as JSON for Kaggle API parsing
    print("=== KAGGLE_MOUNT_PROBE_RESULTS ===")
    print(json.dumps(results, indent=2))
    print("=== END_RESULTS ===")
    
    # Summary to stdout
    print(f"\nMounted Paths: {len(results['mounted_paths'])}")
    print(f"Discovered .safetensors Models: {len(results['discovered_models'])}")
    
    if results["discovered_models"]:
        for model in results["discovered_models"]:
            print(f"  → {model['absolute_path']} ({model['size_mb']} MB)")
    
    if results["disk_usage"]:
        print(f"\n/kaggle/working Disk Usage:")
        print(f"  Total: {results['disk_usage']['total_gb']} GB")
        print(f"  Free:  {results['disk_usage']['free_gb']} GB")
    
    sys.exit(0 if not results["errors"] else 1)

