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
from core.contracts import AgentResult, RecordStored, SystemQuery
from core.security import log_action


class ExtractedList(list):
    def get(self, key, default=None):
        if key == "success":
            return True
        return default


#: Key prefixes written by the machine, not by the user.
#:
#: `auto_store_conversation_turn` writes one row per exchange, keyed `turn_…`,
#: whose value is the whole turn serialised — `"Agent: MasterPlanner | User: … |
#: Assistant: …"`. `recall` is a TF-IDF *similarity* search, so those rows come
#: back for almost any query, and anything that reads `matches[0]["value"]` as a
#: fact is reading a transcript.
#:
#: That produced two separate incidents. A WhatsApp message was addressed to a
#: number lifted from an unrelated saved turn (handoff.md §9.2). And "what's my
#: name" answered `"Your name is Agent: MasterPlanner | User: is my name |
#: Assistant: Hello! I am M.O.N.D.A.Y. …"` — then stored *that* as the next turn,
#: so each retelling nested the previous one and the answer grew without bound.
#:
#: Both callers now filter on this one tuple rather than each keeping their own
#: copy of the prefix list.
MACHINE_WRITTEN_KEY_PREFIXES = ("turn_", "conversation", "session_", "log_")


def is_machine_written(key: str) -> bool:
    """Whether a memory row was written by the assistant rather than the user."""
    return str(key or "").strip().lower().startswith(MACHINE_WRITTEN_KEY_PREFIXES)


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
            # ── Contacts are their own table, and that is the whole point ────
            # A contact used to be a `memories` row like "papa's number" =
            # "+91…", found by `recall`, which is a TF-IDF *similarity* search
            # over every row in the store. Similarity does not distinguish a
            # contact record from a saved conversation transcript that happens
            # to mention the same person, and once it did not: a WhatsApp
            # message was addressed to a phone number lifted from an unrelated
            # turn (handoff.md §9.2).
            #
            # Four validation guards were added afterwards and they work, but
            # they are a filter bolted onto the wrong data model. A lookup that
            # reads *this* table cannot return a transcript, because transcripts
            # are not in it. That is a structural answer rather than a careful
            # one, and structural answers do not have to be remembered by the
            # next person to touch the code.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    phone TEXT,
                    email TEXT,
                    source TEXT DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    # ── Contacts ─────────────────────────────────────────────────────────────
    def save_contact(
        self, name: str, phone: str = "", email: str = "", source: str = "user"
    ) -> Dict[str, Any]:
        """Stores a contact by name. Blank fields leave the stored value alone.

        Upserts on name, case-insensitively, so teaching a number twice updates
        rather than duplicating — and so a later email does not erase a phone
        number taught earlier.
        """
        name_clean = (name or "").strip()
        if not name_clean:
            return AgentResult.failed(
                "A contact needs a name.", error="NO_CONTACT_NAME"
            ).as_dict()
        if not (phone or "").strip() and not (email or "").strip():
            return AgentResult.failed(
                f"Nothing to save for {name_clean} — give me a number or an address.",
                error="NO_CONTACT_DETAILS",
            ).as_dict()

        with sqlite3.connect(MEMORIES_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, phone, email FROM contacts WHERE name = ? COLLATE NOCASE",
                (name_clean,),
            )
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    "UPDATE contacts SET phone = ?, email = ?, source = ?, "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    ((phone or "").strip() or row[1],
                     (email or "").strip() or row[2],
                     source, row[0]),
                )
                contact_id = row[0]
            else:
                cursor.execute(
                    "INSERT INTO contacts (name, phone, email, source) VALUES (?, ?, ?, ?)",
                    (name_clean, (phone or "").strip() or None,
                     (email or "").strip() or None, source),
                )
                contact_id = cursor.lastrowid
            conn.commit()

        log_action("save_contact", name_clean, 1, "success", self.name, {"id": contact_id})
        return AgentResult.ok(
            f"✓ Saved {name_clean}.",
            evidence=RecordStored(store="memories.db:contacts", key=name_clean),
            data={"id": contact_id, "name": name_clean,
                  "phone": (phone or "").strip(), "email": (email or "").strip()},
        ).as_dict()

    def get_contact(self, name: str) -> Optional[Dict[str, Any]]:
        """Exact, case-insensitive lookup. None when there is no such contact.

        **Exact on purpose.** The failure this table exists to prevent came from
        a *similar* match, so there is no fuzzy fallback here and there should
        never be one. Not knowing a number is a recoverable state — MONDAY asks
        for it and saves it. Confidently using the wrong one is not.
        """
        key = (name or "").strip()
        if not key:
            return None
        with sqlite3.connect(MEMORIES_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT name, phone, email, source FROM contacts "
                "WHERE name = ? COLLATE NOCASE",
                (key,),
            ).fetchone()
        return dict(row) if row else None

    def list_contacts(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(MEMORIES_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT name, phone, email, source FROM contacts ORDER BY name"
            ).fetchall()
        return [dict(r) for r in rows]

    def remember(self, key: str, value: str, topic: str = "general") -> Dict[str, Any]:
        """Stores a persistent key-value memory record in SQLite database."""
        key_clean = key.strip()
        val_clean = value.strip()
        topic_clean = topic.strip()

        if not key_clean:
            return AgentResult.failed(
                "Memory key cannot be empty.", error="EMPTY_KEY"
            ).as_dict()

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
        return AgentResult.ok(
            f"✓ Memory saved: '{key_clean}' = '{val_clean}' (Topic: {topic_clean}).",
            evidence=RecordStored(store="memories.db", key=key_clean),
            data={
                "id": mem_id,
                "key": key_clean,
                "value": val_clean,
                "topic": topic_clean,
            },
        ).as_dict()

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
            return AgentResult.ok(
                f"Found 0 matching memories for '{query_clean}'.",
                evidence=SystemQuery(source="memories.db", detail="0 rows stored"),
                data={"query": query_clean, "matches": []},
            ).as_dict()

        # Check for exact key match first
        exact_matches = [r for r in rows if r[1].lower() == query_clean.lower()]
        if exact_matches:
            matched_items = [
                {"id": r[0], "key": r[1], "value": r[2], "topic": r[3],
                 "similarity": 1.0, "match_method": "exact_key"}
                for r in exact_matches
            ]
            return AgentResult.ok(
                f"✓ Recalled exact memory: '{matched_items[0]['key']}' = '{matched_items[0]['value']}'.",
                evidence=SystemQuery(
                    source="memories.db", detail=f"exact key match on '{query_clean}'"
                ),
                data={"query": query_clean, "matches": matched_items},
            ).as_dict()

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
                    results.append({
                        "id": r[0], "key": r[1], "value": r[2], "topic": r[3],
                        "similarity": round(score, 4), "match_method": "tfidf",
                    })
            method = "tfidf"
        except Exception:
            # `similarity: 0.5` here was not a similarity — the vectoriser had
            # failed, nothing was scored, and 0.5 was a constant attached to every
            # substring hit. Callers that rank or threshold on this field were
            # ranking on a placeholder. The number is kept so those callers keep
            # working, but `match_method` now says where it came from.
            results = [
                {"id": r[0], "key": r[1], "value": r[2], "topic": r[3],
                 "similarity": 0.5, "match_method": "substring_fallback"}
                for r in rows if query_clean.lower() in f"{r[1]} {r[2]}".lower()
            ][:limit]
            method = "substring_fallback"

        msg = f"✓ Recalled {len(results)} memories matching '{query_clean}'." if results else f"Found 0 matching memories for '{query_clean}'."
        log_action("recall_memory", query_clean, 1, "success", self.name, {"match_count": len(results)})
        return AgentResult.ok(
            msg,
            evidence=SystemQuery(
                source="memories.db",
                detail=f"{len(rows)} rows searched by {method}, {len(results)} matched",
            ),
            data={"query": query_clean, "matches": results},
        ).as_dict()

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
            return AgentResult.failed(
                "Empty prompt or response.", error="EMPTY_TURN"
            ).as_dict()
        turn_key = f"turn_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        turn_val = f"Agent: {agent_name} | User: {user_prompt[:200]} | Assistant: {assistant_response[:200]}"
        res = self.remember(turn_key, turn_val, topic="conversation_history")
        # Reported success unconditionally, even when the write it delegates to
        # had failed. It now carries the store's own verdict.
        if not res.get("success"):
            return res
        return AgentResult.ok(
            f"✓ Conversation turn logged as '{turn_key}'.",
            evidence=RecordStored(store="memories.db", key=turn_key),
            data={"turn_key": turn_key, "result": res},
        ).as_dict()

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

        return AgentResult.ok(
            f"✓ {len(sug)} proactive suggestion(s) from stored memories.",
            evidence=SystemQuery(source="memories.db", detail=f"{len(rows)} recent rows"),
            data={"suggestions": sug},
        ).as_dict()
