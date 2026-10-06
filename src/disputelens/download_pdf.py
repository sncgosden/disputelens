"""Download the selected Visa guide without parsing or indexing it."""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx


URL = (
    "https://usa.visa.com/content/dam/VCOM/global/support-legal/"
    "documents/merchants-dispute-management-guidelines.pdf"
)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DESTINATION = PROJECT_ROOT / "data" / "raw" / "visa-dispute-management-guide"
MAX_BYTES = 20 * 1024 * 1024


def main() -> int:
    pdf_path = DESTINATION / "source.pdf"
    metadata_path = DESTINATION / "provenance.json"
    if pdf_path.exists() or metadata_path.exists():
        print("STOP: a saved copy already exists. Review it before replacing it.")
        return 1
    print(f"Downloading: {URL}")
    try:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            with client.stream(
                "GET", URL,
                headers={"Accept": "application/pdf", "User-Agent": "DisputeLens-learning-project/0.1"},
            ) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                chunks = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("PDF exceeds the 20 MB download limit")
                    chunks.append(chunk)
                content = b"".join(chunks)
                if not content.startswith(b"%PDF-"):
                    raise ValueError("Response is not a PDF; nothing saved")
                resolved_url = str(response.url)
                etag = response.headers.get("etag")
                last_modified = response.headers.get("last-modified")
    except (httpx.HTTPError, ValueError) as error:
        print(f"Download failed: {error}")
        return 1

    metadata = {
        "source_id": "visa-dispute-management-guide",
        "title": "Dispute Management Guidelines for Visa Merchants",
        "publisher": "Visa",
        "requested_url": URL,
        "resolved_url": resolved_url,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "document_type": "pdf",
        "corpus": "real",
        "scheme": "Visa",
        "scope": "Visa merchant dispute guidance; preserve regional qualifications",
        "edition_seen_during_selection": "June 2024",
        "downloaded_edition_verified": False,
        "effective_date": None,
        "selected_sections": ["13.1", "13.2", "13.6"],
        "content_type": content_type,
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "etag": etag,
        "last_modified": last_modified,
    }
    DESTINATION.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(content)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"SAVED PDF: {pdf_path.relative_to(PROJECT_ROOT)}")
    print(f"SAVED METADATA: {metadata_path.relative_to(PROJECT_ROOT)}")
    print(f"Downloaded {len(content):,} bytes.")
    print("Open the PDF and check its edition. Parsing and indexing have not run yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
