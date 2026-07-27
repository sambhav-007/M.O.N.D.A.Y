"""
M.O.N.D.A.Y. — Memory Agent & Persistent Knowledge Matrix
===========================================================
Executes persistent memory storage, recall, and topic clustering:
  • Persistent SQLite database (`data/memory.db`)
  • Store & recall user facts ("Remember X")
  • Semantic & TF-IDF recall across memories
  • Integrates Component 2.3 (Memory Clustering) for proactive suggestions
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from core.config import MEMORIES_DB_PATH
from core.security import log_action


class MemoryAgent:
    """Specialized worker for persistent user context, memory recall, and clustering."""

    def __init__(self) -> None:
        self.name = "MemoryAgent"
        self._init_db()

    def _init_db(self) -> None:
        """Initializes the SQLite relational memory store."""
        with sqlite3.connect(MEMORIES_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    topic TEXT DEFAULT 'general',
                    access_count INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def remember(self, key: str, value: str, topic: str = "general") -> Dict[str, Any]:
        """Stores a persistent key-value memory record in SQLite database."""
        key_clean = key.strip()
        val_clean = value.strip()
        topic_clean = topic.strip()

        with sqlite3.connect(MEMORIES_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM memories WHERE key = ?", (key_clean,))
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    "UPDATE memories SET value = ?, topic = ?, last_accessed = CURRENT_TIMESTAMP WHERE id = ?",
                    (val_clean, topic_clean, row[0]),
                )
                mem_id = row[0]
            else:
                cursor.execute(
                    "INSERT INTO memories (key, value, topic) VALUES (?, ?, ?)",
                    (key_clean, val_clean, topic_clean),
                )
                mem_id = cursor.lastrowid
            conn.commit()

        log_action("store_memory", key_clean, 1, "success", self.name, {"id": mem_id, "topic": topic_clean})
        return {
            "success": True,
            "id": mem_id,
            "key": key_clean,
            "value": val_clean,
            "topic": topic_clean,
            "message": f"✓ Memory saved: '{key_clean}' = '{val_clean}' (Topic: {topic_clean}).",
        }

    def store(self, key: str, value: str, topic: str = "general") -> Dict[str, Any]:
        """Alias for remember()."""
        return self.remember(key, value, topic)

    def recall(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """
        Retrieves matching memories using exact key lookup or TF-IDF vector similarity.
        """
        query_clean = query.strip()
        with sqlite3.connect(MEMORIES_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, key, value, topic FROM memories")
            rows = cursor.fetchall()

        if not rows:
            return {"success": True, "query": query_clean, "matches": [], "message": f"Found 0 matching memories for '{query_clean}'."}

        # Check for exact key match first
        exact_matches = [r for r in rows if r[1].lower() == query_clean.lower()]
        if exact_matches:
            matched_items = [{"id": r[0], "key": r[1], "value": r[2], "topic": r[3], "similarity": 1.0} for r in exact_matches]
            return {
                "success": True,
                "query": query_clean,
                "matches": matched_items,
                "message": f"✓ Recalled exact memory: '{matched_items[0]['key']}' = '{matched_items[0]['value']}'.",
            }

        # TF-IDF Vector Similarity Search across memories
        corpus = [f"{r[1]} {r[2]} {r[3]}" for r in rows]
        try:
            vectorizer = TfidfVectorizer(stop_words="english")
            tfidf_matrix = vectorizer.fit_transform(corpus + [query_clean])
            query_vec = tfidf_matrix[-1]
            corpus_vecs = tfidf_matrix[:-1]

            sims = cosine_similarity(query_vec, corpus_vecs)[0]
            top_indices = sims.argsort()[::-1][:limit]

            results = []
            for idx in top_indices:
                score = float(sims[idx])
                if score > 0.05 or query_clean.lower() in corpus[idx].lower():
                    r = rows[idx]
                    results.append({"id": r[0], "key": r[1], "value": r[2], "topic": r[3], "similarity": round(score, 4)})
        except Exception:
            results = [
                {"id": r[0], "key": r[1], "value": r[2], "topic": r[3], "similarity": 0.5}
                for r in rows if query_clean.lower() in f"{r[1]} {r[2]}".lower()
            ][:limit]

        msg = f"✓ Recalled {len(results)} memories matching '{query_clean}'." if results else f"Found 0 matching memories for '{query_clean}'."
        log_action("recall_memory", query_clean, 1, "success", self.name, {"match_count": len(results)})
        return {
            "success": True,
            "query": query_clean,
            "matches": results,
            "message": msg,
        }
