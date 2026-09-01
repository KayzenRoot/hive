from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.config import Settings
from app.task_intake import (
    IntakeValidationError,
    TaskTextRequest,
    validate_structured_source,
    validate_upload_source,
)


def settings_for(tmp_path: Path) -> Settings:
    return Settings(
        data_root=tmp_path / "data",
        task_max_upload_bytes=1024 * 1024,
        task_max_extracted_text_bytes=1024,
        task_max_structured_text_bytes=1024,
        task_max_pdf_pages=4,
    )


def make_text_pdf(path: Path, values: list[str]) -> None:
    writer = PdfWriter()
    for value in values:
        page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        content = DecodedStreamObject()
        content.set_data(f"BT /F1 12 Tf 72 200 Td ({value}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(content)
    with path.open("wb") as handle:
        writer.write(handle)


def test_txt_bom_and_markdown_normalize_only_derived_text(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    txt = tmp_path / "instructions.txt"
    original = b"\xef\xbb\xbffirst\r\nsecond\rthird"
    txt.write_bytes(original)
    markdown = tmp_path / "notes.md"
    markdown.write_bytes(b"# Title\r\n\r\nBody")

    txt_source = validate_upload_source(txt, txt.name, settings)
    markdown_source = validate_upload_source(markdown, markdown.name, settings)

    assert txt.read_bytes() == original
    assert txt_source.source_type == "TXT"
    assert txt_source.extraction.text == "first\nsecond\nthird"
    assert markdown_source.source_type == "MARKDOWN"
    assert markdown_source.extraction.text == "# Title\n\nBody"


def test_structured_text_is_deterministic_and_utf8_bounded(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    path = tmp_path / "structured.part"
    path.write_bytes(b"title\r\nbody")

    source = validate_structured_source(
        path, TaskTextRequest(title="Task", text="title\r\nbody", format="text"), settings
    )

    assert source.source_type == "STRUCTURED_TEXT"
    assert source.extraction.text == "title\nbody"
    assert path.read_bytes() == b"title\r\nbody"


def test_invalid_binary_and_unsupported_pdf_magic_are_rejected(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    binary = tmp_path / "binary.txt"
    binary.write_bytes(b"not text\x00payload")
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"not a pdf")

    with pytest.raises(IntakeValidationError):
        validate_upload_source(binary, binary.name, settings)
    with pytest.raises(IntakeValidationError):
        validate_upload_source(fake_pdf, fake_pdf.name, settings)


def test_text_layer_pdf_is_bounded_and_deterministic(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    pdf = tmp_path / "text-layer.pdf"
    make_text_pdf(pdf, ["Hello HIVE", "Second page"])

    first = validate_upload_source(pdf, pdf.name, settings)
    second = validate_upload_source(pdf, pdf.name, settings)

    assert first.source_type == "PDF"
    assert first.extraction.status == "READY"
    assert first.extraction.page_count == 2
    assert first.extraction.text == second.extraction.text == "Hello HIVE\nSecond page"


def test_no_text_pdf_is_retained_as_explicit_failure(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    pdf = tmp_path / "empty.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    with pdf.open("wb") as handle:
        writer.write(handle)

    source = validate_upload_source(pdf, pdf.name, settings)

    assert source.extraction.status == "EXTRACTION_FAILED"
    assert source.extraction.error == "no_extractable_text"
    assert source.extraction.page_count == 1
    assert pdf.read_bytes().startswith(b"%PDF-")


def test_upload_text_limit_is_rejected(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    path = tmp_path / "large.txt"
    path.write_bytes(b"x" * 1025)

    with pytest.raises(IntakeValidationError, match="size limit"):
        validate_upload_source(path, path.name, settings)
