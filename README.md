# OCRYON

**Local-first intelligent document recognition for Windows.**

OCRYON is an open-source desktop OCR application focused on fast, private and convenient conversion of scans, screenshots, photos and PDF pages into editable text.

## Project status

**0.1 Alpha — active development**

- [x] Project architecture
- [x] Windows-first desktop target
- [x] Image/PDF import
- [x] Document preview
- [x] Offline OCR backend architecture
- [x] Editable per-page recognition results
- [x] Background OCR without freezing the GUI
- [x] Batch OCR for all loaded pages
- [x] Automatic OCR image preprocessing
- [x] TXT export
- [x] DOCX export
- [x] Searchable PDF export with invisible OCR text layer
- [x] Original OCRYON application mark
- [ ] Bundled OCR runtime and language data
- [ ] Word-level OCR coordinates and layout reconstruction
- [ ] Advanced preprocessing controls
- [ ] Windows EXE packaging
- [ ] Windows installer

## Principles

- Offline-first: documents stay on the user's computer.
- Modern Windows 10/11 desktop UI.
- OCR engine separated from the UI so recognition backends can evolve independently.
- Multilingual architecture with English fallback.
- No subscription.

## Stack

- Python 3.12
- PySide6 / Qt
- PyMuPDF
- Pillow
- Tesseract OCR backend
- python-docx

## Development OCR

Current development builds use the Tesseract backend. Set the `OCRYON_TESSERACT`
environment variable to a local `tesseract.exe`, or make Tesseract available on
`PATH`. Release builds are planned to bundle the runtime so users do not need a
separate OCR installation.

## Current workflow

1. Open an image or multi-page PDF.
2. Preview individual pages.
3. Recognize one page or the full loaded batch.
4. OCR runs outside the GUI thread.
5. Edit recognized text per page.
6. Export recognized pages to TXT, DOCX or searchable PDF.

## License

License will be selected before the first public alpha release.
