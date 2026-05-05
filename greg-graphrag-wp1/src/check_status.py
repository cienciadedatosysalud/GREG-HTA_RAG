import pandas as pd
from src.shared.db_clients import falkor_client, get_lance_db, GRAPH_NAME

def check_live_status():
    print("\n" + "="*60)
    print("📊 GREG LIVE CATALOG STATUS REPORT")
    print("="*60)

    # 1. Technical Registry (LanceDB)
    print("\n[📁 LANCE DB - TECHNICAL FILE REGISTRY]")
    try:
        db = get_lance_db()
        registry = db.open_table("document_registry")
        df_lance = registry.to_pandas()
        if df_lance.empty:
            print("📭 No technical records found.")
        else:
            # Reorder for readability
            cols = ['filename', 'status', 'timestamp', 'doc_id']
            print(df_lance[cols].to_string(index=False))
    except Exception as e:
        print(f"⚠️ Could not access document_registry table: {e}")

    # 2. Business Metadata (FalkorDB)
    print("\n[🕸️  FALKOR DB - GRAPH METADATA]")
    try:
        graph = falkor_client.select_graph(GRAPH_NAME)
        query = "MATCH (d:Document) RETURN d.filename, d.authority,d.region, d.year, d.title, d.link"
        res = graph.query(query)
        
        if not res.result_set:
            print("📭 No enriched documents found in the graph.")
        else:
            df_falkor = pd.DataFrame(res.result_set, columns=['Filename', 'Authority', 'Region', 'Year', 'Title', 'Link'])
            print(df_falkor.to_string(index=False))
    except Exception as e:
        print(f"⚠️ Could not access FalkorDB graph: {e}")
        
    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    check_live_status()