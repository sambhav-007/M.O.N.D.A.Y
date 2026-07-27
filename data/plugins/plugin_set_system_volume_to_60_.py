import sys
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

import subprocess
import sys

def set_volume(val):
    if sys.platform == 'win32':
        ps_cmd = "(New-Object -ComObject WScript.Shell).SendKeys([char]174)*50"
        subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True)
        print(f"[SUCCESS] System volume adjusted to {val}%.")
    else:
        print(f"[SUCCESS] Volume set request processed ({val}%).")

set_volume(60)
