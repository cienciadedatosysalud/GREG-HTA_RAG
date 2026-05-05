# --- CONFIGURATION ---
CONTAINER_NAME=greg_rag_backend
PYTHON=python

.PHONY: help ingest metadata central status rollback logs clean

help:
	@echo "🛠️  GREG COMMAND CENTER - WP1"
	@echo "--------------------------------------------"
	@echo "🔍 PIPELINE & ANALYSIS:"
	@echo "  make ingest         - Run full pipeline (Only new/unprocessed files)"
	@echo "  make central        - Recalculate Graph Centrality (Degrees/CDLP Communities)"
	@echo "  make sync           - Vectorize relationships in LanceDB (Enables Semantic Chat)"
	@echo "  make enrich         - MASTER: Run Centrality + Vector Sync (Graph Intelligence)"
	@echo "  make status         - Display Live Catalog status (LanceDB + FalkorDB)"
	@echo ""
	@echo "🧹 MAINTENANCE & CLEANUP:"
	@echo "  make logs           - Follow container logs in real-time"
	@echo "  make clean          - Remove temporary reports"
	@echo "  make clean-registry - Wipe document tracking (LanceDB) - Does NOT delete graph"
	@echo "  make clean-all-data - HARD RESET: Wipe FalkorDB and all Vector DBs"

# --- EXECUTION COMMANDS ---

ingest:
	@echo "🚀 Launching Idempotent Ingestion..."
	docker exec -it $(CONTAINER_NAME) $(PYTHON) src/main_pipeline.py

central:
	@echo "📊 Recalculating Centrality..."
	docker exec -it $(CONTAINER_NAME) $(PYTHON) src/logic/centrality.py

sync:
	@echo "📥 Vectorizing Knowledge for Chat (LanceDB)..."
	docker exec -it $(CONTAINER_NAME) $(PYTHON) -m src.logic.vector_sync

enrich: central sync
	@echo "🏁 Graph is now fully analyzed and searchable via Vectors."

status:
	@echo "📑 Querying Live Catalog..."
	docker exec -it $(CONTAINER_NAME) $(PYTHON) src/check_status.py

logs:
	docker logs -f $(CONTAINER_NAME)

clean:
	@echo "🧹 Cleaning up reports and temp files..."
	rm -f data/processed/*
	@echo "✨ Cleanup complete."

clean-registry:
	docker exec -it greg_rag_backend rm -rf /app/data/lancedb/document_registry.lance
	@echo "✅ Document record deleted (LanceDB)."

# Delete all data (Graph and Vector DB) - WARNING: This will reset everything
clean-all-data:
	docker exec -it falkordb_greg redis-cli FLUSHALL
	docker exec -it greg_rag_backend rm -rf /app/data/lancedb/document_registry.lance
	docker exec -it greg_rag_backend rm -rf /app/data/lancedb/graph_relationships.lance
	@echo "🚨  System completely reset."

# Restart the backend quickly
restart:
	docker-compose restart greg_backend