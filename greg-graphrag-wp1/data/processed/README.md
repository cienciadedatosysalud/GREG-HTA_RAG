# Processed Data Store (JSONL)

This directory contains the structured output from the extraction pipeline, stored in **JSONL (JSON Lines)** format.

## 📌 Purpose
The `processed/` folder acts as the staging area for extracted knowledge. By using `.jsonl` files, the system ensures that each extracted entity or relationship is stored as a separate, valid JSON object on a new line. This format allows for:
* **Streaming ingestion**: High efficiency when loading data into FalkorDB or LanceDB.
* **Scalability**: Better handling of large datasets compared to standard JSON arrays.

## 📁 Contents
* **Extraction Files (`*.jsonl`)**: These files contain the core intelligence extracted from the PDFs, including:
    * **Nodes**: Concepts and entities found in the text.
    * **Edges**: Semantic relationships between those concepts (triplets).
    * **Metadata**: References back to the original PDF page and text chunk.
* **Source Tracking**: Records of which PDF files have been successfully processed to avoid duplication.

## ⚙️ Workflow
1. **Extraction**: The pipeline reads the raw PDF from `data/raw/`.
2. **Serializing**: The extraction logic transforms text into structured objects and appends them to a `.jsonl` file here.
3. **Loading**: The ingestion script reads these lines one by one to populate the Graph and Vector databases.

## ⚠️ Important Notes
* **Data Format**: Each line in the `.jsonl` files must be a standalone valid JSON object.
* **Re-processing**: To force a clean re-ingestion of a specific document, remove its corresponding `.jsonl` file from this directory.
* **Debug**: These files are human-readable and can be inspected to verify the quality of the concept extraction before it reaches the database.

---
*Part of the GREG GraphRAG Project*