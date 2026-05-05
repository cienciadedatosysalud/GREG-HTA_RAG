# Raw Data Input

This directory is the **entry point** for the ingestion pipeline. All source documents intended for processing must be placed here.

## 📌 Purpose
The `raw/` folder is monitored by the system to identify new knowledge sources. The pipeline reads the documents in this folder to perform OCR, text extraction, and entity recognition.

## 📁 Accepted Formats
* **PDF (.pdf)**: The system is currently optimized for PDF guides and documentation.
* **Text Preparation**: For best results, ensure the PDFs are text-searchable (not just scanned images) or ensure the OCR engine is properly configured in your `.env` file.

## ⚙️ Ingestion Workflow
1. **Upload**: Place your PDF file(s) inside this `data/raw/` directory.
2. **Execution**: Run `make ingest` from the root of the `greg-graphrag-wp1` folder.
3. **Analysis**: The system will parse these files and move the structured results (JSONL) to the `processed/` folder.

## ⚠️ Important Notes
* **File Names**: Avoid using special characters or excessive spaces in filenames to ensure compatibility with the processing scripts.
* **Cleaning**: Once a file has been successfully processed and its data is persistent in FalkorDB/LanceDB, you may archive the raw file to keep this directory organized.
* **Duplicate Prevention**: The system checks for existing records to avoid re-processing the same file unless the `processed/` data is cleared.

---
*Part of the GREG GraphRAG Project*