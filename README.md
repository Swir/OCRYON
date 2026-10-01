# OCRYON

**Local-first intelligent document recognition for Windows.**

OCRYON is an open-source desktop OCR application focused on fast, private and convenient conversion of scans, screenshots, photos and PDF pages into editable text.

## Project status

**0.2.0 Alpha — active development**

Public test Beta `v0.1.0-beta.1` is frozen for user testing. Development continues on `dev/0.2.0` without rewriting the historical Beta release.

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
- [x] Bundled OCR runtime and ENG/PL/NOR language data
- [x] Windows EXE/ZIP packaging pipeline
- [x] Windows installer pipeline
- [x] Word-level OCR coordinates and first-pass layout reconstruction
- [ ] Advanced preprocessing controls
- [ ] Accessibility and HiDPI polish
- [ ] Diagnostics and recovery UI
- [ ] 0.2.0 frozen Windows package/installer smoke
- [ ] Stable 0.2.0 release

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
`PATH`. Release candidates bundle the runtime and ENG/PL/NOR data so testers do
not need a separate OCR installation.

## Current workflow

1. Open an image or multi-page PDF.
2. Preview individual pages.
3. Recognize one page or the full loaded batch.
4. OCR runs outside the GUI thread.
5. Word-level coordinates are captured for layout-aware exports.
6. Edit recognized text per page.
7. Export recognized pages to TXT, DOCX or searchable PDF.

Manual edits intentionally invalidate stale OCR coordinates for that page, so searchable-PDF export falls back to the edited page text instead of exporting mismatched layout data.

## License

License will be selected before the first stable release.
