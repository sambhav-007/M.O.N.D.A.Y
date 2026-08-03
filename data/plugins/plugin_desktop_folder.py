import sys
import argparse
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

import os
from pathlib import Path

def create_desktop_folder(folder_name: str = "NewFolder") -> str:
    """Generalized desktop folder creator."""
    desktop = Path.home() / "Desktop"
    target_dir = desktop / folder_name
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"[SUCCESS] Created generalized desktop folder at: {target_dir}")
    return str(target_dir)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generalized Desktop Folder Plugin")
    parser.add_argument("--folder_name", type=str, default="NewFolder", help="Target folder name")
    args = parser.parse_args()
    create_desktop_folder(args.folder_name)
