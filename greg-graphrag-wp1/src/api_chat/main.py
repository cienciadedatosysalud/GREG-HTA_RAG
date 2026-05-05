import os
import ollama
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from falkordb import FalkorDB
import re 
import json
import asyncio
import lancedb
import time 
from typing import Optional
# ================= CONFIGURACIÓN =================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Conectividad Dinámica ---
FALKOR_HOST = os.getenv("FALKOR_HOST", "falkordb")
FALKOR_PORT = int(os.getenv("FALKOR_PORT", 6379))

# Formateo de URL Ollama
raw_host = os.getenv("OLLAMA_HOST", "http://ollama")
raw_port = os.getenv("OLLAMA_PORT", "11434")
if not raw_host.startswith("http"): raw_host = f"http://{raw_host}"
OLLAMA_HOST = f"{raw_host}:{raw_port}" if ":" not in raw_host.replace("http://", "") else raw_host

# Configuración de Grafos y Tablas
GRAPH_KNOWLEDGE = os.getenv("GRAPH_NAME", "rwe_knowledge_graph")
GRAPH_HISTORY = os.getenv("GRAPH_CONVERSATIONS", "chat_history_graph")
LANCEDB_PATH = os.getenv("LANCEDB_PATH", "/app/data/lancedb")
LANCE_TABLE_RELS = "graph_relationships"

# Modelos
LLM_MODEL = os.getenv("MODEL_CHAT", "gemma4:26b")
MODEL_QUERY_REFINER = os.getenv("MODEL_QUERY_REFINER", "llama3.1:8b")
MODEL_EMBEDDING = os.getenv("MODEL_EMBEDDING", "nomic-embed-text")

# Clientes
client_ollama = ollama.Client(host=OLLAMA_HOST)

try:
    db_lance = lancedb.connect(LANCEDB_PATH)
    rel_table = db_lance.open_table(LANCE_TABLE_RELS) if LANCE_TABLE_RELS in db_lance.list_tables() else None
    print(f"✅ LanceDB connected at {LANCEDB_PATH}")
except Exception as e:
    print(f"❌ Error LanceDB: {e}")
    rel_table = None

try:
    db_falkor = FalkorDB(host=FALKOR_HOST, port=FALKOR_PORT)
    graph_kb = db_falkor.select_graph(GRAPH_KNOWLEDGE)
    graph_hist = db_falkor.select_graph(GRAPH_HISTORY)
    graph_hist.query("CREATE INDEX FOR (u:User) ON (u.id)")
    graph_hist.query("CREATE INDEX FOR (s:ChatSession) ON (s.id)")
    print(f"✅ FalkorDB connected (Dual Graph)")
except Exception as e:
    print(f"❌ Error FalkorDB: {e}")


class ChatRequest(BaseModel):
    message: str
    session_id: str
    user_id: str
    message_id: str

class FeedbackRequest(BaseModel):
    session_id: str
    message_id: str
    vote: int
    reason: Optional[str] = None

# ================= 1. Conversation History Management (Graph: graph_hist) =================

def save_feedback(session_id: str, content_preview: str, vote: int, reason: str = None):
    """
    Finds the assistant's latest message in the session and assigns the vote to it.
    """
    cypher = """
    MATCH (s:ChatSession {id: $session_id})-[:HAS_MESSAGE]->(m:Message {role: 'assistant'})
    WHERE m.content CONTAINS $preview
    SET m.vote = $vote, m.feedback_reason = $reason
    RETURN m.timestamp
    """
    
    preview = content_preview[:50]
    
    try:
        graph_hist.query(cypher, {
            "session_id": session_id,
            "preview": preview,
            "vote": vote,
            "reason": reason
        })
        return True
    except Exception as e:
        print(f"⚠️ Error al guardar feedback: {e}")
        return False

def save_to_history(session_id, user_id, role, content, source="general", message_id=None):
    m_id = message_id if message_id else f"msg_{int(time.time()*1000)}"
    
    #Save messages by linking them to a session and an owner
    cypher = """
    MERGE (u:User {id: $user_id})
    MERGE (s:ChatSession {id: $session_id})
    MERGE (u)-[:OWNER_OF]->(s)
    ON CREATE SET s.created_at = timestamp(), s.title = $title
    
    CREATE (m:Message {id: $message_id, role: $role, content: $content, timestamp: timestamp(),source:$source})
    CREATE (s)-[:HAS_MESSAGE]->(m)
    """
    
    title = (content[:45] + "...") if len(content) > 45 else content
    
    try:
        graph_hist.query(cypher, {
            "session_id": session_id, 
            "user_id": user_id, 
            "role": role, 
            "content": content,
            "title": title,
            "source":source,
            "message_id": m_id
        })
    except Exception as e:
        print(f"⚠️ Error en FalkorDB Historial: {e}")

def get_recent_memory(session_id, limit=4):
    
    # Retrieve only interactions that were successful with the Graph.
    cypher = """
    MATCH (s:ChatSession {id: $session_id})-[:HAS_MESSAGE]->(m:Message)
    WHERE m.source = 'graph_rag'
    RETURN m.role, m.content
    ORDER BY m.timestamp DESC
    LIMIT $limit
    """
    res = graph_hist.query(cypher, {"session_id": session_id, "limit": limit})
    memory_parts = []
    for row in reversed(res.result_set):
        role = row[0].upper()
        content = row[1]        
        clean_content = re.split(r'\*\*?REFERENCES\*\*?', content, flags=re.IGNORECASE)[0]
        clean_content = re.sub(r'\[\d+(?:,\s*\d+)*\]', '', clean_content)
        clean_content = re.sub(r'\[Ref:.*?\]', '', clean_content)
        clean_content = clean_content.strip()
        
        memory_parts.append(f"{role}: {clean_content}")
        
    return "\n".join(memory_parts)

# ================= 2. KB GraphRAG SEARCH (Graph: graph_kb) =================


def clean_evidence(text):
    """Cleaning up references and noise"""
    if not text: return ""
    text = re.sub(r'\[Ref:.*?\]', '', text)
    text = text.replace("[:", "").replace("/n", " ").replace("##", "")
    return re.sub(r'\s+', ' ', text).strip()

def get_embedding(text, is_query=True):
    """Generates embeddings with proper prefixing"""
    try:
        prefix = "search_query: " if is_query else "search_document: "
        response = client_ollama.embeddings(model=MODEL_EMBEDDING, prompt=f"{prefix}{text}")
        return response["embedding"]
    except Exception as e:
        print(f"⚠️ Embedding Error: {e}")
        return []
    
def get_parent_metadata(doc_refs):
    if not doc_refs: return {}

    doc_refs = list(set(doc_refs))
    
    cypher = """
    MATCH (p:ParentChunk)
    WHERE p.doc_ref IN $refs
    RETURN DISTINCT p.doc_ref, p.doc_link, p.doc_authority, p.doc_official_title, p.doc_year, p.doc_region
    """
    try:
        res = graph_kb.query(cypher, {"refs": doc_refs})
        meta_map = {}
        for row in res.result_set:
            meta_map[row[0]] = {
                "link": row[1] or "#",
                "authority": row[2] or "N/A",
                "title": row[3] or row[0],
                "year": row[4] or "",
                "region": row[5] or ""
            }
        return meta_map
    except:
        return {}

# ================= 2. SEARCH FUNCTIONS (Exact Scores) =================

def search_chunks_text(user_question, k=15):
    """Vector search for raw text chunks. Threshold: score < 0.50"""
    if not graph_kb: return []
    
    vec = get_embedding(user_question)
    if not vec: return []

    cypher = """
    CALL db.idx.vector.queryNodes('ChildChunk', 'embedding', $k, vecf32($vec))
    YIELD node, score
    WHERE score < 0.45
    MATCH (node)<-[:HAS_CHILD]-(parent:ParentChunk)
    RETURN node.content, score, parent.filename, parent.doc_ref, 
           parent.doc_link, parent.doc_authority, parent.doc_official_title, parent.doc_year
    ORDER BY score ASC
    """
    try:
        res = graph_kb.query(cypher, {"k": k, "vec": vec})
        results = []
        for row in res.result_set:
            content, score, filename, doc_ref, link, auth, title, year = row 
            
            results.append({
                "text": f"📄 SOURCE [{doc_ref}]: {content}",
                "score": score,
                "ref": doc_ref,
                "link": link or "#",
                "authority": auth or "N/A",
                "title": title or filename,
                "year": year or ""
            })
        return results
    except Exception as e:
        print(f"   ⚠️ Text Search Error: {e}")
        return []

def search_entities_raw(search_q, terms=None, k=25):
    if not graph_kb: return {}
    vec = get_embedding(search_q)
    terms = terms if isinstance(terms, list) else []

    cypher = """
    CALL db.idx.vector.queryNodes('Entity', 'embedding', $k, vecf32($vec))
    YIELD node, score
    WHERE score < 0.60
    WITH collect(node) AS vector_nodes

    OPTIONAL MATCH (e:Entity)
    WHERE any(term IN $terms WHERE toLower(e.name) = toLower(term))
    WITH vector_nodes, collect(e) AS term_nodes

    WITH vector_nodes + term_nodes AS combined_nodes
    UNWIND combined_nodes AS node
    WITH DISTINCT node
    WHERE node IS NOT NULL

    WITH node
    ORDER BY (coalesce(node.pagerank, 0) * 0.4) + (coalesce(node.out_degree, 0) * 0.6) DESC
    LIMIT 15

    OPTIONAL MATCH (node)-[r]->(neighbor:Entity)
    WHERE type(r) <> 'MENTIONED_IN'

    RETURN 
        node.name, 
        node.description, 
        node.pagerank, 
        node.out_degree,
        collect({
            rel_id: id(r),
            type: type(r),
            target_name: neighbor.name,
            target_def: neighbor.description,
            logic: r.description,
            verbs: r.verbs
        }) AS impacts
    """
    try:
        res = graph_kb.query(cypher, {"k": k, "vec": vec, "terms": terms})
        return res.result_set
    except Exception as e: 
        print(f"⚠️ Error en Cypher: {e}")
        return []

async def search_chunks_text_async(user_question, k=15):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, search_chunks_text, user_question, k)
 

# ================= 3. LOGIC FOR GENERATING THE RESPONSE AND STREAMING =================

def query_refiner(user_message, memory_text):
    refiner_prompt = f"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>
    ROLE: Strategic Research Assistant in RWE/HTA.
    TASK: Process the user message for a Hybrid RAG (Graph + Vector).
    
    [CONTEXT MEMORY]:
    {memory_text}

    [INSTRUCTIONS]:
    1. If it's a follow-up question (e.g., "Tell me more about that"), use [CONTEXT MEMORY] to create a self-contained query.
    2. "standalone_query" must be optimized for SEMANTIC search (embedding).
    3. "search_terms" must be the EXACT technical entities (e.g., "EMA", "FDA", "RWE") for GRAPH matching. Keep them in their original technical case.
    4. If it's a greeting or non-technical, set is_technical: false.

    Return ONLY JSON:
    {{
      "is_technical": boolean,
      "standalone_query": "Self-contained technical question",
      "search_terms": ["Entity1", "Entity2"]
    }}
    <|eot_id|><|start_header_id|>user<|end_header_id|>
    Message: "{user_message}"
    JSON: <|eot_id|><|start_header_id|>assistant<|end_header_id|>"""
    
    try:
        response = client_ollama.chat(
            model=MODEL_QUERY_REFINER, 
            messages=[{'role': 'user', 'content': refiner_prompt}],
            format="json",
            options={'temperature': 0.1}
        )
        data = json.loads(response['message']['content'])
        
        if data.get("is_technical") and not data.get("standalone_query"):
            data["standalone_query"] = user_message
            
        return data
    except Exception as e:
        print(f"⚠️ Refiner Error: {e}")
        return {"is_technical": True, "standalone_query": user_message, "search_terms": []}


async def rag_stream_generator(question: str, session_id: str, user_id: str, message_id: str):
    save_to_history(session_id, user_id, "user", question)
    memory_text = get_recent_memory(session_id, limit=4)
    refined = query_refiner(question, memory_text)
    
    search_q = refined.get("standalone_query", question)
    search_terms = refined.get("search_terms", [])
    query_vec = get_embedding(search_q)

    raw_entities = search_entities_raw(search_q, search_terms)
    
    processed_entities = {}
    best_semantic_dist = 1.0 
    

    for row in raw_entities:
        
        name, desc, p_rank, out_deg, impacts = row
        if not name: continue
        
        final_impacts = []
        if rel_table:

            rel_ids = [imp['rel_id'] for imp in impacts if imp.get('rel_id') is not None]
            num_impacts_falkor = len(rel_ids)
            
            search_res = []
            if rel_ids:
                ids_filter = ", ".join(map(str, rel_ids))                
                search_query = rel_table.search(query_vec)\
                    .where(f"rel_id IN ({ids_filter})")\
                    .limit(6)\
                    .refine_factor(5)
                
                search_res = search_query.to_list()
                
            for sr in search_res:
                dist = sr['_distance']
                best_semantic_dist = min(best_semantic_dist, dist)
                
                if sr == search_res[0]:
                    print(f"   🔝 Best Rel Score: {dist:.4f} | Text: {sr['text'][:60]}...")

                final_impacts.append({
                    "type": sr['type'],
                    "target": sr['target'],
                    "logic": sr['text'], 
                    "verbs": sr['verbs'],
                    "dist": dist 
                })
        
        processed_entities[name] = {
            "def": desc,
            "influence": out_deg or 0,
            "rels": final_impacts
        }

    # 3. CASCADE STRATEGY (Conditional evidence)
    # If the graph is very precise (<0.35), we fetch few chunks. 
    # If it is weak (>0.50) or nonexistent, we fetch the maximum number.
    if best_semantic_dist < 0.35:
        k_chunks = 4 
    elif best_semantic_dist < 0.50:
        k_chunks = 8
    else:
        k_chunks = 15

    raw_text_results = await search_chunks_text_async(search_q, k=k_chunks)

    #4. Reference Mapping
    ordered_unique_refs = []

    for name, data in processed_entities.items():
        refs = re.findall(r'\[Ref:\s*([^\]\s,]+)\]', data['def'])
        for r in refs:
            if r not in ordered_unique_refs: ordered_unique_refs.append(r)
        for rel in data['rels']:
            refs = re.findall(r'\[Ref:\s*([^\]\s,]+)\]', rel['logic'])
            for r in refs:
                if r not in ordered_unique_refs: ordered_unique_refs.append(r)
    
    for chunk in raw_text_results:
        if chunk['ref'] not in ordered_unique_refs: ordered_unique_refs.append(chunk['ref'])
    
    meta_library = get_parent_metadata(ordered_unique_refs)
    ref_map = {}
    ref_map_readable = []
    sources_footer_list = []
    for i, d_ref in enumerate(ordered_unique_refs):
        data = meta_library.get(d_ref)
        if not data: continue
        num = i + 1
        label = f"{data['authority']} - {data['title']}"
        ref_map[d_ref] = {"num": num}
        ref_map_readable.append(f"Source [{num}]: {label}")
        sources_footer_list.append(f"[{num}] **[{label}]({data.get('link', '#')})**")

    #5. CONTEXT FORMAT FOR PROMPT
    entity_context = []
    for name, data in processed_entities.items():
        
        clean_def = data['def']
        for dr, m in ref_map.items():
            # Usamos regex para encontrar "[Ref: nombre_archivo]" y cambiarlo por "[num]"
            pattern = r'\[Ref:\s*' + re.escape(dr) + r'\]'
            clean_def = re.sub(pattern, f"[{m['num']}]", clean_def)
        
        # Limpieza final de seguridad para Refs no encontradas en el map
        clean_def = re.sub(r'\[Ref:.*?\]', '', clean_def).strip()
        
        influence_tag = " [STRATEGIC HUB]" if data['influence'] > 3 else ""
        info = f"CONCEPT: {name}{influence_tag}\nDEFINITION: {clean_def}\n"
        
        # 2. Limpieza de los Impactos Estratégicos (Relaciones)
        if data['rels']:
            info += "STRATEGIC IMPACTS:\n"
            for rel in data['rels']:
                clean_logic = rel['logic']
                for dr, m in ref_map.items():
                    # Aplicamos la misma lógica de Regex aquí
                    pattern = r'\[Ref:\s*' + re.escape(dr) + r'\]'
                    clean_logic = re.sub(pattern, f"[{m['num']}]", clean_logic)
                
                # Limpieza final de seguridad para la lógica
                clean_logic = re.sub(r'\[Ref:.*?\]', '', clean_logic).strip()
                
                verbs = f" ({rel['verbs']})" if rel['verbs'] else ""
                info += f"- {rel['type']}{verbs} -> {rel['target']}: {clean_logic}\n"
                
        entity_context.append(info)

    text_context = [f"DOC SOURCE [{ref_map[c['ref']]['num']}]: {clean_evidence(c['text'])}" 
                    for c in raw_text_results if c['ref'] in ref_map]

    max_ref = len(ordered_unique_refs)

    prompt = f"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>
    [SYSTEM ARCHITECTURE]
    Senior Strategic Consultant & Regulatory Analyst. You are a "Closed-System Analyst". 
    Your integrity depends on numerical precision.

    [STRICT CITATION PROTOCOLS]
    1. **HARD LIMIT:** You have access to exactly {max_ref} documents.
    2. **VALID RANGE:** Use ONLY citations from [1] to [{max_ref}]. 
    3. **ANTI-HALLUCINATION:** Never use a number higher than [{max_ref}]. If a claim lacks documentary evidence in the provided repository, DO NOT invent a citation.
    4. **INTEGRATED ANALYSIS:** Weave "STRATEGIC GRAPH LOGIC" and "DOCUMENTARY EVIDENCE" into a cohesive briefing.
    5. **NARRATIVE ANCHORING:** Lead with the strategic insight and anchor it with the citation [n] only if the fact is present in the text. If describing a causal link from the Graph not present in the text, explain the logic without a numerical citation.

    [REFERENCE MAPPING]
    {"/n".join(ref_map_readable)}
    <|eot_id|><|start_header_id|>user<|end_header_id|>
    [KNOWLEDGE REPOSITORY]
    ### STRATEGIC GRAPH LOGIC (Causal Mechanisms):
    {"/n".join(entity_context) if entity_context else "NO GRAPH DATA."}

    ### EMPIRICAL DOCUMENTARY EVIDENCE (Factual Substance):
    {"/n".join(text_context) if text_context else "NO DOCUMENTARY EVIDENCE."}

    [CONVERSATIONAL CONTEXT]
    {memory_text if memory_text else "Strategic session initiation."}

    [STRATEGIC TASK]
    Original User Request: "{question}"
    Technical Scope (Refined): "{search_q}"

    [FINAL EXECUTIVE INSTRUCTION]
    Deliver a high-level briefing. You are strictly forbidden from citing documents outside the range [1]-[{max_ref}]. Professional prose only.

    ANALYSIS:
    <|eot_id|><|start_header_id|>assistant<|end_header_id|>"""
   
        
    # 6. STREAMING & FOOTER
    full_res = ""
    try:
        #yield " " 
        stream = client_ollama.chat(
            model=LLM_MODEL,
            messages=[{'role': 'user', 'content': prompt}], 
            stream=True,
            options={
                'temperature': 0.1,
                'num_ctx': 8192
            }
            )
        for chunk in stream:
            content = chunk['message']['content']
            if content:
                if re.search(r'###\s*References|References:|^\s*References', content, re.IGNORECASE):
                    break
                full_res += content
                yield content
                
        if sources_footer_list:
            bracket_contents = re.findall(r'\[([\d\s,.\-]+)\]', full_res)
            used_indices = set()
            for content in bracket_contents:
                numbers = re.split(r'[,\s.\-]+', content)
                for n in numbers:
                    if n.isdigit():
                        used_indices.add(n)
            
            total_consulted = len(sources_footer_list)
            seen_numbers = set()
            filtered_footer = []
            
            for ref_string in sources_footer_list:
                # Extraemos el número de la referencia actual, ej: "[1]" -> "1"
                match = re.search(r'^\[(\d+)\]', ref_string)
                if match:
                    num_str = match.group(1)
                    # Solo añadimos si fue citado Y no lo hemos visto ya
                    if num_str in used_indices and num_str not in seen_numbers:
                        filtered_footer.append(ref_string)
                        seen_numbers.add(num_str)
            
            # 3. Construcción del Bloque Final
            num_cited = len(filtered_footer)
            header = f"\n\n**REFERENCES** (Sources consulted: {total_consulted} | Cited in this analysis: {num_cited})\n\n"
            
            if filtered_footer:
                # Ordenar numéricamente para que el listado sea profesional
                filtered_footer.sort(key=lambda x: int(re.search(r'\[(\d+)\]', x).group(1)))
                footer_content = header + "\n\n".join(filtered_footer)
            else:
                footer_content = f"\n\n**REFERENCES** (Sources consulted: {total_consulted} | No specific direct citations used)."
            
            yield footer_content
            full_res += footer_content
            
        save_to_history(session_id, user_id, "assistant", full_res, "graph_rag",message_id=message_id)
        
    except Exception as e:
        yield f"\n[Error processing references: {str(e)}]"

# ================= 4. API ENDPOINTS =================

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    return StreamingResponse(
        rag_stream_generator(req.message, req.session_id, req.user_id,req.message_id), 
        media_type="text/plain"
    )

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    cypher = """
    MATCH (s:ChatSession {id: $id})
    SET s.deleted = true
    RETURN s.id
    """
    try:
        res = graph_hist.query(cypher, {"id": session_id})
        if not res.result_set:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"status": "success", "message": "Session archived"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. MODIFICADO: Listado de Sesiones (Filtrar borrados)
@app.get("/sessions/{user_id}")
async def get_user_sessions(user_id: str):
    cypher = """
    MATCH (u:User {id: $user_id})-[:OWNER_OF]->(s:ChatSession)
    WHERE s.deleted IS NULL OR s.deleted = false
    RETURN s.id, s.title, s.created_at
    ORDER BY s.created_at DESC
    """
    try:
        res = graph_hist.query(cypher, {"user_id": user_id})
        return [{"id": row[0], "title": row[1], "date": row[2]} for row in res.result_set]
    except:
        return []

# 3. MODIFICADO: Carga de Historial (Seguridad opcional)
@app.get("/history/{session_id}")
async def get_full_history(session_id: str):
    cypher = """
    MATCH (s:ChatSession {id: $id})
    WHERE s.deleted IS NULL OR s.deleted = false
    MATCH (s)-[:HAS_MESSAGE]->(m:Message)
    RETURN m.role, m.content
    ORDER BY m.timestamp ASC
    """
    try:
        res = graph_hist.query(cypher, {"id": session_id})
        return {"messages": [{"role": row[0], "content": row[1]} for row in res.result_set]}
    except:
        return {"messages": []}


@app.post("/chat/feedback")
async def chat_feedback(req: FeedbackRequest):
    cypher = """
    MATCH (s:ChatSession {id: $session_id})-[:HAS_MESSAGE]->(m:Message {id: $message_id})
    SET m.vote = $vote, 
        m.feedback_reason = $reason,
        m.feedback_at = timestamp()
    RETURN m.id
    """
    try:
        res = graph_hist.query(cypher, {
            "session_id": req.session_id,
            "message_id": req.message_id,
            "vote": req.vote,
            "reason": req.reason
        })
        
        if not res.result_set:
            raise HTTPException(status_code=404, detail="Mensaje no encontrado")
            
        return {"status": "success", "message": "Feedback guardado"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
