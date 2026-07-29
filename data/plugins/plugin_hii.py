import sys
import argparse
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

import platform

def execute_hii(query: str) -> None:
    """Generalized dynamic task plugin."""
    print(f"✓ Generalized Dynamic Task Executed: '{query}'")
    print(f"  System Environment: {platform.system()} {platform.release()} | Python: {sys.version.split()[0]}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generalized Task Plugin")
    parser.add_argument("--query", type=str, default="hii", help="Task prompt query")
    args = parser.parse_args()
    execute_hii(args.query)
