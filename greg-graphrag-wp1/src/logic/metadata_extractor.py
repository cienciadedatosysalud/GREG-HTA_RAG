import re
import json
from src.shared.db_clients import client_ollama, MODEL_NAME, TEMPERATURE_METADATA, NUM_CTX
from src.ingestion.prompts import PROMPT_EXTRACT_METADATA


def extract_document_metadata(chunks_text, doc_id):
    # We use the first two chunks as context
    context = "\n---\n".join(chunks_text[:2])
    prompt = PROMPT_EXTRACT_METADATA.format(context=context)    
    try:
        response = client_ollama.generate(model=MODEL_NAME, prompt=prompt, options={'temperature': TEMPERATURE_METADATA,'num_ctx': NUM_CTX})
        content = response.get('response', '')
        
        # Cleaning up null bytes to prevent the FalkorDB error
        content = re.sub(r'\x00', '', content, flags=re.DOTALL)
        
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            meta = json.loads(match.group())
            meta['doc_id'] = doc_id
            return meta
    except Exception as e:
        print(f"   ⚠️ Error extracting metadata: {e}")
    return None