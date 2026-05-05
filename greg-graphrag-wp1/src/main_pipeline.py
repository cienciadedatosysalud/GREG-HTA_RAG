import os
import uuid
import json
import hashlib
import shutil
from datetime import datetime
from pathlib import Path


# DB and Processing imports
from src.shared.db_clients import get_lance_db, MODEL_NAME, client_ollama, TEMPERATURE_EXTRACTOR, CHILD_SIZE,CHILD_OVERLAP, NUM_CTX, REPEAT_PENALTY,MIN_PARENT_SIZE,MAX_PARENT_SIZE
from src.ingestion.extractor import (
    clean_response_json, 
    normalize_relation_type
)

from src.ingestion.persistence import (
    init_db, 
    FalkorLoader, 
    create_child_chunks
)
from src.ingestion.prompts import SYSTEM_PROMPT_EXTRACTOR_V2

from src.logic.centrality import calculate_graph_centrality
from src.logic.vector_sync import sync_relationships_to_lancedb

from src.logic.metadata_extractor import extract_document_metadata
from src.shared.utils import append_to_manifest

# --- CONFIGURACIÓN DE RUTAS ---
RAW_DIR = os.getenv("RAW_DATA_PATH", "data/raw")
PROCESSED_DIR = os.getenv("PROCESSED_DATA_PATH", "data/processed")

from src.ingestion.ingestion_engine import IngestionEngine


# ================= 0. REGISTRY & FILE HELPERS =================

def get_file_hash(path):
    """Generates a SHA-256 hash to identify the PDF content."""
    hasher = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

def get_registry_table():
    """Retrieves or creates the technical control table in LanceDB."""
    db = get_lance_db()
    table_name = "document_registry"
    try:
        return db.open_table(table_name)
    except Exception:
        initial_data = [{
            "doc_id": "template", "filename": "template", 
            "hash": "template", "status": "template", "timestamp": "template"
        }]
        table = db.create_table(table_name, data=initial_data)
        table.delete("doc_id = 'template'")
        return table
        
def finalize_document(file_path):

    if not os.path.exists(PROCESSED_DIR):
        os.makedirs(PROCESSED_DIR, exist_ok=True)

    filename = os.path.basename(file_path)
    
    try:
        # 4. Mover el PDF original
        dest_path = os.path.join(PROCESSED_DIR, filename)
        shutil.move(file_path, dest_path)
        print(f"📦 Document {filename} moved to processed folder.")

    except Exception as e:
        print(f"❌ Error in finalize_document: {e}")

# ================= 1. CORE EXTRACTION LOGIC =================

def run_extraction(engine,row,file_path):
    path = row['path']
    filename = row['filename']
    doc_id = row['doc_id']
    
    print(f"📄 Processing: {filename}")
    
    # Acumuladores para el resumen
    total_entities = 0
    total_relations = 0
    
    smart_chunks = engine.get_parent_chunks(path)

    print(f"📊 Extracting administrative metadata...")
    head_texts = smart_chunks[:2]
    metadata = extract_document_metadata(head_texts, doc_id)
    if metadata:
        append_to_manifest(metadata)
        print(f"   ✅ Metadata added to manifest: {metadata.get('doc_authority')}")
    else:
        metadata = {} 
    
    nodes_entities_relationships= {"parentchunks":[],"childchunks":[],"entities":[],"relationships":[]}
    
    if not os.path.exists(PROCESSED_DIR):
        os.makedirs(PROCESSED_DIR, exist_ok=True)

    filename_ = os.path.basename(file_path)
    base_name = os.path.splitext(filename_)[0]
    
    # Nombre del archivo de salida
    jsonl_output_path = os.path.join(PROCESSED_DIR, f"{base_name}_payload.jsonl")

    try:
        with open(jsonl_output_path, 'w', encoding='utf-8') as f:
            # --- STEP 4: INGESTION LOOP ---
            metadata['filename']=filename
            metadata['doc_id']=doc_id
            f.write(json.dumps({"type": "node", "label": "Document", "data": metadata}) + "\n")
            doc_length = 0
            for i, chunk in enumerate(smart_chunks):
                doc_length += len(chunk)
                parent_text = chunk
                parent_id = f"parent_{doc_id}_{i}"
                f.write(json.dumps({"type": "node","label": "ParentChunk", "data":{"parent_id":parent_id}}) + "\n")          
                      
                children = create_child_chunks(parent_text, parent_id,target_size=CHILD_SIZE,overlap_sentences=CHILD_OVERLAP)
                for order_, child in enumerate(children):
                    f.write(json.dumps({"type": "node", "label": "ChildChunk", 
                                        "data": {
                                            "parent_id":parent_id,
                                            "order":order_,
                                            "content":child["content"]
                                            }
                                        }) + "\n")
                # C. Graph Extraction
                print(f"\r\033[K📦 Processing Chunk ({len(parent_text)}): {i+1}/{len(smart_chunks)}", end="", flush=True)
                
                response = client_ollama.chat(
                    model=MODEL_NAME,
                    messages=[
                        {'role': 'system', 'content': SYSTEM_PROMPT_EXTRACTOR_V2}, 
                        {'role': 'user', 'content': f"EXTRACT GRAPH:\n\n{parent_text}"}
                    ],
                    options={'temperature': TEMPERATURE_EXTRACTOR,'num_ctx': NUM_CTX,'repeat_penalty': REPEAT_PENALTY,'num_predict': -1}
                )
                
                try:
                    data = json.loads(clean_response_json(response['message']['content']))
                except: continue
                
                                
                # --- ENTITIES ---
                if "entities" in data:
                    total_entities += len(data["entities"])
                    for ent in data["entities"]:
                        
                        if not isinstance(ent, dict):
                            print(f"   ⚠️ Saltando entidad malformada (no es un objeto): {ent}")
                            continue
                        name = ent.get("entity_name", "").strip().upper()
                        if not name: continue
                        raw_desc = ent.get("entity_description", "No description").strip()
                        f.write(json.dumps({"type": "node", "label": "Entity", "data": {"parent_id":parent_id,"name":name,"description":raw_desc}}) + "\n")

                    
                # --- RELATIONSHIPS ---
                if "relationships" in data:
                    total_relations += len(data["relationships"])
                    for rel in data["relationships"]:
                        if not isinstance(rel, dict):
                            print(f"   ⚠️ Saltando entidad malformada (no es un objeto): {rel}")
                            continue
                        src, tgt = rel.get("source_entity", "").upper(), rel.get("target_entity", "").upper()
                        if not src or not tgt: continue 
                        r_name = rel.get("relationship_name", "RELATED").strip()
                        r_desc = rel.get("relationship_description", "No description").strip()
                        source_type = rel.get("source_type", "UNKNOWN").strip()
                        target_type = rel.get("target_type", "UNKNOWN").strip()
                        final_rel_type = normalize_relation_type(r_desc, r_name)
                        f.write(json.dumps(
                            {
                                "type": "relationship", 
                                "label": final_rel_type, 
                                "data": {
                                    "source_doc":doc_id,
                                    "parent_id":parent_id,
                                    "source_entity":src,
                                    "source_type":source_type,
                                    "target_entity":tgt,
                                    "target_type":target_type,
                                    "relationship_type":final_rel_type,
                                    "relationship_verb":r_name,
                                    "relationship_description":r_desc
                                }
                            }) + "\n")

                                    
    except Exception as e:
        print(f"❌ Error in finalize_document: {e}")           

    print()
    return {
        "doc_id":doc_id,
        "processed_at": datetime.now().isoformat(),
        "entities_found": total_entities,
        "relationships_found": total_relations,
        "chunks_total": len(smart_chunks),
        "markdown_length": doc_length,
        "data":nodes_entities_relationships,
        
    }

# ================= 2. MAIN EXECUTION LOOP =================

def main():
    print(f"--- 🚀 Ingestion: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
    init_db()
    engine = IngestionEngine(min_chunk_size=MIN_PARENT_SIZE, max_chunk_size=MAX_PARENT_SIZE)
    
    registry = get_registry_table()
    
    if not os.path.exists(RAW_DIR): return

    files = [f for f in os.listdir(RAW_DIR) if f.endswith(".pdf")]
    processed_hashes = registry.to_pandas()['hash'].tolist() if not registry.to_pandas().empty else []

    for f in files:
        file_path = os.path.join(RAW_DIR, f)
        
        # TODO, If image interpretation is involved, this process is not deterministic, and the same document could produce a different hash.
        file_hash = get_file_hash(file_path)
        
        if file_hash in processed_hashes:
            print(f"⏭️ Skipping {f}")
            continue
            
        doc_id = str(uuid.uuid4())
        row = {'path': file_path, 'filename': f, 'doc_id': doc_id, 'doc_ref': f.replace('.pdf','')}
        
        try:
            run_extraction(engine,row,file_path)            
            finalize_document(file_path)
            print(f"✅ Ingested: {f}")
            
        except Exception as e:
            registry.add([{
                "doc_id": doc_id, "filename": f, "hash": file_hash, 
                "status": f"FAILED: {str(e)}", "timestamp": datetime.now().isoformat()
            }])
            print(f"❌ Error {f}: {e}")

def get_jsonl_paths(directory):
    if not directory.exists():
        print(f"❌ Error: The directory does not exist in {directory}")
        return []

    paths = sorted([str(f) for f in directory.glob("*.jsonl")])
    
    print(f"📂 {len(paths)} files were found to be processed.")
    return paths        

if __name__ == "__main__":
    main()
    falkor_loader = FalkorLoader()
    base_path = Path(__file__).parent / "../data/processed"
    processed_dir = base_path.resolve()
    jsonl_files = get_jsonl_paths(processed_dir)
    for jsonl_file in jsonl_files:
        falkor_loader.load_jsonl(jsonl_file)
    calculate_graph_centrality()
    sync_relationships_to_lancedb()