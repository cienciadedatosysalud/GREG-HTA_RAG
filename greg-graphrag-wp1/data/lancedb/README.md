# LanceDB Vector Store

This directory serves as the **persistent storage** for the LanceDB vector database.

## 📌 Purpose
This folder contains the specialized file formats (Lance format) used to store:
* **Vector Embeddings**: High-dimensional representations of your extracted concepts.
* **Metadata**: Attributes and links associated with each vector.
* **Indexing Data**: Optimized structures that allow for high-speed similarity searches.

## 📁 Storage Details
* **Format**: Unlike traditional SQL databases, LanceDB stores data in a column-oriented, high-performance file format.
* **Persistence**: This directory is mapped as a volume in Docker to ensure that your processed data remains available across container restarts.

## ⚠️ Important Notes
* **Data Integrity**: Avoid modifying or renaming the files inside this directory manually, as it may corrupt the vector table.
* **Version Control**: Large data files in this folder should be excluded from Git via `.gitignore`. Only the schema and ingestion logic should be tracked.
* **Performance**: This folder is optimized for fast I/O. Ensure it is stored on a high-speed disk (SSD) for optimal search performance.

---
*Part of the GREG GraphRAG Project*