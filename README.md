![GREG LOCO](greg-graphrag-wp1/frontend/public/Greg_Logo_Horizontal_RGB_Berry.png)
# GREG GraphRAG Project

A specialized Knowledge Graph-based RAG (Retrieval-Augmented Generation) system. This project integrates **FalkorDB** (Graph Database), **LanceDB** (Vector Store), and **Ollama** (LLM) to transform static PDF documentation into an intelligent, navigable, and queryable assistant.

---

## 📂 Repository Structure

* **`archive/`**: Ontological documentation and evolution.
    * `ontology_v0.0.1/`: Initial entity-relationship definitions.
    * `ontology_v0.0.2/`: Current production-ready ontology.
    > **Note:** Ontologies are stored in **DuckDB database files** for efficient local querying and version tracking.
* **`greg-graphrag-wp1/`**: **Main Project Root**. All commands must be executed from this directory.
    * **`frontend/`**: The web-based Chatbot interface (built with Astro & React).
    * **`src/`**: The core intelligence of the project:
        * **Ingestion Logic**: Scripts to parse PDFs and map them to the ontology.
        * **API**: The backend service that bridges the Chatbot with the databases.
    * **`data/`**: Persistent storage and input directory.
        * `raw/`: Source PDF files.
        * `processed/`: Extracted JSONL data.
        * `falkordb/` & `lancedb/`: Database binary storage.

---

## 🛠 Prerequisites & System Setup

Before launching the project, ensure your environment meets these requirements:

1.  **Docker Desktop / Engine**: Must be installed and running.
2.  **Docker Compose**: Ensure you have version 2.0 or higher.
3.  **Make**: Required to run the automated ingestion pipeline.
    * **Windows**: Install via [Scoop](https://scoop.sh/): `scoop install make`
    * **Linux/Mac**: Usually pre-installed or via `sudo apt install make`.
4.  **Ollama (LLM Provider)**:
    * The project expects an LLM service (like Llama3 or Gemma4) running via Ollama.
    * If running Ollama on the same machine (outside Docker), the host address in `.env` should be `http://host.docker.internal:11434`.

---

## 🚀 Execution Guide (Step-by-Step)

Follow these steps in order to set up and run the system:

### 1. Initialize Configuration
Navigate to the project root and prepare your environment variables:
```bash
cd greg-graphrag-wp1
cp .env.example .env
```
Open `.env` and configure your LLM settings and service ports.

### 2. Deploy the Infrastructure
Build and start the database, backend, and frontend containers:
```bash
docker-compose up -d --build
```

### 3. Data Preparation
Place the PDF guide you wish to analyze inside the `raw` folder:
* **Path:** `greg-graphrag-wp1/data/raw/your_guide.pdf`

### 4. Run Ingestion Pipeline
With the containers running and the PDF in place, execute the extraction process:
```bash
make ingest
```
This command triggers a Python worker that:
1.  Reads the PDF from `data/raw/`.
2.  Extracts entities and relations into `data/processed/*.jsonl`.
3.  Populates **FalkorDB** with the graph and **LanceDB** with vector embeddings.

---

## 🌐 Access Points

| Service | Address | Function |
| :--- | :--- | :--- |
| **GREG Chatbot UI** | [http://localhost](http://localhost) | Interactive interface to query the processed guides. |
| **FalkorDB Browser** | [http://localhost:3000](http://localhost:3000) | Visual exploration of the Knowledge Graph nodes and edges. |

---

### Stopping the System
* **Stop**: `docker-compose stop` (keeps containers, saves time on restart).
* **Down**: `docker-compose down` (removes containers and internal networks).

---
