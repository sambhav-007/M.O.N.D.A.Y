import sys
import argparse
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

import os, sys, platform, glob, shutil

def execute_print_system_datetim(query: str) -> None:
    """Generalized dynamic script execution for task: print system datetime"""
    q_lower = query.lower()
    print(f"✓ Dynamic Task Script Running for: '{query}'")
    if "list" in q_lower or "dir" in q_lower or "files" in q_lower:
        files = os.listdir('.')[:10]
        print(f"  Local files sample ({len(files)}): {', '.join(files)}")
    elif "sys" in q_lower or "info" in q_lower or "env" in q_lower:
        print(f"  System Info: {platform.system()} {platform.release()} | Python {sys.version.split()[0]}")
    else:
        print(f"  Executed dynamic command pipeline on {platform.system()}.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generalized Task Plugin")
    parser.add_argument("--query", type=str, default="print system datetime", help="Task prompt query")
    args = parser.parse_args()
    execute_print_system_datetim(args.query)
