"""
M.O.N.D.A.Y. — Living 3D AI Entity Native Desktop GUI App
=========================================================
Launches a native OS desktop GUI application window displaying
the 3D WebGL Living Entity connected live to the Master Planner engine.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
import threading

# Force Windows console stdout/stderr to UTF-8 with errors='replace'
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import uvicorn
from pathlib import Path
from typing import Optional

# Ensure M.O.N.D.A.Y root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def free_port_if_occupied(port: int = 8000) -> None:
    """Kills any stale process holding the target port to prevent WinError 10048."""
    try:
        import psutil
        for c in psutil.net_connections():
            if c.laddr and c.laddr.port == port and c.pid and c.pid != os.getpid():
                try:
                    psutil.Process(c.pid).kill()
                except Exception:
                    pass
    except Exception:
        pass


# Set by the server thread when it dies, so main() can report the real cause
# instead of opening a window onto an engine that never started.
SERVER_STARTUP_ERROR: Optional[BaseException] = None


def start_fastapi_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Runs uvicorn FastAPI server in background thread after clearing port bindings."""
    global SERVER_STARTUP_ERROR
    try:
        free_port_if_occupied(port)
        from api.main import app
        uvicorn.run(app, host=host, port=port, log_level="error")
    except BaseException as ex:  # noqa: BLE001 - must not vanish into the thread
        SERVER_STARTUP_ERROR = ex
        raise


def launch_native_tkinter_gui(app_url: str) -> None:
    """Fallback Native Tkinter Desktop Application Window."""
    import tkinter as tk
    from tkinter import ttk
    import json
    import urllib.request

    root = tk.Tk()
    root.title("M.O.N.D.A.Y. — Native Desktop AI Assistant")
    root.geometry("1100x750")
    root.configure(bg="#060608")

    # Header
    hdr = tk.Frame(root, bg="#0c0c12", pady=15, padx=20)
    hdr.pack(fill="x")
    title_lbl = tk.Label(
        hdr, text="🤖 M.O.N.D.A.Y. Native Desktop Shell",
        font=("Helvetica", 16, "bold"), fg="#ffd700", bg="#0c0c12"
    )
    title_lbl.pack(side="left")
    status_lbl = tk.Label(
        hdr, text="● Living Entity Active",
        font=("Helvetica", 11, "bold"), fg="#10b981", bg="#0c0c12"
    )
    status_lbl.pack(side="right")

    # Main Body Frame
    body = tk.Frame(root, bg="#060608", padx=20, pady=20)
    body.pack(fill="both", expand=True)

    # Entity Visual Canvas Frame (ASCII Living Animation)
    entity_frame = tk.Frame(body, bg="#0c0c12", highlightbackground="#ff8c00", highlightthickness=1, padx=15, pady=15)
    entity_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

    canvas_title = tk.Label(entity_frame, text="LIVING ENTITY CONSCIOUSNESS", font=("Courier", 12, "bold"), fg="#ffaa00", bg="#0c0c12")
    canvas_title.pack(anchor="w", pady=(0, 10))

    entity_ascii = tk.Text(entity_frame, bg="#060608", fg="#ffd700", font=("Consolas", 10), height=14, borderwidth=0)
    entity_ascii.pack(fill="both", expand=True)

    ascii_art = """
             .---.            .---.
            /     \\          /     \\
           |   o   |        |   o   |
            \\     /          \\     /
             `---'            `---'
       ________________________________
      /                                \\
     |   M.O.N.D.A.Y. 3D ENTITY ACTIVE  |
     |   Status: IDLE (Breathing)      |
      \\________________________________/
               \\            /
                \\          /
                 `--------'
    """
    entity_ascii.insert("1.0", ascii_art)
    entity_ascii.config(state="disabled")

    # Right Log Frame
    log_frame = tk.Frame(body, bg="#0c0c12", highlightbackground="#27272a", highlightthickness=1, padx=15, pady=15)
    log_frame.pack(side="right", fill="both", expand=True, padx=(10, 0))

    log_title = tk.Label(log_frame, text="MULTI-AGENT EXECUTION LOG", font=("Courier", 12, "bold"), fg="#ffaa00", bg="#0c0c12")
    log_title.pack(anchor="w", pady=(0, 10))

    log_text = tk.Text(log_frame, bg="#060608", fg="#f4f4f5", font=("Consolas", 10), borderwidth=0)
    log_text.pack(fill="both", expand=True)
    log_text.insert("1.0", "🧠 M.O.N.D.A.Y. Engine Online.\nType a command below to execute...\n\n")

    # Command Input Row
    input_frame = tk.Frame(root, bg="#0c0c12", pady=15, padx=20)
    input_frame.pack(fill="x")

    cmd_entry = tk.Entry(input_frame, bg="#060608", fg="#ffd700", font=("Consolas", 12), insertbackground="#ffd700")
    cmd_entry.pack(side="left", fill="x", expand=True, padx=10)

    def run_cmd():
        cmd = cmd_entry.get().strip()
        if not cmd:
            return
        log_text.insert("end", f"\nmonday > {cmd}\n")
        cmd_entry.delete(0, "end")

        def query_api():
            try:
                req = urllib.request.Request(
                    "http://127.0.0.1:8000/agent/execute",
                    data=json.dumps({"command": cmd, "user_approved": True}).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    ic = data.get("intent_classification", {})
                    exec_res = data.get("execution_result", {})
                    msg = f"  Intent: {ic.get('predicted_intent')} ({ic.get('confidence')*100:.1f}%)\n  Result: {exec_res.get('message')}\n"
                    root.after(0, lambda: log_text.insert("end", msg))
            except Exception as ex:
                root.after(0, lambda: log_text.insert("end", f"  Error: {ex}\n"))

        threading.Thread(target=query_api, daemon=True).start()

    cmd_entry.bind("<Return>", lambda event: run_cmd())
    btn = tk.Button(input_frame, text="EXECUTE", command=run_cmd, bg="#ff8c00", fg="#000000", font=("Helvetica", 10, "bold"), padx=15)
    btn.pack(side="right")

    root.mainloop()


# Global Configuration Flags
ENABLE_VOICE = True


class DesktopWindowApi:
    """JS-to-Python Bridge for Frameless Window controls."""

    def close_app(self):
        try:
            import webview
            if webview.windows:
                webview.windows[0].destroy()
        except Exception:
            pass
        os._exit(0)

    def minimize_app(self):
        try:
            import webview
            if webview.windows:
                webview.windows[0].minimize()
        except Exception:
            pass

    def toggle_tray(self):
        """Toggles window visibility for System Tray & Alt+Space overlay."""
        try:
            import webview
            if webview.windows:
                w = webview.windows[0]
                if w.is_minimized:
                    w.restore()
                else:
                    w.minimize()
        except Exception:
            pass

    def toggle_voice(self, enabled: bool):
        """Toggles voice synthesis output on or off."""
        global ENABLE_VOICE
        ENABLE_VOICE = bool(enabled)
        from api.main import get_planner
        planner = get_planner()
        planner.voice_agent.set_voice_enabled(ENABLE_VOICE)
        planner.enable_voice = ENABLE_VOICE
        return {"success": True, "enable_voice": ENABLE_VOICE}

    def execute_command(self, command: str):
        """Direct JS-to-Python bridge method for PyWebView native execution."""
        from api.main import get_planner
        planner = get_planner()
        return planner.process_command(command, user_approved=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="M.O.N.D.A.Y. Living 3D AI Entity Native Desktop Application")
    ap.add_argument("--host", default="127.0.0.1", help="Host address")
    ap.add_argument("--port", type=int, default=8000, help="Port number")
    ap.add_argument("--test", action="store_true", help="Non-blocking test mode")
    args = ap.parse_args()

    print("=" * 65)
    print("      M.O.N.D.A.Y. — NATIVE DESKTOP GUI APPLICATION")
    print("=" * 65)
    print(f"🚀 Initializing Engine at http://{args.host}:{args.port}...")

    # Start FastAPI server thread
    server_thread = threading.Thread(
        target=start_fastapi_server,
        args=(args.host, args.port),
        daemon=True
    )
    server_thread.start()

    # Wait until FastAPI engine server is active and serving requests
    import urllib.request
    app_url = f"http://{args.host}:{args.port}/app"
    engine_up = False
    for _ in range(30):
        if SERVER_STARTUP_ERROR is not None:
            break
        try:
            with urllib.request.urlopen(f"http://{args.host}:{args.port}/health", timeout=1) as resp:
                if resp.status == 200:
                    engine_up = True
                    break
        except Exception:
            time.sleep(0.3)

    # Never open a window onto a dead engine — that looks like the app works
    # while every command silently fails.
    if not engine_up:
        print("\n❌ The M.O.N.D.A.Y. engine failed to start; not opening the UI.")
        if SERVER_STARTUP_ERROR is not None:
            print(f"   Cause: {type(SERVER_STARTUP_ERROR).__name__}: {SERVER_STARTUP_ERROR}")
            if "Application Control policy" in str(SERVER_STARTUP_ERROR):
                print(
                    "   Windows Smart App Control blocked a dependency's binary. This "
                    "usually hits freshly-published wheels;\n   reinstalling that package "
                    "at a slightly older version normally clears it."
                )
        else:
            print(f"   No response from http://{args.host}:{args.port}/health after ~9s.")
        sys.exit(1)

    if args.test:
        print("✓ Native Desktop Application verified cleanly.")
        return

    # Try PyWebView Native OS App Window
    try:
        import webview
        print("🖥️  Launching Frameless Native WebGL Desktop App Window via PyWebView...")
        api_bridge = DesktopWindowApi()
        w = webview.create_window(
            title="M.O.N.D.A.Y. — Living 3D AI Entity Assistant",
            url=app_url,
            width=1280,
            height=850,
            frameless=True,
            easy_drag=True,
            background_color="#060608",
            js_api=api_bridge
        )
        webview.start()
    except Exception as ex:
        print(f"🖥️  Launching Native Tkinter Desktop Application Window... (PyWebView: {ex})")
        launch_native_tkinter_gui(app_url)


if __name__ == "__main__":
    main()
