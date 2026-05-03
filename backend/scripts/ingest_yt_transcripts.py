from __future__ import annotations

import argparse
import csv
import shutil
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse, parse_qs

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.chroma import init_chroma, get_or_create_collection

"""
Scaffold for Week 4 transcript ingestion.

Supported input formats:

1) JSONL where each line looks like:
{
  "company": "Deloitte",
  "topic": "Sustainability as a business strategy",
  "source_url": "https://youtube.com/...",
  "speaker": "candidate",
  "text": "I think sustainability drives long-term resilience..."
}

2) Links CSV with columns:
   company,topic,url

When using links CSV, this script tries subtitle-first ingestion:
- yt-dlp downloads auto/caption subtitles (no audio download)
- parse VTT subtitles into text
- chunk text and upsert to ChromaDB

This keeps ingestion lightweight for local workflows.
"""

TIMESTAMP_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}\.\d{3}")


def _normalize_youtube_url(url: str) -> str:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()

    if "youtu.be" in host:
        video_id = parsed.path.strip("/")
        return f"https://www.youtube.com/watch?v={video_id}" if video_id else url

    if "youtube.com" in host:
        qs = parse_qs(parsed.query)
        video_id = (qs.get("v") or [""])[0]
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"

    return url


def _chunk_text(text: str, target_chars: int = 550) -> list[str]:
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for word in words:
        current.append(word)
        current_len += len(word) + 1
        if current_len >= target_chars:
            chunks.append(" ".join(current).strip())
            current = []
            current_len = 0

    if current:
        chunks.append(" ".join(current).strip())

    return [chunk for chunk in chunks if len(chunk) > 40]


def _append_jsonl(path: Path, records: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _parse_vtt_text(vtt_path: Path) -> str:
    lines: list[str] = []
    seen: set[str] = set()

    with vtt_path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("WEBVTT"):
                continue
            if TIMESTAMP_RE.match(line):
                continue
            if line.isdigit():
                continue
            # Skip inline cue tags and duplicate rolling-caption lines.
            cleaned = re.sub(r"<[^>]+>", "", line).strip()
            if not cleaned:
                continue
            if cleaned in seen:
                continue
            seen.add(cleaned)
            lines.append(cleaned)

    return " ".join(lines)


def _download_subtitles(url: str, out_dir: Path) -> Path | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(out_dir / "%(id)s.%(ext)s")
    base_args = [
        "--skip-download",
        "--write-auto-subs",
        "--write-subs",
        "--sub-langs",
        "en.*,en",
        "--sub-format",
        "vtt",
        "-o",
        output_template,
        url,
    ]

    commands: list[list[str]] = []
    if shutil.which("yt-dlp"):
        commands.append(["yt-dlp", *base_args])
    commands.append([sys.executable, "-m", "yt_dlp", *base_args])

    ran = False
    for cmd in commands:
        try:
            result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            continue
        ran = True
        if result.returncode == 0:
            break

    if not ran:
        return None

    candidates = sorted(out_dir.glob("*.vtt"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def ingest_jsonl(file_path: str) -> int:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    client = init_chroma()
    collection = get_or_create_collection(client)
    if collection is None:
        print("ChromaDB unavailable. Install chromadb before ingestion.")
        return 0

    documents: list[str] = []
    ids: list[str] = []
    metadatas: list[dict] = []

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            text = str(record.get("text", "")).strip()
            if not text:
                continue

            company = str(record.get("company", "General"))
            topic = str(record.get("topic", "General GD topic"))
            source_url = str(record.get("source_url", ""))
            speaker = str(record.get("speaker", "unknown"))

            ids.append(f"yt-{uuid.uuid4().hex[:12]}")
            documents.append(text)
            metadatas.append(
                {
                    "company": company,
                    "topic": topic,
                    "source": "youtube",
                    "source_url": source_url,
                    "speaker": speaker,
                }
            )

    if not documents:
        print("No valid transcript lines found.")
        return 0

    collection.add(ids=ids, documents=documents, metadatas=metadatas)
    print(f"Ingested {len(documents)} transcript chunks.")
    return len(documents)


def ingest_links_csv(file_path: str, work_dir: str = "./tmp_subtitles") -> int:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Links CSV not found: {path}")

    client = init_chroma()
    collection = get_or_create_collection(client)
    offline_output = Path(work_dir) / "ingested_chunks.jsonl"
    offline_mode = collection is None
    if offline_mode:
        print(f"ChromaDB unavailable. Writing parsed chunks to {offline_output} instead.")

    out_dir = Path(work_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    inserted = 0
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"company", "topic", "url"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError("CSV must include headers: company,topic,url")

        for row in reader:
            company = (row.get("company") or "General").strip() or "General"
            topic = (row.get("topic") or "General GD topic").strip() or "General GD topic"
            raw_url = (row.get("url") or "").strip()
            url = _normalize_youtube_url(raw_url)
            if not url:
                continue

            try:
                vtt_path = _download_subtitles(url, out_dir)
            except Exception as exc:  # noqa: BLE001
                print(f"Skipped (subtitle extraction error): {url} -> {exc}")
                continue
            if vtt_path is None:
                print(f"Skipped (no subtitles): {url}")
                continue

            text = _parse_vtt_text(vtt_path)
            chunks = _chunk_text(text)
            if not chunks:
                print(f"Skipped (empty subtitle text): {url}")
                continue

            ids = [f"yt-{uuid.uuid4().hex[:12]}" for _ in chunks]
            metadatas = [
                {
                    "company": company,
                    "topic": topic,
                    "source": "youtube",
                    "source_url": url,
                    "speaker": "mixed",
                }
                for _ in chunks
            ]
            if offline_mode:
                records = []
                for idx, chunk in enumerate(chunks):
                    records.append(
                        {
                            "chunk_id": ids[idx],
                            "company": company,
                            "topic": topic,
                            "source": "youtube",
                            "source_url": url,
                            "speaker": "mixed",
                            "text": chunk,
                        }
                    )
                _append_jsonl(offline_output, records)
            else:
                collection.add(ids=ids, documents=chunks, metadatas=metadatas)
            inserted += len(chunks)
            print(f"Ingested {len(chunks)} chunks from {url}")

    if offline_mode:
        print(f"Total chunks exported from links CSV: {inserted}")
    else:
        print(f"Total chunks ingested from links CSV: {inserted}")
    return inserted


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest transcript data into ChromaDB.")
    parser.add_argument("--jsonl", type=str, help="Path to transcript JSONL file.")
    parser.add_argument("--links-csv", type=str, help="Path to links CSV (company,topic,url).")
    parser.add_argument("--work-dir", type=str, default="./tmp_subtitles", help="Temporary subtitle download directory.")
    args = parser.parse_args()

    if args.links_csv:
        ingest_links_csv(args.links_csv, work_dir=args.work_dir)
    elif args.jsonl:
        ingest_jsonl(args.jsonl)
    else:
        default_links = Path(__file__).with_name("sample_yt_links.csv")
        default_jsonl = Path(__file__).with_name("sample_transcripts.jsonl")
        if default_links.exists():
            ingest_links_csv(str(default_links))
        elif default_jsonl.exists():
            ingest_jsonl(str(default_jsonl))
        else:
            print("No input provided.")
            print("Examples:")
            print("  python scripts/ingest_yt_transcripts.py --links-csv scripts/sample_yt_links.csv")
            print("  python scripts/ingest_yt_transcripts.py --jsonl scripts/sample_transcripts.jsonl")
