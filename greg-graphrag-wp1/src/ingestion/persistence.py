import re
from src.shared.db_clients import get_graph, client_ollama, EMBEDDING_MODEL, EMBEDDING_DIM
import json


def get_embedding(text):
    try:
        prefix = "search_document: "
        text_to_embed = prefix + text if not text.startswith(prefix) else text
        response = client_ollama.embeddings(model=EMBEDDING_MODEL, prompt=text_to_embed)
        return response["embedding"]
    except Exception as e:
        print(f"⚠️ Error embedding: {e}")
        return None

def init_db():
    
    try:
        graph = get_graph()
        indices = [
            "CREATE INDEX FOR (p:ParentChunk) ON (p.id)",
            "CREATE INDEX FOR (c:ChildChunk) ON (c.id)",
            "CREATE INDEX FOR (e:Entity) ON (e.name)"
        ]
        for idx in indices:
            try: graph.query(idx)
            except Exception: pass
        
        # Índices vectoriales para Nomic (768)
        try:
            graph.query(f"""
                CREATE VECTOR INDEX FOR (c:ChildChunk) ON (c.embedding)
                OPTIONS {{ dimension: {EMBEDDING_DIM}, similarityFunction: 'cosine' }}
            """)
        except Exception: pass

        try:
            graph.query(f"""
                CREATE VECTOR INDEX FOR (e:Entity) ON (e.embedding)
                OPTIONS {{ dimension: {EMBEDDING_DIM}, similarityFunction: 'cosine' }}
            """)
        except Exception: pass
        return graph
    except Exception as e:
        print(f"❌ Error fatal conectando a FalkorDB: {e}")
        return None

def create_child_chunks(text, parent_id, target_size=1000, overlap_sentences=2):
    if not text: return []
    text = re.sub(r'\s+', ' ', text).strip()
    raw_sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    sentences = [s.strip() for s in raw_sentences if s.strip()]

    chunks = []
    current_chunk = [] 
    current_len = 0    
    
    for sentence in sentences:
        sentence_len = len(sentence)
        additional_len = sentence_len + (1 if current_len > 0 else 0)
        
        if (current_len + additional_len > target_size) and current_chunk:
            chunks.append({
                "id": f"{parent_id}_c_{len(chunks)}",
                "content": " ".join(current_chunk)
            })
            overlap_count = min(len(current_chunk) - 1, overlap_sentences)
            overlap_start = max(0, len(current_chunk) - overlap_count)
            keep_sentences = current_chunk[overlap_start:]
            current_chunk = keep_sentences + [sentence]
            current_len = sum(len(s) for s in current_chunk) + len(current_chunk) - 1 
        else:
            current_chunk.append(sentence)
            current_len += additional_len

    if current_chunk:
        final_content = " ".join(current_chunk)
        if len(final_content) < 200 and chunks:
            chunks[-1]["content"] += " " + final_content
        else:
            chunks.append({
                "id": f"{parent_id}_c_{len(chunks)}",
                "content": final_content
            })
    return chunks

class FalkorLoader:
    def __init__(self):
        self.graph = get_graph()

    def load_jsonl(self, file_path):
        nodes = []
        relationships = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line: continue

                fixed_line = line.replace('}{', '}\n{')
                sub_lines = fixed_line.split('\n')

                for sub_line in sub_lines:
                    try:
                        data = json.loads(sub_line)
                        if data.get("type") == "node":
                            nodes.append(data)
                        elif data.get("type") == "relationship":
                            relationships.append(data)
                    except json.JSONDecodeError as e:
                        print(f"❌ Error irreparable en línea {line_num}: {e}")

        # 2. Hierarchical order of tags
        label_priority = {"Document": 1,  "ParentChunk": 2, "ChildChunk": 3, "Entity": 4}
        nodes.sort(key=lambda x: label_priority.get(x['label'], 99))
        document_id = ""
        for node in nodes:
            if node['label'] == 'Document':
                label = node["label"]
                props = node["data"]
                node_id = props["doc_id"]
                document_id = node_id
                query = f"MERGE (n:{label} {{id: $id}}) SET n += $props"
                self.graph.query(query, {'id': node_id, 'props': props})            
            if node['label'] == 'ParentChunk':
                label = node["label"]
                props = node["data"]
                node_id = props["parent_id"]
                query = """
                MATCH (p:Document {id: $doc_id})
                MERGE (c:ParentChunk {id: $parent_id})
                SET c += $props
                MERGE (p)-[:CONTAINS]->(c)
                """
                self.graph.query(query, {'doc_id': document_id, 'parent_id':node_id, 'props': props})   
                  
            if node['label'] == 'ChildChunk':
                label = node["label"]
                props = node["data"]
                parent_id = props['parent_id']
                
                child_id = parent_id+'_'+str(props['order'])
                del props['parent_id']
                props["content"] = re.sub(r'[\x00-\x1f\x7f-\x9f]', '',  props["content"])
                vector = get_embedding(props["content"])
                props['embedding'] = vector
                query = """
                MATCH (p:ParentChunk {id: $parent_id})
                MERGE (c:ChildChunk {id: $child_id})
                SET c += $props
                MERGE (p)-[:HAS_CHILD]->(c)
                """
                
                params = {
                    'parent_id': parent_id,
                    'child_id': child_id,
                    'props': props
                }
                
                try:
                    self.graph.query(query, params)
                except Exception as e:
                    print(f"❌ Error al relacionar ChildChunk {child_id}: {e}")                                
                
            if node['label'] == 'Entity':
                label = "Entity"
                props = node["data"].copy()             

                parent_id = props.pop("parent_id", None)
                entity_name = props.get("name", "Unknown")
            
                entity_id = entity_name.upper().replace(" ", "_")

                entity_vec = get_embedding(f"{entity_name.upper()}: {props['description']}")
                props['embedding']=entity_vec

                query = """
                MATCH (p:ParentChunk {id: $parent_id})
                MERGE (e:Entity {id: $entity_id})
                SET e += $props
                MERGE (e)-[:MENTIONED_IN]->(p)
                """
                
                params = {
                    'parent_id': parent_id,
                    'entity_id': entity_id,
                    'props': props
                }
                
                try:
                    if parent_id:
                        self.graph.query(query, params)
                    else:
                        print(f"⚠️ Entidad {entity_name} no tiene parent_id")
                except Exception as e:
                    print(f"❌ Error al insertar entidad {entity_name}: {e}")
                    
        for relationship in relationships:
            label = relationship["label"].upper().replace(" ", "_")
            data = relationship["data"].copy()
            
            source_name = data.pop("source_entity")
            target_name = data.pop("target_entity")
            source_type = data.get("source_type", "") 
            
            source_id = source_name.upper().replace(" ", "_")
            
            # 3. FILTERING LOGIC FOR REFLEXIVE RELATIONS
            if target_name.upper() == "SELF":
                # If it is CORE_ENTITY, we abort the creation of this relationship entirely 
                # (this refers to the neutral concept)
                if source_type == "CORE_ENTITY":
                    continue 
                
                # If it is NOT CORE_ENTITY, the target is the same as the source
                target_id = source_id
            else:
                # Normal relationship between two distinct entities
                target_id = target_name.upper().replace(" ", "_")

            props = data
            query = f"""
            MATCH (src:Entity {{id: $source_id}})
            MATCH (tgt:Entity {{id: $target_id}})
            MERGE (src)-[r:{label}]->(tgt)
            SET r += $props
            """
            
            params = {
                'source_id': source_id,
                'target_id': target_id,
                'props': props
            }
            
            try:
                self.graph.query(query, params)
            except Exception as e:
                print(f"❌ Error al crear relación {label} entre {source_id} y {target_id}: {e}")

        
        

            