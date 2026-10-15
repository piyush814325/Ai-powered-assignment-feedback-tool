import base64
import io
from pathlib import Path
from typing import List, Optional, Tuple

import fitz
import pytesseract
from docx import Document
from PIL import Image

from app.config import VERIFICATION_MIN_CONTENT_CHARS


class DocumentParser:
    """Parses uploaded document bytes and extracts text, code, and images."""

    ALLOWED_EXTENSIONS = {
        ".pdf", ".docx", ".txt", ".py", ".java", ".cpp", ".js", ".ts",
        ".png", ".jpg", ".jpeg",
    }

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
        if file_ext in {".png", ".jpg", ".jpeg"}:
            return DocumentParser._parse_image(content)
        if file_ext in {".py", ".java", ".cpp", ".js", ".ts", ".txt"}:
            return DocumentParser._parse_code(content, file_ext)
        raise ValueError(f"Unsupported file type: {file_ext}")

    @staticmethod
    def _parse_pdf(content: bytes) -> Tuple[str, None, Optional[List[str]], str]:
        text = ""
        images_base64 = []
        try:
            doc = fitz.open(stream=content, filetype="pdf")
            for page_num in range(doc.page_count):
                page = doc.load_page(page_num)
                page_text = page.get_text("text")
                if len(" ".join(str(page_text).split())) < VERIFICATION_MIN_CONTENT_CHARS:
                    try:
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                        page_image = Image.open(io.BytesIO(pix.tobytes("png")))
                        ocr_text = pytesseract.image_to_string(page_image)
                        if ocr_text.strip():
                            page_text = f"{page_text}\n{ocr_text}"
                    except Exception:
                        pass
                text += f"--- Page {page_num + 1} ---\n{page_text}\n"

                for image_info in page.get_images():
                    try:
                        pix = fitz.Pixmap(doc, image_info[0])
                        if pix.n >= 5:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        image_data = pix.tobytes("png")
                        encoded = base64.b64encode(image_data).decode("utf-8")
                        images_base64.append(f"data:image/png;base64,{encoded}")
                    except Exception:
                        continue
            doc.close()
            return text, None, images_base64 or None, "pdf"
        except Exception as error:
            raise ValueError(f"Error parsing PDF: {error}") from error

    @staticmethod
    def _parse_docx(content: bytes) -> Tuple[str, None, Optional[List[str]], str]:
        text = ""
        images_base64 = []
        try:
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
            return text, None, images_base64 or None, "docx"
        except Exception as error:
            raise ValueError(f"Error parsing DOCX: {error}") from error

    @staticmethod
    def _parse_image(content: bytes) -> Tuple[str, None, Optional[List[str]], str]:
        try:
            image = Image.open(io.BytesIO(content))
            try:
                text = pytesseract.image_to_string(image)
            except Exception:
                text = "[OCR text extraction unavailable: Tesseract engine not found on server]"
            encoded = base64.b64encode(content).decode("utf-8")
            return text, None, [f"data:image/png;base64,{encoded}"], "image"
        except Exception as error:
            raise ValueError(f"Error parsing image: {error}") from error

    @staticmethod
    def _parse_code(content: bytes, file_ext: str) -> Tuple[str, str, None, str]:
        code = content.decode("utf-8", errors="ignore")
        return code, code, None, "code" if file_ext != ".txt" else "txt"
