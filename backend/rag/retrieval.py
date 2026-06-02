"""
BM25 retrieval over the Oil Macro Trading curriculum.

Pure-Python BM25 (Okapi formulation) — no external deps beyond stdlib.
Loaded once at import time; chunks are detected by chapter headers in the
extracted curriculum text. Each chunk preserves its chapter title so the
chat answer can cite the source ("Chapter 8 · Market Pricing — page on
M1-M2 spreads").

Public API:
  build_index() -> index dict (called automatically on import)
  search(query: str, k: int = 5) -> list[Chunk]
"""

from __future__ import annotations

import logging
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("pulse.rag.retrieval")

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
_BOOK_PATH   = os.path.join(_BACKEND, "data", "curriculum.txt")
_EXPERT_PATH = os.path.join(_BACKEND, "data", "expert_knowledge.md")

# ── BM25 parameters (Okapi defaults) ────────────────────────────────────────
_K1 = 1.5
_B  = 0.75

# Lightweight stopwords — keep meaningful trading vocabulary intact.
_STOP = set("""
a an and as at be but by for from has have he her his i if in is it its of on
or so that the their them they this to was we were will with you your he's it's
""".split())


def _tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumeric, drop stopwords + short noise."""
    toks = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9\-]+", text.lower())
    return [t for t in toks if t not in _STOP and len(t) > 1]


# Characters used in the curriculum's ASCII box-drawing diagrams that look
# garbled when quoted back in chat. Strip them at chunk-build time.
_BOX_CHARS = "─━│┃┄┅┆┇┈┉┊┋┌┍┎┏┐┑┒┓└┕┖┗┘┙┚┛├┝┞┟┠┡┢┣┤┥┦┧┨┩┪┫┬┭┮┯┰┱┲┳┴┵┶┷┸┹┺┻┼┽┾┿╀╁╂╃╄╅╆╇╈╉╊╋╌╍╎╏═║╒╓╔╕╖╗╘╙╚╛╜╝╞╟╠╡╢╣╤╥╦╧╨╩╪╫╬█▀▁▂▃▄▅▆▇▉▊▋▌▍▎▏▐░▒▓▔▕▖▗▘▙▚▛▜▝▞▟◆◇◈◉◊○●◐◑◒◓◔◕◖◗◘◙◚◛◜◝◞◟◠◡◢◣◤◥◦◧◨◩◪◫◬◭◮◯→←↑↓↔↕▶◀▲▼"
_BOX_RE = re.compile(f"[{re.escape(_BOX_CHARS)}]")

def _clean(text: str) -> str:
    """Strip ASCII box-drawing characters that look garbled when echoed back."""
    return _BOX_RE.sub(" ", text)


# ── Chunking ────────────────────────────────────────────────────────────────

@dataclass
class Chunk:
    id: int
    chapter_num: Optional[int]
    chapter_title: str
    section: str
    text: str
    tokens: list[str]


# Chapter header in the source looks like "C H A P T E R   ONE" — each
# letter separated by AT LEAST ONE whitespace. The trailing word is the
# chapter number (ONE..TWELVE) optionally with extra spaces (E L E V E N)
# and the source has occasional OCR junk like "FIVE78945612378954654123576179"
# that we tolerate by accepting trailing garbage and re-parsing the head.
_CHAPTER_RE = re.compile(
    r"^\s*C\s+H\s+A\s+P\s+T\s+E\s+R\s+([A-Z][A-Z\s]*?)(?:[^A-Z\s]+)?\s*$",
    re.IGNORECASE,
)

# Roman / word-number -> integer
_WORD_TO_INT = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13,
}


def _parse_chapter_word(word: str) -> Optional[int]:
    """Map 'ONE', 'TWO', 'E L E V E N' etc. to integers. Tolerant of spaces."""
    cleaned = re.sub(r"\s+", "", word).lower().strip()
    return _WORD_TO_INT.get(cleaned)


def _load_chunks() -> list[Chunk]:
    """Walk the curriculum text and emit one Chunk per logical section."""
    if not os.path.exists(_BOOK_PATH):
        log.warning("Curriculum text not found at %s", _BOOK_PATH)
        return []

    with open(_BOOK_PATH, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    chunks: list[Chunk] = []
    cur_chapter_num: Optional[int] = None
    cur_chapter_title: str = "Front Matter"
    cur_section: str = "Intro"
    cur_buf: list[str] = []
    cid = 0

    def _flush():
        nonlocal cid, cur_buf
        text = " ".join(s.strip() for s in cur_buf if s.strip())
        text = _clean(text)                       # strip ASCII art
        text = re.sub(r"\s+", " ", text).strip()
        # Drop tiny noise chunks
        if len(text) < 200:
            cur_buf = []
            return
        chunks.append(Chunk(
            id=cid,
            chapter_num=cur_chapter_num,
            chapter_title=cur_chapter_title,
            section=cur_section,
            text=text,
            tokens=_tokenize(text),
        ))
        cid += 1
        cur_buf = []

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        # Chapter header line
        m = _CHAPTER_RE.match(line)
        if m:
            _flush()
            num = _parse_chapter_word(m.group(1))
            # The next non-empty line is the chapter title; the line after is subtitle (skip)
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            chap_title = lines[j].strip() if j < len(lines) else ""
            cur_chapter_num = num
            cur_chapter_title = chap_title or f"Chapter {num or '?'}"
            cur_section = chap_title or "Intro"
            i = j + 1
            continue

        # CHAPTER SUMMARY → close this chapter's chunk before summary
        if line.strip().upper() == "CHAPTER SUMMARY":
            _flush()
            cur_section = "Summary"

        # Section heading heuristic: a line that's a numbered section like "1. Industry Participants"
        # or a short Title-Case line followed by paragraph text.
        if re.match(r"^\s*\d+\.\s+[A-Z]", line) and len(line) < 80:
            _flush()
            cur_section = line.strip()

        # Heuristic: a Title Case line (≤ 8 words) immediately followed by a paragraph
        elif (line and line == line.title() and 2 <= len(line.split()) <= 8
              and i + 1 < len(lines) and len(lines[i + 1].strip()) > 50):
            _flush()
            cur_section = line.strip()

        cur_buf.append(line)

        # Hard chunk size cap — flush if buffer grows beyond ~1500 chars
        joined_len = sum(len(s) for s in cur_buf)
        if joined_len > 1500:
            _flush()
        i += 1

    _flush()
    log.info("Loaded %d curriculum chunks from %s", len(chunks), _BOOK_PATH)
    return chunks


def _load_markdown_chunks(path: str, source_label: str, start_id: int) -> list[Chunk]:
    """
    Parse a markdown file into Chunks using H1/H2/H3 headings as section breaks.

    Sections are tagged with chapter_num=None (the expert knowledge file isn't
    chapter-numbered like the curriculum) and `chapter_title` carries the H1
    heading so the chat citation reads e.g. "Expert · OPEC+ Deep Mechanics /
    Compliance theory".
    """
    if not os.path.exists(path):
        log.warning("Markdown source not found at %s", path)
        return []

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    chunks: list[Chunk] = []
    cur_h1 = source_label
    cur_h2 = "Intro"
    cur_buf: list[str] = []
    cid = start_id

    def _flush_md():
        nonlocal cid, cur_buf
        text = " ".join(s.strip() for s in cur_buf if s.strip())
        # Strip markdown table pipes, bullet markers, hash signs so BM25 hits
        # are about content, not formatting.
        text = re.sub(r"^[#>|*\-+\s]+", " ", text)
        text = re.sub(r"[`*_]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 200:
            cur_buf = []
            return
        chunks.append(Chunk(
            id=cid,
            chapter_num=None,
            chapter_title=f"{source_label} · {cur_h1}",
            section=cur_h2,
            text=text,
            tokens=_tokenize(text),
        ))
        cid += 1
        cur_buf = []

    for raw in lines:
        line = raw.rstrip()
        # H1
        m = re.match(r"^#\s+(.+)$", line)
        if m:
            _flush_md()
            cur_h1 = m.group(1).strip()
            cur_h2 = "Intro"
            continue
        # H2
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            _flush_md()
            cur_h2 = m.group(1).strip()
            continue
        # H3 — treat as sub-section break so deep topics don't get merged.
        m = re.match(r"^###\s+(.+)$", line)
        if m:
            _flush_md()
            cur_h2 = m.group(1).strip()
            continue

        cur_buf.append(line)
        # Cap buffer size for retrieval quality.
        if sum(len(s) for s in cur_buf) > 1500:
            _flush_md()

    _flush_md()
    log.info("Loaded %d expert knowledge chunks from %s", len(chunks), path)
    return chunks


def _load_all_chunks() -> list[Chunk]:
    """Combine curriculum (legacy text format) + expert knowledge (markdown)."""
    base = _load_chunks()
    expert = _load_markdown_chunks(_EXPERT_PATH, "Expert Knowledge", start_id=len(base))
    return base + expert


# ── BM25 index ──────────────────────────────────────────────────────────────

@dataclass
class _Index:
    chunks: list[Chunk]
    doc_freq: dict[str, int]   # term -> # docs containing it
    avg_doclen: float
    n_docs: int


def _build_index(chunks: list[Chunk]) -> _Index:
    df: dict[str, int] = defaultdict(int)
    for c in chunks:
        for t in set(c.tokens):
            df[t] += 1
    n = len(chunks) or 1
    avg = sum(len(c.tokens) for c in chunks) / n if chunks else 0
    return _Index(chunks=chunks, doc_freq=dict(df), avg_doclen=avg, n_docs=n)


def _bm25_score(query_tokens: list[str], chunk: Chunk, idx: _Index) -> float:
    if not chunk.tokens:
        return 0.0
    score = 0.0
    tf = Counter(chunk.tokens)
    dl = len(chunk.tokens)
    for q in query_tokens:
        df = idx.doc_freq.get(q, 0)
        if df == 0:
            continue
        # Okapi IDF
        idf = math.log((idx.n_docs - df + 0.5) / (df + 0.5) + 1.0)
        f = tf.get(q, 0)
        if f == 0:
            continue
        denom = f + _K1 * (1 - _B + _B * dl / idx.avg_doclen) if idx.avg_doclen > 0 else 1
        score += idf * (f * (_K1 + 1)) / denom
    return score


# ── Module-load: build the index once ───────────────────────────────────────

_CHUNKS = _load_all_chunks()
_INDEX = _build_index(_CHUNKS)


def search(query: str, k: int = 5) -> list[dict]:
    """
    Search the curriculum for chunks relevant to `query`. Returns top-K dicts:
      [{"chapter": int|None, "chapter_title": str, "section": str,
        "text": str, "score": float, "id": int}, ...]
    """
    if not _INDEX.chunks:
        return []
    q_toks = _tokenize(query)
    if not q_toks:
        return []
    scored = [
        (_bm25_score(q_toks, c, _INDEX), c)
        for c in _INDEX.chunks
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for score, c in scored[:k]:
        if score <= 0:
            continue
        out.append({
            "id":            c.id,
            "chapter":       c.chapter_num,
            "chapter_title": c.chapter_title,
            "section":       c.section,
            "text":          c.text,
            "score":         round(float(score), 3),
        })
    return out


def index_stats() -> dict:
    """For diagnostics."""
    return {
        "chunks":     len(_INDEX.chunks),
        "vocab":      len(_INDEX.doc_freq),
        "avg_doclen": round(_INDEX.avg_doclen, 1),
        "book_path":  _BOOK_PATH,
        "book_exists":os.path.exists(_BOOK_PATH),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Index stats:", index_stats())
    for q in [
        "what is backwardation",
        "OPEC spare capacity",
        "3-2-1 crack spread formula",
        "negative WTI 2020 Cushing",
        "Hormuz chokepoint",
        "RBOB summer winter spec change",
    ]:
        print(f"\n=== {q} ===")
        for hit in search(q, k=3):
            print(f"  [{hit['score']:.2f}] Ch{hit['chapter']} {hit['chapter_title']} / {hit['section']}")
            print(f"       {hit['text'][:140]}...")
