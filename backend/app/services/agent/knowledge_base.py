"""轻量项目知识库（LC-02）：按主题维护的小型 Markdown 库 + 关键词检索。

不引入向量数据库（docs/langchain_agent_v1_plan.md §3）：按标题/章节切分，
对查询做中文 bigram + 拉丁词切词，按标题命中加权的相关度返回 3～5 个片段。
知识规模扩大后再评估 embeddings/RAG。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"

MAX_MATCHES = 5
# 单个片段最大字符数，避免 observation 过长
MAX_SNIPPET_CHARS = 900

_LATIN_RE = re.compile(r"[a-z0-9_.]+", re.IGNORECASE)


@dataclass
class KnowledgeChunk:
    source: str  # 文件名（不含扩展名）
    section: str  # 章节标题
    body: str


def _terms(text: str) -> list[str]:
    """切词：拉丁/数字子串原样保留，中文按字符 bigram。"""
    terms: list[str] = []
    for match in _LATIN_RE.finditer(text.lower()):
        terms.append(match.group(0))
    chinese = re.sub(r"[^\u4e00-\u9fff]", "", text)
    terms.extend(
        chinese[index : index + 2] for index in range(len(chinese) - 1)
    )
    if len(chinese) == 1:
        terms.append(chinese)
    return terms


def _load_chunks(directory: Path = KNOWLEDGE_DIR) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    for path in sorted(directory.glob("*.md")):
        current_section: str | None = None
        body_lines: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                continue  # 文件主标题不作物料片段
            if line.startswith("## "):
                if current_section is not None:
                    chunks.append(
                        KnowledgeChunk(path.stem, current_section, "\n".join(body_lines).strip())
                    )
                current_section = line.lstrip("# ").strip()
                body_lines = []
            else:
                body_lines.append(line)
        if current_section is not None:
            chunks.append(
                KnowledgeChunk(path.stem, current_section, "\n".join(body_lines).strip())
            )
    return chunks


_CHUNKS: list[KnowledgeChunk] | None = None


def _chunks() -> list[KnowledgeChunk]:
    global _CHUNKS
    if _CHUNKS is None:
        _CHUNKS = _load_chunks()
    return _CHUNKS


def reload_knowledge() -> None:
    """测试或知识文件更新后重置缓存。"""
    global _CHUNKS
    _CHUNKS = None


def search_knowledge(query: str, limit: int = MAX_MATCHES) -> list[dict]:
    """按相关度返回知识片段：[{source, section, content, score}]。"""
    query_terms = set(_terms(query))
    if not query_terms:
        return []
    scored: list[tuple[int, KnowledgeChunk]] = []
    for chunk in _chunks():
        heading_terms = set(_terms(chunk.section))
        body_terms = set(_terms(chunk.body))
        score = 3 * len(query_terms & heading_terms) + len(query_terms & body_terms)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    matches = []
    for score, chunk in scored[:limit]:
        body = chunk.body
        if len(body) > MAX_SNIPPET_CHARS:
            body = body[:MAX_SNIPPET_CHARS] + "…"
        matches.append(
            {
                "source": chunk.source,
                "section": chunk.section,
                "content": body,
                "score": score,
            }
        )
    return matches
