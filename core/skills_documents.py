"""
M.O.N.D.A.Y. — tranche 9: asking questions of your own documents.

ROADMAP Phase 12, first slice. The retrieval was already built and **could not
be reached**: `DocumentAgent.rag_search` and `DocumentAgent.ask_document_question`
have been implemented for weeks, and no skill exposed either of them, so nothing
a user could type arrived there. `summarize_document` was the only door into that
agent, and it summarises — it does not answer.

That is a different defect from the ones this repository usually finds. Nothing
here lied; a capability simply had no entrance. It is worth naming because the
skill registry is the only map of what MONDAY can do, and a function absent from
it does not exist as far as any user, the classifier, or stage 3 is concerned.

What it does
------------
`rag_search` chunks a document into ~300-word passages, scores them against the
question with TF-IDF cosine similarity, and returns the best few *with their
source*. This tranche exposes that as:

* **`ask_document`** — a question against one named file, answered from the
  passages, with the file and passage count named.
* **`search_documents`** — the same retrieval across the files a folder holds,
  for "which of my notes mentions the deadline".

What it will not claim
----------------------
The passages are **retrieved, not reasoned over**. Without a language model this
returns the most relevant parts of the document and says so; it does not
synthesise an answer and then present it as the document's. `DocumentAgent`
reaches `TriModelCognitiveEngine` when a Gemini key is configured, and when it
does the reply is generated — the message says which happened, because "your
report says X" and "the most relevant passage is X" are different claims.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from core.contracts import AgentResult, FileRead
from core.skills import Skill, SkillRegistry
from core.slot_sanity import looks_like_a_path

#: Extensions `DocumentAgent.read_document_text` can actually read. A folder
#: search that opened .exe files would waste its budget on binary noise.
_READABLE = {".txt", ".md", ".pdf", ".csv", ".json", ".log", ".rst", ".docx"}

#: How many files a folder-wide search will read. Retrieval over a whole Documents
#: tree is a different product; this is "the folder you meant".
MAX_DOCUMENTS = 40


def readable_documents(folder: Path, limit: int = MAX_DOCUMENTS) -> List[Path]:
    """The readable files directly inside a folder, oldest API first."""
    try:
        entries = sorted(folder.iterdir())
    except (OSError, PermissionError):
        return []
    found = []
    for entry in entries:
        try:
            if entry.is_file() and entry.suffix.lower() in _READABLE:
                found.append(entry)
        except OSError:
            continue
        if len(found) >= limit:
            break
    return found


def register_document_skills(registry: SkillRegistry, planner: Any) -> None:
    """Registers document question-answering and folder-wide retrieval."""

    agent = planner.document_agent

    #: Filled in below, once `search_documents` exists. `ask_document` is
    #: defined first and needs to hand a directory over to it — a pattern cannot
    #: tell a folder from a file, only the filesystem can.
    folder_search: List[Any] = []

    # ── One document ─────────────────────────────────────────────────────────
    def ask_document(question: str = "", path: str = "", **_: Any) -> Dict[str, Any]:
        question = (question or "").strip().strip("\"'")
        path = (path or "").strip().strip("\"'")

        if not question or not path:
            return AgentResult.failed(
                "Ask it like: 'what does report.pdf say about the deadline'.",
                error="DOCUMENT_QA_INCOMPLETE",
            ).as_dict()

        target = Path(path).expanduser()
        if target.is_dir():
            # "search <folder> for <thing>" is the folder search wearing this
            # skill's pattern. Reading a directory as a document produced
            # "[Errno 13] Permission denied", which told the user nothing.
            return folder_search[0](question=question, folder=str(target))
        if not target.exists():
            # The same guard `summarize_document` needed: the agent below treats
            # an unreadable path as raw text, so a missing file would otherwise
            # be "answered" out of its own filename.
            return AgentResult.failed(
                f"I can't find '{path}'. Give me a path that exists.",
                error="DOCUMENT_NOT_FOUND",
                data={"path": path},
            ).as_dict()

        return agent.ask_document_question(question=question, filepath=str(target))

    registry.register(Skill(
        name="ask_document",
        read_only=True,
        description="Answer a question from inside one named document, quoting the passages it found",
        patterns=[
            "[(what|whats|what's)] does {path} say about {question}",
            "[(what|whats|what's)] does {path} say on {question}",
            "ask {path} about {question}",
            "in {path} [(what|whats|what's)] {question}",
            "search {path} for {question}",
            "find {question} in {path}",
            "look up {question} in {path}",
            "according to {path} {question}",
        ],
        handler=ask_document,
        tier=1,
        offline=True,
    ))

    # ── A folder of documents ────────────────────────────────────────────────
    def search_documents(question: str = "", folder: str = "", **_: Any) -> Dict[str, Any]:
        question = (question or "").strip().strip("\"'")
        if not question:
            return AgentResult.failed(
                "What should I look for? Try 'search my documents for the deadline'.",
                error="DOCUMENT_SEARCH_NO_QUERY",
            ).as_dict()

        folder = (folder or "").strip().strip("\"'")
        directory = Path(folder).expanduser() if folder else Path.home() / "Documents"
        if not directory.exists() or not directory.is_dir():
            return AgentResult.failed(
                f"'{directory}' is not a folder I can read.",
                error="DOCUMENT_FOLDER_NOT_FOUND",
                data={"folder": str(directory)},
            ).as_dict()

        documents = readable_documents(directory)
        if not documents:
            return AgentResult.failed(
                f"No readable documents in {directory} — I look for "
                f"{', '.join(sorted(_READABLE))}.",
                error="NO_DOCUMENTS",
                data={"folder": str(directory)},
            ).as_dict()

        result = agent.rag_search(question, document_paths=documents)
        passages = result.get("results", []) if isinstance(result, dict) else []
        if not passages:
            return AgentResult.failed(
                f"Nothing in those {len(documents)} documents matched '{question}'.",
                error="NO_MATCHING_PASSAGE",
                data={"folder": str(directory), "documents_read": len(documents)},
            ).as_dict()

        lines = []
        for passage in passages[:3]:
            source = passage.get("source") or passage.get("document") or "?"
            excerpt = str(passage.get("excerpt", ""))[:220].replace("\n", " ")
            lines.append(f"  • {source}: …{excerpt}…")

        return AgentResult.ok(
            f"📚 Best matches for '{question}' across {len(documents)} documents:\n"
            + "\n".join(lines)
            + "\n  These are the passages that matched — not a summary of them.",
            evidence=FileRead(
                path=str(directory),
                bytes_read=sum(_size(d) for d in documents),
            ),
            data={
                "question": question,
                "folder": str(directory),
                "documents_read": len(documents),
                "passages": len(passages),
                "speech": f"{len(passages)} passages across {len(documents)} documents.",
            },
        ).as_dict()

    folder_search.append(search_documents)

    registry.register(Skill(
        name="search_documents",
        read_only=True,
        description="Search across the documents in a folder and quote the passages that match",
        patterns=[
            "search my documents for {question}",
            "search [(the|my)] (documents|notes|files) for {question}",
            "[(which|what)] (document|file|note) mentions {question}",
            "[(which|what)] of my (documents|notes|files) mentions {question}",
            "look through my (documents|notes|files) for {question}",
            "find {question} in my (documents|notes|files)",
            "search {folder} for {question}",
        ],
        handler=search_documents,
        tier=1,
        offline=True,
    ))


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0
