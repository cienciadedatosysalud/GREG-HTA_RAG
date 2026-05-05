# FalkorDB Persistence Store

This directory is used to maintain **data persistence** for the FalkorDB service. 

## 📌 Purpose
FalkorDB stores its graph snapshots and log files here. By mapping this local folder to the Docker container, all graph data, entities, and relationships are preserved even if the containers are stopped, removed, or updated.

## 📁 Storage Details
* **Snapshot Files**: Binary representations of the graph database.
* **Persistence Mode**: Configured via `docker-compose.yml` through volume mapping.

## ⚠️ Important Notes
* **Do Not Delete**: Deleting files in this folder will result in total loss of the ingested knowledge graph.
* **Permissions**: Ensure the Docker daemon has read/write permissions for this directory.
* **Git**: Typically, the contents of this folder are ignored by Git (via `.gitignore`) to avoid committing large binary database files.

---
*Part of the GREG GraphRAG Project*