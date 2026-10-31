import base64
import io
from pathlib import Path
from typing import List, Optional, Tuple
import unicodedata
import zipfile

import pymupdf as fitz
from docx import Document


class DocumentParser:
    """Parses uploaded document bytes and extracts text for accepted student file types."""

    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".py", ".java", ".cpp", ".js", ".ts"}

    @staticmethod
    def parse_document(
        content: bytes,
        file_name: str,
    ) -> Tuple[str, Optional[str], Optional[List[str]], str]:
        file_ext = Path(file_name).suffix.lower()
        if file_ext == ".pdf":
            return DocumentParser._parse_pdf(content)
        if file_ext == ".docx":
            return DocumentParser._parse_docx(content)
        if file_ext in {".py", ".java", ".cpp", ".js", ".ts"}:
            return DocumentParser._parse_code(content)
        raise ValueError(f"Unsupported file type: {file_ext}")

    @staticmethod
    def _parse_pdf(content: bytes) -> Tuple[str, None, Optional[List[str]], str]:
        if not content.startswith(b"%PDF"):
            raise ValueError("This file is not a valid PDF. Please upload a PDF file.")
        text = ""
        try:
            doc = fitz.open(stream=content, filetype="pdf")
            extraction_flags = (
                fitz.TEXTFLAGS_TEXT
                & ~fitz.TEXT_PRESERVE_LIGATURES
                & ~fitz.TEXT_USE_CID_FOR_UNKNOWN_UNICODE
            )
            for page_num in range(doc.page_count):
                page = doc.load_page(page_num)
                page_text = unicodedata.normalize(
                    "NFKC",
                    page.get_text("text", flags=extraction_flags),
                )
                if not page_text.strip():
                    raise ValueError("This PDF has no readable text. It looks scanned. Please upload a text-based PDF or a DOCX.")
                text += f"--- Page {page_num + 1} ---\n{page_text}\n"
            doc.close()
            return text, None, None, "pdf"
        except ValueError:
            raise
        except Exception as error:
            raise ValueError(f"Error parsing PDF: {error}") from error

    @staticmethod
    def _parse_docx(content: bytes) -> Tuple[str, None, Optional[List[str]], str]:
        text = ""
        images_base64 = []
        try:
            if not zipfile.is_zipfile(io.BytesIO(content)):
                raise ValueError("This DOCX is invalid. Please upload a readable DOCX file.")
            with zipfile.ZipFile(io.BytesIO(content)) as zip_file:
                names = set(zip_file.namelist())
                if "word/document.xml" not in names:
                    raise ValueError("This DOCX is invalid. Please upload a readable DOCX file.")
                zip_file.read("word/document.xml")
                doc = Document(io.BytesIO(content))
                for para in doc.paragraphs:
                    if para.text:
                        text += para.text + "\n"
                for table in doc.tables:
                    for row in table.rows:
                        text += " | ".join(cell.text.strip() for cell in row.cells) + "\n"
                for rel in doc.part.rels.values():
                    if (
                        hasattr(rel, "target_ref")
                        and "image" in str(rel.target_ref)
                        and not getattr(rel, "is_external", False)
                    ):
                        encoded = base64.b64encode(rel.target_part.blob).decode("utf-8")
                        images_base64.append(f"data:image/png;base64,{encoded}")
                if not text.strip():
                    raise ValueError("This DOCX has no readable text. Please upload a readable DOCX file.")
            return text, None, images_base64 or None, "docx"
        except ValueError:
            raise
        except Exception as error:
            raise ValueError(f"Error parsing DOCX: {error}") from error

    @staticmethod
    def _parse_code(content: bytes) -> Tuple[str, str, None, str]:
        code = content.decode("utf-8", errors="ignore")
        return code, code, None, "code"
