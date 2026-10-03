import io
import os
import re
import time
import warnings
from typing import List, Dict, Any, Optional

# Suppress library deprecation and version warnings
warnings.filterwarnings("ignore")

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    import pymupdf as fitz  # type: ignore
except (ImportError, Exception):
    try:
        import fitz  # type: ignore
    except (ImportError, Exception):
        fitz = None

try:
    import pypdf  # type: ignore
except (ImportError, Exception):
    pypdf = None

try:
    import docx  # type: ignore
except (ImportError, Exception):
    docx = None

try:
    import google.generativeai as genai  # type: ignore
except (ImportError, Exception):
    genai = None


STOP_WORDS = {
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "can", "could", "will", "would", "should", "what",
    "which", "who", "whom", "this", "that", "these", "those", "how", "give",
    "me", "tell", "show", "command", "commands", "please", "check", "run", "use",
    "about", "into", "through", "during", "before", "after", "above", "below"
}


class RAGEngine:
    def __init__(self):
        # In-memory document storage: doc_name -> {chunks, vectorizer, matrix, total_pages, items}
        self.documents: Dict[str, Dict[str, Any]] = {}
        self.gemini_model = None
        self._init_llm()

    def _init_llm(self, api_key: Optional[str] = None):
        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if key and genai:
            try:
                genai.configure(api_key=key)
                for model_name in ["gemini-1.5-flash", "gemini-2.5-flash", "gemini-pro"]:
                    try:
                        self.gemini_model = genai.GenerativeModel(model_name)
                        print(f"[RAG] Active Gemini model: {model_name}")
                        break
                    except Exception:
                        continue
            except Exception as e:
                print(f"[RAG] Warning: Could not initialize Gemini API: {e}")
                self.gemini_model = None
        else:
            self.gemini_model = None

    def clean_text(self, text: str) -> str:
        """Removes header/footer artifacts and normalizes spacing."""
        text = re.sub(r'Page\s*\|\s*\d+', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Page\s+\d+\s+of\s+\d+', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+(git\s+[\w\-\:]+)', r'\n\1', text)
        return text

    def extract_text_from_file(self, filename: str, file_bytes: bytes) -> List[Dict[str, Any]]:
        """Parses document bytes into a list of page dicts."""
        ext = os.path.splitext(filename)[1].lower()
        pages = []

        if ext == ".pdf":
            if fitz:
                try:
                    doc = fitz.open(stream=file_bytes, filetype="pdf")
                    for page_idx, page in enumerate(doc):
                        text = page.get_text()
                        if text and text.strip():
                            cleaned = self.clean_text(text.strip())
                            if cleaned:
                                pages.append({"page": page_idx + 1, "text": cleaned})
                except Exception as err:
                    print(f"[RAG] PyMuPDF failed: {err}")

            if not pages and pypdf:
                try:
                    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                    for idx, page in enumerate(reader.pages):
                        text = page.extract_text()
                        if text and text.strip():
                            cleaned = self.clean_text(text.strip())
                            if cleaned:
                                pages.append({"page": idx + 1, "text": cleaned})
                except Exception as err:
                    print(f"[RAG] pypdf error: {err}")

        elif ext in [".docx", ".doc"]:
            if docx:
                try:
                    doc = docx.Document(io.BytesIO(file_bytes))
                    full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
                    if full_text.strip():
                        cleaned = self.clean_text(full_text.strip())
                        chars_per_page = 2500
                        for idx, start in enumerate(range(0, len(cleaned), chars_per_page)):
                            pages.append({
                                "page": idx + 1,
                                "text": cleaned[start:start + chars_per_page].strip()
                            })
                except Exception as err:
                    print(f"[RAG] python-docx error: {err}")

        # Plain text, CSV, Markdown fallback
        if not pages:
            try:
                text_content = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                text_content = file_bytes.decode("latin-1", errors="ignore")

            cleaned = self.clean_text(text_content.strip())
            chars_per_page = 2000
            for idx, start in enumerate(range(0, len(cleaned), chars_per_page)):
                pages.append({
                    "page": idx + 1,
                    "text": cleaned[start:start + chars_per_page].strip()
                })

        return pages

    def extract_atomic_items(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extracts atomic command entries or key sentences with page numbers:
        e.g. 'git push: Pushes committed changes...' -> {command, description, page, raw}
        """
        items = []
        for p in pages:
            lines = [l.strip() for l in p["text"].splitlines() if l.strip()]
            for line in lines:
                match = re.match(r'^(git\s+[^:\n]+):\s*(.+)$', line, re.IGNORECASE)
                if match:
                    cmd = match.group(1).strip()
                    desc = match.group(2).strip()
                    items.append({
                        "type": "command",
                        "command": cmd,
                        "description": desc,
                        "page": p["page"],
                        "raw": line
                    })
                elif len(line) > 15:
                    items.append({
                        "type": "sentence",
                        "command": "",
                        "description": line,
                        "page": p["page"],
                        "raw": line
                    })
        return items

    def chunk_document(self, filename: str, pages: List[Dict[str, Any]], chunk_size: int = 600, overlap: int = 100) -> List[Dict[str, Any]]:
        """Chunks pages into overlapping text fragments."""
        chunks = []
        chunk_id = 0

        for page_data in pages:
            page_num = page_data["page"]
            text = page_data["text"]

            paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
            current_chunk = ""

            for p in paragraphs:
                if len(current_chunk) + len(p) <= chunk_size:
                    current_chunk += ("\n" if current_chunk else "") + p
                else:
                    if current_chunk.strip():
                        chunks.append({
                            "chunk_id": chunk_id,
                            "doc_name": filename,
                            "page": page_num,
                            "text": current_chunk.strip()
                        })
                        chunk_id += 1
                    overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else ""
                    current_chunk = overlap_text + ("\n" if overlap_text else "") + p

            if current_chunk.strip():
                chunks.append({
                    "chunk_id": chunk_id,
                    "doc_name": filename,
                    "page": page_num,
                    "text": current_chunk.strip()
                })
                chunk_id += 1

        return chunks

    def index_document(self, filename: str, file_bytes: bytes) -> Dict[str, Any]:
        """Indexes document pages, chunks, and structured items."""
        pages = self.extract_text_from_file(filename, file_bytes)
        if not pages:
            raise ValueError(f"Could not extract readable text from '{filename}'.")

        chunks = self.chunk_document(filename, pages)
        items = self.extract_atomic_items(pages)

        # Build TF-IDF vector matrix
        corpus = [c["text"] for c in chunks]
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", max_features=12000)
        matrix = vectorizer.fit_transform(corpus)

        # Store all text in lowercase for fast containment checking
        full_text_lower = " ".join([p["text"].lower() for p in pages])

        self.documents[filename] = {
            "chunks": chunks,
            "items": items,
            "vectorizer": vectorizer,
            "matrix": matrix,
            "full_text_lower": full_text_lower,
            "total_pages": len(pages),
            "total_chunks": len(chunks),
            "indexed_at": time.time()
        }

        print(f"[RAG] Indexed '{filename}': {len(pages)} pages, {len(chunks)} chunks, {len(items)} structured items.")
        return {
            "status": "success",
            "document_name": filename,
            "total_pages": len(pages),
            "total_chunks": len(chunks)
        }

    def retrieve(self, query: str, doc_name: str, top_k: int = 4) -> List[Dict[str, Any]]:
        """Retrieves top-K most relevant chunks using vector similarity."""
        if doc_name not in self.documents:
            if self.documents:
                doc_name = next(iter(self.documents))
            else:
                return []

        doc_info = self.documents[doc_name]
        vectorizer = doc_info["vectorizer"]
        matrix = doc_info["matrix"]
        chunks = doc_info["chunks"]

        query_vec = vectorizer.transform([query])
        similarities = cosine_similarity(query_vec, matrix).flatten()

        max_sim = float(np.max(similarities)) if len(similarities) > 0 else 0.0
        # If maximum similarity is negligible, query is out-of-domain
        if max_sim < 0.05:
            return []

        top_indices = [i for i in np.argsort(similarities)[::-1] if similarities[i] > 0.03][:top_k]
        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            chunk = chunks[idx]
            results.append({
                "page": chunk["page"],
                "text": chunk["text"],
                "score": score
            })

        return results

    def extract_query_keywords(self, query: str) -> List[str]:
        """Extracts core action/subject keywords from query."""
        tokens = re.findall(r'[a-zA-Z0-9_\-]+', query.lower())
        return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]

    def synthesize_structured_answer(self, query: str, doc_name: str, retrieved: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Creates clean, readable, formatted Markdown answers with code blocks,
        bullet points, and relevant variants instead of raw wall-of-text.
        """
        doc_info = self.documents.get(doc_name)
        items = doc_info.get("items", []) if doc_info else []
        keywords = self.extract_query_keywords(query)

        # 1. Search for atomic command matches
        matched_commands = []
        related_commands = []
        other_matches = []

        if items:
            for item in items:
                raw_lower = item["raw"].lower()
                cmd_lower = item.get("command", "").lower()

                # Calculate match score based on keyword overlap
                match_count = sum(1 for kw in keywords if kw in raw_lower)
                cmd_exact_match = any(kw in cmd_lower for kw in keywords)

                if match_count > 0:
                    score = match_count * 2 + (3 if cmd_exact_match else 0)
                    if item["type"] == "command":
                        words_in_cmd = len(cmd_lower.split())
                        if words_in_cmd <= 2 and cmd_exact_match:
                            matched_commands.append((score + 5, item))
                        else:
                            related_commands.append((score, item))
                    else:
                        other_matches.append((score, item))

        # Sort matches by relevance score
        matched_commands.sort(key=lambda x: x[0], reverse=True)
        related_commands.sort(key=lambda x: x[0], reverse=True)
        other_matches.sort(key=lambda x: x[0], reverse=True)

        sources = []
        seen_pages = set()

        # CASE A: If we found specific command matches (e.g., git commands)
        if matched_commands or related_commands:
            primary = matched_commands[0][1] if matched_commands else related_commands[0][1]
            primary_cmd = primary["command"]
            primary_desc = primary["description"]
            primary_page = primary["page"]

            seen_pages.add(primary_page)
            sources.append({"page": primary_page, "snippet": f"{primary_cmd}: {primary_desc}"})

            # Start building readable output
            ans = f"### Command: `{primary_cmd}`\n\n"
            ans += f"```bash\n{primary_cmd}\n```\n\n"
            ans += f"**Description:**\n{primary_desc}\n\n"

            # Add related variations / options that share the root command keyword
            root_cmd_word = primary_cmd.split()[1].lower() if len(primary_cmd.split()) > 1 else primary_cmd.lower()
            other_options = [
                x[1] for x in matched_commands[1:] + related_commands
                if x[1]["command"].lower() != primary_cmd.lower() and (root_cmd_word in x[1]["command"].lower() or any(kw in x[1]["command"].lower() for kw in keywords))
            ]
            # Deduplicate by command name
            unique_options = []
            seen_cmds = {primary_cmd.lower()}
            for opt in other_options:
                if opt["command"].lower() not in seen_cmds:
                    seen_cmds.add(opt["command"].lower())
                    unique_options.append(opt)

            if unique_options:
                ans += "---\n\n#### Options & Variations:\n"
                for opt in unique_options[:4]:
                    ans += f"- `{opt['command']}`: {opt['description']}\n"
                    if opt["page"] not in seen_pages:
                        seen_pages.add(opt["page"])
                        sources.append({"page": opt["page"], "snippet": f"{opt['command']}: {opt['description']}"})
                ans += "\n"

            pages_str = ", ".join([f"Page {p}" for p in sorted(seen_pages)])
            ans += f"*Source: {doc_name} ({pages_str})*"
            return {"answer": ans, "sources": sources}

        # CASE B: General Q&A / Conceptual / Explanatory questions
        # Look for sentences that actually match the keywords
        found_any_relevant = False
        ans = f"### Answer from **{doc_name}**\n\n"
        top_chunks = retrieved[:2]

        for idx, chunk in enumerate(top_chunks):
            page_num = chunk["page"]
            text = chunk["text"]

            sentences = [s.strip() for s in re.split(r'(?<=[.?!])\s+', text) if len(s.strip()) > 20]
            relevant_sentences = [
                s for s in sentences
                if any(kw in s.lower() for kw in keywords)
            ]

            if relevant_sentences:
                found_any_relevant = True
                ans += f"**Key Points (Page {page_num}):**\n"
                for s in relevant_sentences[:3]:
                    ans += f"- {s}\n"
                ans += "\n"
                sources.append({"page": page_num, "snippet": text[:150] + "..." if len(text) > 150 else text})

        if not found_any_relevant:
            # STRICT GUARD: Don't guess or dump random sentences when query isn't in document
            return {
                "answer": f"I could not find any information regarding this in **{doc_name}**. This question appears to be outside the contents of the document.",
                "sources": []
            }

        return {"answer": ans, "sources": sources}

    def generate_answer(self, query: str, doc_name: str, history: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Retrieves relevant context and generates a grounded, readable response."""
        doc_info = self.documents.get(doc_name)
        if not doc_info:
            return {
                "answer": f"Document '{doc_name}' is not currently loaded or indexed. Please upload your document to start asking questions.",
                "sources": []
            }

        # -------------------------------------------------------------
        # STRICT OUT-OF-DOCUMENT GUARDRAILS
        # -------------------------------------------------------------
        keywords = self.extract_query_keywords(query)
        full_text_lower = doc_info.get("full_text_lower", "")

        # If user asked a specific question and none of the keywords appear in the document:
        if keywords:
            keyword_found = any(kw in full_text_lower for kw in keywords)
            if not keyword_found:
                return {
                    "answer": f"I could not find any information regarding this in **{doc_name}**. The document does not contain information about *'{query}'*.",
                    "sources": []
                }

        retrieved = self.retrieve(query, doc_name, top_k=4)
        if not retrieved:
            return {
                "answer": f"I could not find any information regarding this in **{doc_name}**. This question appears to be outside the contents of the document.",
                "sources": []
            }

        # 1. If Gemini API is configured, use LLM with strict grounding instructions
        if self.gemini_model:
            try:
                context_str = "\n\n".join([f"[Page {item['page']}]: {item['text']}" for item in retrieved])
                system_prompt = (
                    "You are a strict and helpful Document Assistant. "
                    "You must answer the user's question using ONLY the provided document excerpts below.\n\n"
                    "CRITICAL RULES:\n"
                    "- If the answer is NOT explicitly present in the document excerpts, you MUST reply: "
                    f"'I could not find any information regarding this in {doc_name}. The document does not cover this topic.'\n"
                    "- Do NOT use external knowledge. Do NOT answer questions about unrelated people, general knowledge, or topics outside the document.\n"
                    "- If a command or code is requested, present it in a bash code block followed by a concise description.\n"
                    "- Cite the page number(s) at the end.\n\n"
                    f"--- DOCUMENT EXCERPTS FROM {doc_name} ---\n{context_str}\n\n"
                    f"--- USER QUESTION ---\n{query}"
                )
                response = self.gemini_model.generate_content(system_prompt)
                sources = [{"page": item["page"], "snippet": item["text"][:140] + "..."} for item in retrieved]
                return {"answer": response.text, "sources": sources}
            except Exception as e:
                print(f"[RAG] Gemini generation failed: {e}. Using high-precision structured synthesizer.")

        # 2. Intelligent, High-Precision Structured Synthesizer (Works 100% offline & clean)
        return self.synthesize_structured_answer(query, doc_name, retrieved)
