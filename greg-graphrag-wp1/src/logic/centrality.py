from src.shared.db_clients import get_graph

def calculate_graph_centrality():
    """
    Computes high-performance graph metrics directly inside FalkorDB.
    Uses CDLP for community detection and Pure Cypher for degree/frequency.
    Designed to handle 35+ custom relationship types (HINDERS_LEGAL, etc.)
    """
    graph = get_graph()
    
    print("🚀 Starting Centrality & Analytics Pipeline...")

    # 1. Real Evidence Frequency (Unique Documents)
    # Counts how many distinct PDF files support each entity
    print("📈 Updating Document Frequency (Consensus)...")
    try:
        graph.query("""
            MATCH (e:Entity)
            OPTIONAL MATCH (e)-[:MENTIONED_IN]->(p:ParentChunk)<-[:CONTAINS]-(d:Document)
            WITH e, count(DISTINCT d) AS unique_docs
            SET e.doc_frequency = unique_docs
        """)
        print("✅ Document frequency updated.")
    except Exception as e:
        print(f"⚠️ Error in Doc Frequency: {e}")

    # 2. Knowledge Connections (Differentiated Degree)
    # Analyzes connections between entities, ignoring document structure
    print("📈 Updating Knowledge Degrees (Out/In)...")
    try:
        graph.query("""
            MATCH (e:Entity)
            OPTIONAL MATCH (e)-[r]->(m:Entity)
            WITH e, count(DISTINCT m) AS out_k
            OPTIONAL MATCH (e)<-[r2]-(m2:Entity)
            WITH e, out_k, count(DISTINCT m2) AS in_k
            SET e.knowledge_out_degree = out_k,
                e.knowledge_in_degree = in_k
        """)
        print("✅ Knowledge degrees updated.")
    except Exception as e:
        print(f"⚠️ Error in Degrees: {e}")

    # 3. Community Detection (CDLP - Label Propagation)
    # Groups entities into clusters based on ALL your normalized relations
    print("🌐 Detecting thematic communities (Streaming Update)...")
    try:
        graph.query("""
            CALL algo.labelPropagation({
                nodeLabels: ['Entity'],
                maxIterations: 25
            }) 
            YIELD node, communityId
            SET node.community = communityId
        """)
        print("✅ Communities updated manually via Stream.")
    except Exception as e:
        print(f"⚠️ algo.labelPropagation failed: {e}")


    print("✅ Centrality sync complete. Metrics are now persistent in the graph.")

if __name__ == "__main__":
    calculate_graph_centrality()