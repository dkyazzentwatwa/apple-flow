from __future__ import annotations

import zipfile
from pathlib import Path

from apple_flow.attachments import AttachmentProcessor


def test_extracts_text_file(tmp_path):
    text_file = tmp_path / "note.txt"
    text_file.write_text("hello from attachment", encoding="utf-8")
    processor = AttachmentProcessor()

    block, metadata = processor.build_prompt_block(
        "m1",
        [
            {
                "filename": "note.txt",
                "mime_type": "text/plain",
                "path": str(text_file),
            }
        ],
    )

    assert "Attached files (processed):" in block
    assert "status=ok" in block
    assert "hello from attachment" in block
    assert metadata[0]["status"] == "ok"


def test_pdf_reports_extractor_unavailable_without_pdftotext(tmp_path, monkeypatch):
    pdf_file = tmp_path / "doc.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 test")
    monkeypatch.setattr("apple_flow.attachments.shutil.which", lambda _name: None)
    processor = AttachmentProcessor()

    block, metadata = processor.build_prompt_block(
        "m2",
        [{"filename": "doc.pdf", "mime_type": "application/pdf", "path": str(pdf_file)}],
    )

    assert "status=pdf_extractor_unavailable" in block
    assert metadata[0]["status"] == "pdf_extractor_unavailable"


def test_image_reports_ocr_unavailable_without_tesseract(tmp_path, monkeypatch):
    image_file = tmp_path / "image.png"
    image_file.write_bytes(b"not-a-real-png")

    def _which(name: str):
        return None if name == "tesseract" else "/usr/bin/false"

    monkeypatch.setattr("apple_flow.attachments.shutil.which", _which)
    processor = AttachmentProcessor(enable_image_ocr=True)

    block, metadata = processor.build_prompt_block(
        "m3",
        [{"filename": "image.png", "mime_type": "image/png", "path": str(image_file)}],
    )

    assert "status=ocr_unavailable" in block
    assert f"path: {image_file}" in block
    assert "analyze this image directly from its file path" in block
    assert metadata[0]["status"] == "ocr_unavailable"
    assert metadata[0]["source_path"] == str(image_file)


def test_missing_file_is_marked():
    processor = AttachmentProcessor()
    block, metadata = processor.build_prompt_block(
        "m4",
        [{"filename": "missing.txt", "mime_type": "text/plain", "path": "/tmp/does-not-exist"}],
    )
    assert "status=missing_file" in block
    assert metadata[0]["status"] == "missing_file"


def test_truncation_limits_are_enforced(tmp_path):
    huge = tmp_path / "huge.txt"
    huge.write_text("x" * 500, encoding="utf-8")
    processor = AttachmentProcessor(
        max_text_chars_per_file=100,
        max_total_text_chars=80,
    )
    block, metadata = processor.build_prompt_block(
        "m5",
        [{"filename": "huge.txt", "mime_type": "text/plain", "path": str(huge)}],
    )
    assert "status=truncated" in block
    assert "Attachment text truncated due to max-total-text limit." in block
    assert metadata[0]["status"] == "truncated"


def test_docx_pptx_xlsx_extract_text(tmp_path):
    docx = tmp_path / "doc.docx"
    with zipfile.ZipFile(docx, "w") as zf:
        zf.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Hello DOCX</w:t></w:r></w:p></w:body></w:document>",
        )

    pptx = tmp_path / "slides.pptx"
    with zipfile.ZipFile(pptx, "w") as zf:
        zf.writestr(
            "ppt/slides/slide1.xml",
            '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            "<p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Hello PPTX</a:t></a:r></a:p>"
            "</p:txBody></p:sp></p:spTree></p:cSld></p:sld>",
        )

    xlsx = tmp_path / "sheet.xlsx"
    with zipfile.ZipFile(xlsx, "w") as zf:
        zf.writestr(
            "xl/sharedStrings.xml",
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<si><t>Hello XLSX</t></si></sst>",
        )
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData></worksheet>',
        )

    processor = AttachmentProcessor()
    block, metadata = processor.build_prompt_block(
        "m6",
        [
            {"filename": docx.name, "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "path": str(docx)},
            {"filename": pptx.name, "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation", "path": str(pptx)},
            {"filename": xlsx.name, "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "path": str(xlsx)},
        ],
    )

    statuses = {item["filename"]: item["status"] for item in metadata}
    assert statuses["doc.docx"] == "ok"
    assert statuses["slides.pptx"] == "ok"
    assert statuses["sheet.xlsx"] == "ok"
    assert "Hello DOCX" in block
    assert "Hello PPTX" in block
    assert "Hello XLSX" in block


def test_audio_attachment_transcription_suggests_voice_task(tmp_path, monkeypatch):
    audio_file = tmp_path / "voice-note.m4a"
    audio_file.write_bytes(b"fake audio bytes")

    def _fake_run_command(args: list[str], *, timeout: int = 30):
        output_dir = Path(args[args.index("--output_dir") + 1])
        (output_dir / f"{audio_file.stem}.txt").write_text("summarize the deployment plan", encoding="utf-8")
        return "", ""

    monkeypatch.setattr("apple_flow.attachments.shutil.which", lambda _name: "/opt/homebrew/bin/whisper")
    monkeypatch.setattr(AttachmentProcessor, "_run_command", staticmethod(_fake_run_command))

    processor = AttachmentProcessor()
    analysis = processor.analyze_attachments(
        "m-audio",
        [{"filename": audio_file.name, "mime_type": "audio/m4a", "path": str(audio_file)}],
    )

    assert analysis.voice_transcript == "summarize the deployment plan"
    assert analysis.suggested_text == "voice-task: summarize the deployment plan"
    assert analysis.suggested_reason == "voice_attachment_transcript"
    assert "kind=audio status=ok" in analysis.prompt_block
    assert "summarize the deployment plan" in analysis.prompt_block
    assert analysis.metadata[0]["media_kind"] == "audio"
