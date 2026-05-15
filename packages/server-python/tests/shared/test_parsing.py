def test_pdf_parser_extracts_text():
    from app.shared.parsing.pdf_parser import extract_pdf_text
    assert callable(extract_pdf_text)


def test_docx_parser_extracts_text():
    from app.shared.parsing.docx_parser import extract_docx_text
    assert callable(extract_docx_text)


def test_xlsx_parser_extracts_rows():
    from app.shared.parsing.xlsx_parser import extract_xlsx_rows
    assert callable(extract_xlsx_rows)


def test_chunker_splits_by_heading():
    from app.shared.parsing.chunker import chunk_by_structure
    assert callable(chunk_by_structure)
