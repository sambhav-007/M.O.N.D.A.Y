import sys
import argparse
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

import platform

def execute_show_those_results_y(query: str) -> None:
    """Generalized dynamic task plugin."""
    print(f"✓ Generalized Dynamic Task Executed: '{query}'")
    print(f"  System Environment: {platform.system()} {platform.release()} | Python: {sys.version.split()[0]}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generalized Task Plugin")
    parser.add_argument("--query", type=str, default="show those results you just found", help="Task prompt query")
    args = parser.parse_args()
    execute_show_those_results_y(args.query)
