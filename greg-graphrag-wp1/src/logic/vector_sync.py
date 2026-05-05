import pandas as pd
from src.shared.db_clients import get_graph, get_lance_db
from src.ingestion.persistence import get_embedding

def sync_relationships_to_lancedb():
    graph_kb = get_graph()
    db_lance = get_lance_db()
    
    print("📥 Downloading relationships from FalkorDB for vector indexing...")
    
    cypher = """
    MATCH (s:Entity)-[r]->(t:Entity)
    RETURN id(r) as rel_id, s.name as source, t.name as target, 
           type(r) as type, r.description as desc, r.verbs as verbs
    """
    res = graph_kb.query(cypher)
    
    data = []
    for row in res.result_set:
        rel_id, source, target, r_type, clean_description, verbs = row
        verbs_str = ", ".join(verbs) if isinstance(verbs, list) else str(verbs)
        
        # Enriched string for embedding (Relational semantics)
        text_to_embed = f"Relationship: {source} {r_type} {target}. Context: {clean_description}. Actions: {verbs_str}"
           
        data.append({
            "vector": get_embedding(text_to_embed),
            "id": str(rel_id),
            "source": source,
            "target": target,
            "type": r_type,
            "verbs": verbs_str,
            "text": clean_description
        })

    if data:
        df = pd.DataFrame(data)
        # Create or overwrite the table for vector search
        db_lance.create_table("graph_relationships", data=df, mode="overwrite")
        print(f"✅ {len(data)} relationships synchronized in LanceDB.")
    else:
        print("⚠️ No relationships found to synchronize.")

if __name__ == "__main__":
    sync_relationships_to_lancedb()