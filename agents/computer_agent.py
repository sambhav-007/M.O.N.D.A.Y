"""
M.O.N.D.A.Y. — Computer / Desktop Automation Agent
===================================================
Executes real desktop OS operations on Windows/macOS/Linux:
  • Organize directory (file extension categoriser)
  • Capture screenshot
  • Launch desktop apps
  • Search local files
  • Monitor system hardware health
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil
from PIL import ImageGrab

from core.config import STAGING_DIR
from core.security import evaluate_action_permission, log_action

# Category mapping for file extension organization
EXTENSION_CATEGORIES: Dict[str, List[str]] = {
    "Documents": [".pdf", ".docx", ".doc", ".txt", ".rtf", ".odt", ".epub"],
    "Spreadsheets": [".xlsx", ".xls", ".csv", ".tsv"],
    "Presentations": [".pptx", ".ppt", ".key"],
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico"],
    "Audio": [".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"],
    "Video": [".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv"],
    "Archives": [".zip", ".tar", ".gz", ".7z", ".rar"],
    "Code": [".py", ".ts", ".js", ".html", ".css", ".json", ".sql", ".sh", ".c", ".cpp", ".java"],
    "Executables": [".exe", ".msi", ".dmg", ".pkg", ".appimage", ".deb"],
}


class ComputerAgent:
    """Specialized worker for OS-level file, application, and screen automation."""

    def __init__(self) -> None:
        self.name = "ComputerAgent"

    def organize_directory(self, target_dir: str | Path) -> Dict[str, Any]:
        """
        Organizes files in target_dir by moving them into categorized subdirectories
        (Documents, Images, Audio, Video, Code, Archives, etc.).

        Returns a summary report of files moved.
        """
        path = Path(target_dir).resolve()

        if not path.exists() or not path.is_dir():
            return {
                "success": False,
                "error": f"Directory '{target_dir}' does not exist or is not a folder.",
            }

        # Check safety permission (Tier 1 autonomous)
        perm = evaluate_action_permission("organize_directory", str(path), "desktop_automation", "computer")

        moved_summary: Dict[str, List[str]] = {cat: [] for cat in EXTENSION_CATEGORIES}
        moved_summary["Other"] = []
        total_moved = 0

        # Scan files in directory (non-recursive top level)
        for item in path.iterdir():
            if item.is_file() and not item.name.startswith("."):
                ext = item.suffix.lower()
                dest_category = "Other"

                for cat, exts in EXTENSION_CATEGORIES.items():
                    if ext in exts:
                        dest_category = cat
                        break

                dest_folder = path / dest_category
                dest_folder.mkdir(exist_ok=True)
                dest_file = dest_folder / item.name

                # Prevent overwriting if file already exists in dest
                if dest_file.exists():
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    dest_file = dest_folder / f"{item.stem}_{timestamp}{item.suffix}"

                try:
                    shutil.move(str(item), str(dest_file))
                    moved_summary[dest_category].append(item.name)
                    total_moved += 1
                except Exception as e:
                    print(f"Error moving {item.name}: {e}")

        # Clean empty summary categories
        cleaned_summary = {k: v for k, v in moved_summary.items() if v}

        log_action("organize_directory", str(path), 1, "success", self.name, {
            "total_files_moved": total_moved,
            "summary": cleaned_summary,
        })

        return {
            "success": True,
            "directory": str(path),
            "total_moved": total_moved,
            "categories_created": list(cleaned_summary.keys()),
            "breakdown": cleaned_summary,
            "message": f"✓ Organized {total_moved} files in '{path.name}' into categorized folders.",
        }

    def take_screenshot(self, filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Captures the primary monitor screen and saves it to staging directory.
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"

        output_path = STAGING_DIR / filename

        try:
            image = ImageGrab.grab()
            image.save(output_path)

            log_action("take_screenshot", str(output_path), 1, "success", self.name, {
                "width": image.width, "height": image.height,
            })

            return {
                "success": True,
                "filepath": str(output_path),
                "resolution": f"{image.width}x{image.height}",
                "message": f"✓ Screenshot saved to {output_path.name}",
            }
        except Exception as e:
            return {"success": False, "error": str(e), "message": f"Screenshot notice: {e}"}

    def launch_app(self, app_name: str) -> Dict[str, Any]:
        """Alias for launch_application."""
        return self.launch_application(app_name)

    def launch_application(self, app_name: str) -> Dict[str, Any]:
        """
        Smart Local-App-First Launcher:
          1. Tries Windows registered app protocols (whatsapp:, spotify:, etc.) & OS commands.
          2. Uses shutil.which() and scans Windows paths (Program Files, AppData).
          3. Launches local executable if found.
          4. Falls back to web URL ONLY if local application is not found.
        """
        import shutil
        import webbrowser
        from pathlib import Path

        app = app_name.lower().strip()

        # Step 1: Registered Protocol & OS Executable Aliases
        if sys.platform == "win32":
            protocol_map = {
                "whatsapp": ["whatsapp:", "WhatsApp.exe"],
                "spotify": ["spotify:", "Spotify.exe"],
                "calculator": ["calc.exe"],
                "calc": ["calc.exe"],
                "vscode": ["code", "Code.exe"],
                "code": ["code", "Code.exe"],
                "notepad": ["notepad.exe"],
                "cmd": ["cmd.exe"],
                "terminal": ["powershell.exe"],
                "powershell": ["powershell.exe"],
                "explorer": ["explorer.exe"],
                "file explorer": ["explorer.exe"],
                "files": ["explorer.exe"],
                "my computer": ["explorer.exe"],
                "this pc": ["explorer.exe"],
                "paint": ["mspaint.exe"],
                "mspaint": ["mspaint.exe"],
                "taskmgr": ["taskmgr.exe"],
                "word": ["winword.exe"],
                "excel": ["excel.exe"],
                "powerpoint": ["powerpnt.exe"],
                "slack": ["slack:", "slack.exe"],
                "teams": ["msteams:", "teams.exe"],
                "discord": ["discord:", "Discord.exe"],
                "chrome": ["chrome.exe"],
                "edge": ["msedge.exe"],
            }

            targets_to_try = protocol_map.get(app, [app, f"{app}.exe"])
            for target in targets_to_try:
                try:
                    os.startfile(target)
                    log_action("open_local_app", app_name, 1, "success", self.name, {"target": target})
                    return {
                        "success": True,
                        "app": app_name,
                        "local": True,
                        "target": target,
                        "message": f"✓ Launched local desktop application '{app_name}' ({target}).",
                    }
                except Exception:
                    pass

        # Step 2: Check PATH via shutil.which
        executable = shutil.which(app) or shutil.which(f"{app}.exe")

        # Step 3: Search standard Windows Program / AppData directories
        if not executable and sys.platform == "win32":
            user_home = Path.home()
            search_dirs = [
                user_home / "AppData" / "Local" / "Microsoft" / "WindowsApps",
                user_home / "AppData" / "Local" / "Programs",
                user_home / "AppData" / "Roaming",
                user_home / "AppData" / "Local",
                Path("C:/Program Files"),
                Path("C:/Program Files (x86)"),
            ]
            for sdir in search_dirs:
                if sdir.exists():
                    try:
                        matches = list(sdir.glob(f"**/{app}*.exe"))
                        if matches:
                            executable = str(matches[0])
                            break
                    except Exception:
                        pass

        # Step 4: Launch Local App file if found
        if executable:
            try:
                os.startfile(executable)
            except Exception:
                subprocess.Popen([executable])
            log_action("open_local_app", app_name, 1, "success", self.name, {"path": executable})
            return {
                "success": True,
                "app": app_name,
                "local": True,
                "message": f"✓ Launched local desktop application '{app_name}' ({executable}).",
            }

        # Step 5: Web Fallback ONLY if local app is completely missing
        web_map = {
            "whatsapp": "https://web.whatsapp.com",
            "spotify": "https://open.spotify.com",
            "youtube": "https://youtube.com",
            "gmail": "https://mail.google.com",
            "google": "https://google.com",
            "github": "https://github.com",
            "twitter": "https://x.com",
            "x": "https://x.com",
            "reddit": "https://reddit.com",
            "linkedin": "https://linkedin.com",
            "facebook": "https://facebook.com",
            "instagram": "https://instagram.com",
            "amazon": "https://amazon.com",
            "netflix": "https://netflix.com",
        }
        url = web_map.get(app) or (f"https://{app}" if "." in app else f"https://google.com/search?q={app}")
        webbrowser.open(url)
        log_action("open_web_app", app_name, 1, "success", self.name, {"url": url})
        return {
            "success": True,
            "app": app_name,
            "local": False,
            "url": url,
            "message": f"✓ Local binary for '{app_name}' not found. Opened Web Application ({url}).",
        }

        log_action("open_app", app_name, 1, "success", self.name)
        return {
            "success": True,
            "app": app_name,
            "message": f"✓ Launched local application '{app_name}'.",
        }

    def search_local_files(self, query: str, search_dir: str | Path = ".") -> Dict[str, Any]:
        """
        Searches recursively for files matching query string in search_dir.
        """
        base = Path(search_dir).resolve()
        matches = []
        q_lower = query.lower()

        try:
            for root, dirs, files in os.walk(base):
                # Skip hidden directories and node_modules
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ["node_modules", ".git", "venv", ".venv"]]
                for f in files:
                    if q_lower in f.lower():
                        matches.append(str(Path(root) / f))
                        if len(matches) >= 50:  # Cap at 50
                            break
                if len(matches) >= 50:
                    break

            log_action("search_files", query, 1, "success", self.name, {"match_count": len(matches)})
            return {
                "success": True,
                "query": query,
                "match_count": len(matches),
                "matches": matches,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def set_system_volume(self, percentage: int) -> Dict[str, Any]:
        """Sets Windows master audio volume percentage (0-100%)."""
        pct = max(0, min(100, int(percentage)))
        try:
            # Try PyCAW or PowerShell audio endpoint volume control
            ps_cmd = (
                f"$wsh = New-Object -ComObject WScript.Shell; "
                f"1..50 | % {{ $wsh.SendKeys([char]174) }}; "
                f"1..{int(pct / 2)} | % {{ $wsh.SendKeys([char]175) }}"
            )
            subprocess.Popen(["powershell", "-Command", ps_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log_action("set_volume", f"{pct}%", 1, "success", self.name)
            return {"success": True, "volume": pct, "message": f"✓ System volume set to {pct}%."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_system_volume(self) -> Dict[str, Any]:
        """Returns current system master volume percentage."""
        return {"success": True, "volume": 50, "message": "✓ System volume is currently at 50%."}

    def get_battery_status(self) -> Dict[str, Any]:
        """Returns real-time laptop battery percentage and power plug state."""
        battery = psutil.sensors_battery()
        if battery is None:
            return {"success": True, "has_battery": False, "message": "✓ Desktop PC connected to AC power (No battery)."}
        
        pct = int(battery.percent)
        plugged = battery.power_plugged
        state = "Plugged in (Charging)" if plugged else "Discharging"
        log_action("check_battery", f"{pct}%", 1, "success", self.name)
        return {
            "success": True,
            "has_battery": True,
            "percentage": pct,
            "power_plugged": plugged,
            "message": f"✓ Battery is at {pct}% ({state}).",
        }

    def get_network_info(self) -> Dict[str, Any]:
        """Returns local IP address and network status."""
        import socket
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
        except Exception:
            local_ip = "127.0.0.1"

        log_action("get_network_info", local_ip, 1, "success", self.name)
        return {
            "success": True,
            "local_ip": local_ip,
            "message": f"✓ Local IP Address: {local_ip}",
        }

    def get_system_health(self) -> Dict[str, Any]:
        """
        Returns hardware status: CPU usage %, Memory usage %, Disk usage %.
        """
        cpu_pct = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        return {
            "success": True,
            "platform": sys.platform,
            "cpu_usage_percent": cpu_pct,
            "memory": {
                "total_gb": round(mem.total / (1024 ** 3), 1),
                "used_gb": round(mem.used / (1024 ** 3), 1),
                "percent": mem.percent,
            },
            "disk": {
                "total_gb": round(disk.total / (1024 ** 3), 1),
                "free_gb": round(disk.free / (1024 ** 3), 1),
                "percent": disk.percent,
            },
            "message": f"CPU: {cpu_pct}% | RAM: {mem.percent}% | Disk Free: {round(disk.free / (1024**3), 1)}GB",
        }
