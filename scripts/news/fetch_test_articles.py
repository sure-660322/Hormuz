"""Fetch the ten Media Cloud test candidates without bypassing access controls."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, parse, request, robotparser

from lxml import html


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/126 Safari/537.36 HormuzNewsResearch/0.1"
)
MAX_HTML_BYTES = 8 * 1024 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024
TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def clean_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def canonicalize_url(url: str) -> str:
    parts = parse.urlsplit(url)
    kept_query = []
    for key, value in parse.parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in TRACKING_PARAMETERS:
            continue
        kept_query.append((key, value))
    return parse.urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path or "/",
            parse.urlencode(kept_query, doseq=True),
            "",
        )
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc
    return records


def robots_allowed(url: str) -> tuple[bool, str | None]:
    parts = parse.urlsplit(url)
    robots_url = parse.urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
    parser = robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        req = request.Request(robots_url, headers={"User-Agent": USER_AGENT})
        with request.urlopen(req, timeout=15) as response:
            content = response.read(512 * 1024).decode("utf-8", errors="replace")
        parser.parse(content.splitlines())
        return parser.can_fetch(USER_AGENT, url), None
    except error.HTTPError as exc:
        if exc.code in {401, 403}:
            return False, f"robots_http_{exc.code}"
        return True, f"robots_unavailable_http_{exc.code}"
    except Exception as exc:  # A missing robots file should not mask a normal page.
        return True, f"robots_unavailable_{type(exc).__name__}"


def fetch_bytes(url: str, limit: int, timeout: int = 30) -> tuple[bytes, Any, str]:
    req = request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8",
        },
    )
    with request.urlopen(req, timeout=timeout) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError(f"response_exceeds_{limit}_bytes")
        return data, response.headers, response.geturl()


def meta_content(document: Any, *selectors: str) -> str | None:
    for selector in selectors:
        values = document.xpath(selector)
        for value in values:
            if hasattr(value, "get"):
                candidate = value.get("content") or value.get("href")
            else:
                candidate = str(value)
            candidate = clean_text(candidate)
            if candidate:
                return candidate
    return None


def iter_jsonld(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_jsonld(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_jsonld(child)


def jsonld_metadata(document: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for raw in document.xpath('//script[@type="application/ld+json"]/text()'):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for item in iter_jsonld(parsed):
            kind = item.get("@type")
            kinds = {kind} if isinstance(kind, str) else set(kind or [])
            if not kinds.intersection({"Article", "NewsArticle", "ReportageNewsArticle"}):
                continue
            for key in ("headline", "datePublished", "articleBody"):
                if key not in result and item.get(key):
                    result[key] = item[key]
            image = item.get("image")
            if image and "image" not in result:
                if isinstance(image, str):
                    result["image"] = image
                elif isinstance(image, list) and image:
                    first = image[0]
                    result["image"] = first if isinstance(first, str) else first.get("url")
                elif isinstance(image, dict):
                    result["image"] = image.get("url") or image.get("contentUrl")
    return result


def extract_paragraphs(document: Any) -> str:
    for bad in document.xpath("//script|//style|//noscript|//nav|//footer|//form|//aside"):
        parent = bad.getparent()
        if parent is not None:
            parent.remove(bad)

    groups = [
        document.xpath("//article//p"),
        document.xpath('//*[@itemprop="articleBody"]//p'),
        document.xpath("//main//p"),
        document.xpath("//body//p"),
    ]
    best: list[str] = []
    for group in groups:
        paragraphs: list[str] = []
        seen: set[str] = set()
        for node in group:
            text = clean_text(node.text_content())
            if not text or len(text) < 30 or text in seen:
                continue
            seen.add(text)
            paragraphs.append(text)
        if sum(map(len, paragraphs)) > sum(map(len, best)):
            best = paragraphs
        if sum(map(len, best)) >= 800:
            break
    return "\n\n".join(best)


def extract_page(data: bytes, headers: Any, final_url: str) -> dict[str, Any]:
    charset = headers.get_content_charset() or "utf-8"
    text = data.decode(charset, errors="replace")
    document = html.fromstring(text, base_url=final_url)
    document.make_links_absolute(final_url)
    jsonld = jsonld_metadata(document)

    title = meta_content(
        document,
        '//meta[@property="og:title"]/@content',
        '//meta[@name="twitter:title"]/@content',
        "//title/text()",
    ) or clean_text(jsonld.get("headline"))
    source = meta_content(document, '//meta[@property="og:site_name"]/@content')
    published = meta_content(
        document,
        '//meta[@property="article:published_time"]/@content',
        '//meta[@name="date"]/@content',
        '//meta[@name="pub_date"]/@content',
        '//time/@datetime',
    ) or clean_text(jsonld.get("datePublished"))
    canonical = meta_content(document, '//link[contains(@rel,"canonical")]/@href')
    image_url = meta_content(
        document,
        '//meta[@property="og:image"]/@content',
        '//meta[@name="twitter:image"]/@content',
    ) or clean_text(jsonld.get("image"))
    image_caption = meta_content(
        document,
        '//meta[@property="og:image:alt"]/@content',
        '//meta[@name="twitter:image:alt"]/@content',
    )
    content = clean_text(jsonld.get("articleBody")) or extract_paragraphs(document)
    return {
        "title": title,
        "source": source,
        "published_at": published,
        "canonical_url": canonicalize_url(canonical or final_url),
        "content": content or "",
        "image_url": parse.urljoin(final_url, image_url) if image_url else None,
        "image_caption": image_caption,
    }


def image_extension(content_type: str | None, image_url: str) -> str:
    clean_type = (content_type or "").split(";", 1)[0].strip().lower()
    known = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
    if clean_type in known:
        return known[clean_type]
    guessed = mimetypes.guess_extension(clean_type) if clean_type else None
    if guessed:
        return guessed
    suffix = Path(parse.urlsplit(image_url).path).suffix.lower()
    return suffix if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"} else ".img"


def download_image(image_url: str, article_id: str, image_dir: Path, project_root: Path) -> dict[str, Any]:
    result = {
        "original_url": image_url,
        "local_path": None,
        "caption": None,
        "download_status": "failed",
        "failure_reason": None,
    }
    try:
        data, headers, _ = fetch_bytes(image_url, MAX_IMAGE_BYTES, timeout=30)
        content_type = headers.get("Content-Type", "")
        if not content_type.lower().startswith("image/"):
            raise ValueError(f"unexpected_content_type:{content_type}")
        destination = image_dir / f"{article_id}{image_extension(content_type, image_url)}"
        destination.write_bytes(data)
        result["local_path"] = destination.relative_to(project_root).as_posix()
        result["download_status"] = "success"
    except Exception as exc:
        result["failure_reason"] = f"{type(exc).__name__}:{exc}"
    return result


def fetch_candidate(candidate: dict[str, Any], image_dir: Path, project_root: Path) -> dict[str, Any]:
    original_url = candidate["url"]
    initial_canonical = canonicalize_url(original_url)
    article_id = hashlib.sha256(initial_canonical.encode("utf-8")).hexdigest()
    candidate_title = candidate.get("title")
    candidate_source = candidate.get("source")
    candidate_published_at = candidate.get("published_at")
    result: dict[str, Any] = {
        "id": article_id,
        "title": candidate_title,
        "source": candidate_source,
        "published_at": candidate_published_at,
        "url": original_url,
        "canonical_url": initial_canonical,
        "content": "",
        "images": [],
        "language": candidate.get("language"),
        "retrieved_at": utc_now(),
        "query_source": candidate.get("query_source", "mediacloud_v4"),
        "fetch_status": "failed",
        "http_status": None,
        "failure_reason": None,
        "robots_note": None,
        "candidate_title": candidate_title,
        "candidate_source": candidate_source,
        "candidate_published_at": candidate_published_at,
        "page_title": None,
        "page_source": None,
        "page_published_at": None,
    }

    allowed, robots_note = robots_allowed(original_url)
    result["robots_note"] = robots_note
    if not allowed:
        result["fetch_status"] = "robots_disallowed"
        result["failure_reason"] = robots_note or "robots_disallowed"
        return result

    try:
        page_data, headers, final_url = fetch_bytes(original_url, MAX_HTML_BYTES)
        result["http_status"] = 200
        content_type = headers.get("Content-Type", "")
        if "html" not in content_type.lower():
            raise ValueError(f"unexpected_content_type:{content_type}")
        extracted = extract_page(page_data, headers, final_url)
        result["page_title"] = extracted["title"]
        result["page_source"] = extracted["source"]
        result["page_published_at"] = extracted["published_at"]
        page_title = extracted["title"]
        if (
            candidate_title
            and page_title
            and candidate_title.casefold().startswith(page_title.casefold())
            and len(page_title) < len(candidate_title)
        ):
            result["title"] = candidate_title
        else:
            result["title"] = page_title or candidate_title
        result["source"] = extracted["source"] or candidate_source
        # Raw output preserves the discovery timestamp as the primary value.
        # The page-provided timestamp is retained separately for later cleaning.
        result["published_at"] = candidate_published_at or extracted["published_at"]
        result["canonical_url"] = extracted["canonical_url"]
        result["content"] = extracted["content"]
        if extracted["image_url"]:
            image = download_image(extracted["image_url"], article_id, image_dir, project_root)
            image["caption"] = extracted["image_caption"]
            result["images"] = [image]
        result["fetch_status"] = "success" if len(result["content"]) >= 200 else "partial"
        if result["fetch_status"] == "partial":
            result["failure_reason"] = "content_too_short"
    except error.HTTPError as exc:
        result["http_status"] = exc.code
        result["failure_reason"] = f"HTTPError:{exc.code}"
    except Exception as exc:
        result["failure_reason"] = f"{type(exc).__name__}:{exc}"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image-dir", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--delay-seconds", type=float, default=2.0)
    args = parser.parse_args()

    if args.output.exists():
        raise FileExistsError(f"Raw output already exists: {args.output}")
    candidates = read_jsonl(args.input)
    if len(candidates) != 10:
        raise ValueError(f"Expected 10 candidates, found {len(candidates)}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.image_dir.mkdir(parents=True, exist_ok=True)
    temporary_output = args.output.with_suffix(args.output.suffix + ".tmp")
    if temporary_output.exists():
        raise FileExistsError(f"Temporary output already exists: {temporary_output}")

    counts: dict[str, int] = {}
    with temporary_output.open("x", encoding="utf-8", newline="\n") as handle:
        for index, candidate in enumerate(candidates, start=1):
            result = fetch_candidate(candidate, args.image_dir, args.project_root)
            handle.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            status = result["fetch_status"]
            counts[status] = counts.get(status, 0) + 1
            print(
                json.dumps(
                    {
                        "index": index,
                        "status": status,
                        "http_status": result["http_status"],
                        "content_chars": len(result["content"]),
                        "images": len(result["images"]),
                        "domain": parse.urlsplit(result["url"]).netloc,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            if index < len(candidates):
                time.sleep(args.delay_seconds)
    temporary_output.replace(args.output)
    print(json.dumps({"output": str(args.output), "counts": counts}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
