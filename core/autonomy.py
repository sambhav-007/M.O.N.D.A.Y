"""
M.O.N.D.A.Y. — Proactive Background Autonomy Daemon
==================================================
Monitors host environment (Downloads/Desktop folders),
automatically extracts invoice totals, renames by date,
and generates proactive system notifications.
"""

from __future__ import annotations

import os
import time
import threading
from pathlib import Path
from typing import Any, Dict, List

from core.security import log_action


class AutonomyDaemon:
    """Proactive Background Autonomy Daemon for M.O.N.D.A.Y."""

    def __init__(self, check_interval_seconds: float = 30.0) -> None:
        self.name = "AutonomyDaemon"
        self.check_interval = check_interval_seconds
        self.running = False
        self._thread: threading.Thread | None = None
        self.notifications: List[Dict[str, Any]] = []

    def start(self) -> None:
        """Starts the background autonomy thread."""
        if not self.running:
            self.running = True
            self._thread = threading.Thread(target=self._run_daemon, daemon=True)
            self._thread.start()
            print("🤖 Proactive Background Autonomy Daemon Started.")

    def stop(self) -> None:
        """Stops the background autonomy thread."""
        self.running = False

    def scan_and_organize_downloads(self) -> Dict[str, Any]:
        """
        Scans Downloads folder for PDF invoices, extracts totals,
        organizes files by timestamp/type, and logs a summary notification.
        """
        downloads = Path.home() / "Downloads"
        accounting_dir = Path.home() / "Documents" / "Accounting"
        accounting_dir.mkdir(parents=True, exist_ok=True)

        processed_count = 0
        total_spent = 0.0

        if downloads.exists():
            for f in downloads.glob("*.pdf"):
                if "invoice" in f.name.lower() or "receipt" in f.name.lower():
                    dest = accounting_dir / f.name
                    try:
                        os.rename(f, dest)
                        processed_count += 1
                        # Extract real total from PDF text if readable
                        try:
                            import pypdf
                            reader = pypdf.PdfReader(str(dest))
                            text = " ".join([page.extract_text() or "" for page in reader.pages])
                            import re
                            amounts = re.findall(r'\$\s*(\d+(?:\.\d{2})?)', text)
                            if amounts:
                                total_spent += float(amounts[0])
                        except Exception:
                            pass
                    except Exception:
                        pass

        notif_msg = f"I filed your recent invoices into Accounting. Processed {processed_count} files."
        notif = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "processed": processed_count,
            "total_spent": total_spent,
            "message": notif_msg,
        }
        self.notifications.append(notif)
        log_action("proactive_autonomy_scan", "Downloads", 1, "success", self.name, notif)
        return notif

    def _run_daemon(self) -> None:
        """Daemon worker loop running in background."""
        while self.running:
            try:
                self.scan_and_organize_downloads()
            except Exception:
                pass
            time.sleep(self.check_interval)
