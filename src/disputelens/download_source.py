"""Save selected public sources and their download provenance."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx


URL = "https://docs.stripe.com/disputes/responding"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", choices=["stripe", "visa"], default="stripe")
    args = parser.parse_args()
    is_pdf = args.source == "visa"
    source_id = "visa-dispute-management-june-2024" if is_pdf else "stripe-respond-to-disputes"
    url = (
        "https://usa.visa.com/content/dam/VCOM/global/support-legal/documents/merchants-dispute-management-guidelines.pdf"
        if is_pdf else URL
    )
    destination = PROJECT_ROOT / "data" / "raw" / source_id
    source_path = destination / ("source.pdf" if is_pdf else "source.html")
    metadata_path = destination / "provenance.json"
    if source_path.exists() or metadata_path.exists():
        print("STOP: a saved copy already exists. Review it before replacing it.")
        return 1
    print(f"Downloading: {url}")
    try:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            response = client.get(
                url,
                headers={
                    "Accept": "application/pdf" if is_pdf else "text/html",
                    "User-Agent": "DisputeLens-learning-project/0.1",
                },
            )
            response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        expected_type = "application/pdf" if is_pdf else "text/html"
        if expected_type not in content_type.lower():
            raise ValueError(f"Expected {expected_type}, received {content_type!r}")
        content = response.content
        if is_pdf and not content.startswith(b"%PDF-"):
            raise ValueError("Response does not look like a PDF")
        if not is_pdf and (not content or b"<html" not in content.lower()):
            raise ValueError("Response does not look like an HTML page")
    except (httpx.HTTPError, ValueError) as error:
        print(f"Download failed: {error}")
        return 1

    metadata = {
        "source_id": source_id,
        "title": "Dispute Management Guidelines for Visa Merchants" if is_pdf else "Respond to disputes",
        "publisher": "Visa" if is_pdf else "Stripe",
        "requested_url": url,
        "resolved_url": str(response.url),
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "document_type": "pdf" if is_pdf else "html",
        "corpus": "real",
        "provider": None if is_pdf else "Stripe",
        "scheme": "Visa" if is_pdf else None,
        "scope": "Visa merchant dispute guidance; initial extraction: conditions 13.1, 13.2, 13.6" if is_pdf else "Stripe merchant dispute-response guidance",
        "edition": "June 2024" if is_pdf else None,
        "edition_basis": "Selected edition verified on source page; confirm downloaded PDF before parsing" if is_pdf else None,
        "publication_date": None,
        "effective_date": None,
        "content_type": content_type,
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "etag": response.headers.get("etag"),
        "last_modified": response.headers.get("last-modified"),
    }
    destination.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(content)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"SAVED {'PDF' if is_pdf else 'HTML'}: {source_path.relative_to(PROJECT_ROOT)}")
    print(f"SAVED METADATA: {metadata_path.relative_to(PROJECT_ROOT)}")
    print(f"Downloaded {len(content):,} bytes.")
    print("Download complete. Parsing and indexing have not run yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
