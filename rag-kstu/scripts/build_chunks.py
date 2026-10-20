#!/usr/bin/env python3
"""Build deterministic semantic chunks from the reviewed KSTU allowlist."""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
from urllib.parse import urldefrag


ROOT = Path.cwd().resolve()
if (Path(__file__).resolve().parent.parent / "UNIVERSITY.md").exists():
    ROOT = Path(__file__).resolve().parents[2]
CATEGORIES = {"prospective student", "current student", "calendar"}
TOKENIZER = "cl100k_base"
TOKENIZER_VERSION = "0.12.0"
TOKENIZER_URL = "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
TOKENIZER_SHA256 = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
_encoding = None


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def path_for(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def check_file(path, expected):
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError(f"Missing SHA256 for {path}")
    actual = sha256(path_for(path).read_bytes())
    if actual != expected:
        raise ValueError(f"Input drift for {path}: expected {expected}, got {actual}")


def token_count(text):
    global _encoding
    if _encoding is None:
        if importlib.metadata.version("tiktoken") != TOKENIZER_VERSION:
            raise ValueError(f"Install pinned tiktoken=={TOKENIZER_VERSION}")
        cache = ROOT / "rag-kstu/data/tokenizer"
        asset = cache / hashlib.sha1(TOKENIZER_URL.encode()).hexdigest()
        if not asset.is_file() or sha256(asset.read_bytes()) != TOKENIZER_SHA256:
            raise ValueError(f"Offline tokenizer asset missing or corrupt: {asset}")
        os.environ["TIKTOKEN_CACHE_DIR"] = str(cache)
        import tiktoken

        _encoding = tiktoken.get_encoding(TOKENIZER)
    return len(_encoding.encode(text, disallowed_special=()))


def resolve_ref(ref):
    """Verify the full reviewed text before applying an optional character slice."""
    check_file(ref["artifact_path"], ref["artifact_sha256"])
    path = path_for(ref["artifact_path"])
    reader = ref["reader"]
    page = ref.get("page_number")
    if page is not None and (type(page) is not int or page < 1):
        raise ValueError(f"Invalid physical page in {ref}")
    if reader == "text":
        text = path.read_text(encoding="utf-8")
    elif reader == "block":
        document = json.loads(path.read_text(encoding="utf-8"))
        pages = [item for item in document["pages"] if item["page_number"] == page]
        if len(pages) != 1:
            raise ValueError(f"Physical page not unique in {ref}")
        block = pages[0]["blocks"][ref["block_index"]]
        text = block.get("markdown") if block.get("type") == "table" else block.get("text")
        if not text:
            text = block.get("text") or block.get("markdown")
    elif reader == "passage":
        document = json.loads(path.read_text(encoding="utf-8"))
        passages = [item for item in document["passages"] if item["id"] == ref["passage_id"]]
        if len(passages) != 1 or passages[0]["page_number"] != page:
            raise ValueError(f"Passage or physical page not unique in {ref}")
        text = passages[0]["text"]
    else:
        raise ValueError(f"Unknown reference reader {reader}")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"Empty approved source text in {ref}")
    if sha256(text.encode()) != ref["text_sha256"]:
        raise ValueError(f"Reviewed text hash mismatch in {ref}")
    start, end = ref.get("start", 0), ref.get("end", len(text))
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
        raise ValueError(f"Invalid text slice in {ref}")
    return text[start:end]


def joined(parts):
    return "\n\n".join(parts)


def body_text(units):
    if units and all(unit.get("kind") == "table_rows" for unit in units):
        return "\n".join(unit["text"].rstrip("\n") for unit in units)
    return joined([unit["text"] for unit in units])


def render_text(context_text, units):
    if units and all(unit.get("kind") == "table_rows" for unit in units):
        return joined(context_text[:-1] + [context_text[-1].rstrip("\n") + "\n" + body_text(units)])
    return joined(context_text + [unit["text"] for unit in units])


def reference_citation(ref, source, role):
    citation = dict(ref, role=role, source_sha256=source["source_sha256"])
    page = ref.get("page_number")
    citation["source_url"] = source["source_url"]
    citation["url"] = urldefrag(source["source_url"])[0] + f"#page={page}" if page else source["source_url"]
    return citation


def overlap_tail(units, context_text, denominator, maximum, following):
    candidates = []
    for start in range(len(units)):
        tail = units[start:]
        tokens = token_count(body_text(tail))
        if tokens / denominator > 0.15:
            continue
        next_text = render_text(context_text, tail + [following])
        if token_count(next_text) <= maximum:
            candidates.append((tail, tokens))
    if not candidates:
        return [], 0, "No complete trailing unit fits the 10–15% overlap target and next chunk size."
    tail, tokens = min(candidates, key=lambda item: abs(item[1] / denominator - 0.125))
    exception = None if 0.10 <= tokens / denominator <= 0.15 else "The nearest complete trailing unit is below 10% of the preceding full chunk."
    return tail, tokens, exception


def chunk_selection(selection, source, settings):
    category = selection["category"]
    if category not in CATEGORIES or selection["eligibility"] not in {"current", "archive"}:
        raise ValueError(f"Unapproved category or eligibility in {selection['selection_id']}")
    if not isinstance(selection.get("audience_restrictions"), (list, str, dict)) or not selection["audience_restrictions"]:
        raise ValueError(f"Missing reviewed audience in {selection['selection_id']}")
    if any(value not in CATEGORIES for value in selection.get("additional_categories", [])):
        raise ValueError("Unapproved additional category")
    if not isinstance(selection.get("topic"), list) or not selection["topic"]:
        raise ValueError("Topics must be a nonempty list")
    if not selection.get("review_evidence") or not selection.get("effective_date_evidence"):
        raise ValueError("Eligibility must retain review and effective-date evidence")
    title = source.get("source") or source.get("title")
    if not isinstance(title, str) or not title.strip() or title == source["source_sha256"]:
        raise ValueError("A reviewed source title is required")
    context = selection.get("context", [])
    context_text = [resolve_ref(ref) for ref in context]
    units = []
    ids = set()
    for unit in selection["units"]:
        if unit["unit_id"] in ids or not unit.get("parts"):
            raise ValueError("Unit IDs must be unique and units must contain approved parts")
        ids.add(unit["unit_id"])
        units.append(dict(unit, text=joined([resolve_ref(ref) for ref in unit["parts"]])))
    if not units:
        raise ValueError("An approved selection must contain at least one semantic unit")
    minimum = settings.get("target_min_tokens", 500)
    target = settings.get("preferred_tokens", 800)
    maximum = settings.get("target_max_tokens", 1000)
    if not 0 < minimum <= target <= maximum:
        raise ValueError("Invalid chunk-size settings")
    chunks = []
    cursor, tail, shared, overlap_exception = 0, [], 0, None
    while cursor < len(units):
        body = list(tail)
        previous_cursor = cursor
        while cursor < len(units):
            candidate = body + [units[cursor]]
            count = token_count(render_text(context_text, candidate))
            if cursor > previous_cursor and (count > maximum or token_count(render_text(context_text, body)) >= target):
                break
            if tail and count > maximum:
                tail, body, shared = [], [], 0
                overlap_exception = "Repeating a complete trailing unit would make the next indivisible unit oversized."
                continue
            body = candidate
            cursor += 1
        text = render_text(context_text, body)
        count = token_count(text)
        refs = [ref for unit in body for ref in unit["parts"]]
        original_is_pdf = Path(source["original_path"]).suffix.lower() == ".pdf"
        all_refs = context + refs
        if any((ref.get("page_number") is None) == original_is_pdf for ref in all_refs):
            raise ValueError("PDF references require physical pages and HTML references require null pages")
        size_exception = None
        if count < minimum:
            size_exception = {"reason": "The remaining complete units cannot reach the minimum without exceeding the maximum or merging unrelated selections.", "measured_tokens": count, "minimum_tokens": minimum}
        elif count > maximum:
            size_exception = {"reason": "An indivisible semantic unit and its required context exceed the maximum.", "measured_tokens": count, "maximum_tokens": maximum}
        previous = chunks[-1] if chunks else None
        overlap = {
            "previous_chunk_id": previous["chunk_id"] if previous else None,
            "shared_unit_ids": [unit["unit_id"] for unit in tail],
            "shared_tokens": shared,
            "denominator_tokens": previous["token_count"] if previous else None,
            "ratio": shared / previous["token_count"] if previous else None,
            "repeated_context_tokens": token_count(joined(context_text)) if previous and context_text else 0,
            "exception": overlap_exception,
        }
        chunk = {
            "selection_id": selection["selection_id"], "university_id": "kstu",
            "text": text, "token_count": count, "source": title,
            "source_url": source["source_url"], "source_sha256": source["source_sha256"],
            "original_path": source["original_path"],
            "extraction_provenance": {"context": context, "body": refs},
            "category": category, "additional_categories": selection.get("additional_categories", []),
            "topic": selection["topic"], "page_number": all_refs[0].get("page_number"),
            "body_page_number": refs[0].get("page_number"),
            "citations": [reference_citation(ref, source, "context") for ref in context] + [reference_citation(ref, source, "body") for ref in refs],
            "academic_year": selection.get("academic_year"),
            "effective_date_evidence": selection["effective_date_evidence"],
            "audience_restrictions": selection["audience_restrictions"],
            "eligibility": selection["eligibility"],
            "current_answer_eligible": selection.get("current_answer_eligible") is True,
            "limitations": selection.get("limitations", []),
            "recognition_status": selection.get("recognition_status", source.get("recognition_status")),
            "review_evidence": selection["review_evidence"],
            "unit_ids": [unit["unit_id"] for unit in body], "overlap": overlap,
            "size_exception": size_exception,
            "tokenizer": {"name": TOKENIZER, "version": TOKENIZER_VERSION},
        }
        if selection["eligibility"] == "current" and not chunk["current_answer_eligible"]:
            raise ValueError("Current output requires explicit current-answer eligibility")
        for field in ("table_scope", "event_association"):
            if field in selection:
                chunk[field] = selection[field]
        chunk["chunk_id"] = "kstu-" + sha256(canonical({"chunk": chunk, "settings": settings}).encode())
        chunks.append(chunk)
        if cursor < len(units):
            tail, shared, overlap_exception = overlap_tail(body, context_text, count, maximum, units[cursor])
    return chunks


def build(manifest_path, output):
    manifest_path = path_for(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("university_id") != "kstu":
        raise ValueError("The chunk adapter accepts only the explicit KSTU allowlist")
    settings = manifest["settings"]
    if settings.get("tokenizer") != TOKENIZER or settings.get("tokenizer_version") != TOKENIZER_VERSION:
        raise ValueError("Manifest must pin cl100k_base with tiktoken 0.12.0")
    for path, expected in manifest["inputs"].items():
        check_file(path, expected)
    sources = {}
    for source in manifest["sources"]:
        key = source["source_sha256"]
        if key in sources:
            raise ValueError("Deduplicate acquisitions in the manifest, retaining their provenance")
        check_file(source["original_path"], key)
        if source.get("extraction_path"):
            check_file(source["extraction_path"], source["extraction_sha256"])
        if not source.get("source_url"):
            raise ValueError("An official source URL is required")
        sources[key] = source
    chunks, selection_ids = [], set()
    for selection in manifest["selections"]:
        if selection["selection_id"] in selection_ids:
            raise ValueError("Selection IDs must be unique")
        selection_ids.add(selection["selection_id"])
        chunks.extend(chunk_selection(selection, sources[selection["source_sha256"]], settings))
    output = path_for(output)
    output.mkdir(parents=True, exist_ok=True)
    counts = {}
    for eligibility in ("current", "archive"):
        subset = [chunk for chunk in chunks if chunk["eligibility"] == eligibility]
        (output / f"chunks.{eligibility}.jsonl").write_text("".join(canonical(chunk) + "\n" for chunk in subset), encoding="utf-8")
        counts[eligibility] = len(subset)
    sizes = sorted(chunk["token_count"] for chunk in chunks)
    stats = {
        "schema_version": 1, "manifest_sha256": sha256(manifest_path.read_bytes()),
        "source_count": len(sources), "selection_count": len(selection_ids), "chunk_counts": counts,
        "tokenizer": {"name": TOKENIZER, "version": TOKENIZER_VERSION, "asset_sha256": TOKENIZER_SHA256},
        "size_distribution": {"minimum": min(sizes) if sizes else None, "maximum": max(sizes) if sizes else None, "under_500": sum(value < 500 for value in sizes), "500_to_1000": sum(500 <= value <= 1000 for value in sizes), "over_1000": sum(value > 1000 for value in sizes)},
        "size_exceptions": [{"chunk_id": chunk["chunk_id"], **chunk["size_exception"]} for chunk in chunks if chunk["size_exception"]],
        "overlaps": [{"chunk_id": chunk["chunk_id"], **chunk["overlap"]} for chunk in chunks if chunk["overlap"]["previous_chunk_id"]],
    }
    (output / "build-stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return chunks, stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="rag-kstu/data/source-manifest.json")
    parser.add_argument("--output", default="rag-kstu/data")
    args = parser.parse_args()
    _, stats = build(args.manifest, args.output)
    print(json.dumps(stats["chunk_counts"], sort_keys=True))


if __name__ == "__main__":
    main()
