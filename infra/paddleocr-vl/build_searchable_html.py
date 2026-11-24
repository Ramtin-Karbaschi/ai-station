#!/usr/bin/env python3
"""Build a visually faithful, searchable HTML document from rendered PDF pages.

The rendered page image is the visual source of truth. OCR text is added as an
almost-transparent, selectable line layer, so figures, tables, maps, and page
geometry are never reconstructed or moved by the OCR engine.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import subprocess
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "ai-station.searchable-html.v1"
PAGE_RE = re.compile(r"(\d+)$")
DIGITS = str.maketrans(
    "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669",
    "01234567890123456789",
)


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").translate(DIGITS)
    return " ".join(value.replace("\u200c", " ").replace("\u200f", "").split()).casefold()


def page_number(path: Path) -> int:
    match = PAGE_RE.search(path.stem)
    if not match:
        raise ValueError(f"page image has no numeric suffix: {path.name}")
    return int(match.group(1))


def page_images(root: Path) -> list[Path]:
    images = [path for path in root.iterdir() if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
    return sorted(images, key=page_number)


def run_tesseract(image: Path, tsv_dir: Path) -> Path:
    destination = tsv_dir / image.stem
    completed = subprocess.run(
        ["tesseract", str(image), str(destination), "-l", "fas+eng", "--psm", "3", "tsv"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"Tesseract failed for {image.name}: {completed.stderr[-1000:]}")
    return destination.with_suffix(".tsv")


def ensure_tsv(images: list[Path], tsv_dir: Path, workers: int) -> None:
    tsv_dir.mkdir(parents=True, exist_ok=True)
    pending = [image for image in images if not (tsv_dir / f"{image.stem}.tsv").is_file()]
    if not pending:
        return
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_tesseract, image, tsv_dir): image for image in pending}
        completed = 0
        for future in as_completed(futures):
            future.result()
            completed += 1
            if completed % 10 == 0 or completed == len(pending):
                print(f"tesseract: {completed}/{len(pending)}", flush=True)


def parse_tsv(path: Path) -> tuple[list[dict[str, Any]], str, float | None]:
    lines: dict[tuple[int, int, int, int], dict[str, Any]] = {}
    confidences: list[float] = []
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            text = (row.get("text") or "").strip()
            if not text:
                continue
            try:
                confidence = float(row.get("conf") or -1)
                left, top = int(row["left"]), int(row["top"])
                width, height = int(row["width"]), int(row["height"])
                key = tuple(int(row[name]) for name in ("page_num", "block_num", "par_num", "line_num"))
            except (KeyError, TypeError, ValueError):
                continue
            line = lines.setdefault(
                key,
                {"words": [], "left": left, "top": top, "right": left + width, "bottom": top + height, "conf": []},
            )
            line["words"].append(text)
            line["left"] = min(line["left"], left)
            line["top"] = min(line["top"], top)
            line["right"] = max(line["right"], left + width)
            line["bottom"] = max(line["bottom"], top + height)
            if confidence >= 0:
                line["conf"].append(confidence)
                confidences.append(confidence)
    parsed: list[dict[str, Any]] = []
    for key, line in sorted(lines.items()):
        parsed.append(
            {
                "order": list(key),
                "text": " ".join(line["words"]),
                "bbox": [line["left"], line["top"], line["right"], line["bottom"]],
                "confidence": round(sum(line["conf"]) / len(line["conf"]), 2) if line["conf"] else None,
            }
        )
    text = "\n".join(line["text"] for line in parsed)
    mean = round(sum(confidences) / len(confidences), 2) if confidences else None
    return parsed, text, mean


def load_vision(path: Path | None) -> dict[int, str]:
    if not path:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {int(item["page"]): str(item.get("vision_text", "")) for item in payload.get("pages", [])}


def safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def line_span(line: dict[str, Any], width: int, height: int) -> str:
    left, top, right, bottom = line["bbox"]
    style = (
        f"left:{left / width * 100:.5f}%;top:{top / height * 100:.5f}%;"
        f"width:{max(1, right - left) / width * 100:.5f}%;height:{max(1, bottom - top) / height * 100:.5f}%;"
        f"font-size:{max(4, bottom - top) / height * 100:.5f}cqh"
    )
    confidence = "" if line["confidence"] is None else f'{line["confidence"]:.2f}'
    return (
        f'<span class="ocr-line" style="{style}" data-confidence="{confidence}" '
        f'dir="auto">{html.escape(line["text"])}</span>'
    )


def build_html(title: str, pages: list[dict[str, Any]]) -> str:
    sections = []
    search_pages = []
    for page in pages:
        number = page["page_number"]
        width, height = page["pixel_size"]
        spans = "".join(line_span(line, width, height) for line in page["lines"])
        sections.append(
            f'''<section class="page-card" id="page-{number}" data-page="{number}">
  <div class="page-label">\u0635\u0641\u062d\u0647 {number}</div>
  <div class="page" style="aspect-ratio:{width}/{height}" aria-label="\u0635\u0641\u062d\u0647 {number}">
    <img src="{html.escape(page['image'])}" width="{width}" height="{height}" alt="\u062a\u0635\u0648\u06cc\u0631 \u062f\u0642\u06cc\u0642 \u0635\u0641\u062d\u0647 {number}" loading="lazy" decoding="async">
    <div class="text-layer" aria-label="\u0645\u062a\u0646 OCR \u0635\u0641\u062d\u0647 {number}">{spans}</div>
  </div>
</section>'''
        )
        search_pages.append({"page": number, "text": page["search_text"], "normalized": normalize(page["search_text"])})
    page_markup = "\n".join(sections)
    search_json = safe_json(search_pages)
    escaped_title = html.escape(title)
    return f'''<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escaped_title}</title>
<style>
:root{{--paper-shadow:0 3px 18px rgba(0,0,0,.18);--accent:#155eef;--bg:#dfe3e8}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--bg);font-family:Tahoma,"Noto Sans Arabic",sans-serif;color:#111}}
.toolbar{{position:sticky;top:0;z-index:20;display:flex;gap:.6rem;align-items:center;padding:.65rem 1rem;background:rgba(255,255,255,.96);box-shadow:0 1px 8px rgba(0,0,0,.18);direction:rtl}}
.toolbar strong{{white-space:nowrap}}.toolbar input{{min-width:12rem;flex:1;padding:.55rem .7rem;border:1px solid #aab2bd;border-radius:.45rem;font:inherit}}
.toolbar button{{padding:.55rem .75rem;border:1px solid #8a94a2;border-radius:.45rem;background:#fff;font:inherit}}#search-status{{font-size:.88rem;white-space:nowrap}}
main{{max-width:980px;margin:1.2rem auto;padding:0 1rem}}.page-card{{margin:0 auto 1.5rem;scroll-margin-top:5rem}}.page-label{{text-align:center;color:#3d4652;margin:.35rem;font-size:.9rem}}
.page{{position:relative;width:100%;container-type:size;background:#fff;box-shadow:var(--paper-shadow);overflow:hidden}}.page>img{{position:absolute;inset:0;width:100%;height:100%;display:block}}
.text-layer{{position:absolute;inset:0;overflow:hidden;line-height:1;direction:rtl}}.ocr-line{{position:absolute;display:block;color:transparent;white-space:nowrap;overflow:visible;transform-origin:top right;user-select:text}}
body.show-ocr .ocr-line{{color:rgba(190,0,0,.72);background:rgba(255,240,0,.20);outline:1px solid rgba(190,0,0,.22)}}.page-card.match .page{{outline:4px solid var(--accent)}}
.noscript{{max-width:980px;margin:1rem auto;background:#fff3cd;padding:1rem}}
@media(max-width:600px){{.toolbar{{flex-wrap:wrap}}.toolbar strong{{width:100%}}main{{padding:0 .35rem}}}}
@media print{{body{{background:#fff}}.toolbar,.page-label{{display:none}}main{{max-width:none;margin:0;padding:0}}.page-card{{margin:0;break-after:page}}.page{{box-shadow:none}}}}
</style>
</head>
<body>
<div class="toolbar" role="search">
  <strong>{escaped_title}</strong>
  <input id="query" type="search" placeholder="\u062c\u0633\u062a‌\u0648\u062c\u0648\u06cc \u0645\u062a\u0646 OCR…" autocomplete="off">
  <button id="search" type="button">\u062c\u0633\u062a‌\u0648\u062c\u0648</button>
  <button id="toggle" type="button" aria-pressed="false">\u0646\u0645\u0627\u06cc\u0634 \u0644\u0627\u06cc\u0647 OCR</button>
  <span id="search-status" aria-live="polite"></span>
</div>
<noscript><div class="noscript">\u062a\u0635\u0648\u06cc\u0631 \u0635\u0641\u062d\u0627\u062a \u0648 \u0627\u0646\u062a\u062e\u0627\u0628 \u0645\u062a\u0646 \u0641\u0639\u0627\u0644 \u0627\u0633\u062a\u061b \u062c\u0633\u062a‌\u0648\u062c\u0648\u06cc \u062f\u0627\u062e\u0644\u06cc \u0633\u0646\u062f \u0628\u0647 JavaScript \u0646\u06cc\u0627\u0632 \u062f\u0627\u0631\u062f.</div></noscript>
<main>{page_markup}</main>
<script id="search-data" type="application/json">{search_json}</script>
<script>
const pages=JSON.parse(document.getElementById('search-data').textContent);let matchIndex=0,matches=[];
const q=document.getElementById('query'),status=document.getElementById('search-status');
function norm(s){{return s.normalize('NFKC').replace(/[\u06f0-\u06f9\u0660-\u0669]/g,c=>'\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669'.indexOf(c)%10).replace(/[\u200c\u200f]/g,' ').replace(/\s+/g,' ').trim().toLowerCase()}}
function search(){{document.querySelectorAll('.page-card.match').forEach(e=>e.classList.remove('match'));const needle=norm(q.value);matches=needle?pages.filter(p=>p.normalized.includes(needle)):[];matchIndex=0;if(!matches.length){{status.textContent=needle?'\u06cc\u0627\u0641\u062a \u0646\u0634\u062f':'';return}};go(0)}}
function go(i){{matchIndex=(i+matches.length)%matches.length;const p=matches[matchIndex];const el=document.getElementById('page-'+p.page);el.classList.add('match');el.scrollIntoView({{behavior:'smooth',block:'start'}});status.textContent=`${{matchIndex+1}} \u0627\u0632 ${{matches.length}} — \u0635\u0641\u062d\u0647 ${{p.page}}`}}
document.getElementById('search').addEventListener('click',()=>matches.length&&norm(q.value)===norm(q.dataset.last||'')?go(matchIndex+1):(q.dataset.last=q.value,search()));q.addEventListener('keydown',e=>{{if(e.key==='Enter')document.getElementById('search').click()}});
document.getElementById('toggle').addEventListener('click',e=>{{const on=document.body.classList.toggle('show-ocr');e.currentTarget.setAttribute('aria-pressed',on);e.currentTarget.textContent=on?'\u067e\u0646\u0647\u0627\u0646‌\u06a9\u0631\u062f\u0646 \u0644\u0627\u06cc\u0647 OCR':'\u0646\u0645\u0627\u06cc\u0634 \u0644\u0627\u06cc\u0647 OCR'}});
</script>
</body></html>'''


def main() -> int:
    # Keep pure HTML/evaluation imports usable in the gateway test environment;
    # Pillow is only needed when the CLI inspects rendered page dimensions.
    from PIL import Image

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--title", default="\u0633\u0646\u062f OCR \u0634\u062f\u0647")
    parser.add_argument("--vision-review", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--canary", action="append", default=[], metavar="PAGE:TEXT")
    args = parser.parse_args()
    if not 1 <= args.workers <= 16:
        parser.error("--workers must be between 1 and 16")
    images = page_images(args.pages_dir)
    if not images:
        parser.error("no page images found")
    numbers = [page_number(path) for path in images]
    if numbers != list(range(1, len(images) + 1)):
        parser.error("page images must be consecutively numbered from 1")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    tsv_dir = args.output_dir / "ocr" / "tsv"
    ensure_tsv(images, tsv_dir, args.workers)
    vision = load_vision(args.vision_review)
    pages: list[dict[str, Any]] = []
    tesseract: list[dict[str, Any]] = []
    for image in images:
        number = page_number(image)
        with Image.open(image) as opened:
            size = [opened.width, opened.height]
        lines, tess_text, confidence = parse_tsv(tsv_dir / f"{image.stem}.tsv")
        search_text = vision.get(number) or tess_text
        relative_image = image.relative_to(args.output_dir).as_posix()
        pages.append(
            {
                "page_number": number,
                "pixel_size": size,
                "image": relative_image,
                "lines": lines,
                "text": search_text,
                "search_text": search_text,
                "text_source": "vision_review" if number in vision else "tesseract",
                "mean_confidence": confidence,
            }
        )
        tesseract.append({"page_number": number, "text": tess_text, "mean_confidence": confidence, "lines": lines})
    canaries = []
    by_page = {page["page_number"]: page for page in pages}
    for spec in args.canary:
        raw_page, separator, expected = spec.partition(":")
        if not separator or not raw_page.isdigit() or not expected:
            parser.error(f"invalid canary: {spec}")
        number = int(raw_page)
        passed = number in by_page and normalize(expected) in normalize(by_page[number]["search_text"])
        canaries.append({"page": number, "expected": expected, "passed": passed})
    structured = {
        "schema_version": SCHEMA_VERSION,
        "source": {"path": str(args.source), "pages": len(pages)},
        "pages": pages,
        "comparison": {"tesseract": tesseract},
        "review_queue": [],
        "acceptance": {
            "zero_page_loss": len(pages) == len(images),
            "all_pages_have_images": all(page["image"] for page in pages),
            "all_pages_have_ocr": all(page["lines"] for page in pages),
            "all_canaries_passed": all(item["passed"] for item in canaries),
            "canaries": canaries,
            "vision_review_pages": len(vision),
        },
    }
    (args.output_dir / "structured.json").write_text(
        json.dumps(structured, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "index.html").write_text(build_html(args.title, pages), encoding="utf-8")
    report = {
        "schema_version": SCHEMA_VERSION,
        "pages": len(pages),
        "page_images": len(images),
        "ocr_pages": sum(bool(page["lines"]) for page in pages),
        "vision_review_pages": len(vision),
        "canaries": canaries,
        "visual_contract": "Each page image is the rendered source page; OCR never reflows visual content.",
    }
    (args.output_dir / "verification-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"pages: {len(pages)}")
    print(f"vision_review_pages: {len(vision)}")
    print(f"output: {args.output_dir / 'index.html'}")
    return 0 if structured["acceptance"]["zero_page_loss"] and structured["acceptance"]["all_pages_have_ocr"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
