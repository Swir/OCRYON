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
- [x] TXT export for the current page
- [ ] Bundled OCR runtime and language data
- [ ] DOCX / searchable PDF export
- [ ] Image preprocessing and OCR quality controls
- [ ] Installer

## Principles

- Offline-first: documents stay on the user's computer.
- Modern Windows 10/11 desktop UI.
- OCR engine separated from the UI so recognition backends can evolve independently.
- Multilingual architecture with English fallback.
- No subscription.

## Planned stack

- Python 3.12
- PySide6 / Qt
- PyMuPDF
- Pillow
- Local OCR backend

## Development OCR

Current development builds use the Tesseract backend. Set the `OCRYON_TESSERACT`
environment variable to a local `tesseract.exe`, or make Tesseract available on
`PATH`. Release builds are planned to bundle the runtime so users do not need a
separate OCR installation.

## License

License will be selected before the first public alpha release.
