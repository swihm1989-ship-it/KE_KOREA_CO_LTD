"""Local extraction of reference contract text with traceable page/paragraph locations."""
import hashlib
import io
import re
import zipfile
from xml.etree import ElementTree


MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 100
MAX_FILES_PER_REQUEST = 5


def extract_reference(file_bytes, filename, *, vision_client=None):
    if not isinstance(file_bytes, bytes) or not file_bytes:
        raise ValueError("The reference document is empty.")
    if len(file_bytes) > MAX_FILE_BYTES:
        raise ValueError("Reference documents are limited to 20 MB each.")
    name = str(filename or "")
    suffix = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    digest = hashlib.sha256(file_bytes).hexdigest()
    if suffix == "pdf":
        try:
            import fitz
            document = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as exc:
            raise ValueError("Could not read this PDF; it may be damaged or encrypted.") from exc
        if document.is_encrypted:
            raise ValueError("Password-protected reference PDFs must be unlocked before upload.")
        if document.page_count > MAX_PDF_PAGES:
            raise ValueError("Reference PDFs are limited to 100 pages.")
        locations = []
        scanned_pages = []
        uncertain_pages = []
        for page_index in range(document.page_count):
            page_number = page_index + 1
            page = document.load_page(page_index)
            text = page.get_text("text").strip()
            if text:
                locations.append({"locator": f"page {page_number}", "text": text})
            else:
                scanned_pages.append(page_number)
        if scanned_pages and vision_client:
            for page_number in scanned_pages:
                page = document.load_page(page_number - 1)
                pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                extracted = vision_client(pixmap.tobytes("png"), page_number)
                if str(extracted or "").strip():
                    locations.append({"locator": f"page {page_number}", "text": str(extracted).strip()})
                    if "needs manual review" in str(extracted).casefold():
                        uncertain_pages.append(page_number)
        if not locations:
            status = "scanned_requires_ocr"
        elif scanned_pages and (not vision_client or uncertain_pages):
            status = "partial" if not vision_client else "extracted"
            if uncertain_pages:
                status = "partial"
        else:
            status = "extracted"
        text = "\n\n".join(f"[{entry['locator']}]\n{entry['text']}" for entry in locations)
        return {"filename": name, "content_hash": digest, "extraction_status": status,
                "extracted_text": text, "source_locations": locations,
                "scanned_pages": scanned_pages, "uncertain_pages": uncertain_pages}
    if suffix == "docx":
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
                xml_bytes = archive.read("word/document.xml")
                if len(xml_bytes) > 30 * 1024 * 1024:
                    raise ValueError("The DOCX expanded content exceeds the 30 MB processing limit.")
                xml = ElementTree.fromstring(xml_bytes)
        except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
            raise ValueError("Could not read this DOCX; verify the document is not damaged.") from None
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = []
        for index, paragraph in enumerate(xml.findall(".//w:body//w:p", namespace), 1):
            text = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace)).strip()
            if text:
                paragraphs.append({"locator": f"paragraph {index}", "text": text})
        if not paragraphs:
            raise ValueError("The DOCX contains no readable text.")
        return {"filename": name, "content_hash": digest, "extraction_status": "extracted",
                "extracted_text": "\n\n".join(f"[{entry['locator']}]\n{entry['text']}" for entry in paragraphs),
                "source_locations": paragraphs, "scanned_pages": []}
    if suffix == "doc":
        raise ValueError("Legacy .doc files are not supported. Save the document as PDF or DOCX.")
    raise ValueError("Upload PDF or DOCX reference contracts only.")


def candidate_clauses(reference):
    """Split extracted reference text into selectable clause candidates."""
    candidates = []
    for location in reference.get("source_locations", []):
        for paragraph in re.split(r"\n\s*\n", location.get("text", "")):
            text = paragraph.strip()
            if len(text) >= 50:
                candidates.append({"text": text, "locator": location.get("locator", "")})
    return candidates
