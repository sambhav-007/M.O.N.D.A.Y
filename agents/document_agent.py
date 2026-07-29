"""
M.O.N.D.A.Y. — Document Intelligence Agent (RAG & Summarisation)
=================================================================
Executes document processing and document-RAG tasks:
  • Reads PDF, TXT, Markdown, CSV, DOCX files
  • Summarizes documents & extracts key takeaways
  • Perform TF-IDF RAG search across ingested files
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pypdf
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from core.security import log_action


class DocumentAgent:
    """Specialized worker for document ingestion, RAG search, and summarization."""

    def __init__(self) -> None:
        self.name = "DocumentAgent"
        self._doc_cache: Dict[str, str] = {}

    def read_document_text(self, filepath: str | Path) -> Tuple[bool, str, str]:
        """
        Reads and extracts plain text from PDF, TXT, MD, CSV files.

        Returns
        -------
        (success, raw_text, error_message)
        """
        path = Path(filepath).resolve()
        if not path.exists():
            return False, "", f"File '{filepath}' not found."

        ext = path.suffix.lower()

        try:
            if ext == ".pdf":
                reader = pypdf.PdfReader(str(path))
                pages_text = []
                for idx, page in enumerate(reader.pages):
                    txt = page.extract_text() or ""
                    pages_text.append(f"--- Page {idx + 1} ---\n{txt}")
                full_text = "\n".join(pages_text)
                return True, full_text, ""

            elif ext in [".txt", ".md", ".csv", ".json", ".py", ".ts", ".js", ".log", ".html"]:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    return True, f.read(), ""
            else:
                # Try plain text fallback
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    return True, f.read()[:50000], ""

        except Exception as e:
            return False, "", f"Failed to extract text from {path.name}: {e}"

    def summarize_document(self, filepath_or_text: str, max_sentences: int = 5) -> Dict[str, Any]:
        """
        Extracts document text and generates an extractive summary
        using TF-IDF sentence scoring.
        """
        path = Path(filepath_or_text)
        doc_name = path.name if path.exists() else "text snippet"
        text = ""

        if path.exists():
            ok, text, err = self.read_document_text(path)
            if not ok:
                return {"success": False, "error": err}
        else:
            text = filepath_or_text

        if not text.strip():
            return {"success": False, "error": "Document text is empty."}

        # Sentence tokenisation
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if len(s.strip()) > 15]

        if not sentences:
            sentences = [text[:200]]

        if len(sentences) <= max_sentences:
            summary = "\n".join(f"• {s}" for s in sentences)
        else:
            # Score sentences using TF-IDF matrix
            try:
                vectorizer = TfidfVectorizer(stop_words="english")
                tfidf_matrix = vectorizer.fit_transform(sentences)
                scores = tfidf_matrix.sum(axis=1).A1

                top_indices = scores.argsort()[::-1][:max_sentences]
                top_indices.sort()  # Maintain original narrative order

                summary_sentences = [sentences[i] for i in top_indices]
                summary = "\n".join(f"• {s}" for s in summary_sentences)
            except Exception:
                summary = "\n".join(f"• {s}" for s in sentences[:max_sentences])

        word_count = len(text.split())
        log_action("summarize_document", doc_name, 1, "success", self.name, {
            "word_count": word_count, "summary_sentences": max_sentences
        })

        return {
            "success": True,
            "document": doc_name,
            "original_word_count": word_count,
            "sentences_analysed": len(sentences),
            "summary": summary,
            "message": f"✓ Summarised {doc_name} ({word_count} words → {max_sentences} key points).",
        }

    def rag_search(self, query: str, document_paths: List[str | Path]) -> Dict[str, Any]:
        """
        Ingests document paths and performs TF-IDF cosine similarity search
        to retrieve the top relevant chunks matching the query.
        """
        all_chunks: List[str] = []
        chunk_sources: List[Tuple[str, int]] = []

        for doc_path in document_paths:
            path = Path(doc_path)
            if not path.exists():
                continue
            ok, text, _ = self.read_document_text(path)
            if not ok or not text.strip():
                continue

            # Split into ~300 word chunks
            words = text.split()
            chunk_size = 300
            for i in range(0, len(words), chunk_size):
                chunk = " ".join(words[i : i + chunk_size])
                all_chunks.append(chunk)
                chunk_sources.append((path.name, i // chunk_size + 1))

        if not all_chunks:
            return {"success": False, "error": "No valid documents found for search."}

        # Vectorize query + chunks
        vectorizer = TfidfVectorizer(stop_words="english")
        tfidf_matrix = vectorizer.fit_transform(all_chunks + [query])

        query_vec = tfidf_matrix[-1]
        chunk_vecs = tfidf_matrix[:-1]

        similarities = cosine_similarity(query_vec, chunk_vecs)[0]
        top_indices = similarities.argsort()[::-1][:4]

        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score > 0.05:
                doc_name, chunk_num = chunk_sources[idx]
                results.append({
                    "document": doc_name,
                    "chunk": chunk_num,
                    "relevance_score": round(score, 4),
                    "excerpt": all_chunks[idx][:350] + "...",
                })

        log_action("rag_search", query, 1, "success", self.name, {"matches": len(results)})

        return {
            "success": True,
            "query": query,
            "total_documents_indexed": len(document_paths),
            "chunks_searched": len(all_chunks),
            "results": results,
            "message": f"✓ Found {len(results)} relevant passages across {len(document_paths)} documents.",
        }

    def compare_documents(self, filepath1: str | Path, filepath2: str | Path) -> Dict[str, Any]:
        """Generates a unified text/code diff comparison report between two files."""
        import difflib
        ok1, text1, err1 = self.read_document_text(filepath1)
        ok2, text2, err2 = self.read_document_text(filepath2)
        if not ok1 or not ok2:
            return {"success": False, "error": f"Failed to read input files: {err1 or err2}"}

        lines1 = text1.splitlines(keepends=True)
        lines2 = text2.splitlines(keepends=True)
        diff = list(difflib.unified_diff(lines1, lines2, fromfile=str(filepath1), tofile=str(filepath2)))
        diff_text = "".join(diff[:100]) or "No differences found (Files are identical)."

        log_action("compare_documents", f"{filepath1} vs {filepath2}", 1, "success", self.name)
        return {
            "success": True,
            "file1": str(filepath1),
            "file2": str(filepath2),
            "diff": diff_text,
            "diff_lines_count": len(diff),
            "diff_report": diff_text,
            "message": f"✓ Generated document diff report between '{Path(filepath1).name}' and '{Path(filepath2).name}' ({len(diff)} diff lines).",
        }

    def query_dataset(self, filepath: str | Path, query_filter: str = "", query_expr: str = "") -> Dict[str, Any]:
        """Queries local CSV/JSON datasets using pandas filtering and analytics."""
        import pandas as pd
        path = Path(filepath).resolve()
        if not path.exists():
            return {"success": False, "error": f"Dataset file '{filepath}' not found."}

        effective_query = query_expr or query_filter
        try:
            if path.suffix.lower() == ".csv":
                df = pd.read_csv(path)
            elif path.suffix.lower() == ".json":
                df = pd.read_json(path)
            else:
                return {"success": False, "error": "Unsupported dataset format. Use CSV or JSON."}

            if effective_query:
                filtered_df = df.query(effective_query) if hasattr(df, "query") else df
            else:
                filtered_df = df

            summary_str = f"Rows: {len(filtered_df)} | Columns: {list(filtered_df.columns)[:5]}"
            sample_records = filtered_df.head(5).to_dict(orient="records")

            return {
                "success": True,
                "dataset": path.name,
                "total_rows": len(df),
                "filtered_rows": len(filtered_df),
                "row_count": len(filtered_df),
                "summary": summary_str,
                "records_sample": sample_records,
                "message": f"✓ Queried dataset '{path.name}': {len(filtered_df)} matching records.",
            }
        except Exception as e:
            return {"success": False, "error": f"Dataset query failed: {e}"}

    def ask_document_question(
        self,
        filepath_or_question: str | Path = "",
        question_or_filepath: str | Path = "",
        document_paths: Optional[List[str | Path]] = None,
        question: str = "",
        filepath: str | Path = "",
    ) -> Dict[str, Any]:
        """Performs RAG search over document and uses cognitive engine to answer question with citations."""
        target_question = question
        target_path = filepath or (document_paths[0] if document_paths else "")

        if not target_question and filepath_or_question:
            arg1_str = str(filepath_or_question)
            if not target_path and (Path(arg1_str).exists() or any(arg1_str.endswith(ext) for ext in [".txt", ".pdf", ".md", ".csv"])):
                target_path = filepath_or_question
                target_question = str(question_or_filepath) if question_or_filepath else ""
            else:
                target_question = arg1_str
                if not target_path and question_or_filepath:
                    target_path = question_or_filepath

        if not target_path and document_paths:
            target_path = document_paths[0]

        if not target_path:
            return {"success": False, "error": "No valid document path provided for QA."}

        path_obj = Path(target_path)
        ok, full_text, err = self.read_document_text(path_obj)
        if not ok:
            return {"success": False, "error": f"Could not read document '{target_path}': {err}"}

        doc_list = document_paths if document_paths else [path_obj]
        rag_res = self.rag_search(target_question, document_paths=doc_list)
        passages = rag_res.get("results", [])

        passage_str = "\n".join([f"Passage {idx+1}: {p['excerpt']}" for idx, p in enumerate(passages[:3])])
        if not passage_str:
            passage_str = full_text[:1500]

        answer = None
        try:
            from core.planner import TriModelCognitiveEngine
            cog = TriModelCognitiveEngine()
            prompt = f"Based on the following document passages:\n{passage_str}\n\nAnswer this question: '{target_question}'"
            answer = cog.generate_cognitive_response(prompt)
        except Exception:
            pass

        if not answer:
            answer = f"Found relevant information in '{path_obj.name}':\n{passage_str[:400]}"

        log_action("ask_document_question", target_question, 1, "success", self.name)
        return {
            "success": True,
            "document": path_obj.name,
            "question": target_question,
            "answer": str(answer),
            "passages_consulted": len(passages),
            "message": f"✓ Document Q&A Answer:\n{answer}",
        }
