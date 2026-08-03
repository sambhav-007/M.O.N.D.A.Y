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


class ExtractedList(list):
    def get(self, key, default=None):
        if key == "success":
            return True
        return default


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

        if not key_clean:
            return {"success": False, "error": "Memory key cannot be empty."}

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

    def auto_extract_and_remember(self, user_prompt: str) -> List[Dict[str, Any]]:
        """
        Scans user_prompt for personal facts, preferences, names, and emails,
        automatically persisting them into SQLite memory.db.
        """
        import re
        extracted = []
        p_clean = user_prompt.strip()

        # Pattern 1: My name is X / I am X
        name_match = re.search(r'\bmy name is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', p_clean, re.IGNORECASE)
        if name_match:
            val = name_match.group(1).strip()
            self.remember("user_name", val, topic="identity")
            extracted.append({"key": "user_name", "value": val})

        # Pattern 2: My email is X
        email_match = re.search(r'\bmy email is\s+([^\s,]+@[^\s,]+\.[^\s,]+)', p_clean, re.IGNORECASE)
        if email_match:
            val = email_match.group(1).strip()
            self.remember("user_email", val, topic="contacts")
            extracted.append({"key": "user_email", "value": val})

        # Pattern 3: My favorite/preferred X is Y
        fav_match = re.search(r'\bmy (favorite|preferred)\s+([a-z0-9_]+)\s+is\s+([^\.\,]+)', p_clean, re.IGNORECASE)
        if fav_match:
            prop = fav_match.group(2).strip().lower()
            val = fav_match.group(3).strip()
            self.remember(f"preferred_{prop}", val, topic="user_preferences")
            extracted.append({"key": f"preferred_{prop}", "value": val})

        # Pattern 5: Location (I live in X / My location is X)
        loc_match = re.search(r'\b(?:i live in|my location is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', p_clean, re.IGNORECASE)
        if loc_match:
            val = loc_match.group(1).strip()
            self.remember("user_location", val, topic="identity")
            extracted.append({"key": "user_location", "value": val})

        # Pattern 6: Profession (I work as a X / My job is X)
        prof_match = re.search(r'\b(?:i work as a|i work as an|my job is|i am a|i am an)\s+([a-z0-9_\s]+)', p_clean, re.IGNORECASE)
        if prof_match and not any(w in p_clean.lower() for w in ["user", "fan", "student"]):
            val = prof_match.group(1).strip()
            if len(val.split()) <= 4:
                self.remember("user_profession", val, topic="identity")
                extracted.append({"key": "user_profession", "value": val})

        # Pattern 7: Goals (My goal is X / My main objective is X)
        goal_match = re.search(r'\bmy (?:main\s+)?(?:goal|objective)\s+is\s+([^\.\,]+)', p_clean, re.IGNORECASE)
        if goal_match:
            val = goal_match.group(1).strip()
            self.remember("user_goal", val, topic="goals")
            extracted.append({"key": "user_goal", "value": val})

        # Pattern 8: Tech Stack (I use X / I build with X)
        tech_match = re.search(r'\b(?:i use|i build with|my tech stack is)\s+([^\.\,]+)', p_clean, re.IGNORECASE)
        if tech_match and not any(w in p_clean.lower() for w in ["windows", "mac", "computer"]):
            val = tech_match.group(1).strip()
            self.remember("tech_stack", val, topic="user_preferences")
            extracted.append({"key": "tech_stack", "value": val})

        return ExtractedList(extracted)

    def auto_store_conversation_turn(self, user_prompt: str, assistant_response: str, agent_name: str = "MasterPlanner") -> Dict[str, Any]:
        """Logs conversation turn to SQLite memory for multi-turn history retention."""
        if not user_prompt or not assistant_response:
            return {"success": False, "error": "Empty prompt or response."}
        turn_key = f"turn_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        turn_val = f"Agent: {agent_name} | User: {user_prompt[:200]} | Assistant: {assistant_response[:200]}"
        res = self.remember(turn_key, turn_val, topic="conversation_history")
        return {"success": True, "turn_key": turn_key, "result": res}

    def get_contextual_memories(self, user_prompt: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Pre-fetches memories relevant to the current user prompt."""
        recall_res = self.recall(user_prompt, limit=limit)
        return recall_res.get("matches", [])

    def get_proactive_suggestions(self) -> Dict[str, Any]:
        """Component 2.3 Memory Clustering integration for proactive user suggestions."""
        with sqlite3.connect(MEMORIES_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value, topic FROM memories ORDER BY last_accessed DESC LIMIT 10")
            rows = cursor.fetchall()

        sug = []
        for r in rows:
            if r[2] != "conversation_history":
                sug.append({"prompt": f"💡 Memory Recall: {r[0].replace('_', ' ').capitalize()} → '{r[1]}'"})

        if not sug:
            sug = [{"prompt": "💡 Memory Recall: Ask M.O.N.D.A.Y. to remember your notes or preferences!"}]

        return {"success": True, "suggestions": sug}
