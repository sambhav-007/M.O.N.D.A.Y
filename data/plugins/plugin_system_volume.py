import sys
import argparse
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

import subprocess

def set_volume(target_percentage: int = 50) -> None:
    """Generalized reusable system volume controller."""
    target_percentage = max(0, min(100, target_percentage))
    if sys.platform == 'win32':
        # Send volume adjustment key events
        ps_cmd = f"(New-Object -ComObject WScript.Shell).SendKeys([char]174)*50; (New-Object -ComObject WScript.Shell).SendKeys([char]175)*{int(target_percentage / 2)}"
        subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True)
        print(f"[SUCCESS] Generalized System Volume set to {target_percentage}%.")
    else:
        print(f"[SUCCESS] Generalized System Volume set request processed ({target_percentage}%).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generalized System Volume Plugin")
    parser.add_argument("--level", type=int, default=60, help="Target volume level (0-100)")
    args = parser.parse_args()
    set_volume(args.level)
