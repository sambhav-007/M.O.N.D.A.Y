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
from core.contracts import AgentResult, ProcessExit, SystemQuery
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

    def create_folder(self, name: str, parent: str | Path | None = None) -> Dict[str, Any]:
        clean_name = name.strip().strip('"\'')
        base = Path(parent).expanduser() if parent else Path.home() / "Desktop"
        target = (base / clean_name).resolve()
        if not clean_name or target.name != clean_name:
            return {"success": False, "error": "INVALID_FOLDER_NAME", "message": "Give me a valid folder name."}
        if target.exists():
            return {"success": False, "error": "FOLDER_EXISTS", "message": f"That folder already exists: {target}"}
        try:
            target.mkdir(parents=False)
        except OSError as exc:
            return {"success": False, "error": "FOLDER_CREATE_FAILED", "message": f"I couldn't create {target}: {exc}"}
        log_action("create_folder", str(target), 1, "success", self.name)
        return {"success": True, "folder": str(target), "message": f"✓ Created folder: {target}"}

    def rename_folder(self, source: str, name: str) -> Dict[str, Any]:
        source_path = Path(source).expanduser().resolve()
        clean_name = name.strip().strip('"\'')
        target = source_path.parent / clean_name
        if not source_path.is_dir():
            return {"success": False, "error": "FOLDER_NOT_FOUND", "message": f"Folder not found: {source_path}"}
        if not clean_name or target.exists():
            return {"success": False, "error": "FOLDER_TARGET_EXISTS", "message": f"Cannot rename to {target}"}
        try:
            source_path.rename(target)
        except OSError as exc:
            return {"success": False, "error": "FOLDER_RENAME_FAILED", "message": f"I couldn't rename {source_path}: {exc}"}
        log_action("rename_folder", f"{source_path} -> {target}", 1, "success", self.name)
        return {"success": True, "folder": str(target), "message": f"✓ Renamed folder to: {target}"}

    def delete_folder(self, target: str) -> Dict[str, Any]:
        path = Path(target).expanduser().resolve()
        if not path.is_dir():
            return {"success": False, "error": "FOLDER_NOT_FOUND", "message": f"Folder not found: {path}"}
        try:
            shutil.rmtree(path)
        except OSError as exc:
            return {"success": False, "error": "FOLDER_DELETE_FAILED", "message": f"I couldn't delete {path}: {exc}"}
        log_action("delete_folder", str(path), 2, "success", self.name)
        return {"success": True, "folder": str(path), "message": f"✓ Deleted folder: {path}"}

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
        """Sets Windows master audio volume percentage (0-100%).

        Works by sending volume-down 50 times to reach zero, then volume-up
        `pct/2` times — each keypress is a 2% step. That is a real mechanism, but
        it used to be launched with `subprocess.Popen` and reported success on
        the next line, before PowerShell had done anything at all: a failure to
        launch, a policy block or a non-zero exit were all reported as
        "✓ System volume set". It now waits for the exit status and reports what
        that status was.
        """
        if sys.platform != "win32":
            return AgentResult.unsupported(
                "set the system volume on this platform",
                detail="The keypress mechanism is Windows-only.",
            ).as_dict()

        pct = max(0, min(100, int(percentage)))
        ps_cmd = (
            f"$wsh = New-Object -ComObject WScript.Shell; "
            f"1..50 | % {{ $wsh.SendKeys([char]174) }}; "
            f"1..{int(pct / 2)} | % {{ $wsh.SendKeys([char]175) }}"
        )
        try:
            proc = subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            log_action("set_volume", f"{pct}%", 1, "timeout", self.name)
            return AgentResult.failed(
                "The volume command did not finish in time; the volume may be "
                "partly changed.",
                error="VOLUME_TIMEOUT",
            ).as_dict()
        except Exception as e:
            log_action("set_volume", f"{pct}%", 1, "failure", self.name)
            return AgentResult.failed(
                f"Could not run the volume command: {e}", error="VOLUME_EXEC_FAILED"
            ).as_dict()

        if proc.returncode != 0:
            log_action("set_volume", f"{pct}%", 1, "failure", self.name)
            return AgentResult.failed(
                f"The volume command failed (exit {proc.returncode}).",
                error="VOLUME_COMMAND_FAILED",
                data={"stderr": (proc.stderr or "").strip()[:200]},
            ).as_dict()

        log_action("set_volume", f"{pct}%", 1, "success", self.name)
        return AgentResult.ok(
            f"✓ System volume set to {pct}%.",
            evidence=ProcessExit(
                command="powershell -Command <volume keypresses>",
                returncode=proc.returncode,
                stdout_excerpt=(proc.stdout or "").strip()[:120],
            ),
            data={"volume": pct},
        ).as_dict()

    def create_file_artifact(self, filename: str, content: str) -> Dict[str, Any]:
        """Creates and saves a text file artifact into staging directory."""
        clean_name = Path(filename).name or "artifact_output.txt"
        target_path = STAGING_DIR / clean_name
        try:
            target_path.write_text(content, encoding="utf-8")
            log_action("create_file_artifact", str(target_path), 1, "success", self.name)
            return {
                "success": True,
                "filepath": str(target_path),
                "filename": clean_name,
                "message": f"✓ Created file artifact at '{target_path.name}'.",
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to save file artifact: {e}"}

    def get_system_volume(self) -> Dict[str, Any]:
        """Returns current system master volume percentage via OS query.

        The fallback used to be `{"success": True, "volume": 50, "message":
        "✓ System volume query completed."}` — a hardcoded 50 presented as a
        reading. It was also the *only* path that ever ran: `Win32_AudioDevice`
        exposes no `Volume` property, so the CIM query never returns a number and
        every caller since has been told the volume is 50%.

        Windows has no supported way to read the master volume from PowerShell
        without a helper (pycaw, nircmd, an AudioDeviceCmdlets module), none of
        which is installed here. So the honest answer is that it cannot be read.
        """
        if sys.platform == "win32":
            try:
                ps_cmd = (
                    "[Math]::Round((Get-CimInstance -ClassName Win32_AudioDevice "
                    "| Select-Object -First 1).Volume * 100)"
                )
                res = subprocess.run(
                    ["powershell", "-Command", ps_cmd],
                    capture_output=True, text=True, timeout=5,
                )
                if res.stdout.strip().isdigit():
                    vol = int(res.stdout.strip())
                    return AgentResult.ok(
                        f"✓ System volume is currently at {vol}%.",
                        evidence=SystemQuery(
                            source="Win32_AudioDevice", detail=f"{vol}%"
                        ),
                        data={"volume": vol},
                    ).as_dict()
            except Exception:
                pass

        return AgentResult.failed(
            "I can't read the current volume on this machine — Windows doesn't "
            "expose it to PowerShell without a helper like pycaw or nircmd, and "
            "neither is installed. I can still set it.",
            error="VOLUME_READ_UNSUPPORTED",
        ).as_dict()

    def get_battery_status(self) -> Dict[str, Any]:
        """Returns real-time laptop battery percentage and power plug state."""
        battery = psutil.sensors_battery()
        if battery is None:
            return AgentResult.ok(
                "✓ Desktop PC connected to AC power (No battery).",
                evidence=SystemQuery(source="psutil.sensors_battery", detail="no battery present"),
                data={"has_battery": False},
            ).as_dict()
        
        pct = int(battery.percent)
        plugged = battery.power_plugged
        state = "Plugged in (Charging)" if plugged else "Discharging"
        log_action("check_battery", f"{pct}%", 1, "success", self.name)
        return AgentResult.ok(
            f"✓ Battery is at {pct}% ({state}).",
            evidence=SystemQuery(source="psutil.sensors_battery", detail=f"{pct}%, plugged={plugged}"),
            data={"has_battery": True, "percentage": pct, "power_plugged": plugged},
        ).as_dict()

    def get_network_info(self) -> Dict[str, Any]:
        """Returns local IP address and network status."""
        import socket
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
        except Exception:
            local_ip = "127.0.0.1"

        log_action("get_network_info", local_ip, 1, "success", self.name)
        return AgentResult.ok(
            f"✓ Local IP Address: {local_ip}",
            # The source matters here more than most: this reads the machine's
            # own adapters, and the defect it replaced looked up a *public* IP
            # from a third party. The evidence says which one happened.
            evidence=SystemQuery(source="socket.gethostbyname", detail=hostname),
            data={"local_ip": local_ip, "hostname": hostname},
        ).as_dict()

    def get_system_health(self) -> Dict[str, Any]:
        """
        Returns hardware status: CPU usage %, Memory usage %, Disk usage %.
        """
        cpu_pct = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        return AgentResult.ok(
            f"CPU: {cpu_pct}% | RAM: {mem.percent}% | Disk Free: {round(disk.free / (1024**3), 1)}GB",
            evidence=SystemQuery(
                source="psutil.cpu_percent/virtual_memory/disk_usage",
                detail=f"cpu {cpu_pct}%, ram {mem.percent}%, disk {disk.percent}%",
            ),
            data={
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
            },
        ).as_dict()

    def list_running_processes(self, limit: int = 15) -> Dict[str, Any]:
        """Lists top system processes sorted by RAM memory usage."""
        processes = []
        try:
            for p in sorted(psutil.process_iter(['pid', 'name', 'memory_percent', 'cpu_percent']),
                            key=lambda p: p.info.get('memory_percent') or 0, reverse=True)[:limit]:
                processes.append({
                    "pid": p.info['pid'],
                    "name": p.info['name'],
                    "memory_percent": round(p.info['memory_percent'] or 0.0, 1),
                    "cpu_percent": round(p.info['cpu_percent'] or 0.0, 1),
                })
            log_action("list_processes", f"top_{limit}", 1, "success", self.name)
            return AgentResult.ok(
                f"✓ Retrieved top {len(processes)} active system processes.",
                evidence=SystemQuery(
                    source="psutil.process_iter",
                    detail=f"{len(processes)} processes by memory",
                ),
                data={
                    "process_count": len(processes),
                    "processes": processes,
                    "top_processes": processes,
                },
            ).as_dict()
        except Exception as e:
            return AgentResult.failed(
                f"I couldn't read the process list: {e}",
                error="PROCESS_LIST_FAILED",
            ).as_dict()

    def terminate_process(self, process_name_or_pid: str | int, user_approved: bool = False) -> Dict[str, Any]:
        """Terminates target process by PID or process name (Tier-2 security gated)."""
        perm = evaluate_action_permission("terminate_process", str(process_name_or_pid), "desktop_automation", "computer", user_approved=user_approved)
        if perm["requires_approval"] and not user_approved:
            return {
                "success": False,
                "tier_2_gated": True,
                "requires_approval": True,
                "action": "terminate_process",
                "target": str(process_name_or_pid),
                "confirmation_prompt": perm["confirmation_prompt"],
                "message": f"🔒 Tier-2 Action Gated: Explicit user approval required to terminate process '{process_name_or_pid}'.",
            }

        target_str = str(process_name_or_pid).lower().strip()
        terminated = []
        try:
            for p in psutil.process_iter(['pid', 'name']):
                if (target_str.isdigit() and p.info['pid'] == int(target_str)) or (target_str in (p.info['name'] or "").lower()):
                    p.kill()
                    terminated.append(f"{p.info['name']} (PID {p.info['pid']})")

            if terminated:
                log_action("terminate_process", target_str, 2, "success", self.name)
                return {
                    "success": True,
                    "target": target_str,
                    "terminated": terminated,
                    "message": f"✓ Terminated process(es): {', '.join(terminated)}.",
                }
            # An approved Tier-2 action that found nothing to do is still an
            # audited outcome, and it needs a `message` — the UI renders that key
            # and would otherwise show nothing at all after the user approved.
            log_action("terminate_process", target_str, 2, "not_found", self.name)
            return {
                "success": False,
                "target": target_str,
                "error": f"Process '{process_name_or_pid}' not found.",
                "message": f"No running process matched '{process_name_or_pid}' — nothing was terminated.",
            }
        except Exception as e:
            log_action("terminate_process", target_str, 2, "error", self.name, {"error": str(e)})
            return {
                "success": False,
                "target": target_str,
                "error": str(e),
                "message": f"Could not terminate '{process_name_or_pid}': {e}",
            }

    def get_desktop_environment_snapshot(self) -> Dict[str, Any]:
        """Compiles screenshot, processes, hardware health, and active window into unified context snapshot."""
        shot_res = self.take_screenshot()
        health_res = self.get_system_health()
        proc_res = self.list_running_processes(limit=5)

        log_action("get_environment_snapshot", "desktop", 1, "success", self.name)
        return {
            "success": True,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "screenshot_path": shot_res.get("filepath"),
            "health": health_res.get("message"),
            "top_processes": [p["name"] for p in proc_res.get("processes", [])],
            "message": f"✓ Desktop Snapshot Compiled | {health_res.get('message')}",
        }
