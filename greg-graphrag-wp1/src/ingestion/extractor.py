import re
import json
from json_repair import repair_json
import re
import json

def clean_response_json(text):
    """
    Extracts entities and relationships lists from raw LLM output 
    and reconstructs a valid JSON object.
    """
    if not text:
        return "{}"
    
    # 1. Remove DeepSeek's reasoning chain
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

    try:
        # 2. STRUCTURAL EXTRACTION
        # Capture everything inside the brackets for entities and relationships
        entities_match = re.search(r'"entities":\s*\[(.*?)\]', text, flags=re.DOTALL)
        rels_match = re.search(r'"relationships":\s*\[(.*?)\]', text, flags=re.DOTALL)

        entities_raw = entities_match.group(1) if entities_match else ""
        rels_raw = rels_match.group(1) if rels_match else ""

        def extract_valid_objects(raw_content):
            """Finds all occurrences of { ... } and joins them with commas."""
            # This ignores 'else', whitespace, or random text between objects
            blocks = re.findall(r'(\{.*?\})', raw_content, flags=re.DOTALL)
            return ", ".join(blocks)

        clean_entities = extract_valid_objects(entities_raw)
        clean_rels = extract_valid_objects(rels_raw)

        # 3. RECONSTRUCT THE JSON
        # This ensures the root keys are always correct
        reconstructed_json = f"""
        {{
            "entities": [{clean_entities}],
            "relationships": [{clean_rels}]
        }}
        """

        # 4. FINAL REPAIR & LOADING
        # repair_json handles unclosed quotes or trailing commas
        repaired = repair_json(reconstructed_json)
        
        # Test if it's valid JSON before returning
        json.loads(repaired) 
        return repaired

    except Exception as e:
        # Fallback to standard extraction if structural reconstruction fails
        print(f"⚠️ Structural reconstruction failed: {e}. Attempting standard fallback...")
        try:
            match = re.search(r'(\{.*\})', text, flags=re.DOTALL)
            if match:
                candidate = repair_json(match.group(1))
                json.loads(candidate)
                return candidate
        except Exception as final_e:
            print(f"❌ Critical JSON parse error: {final_e}")
            return "{}"

def normalize_relation_type(text_description, raw_name):
    text = str(text_description or "").upper()
    verb = str(raw_name or "").upper().replace("_", " ").strip()
    full_context = f"{verb} {text}"

    domain_suffix = ""
    if any(x in full_context for x in ["LEGAL", "GOVERNANCE", "EHDS", "GDPR", "PRIVACY", "CONSENT", "REGULATION", "LAW", "COMPLIANCE", "MANDATE"]):
        domain_suffix = "_LEGAL"
    elif any(x in full_context for x in ["DATA", "INTEROPERABILITY", "QUALITY", "ACCESS", "SOURCE", "LINKAGE", "SILO", "ELECTRONIC RECORD", "EHR", "RWD", "MISSING VALUES"]):
        domain_suffix = "_DATA"
    elif any(x in full_context for x in ["METHOD", "BIAS", "CONFOUNDING", "VALIDITY", "DESIGN", "STUDY", "EVIDENCE", "INFERENCE", "CAUSAL", "SAMPLE SIZE"]):
        domain_suffix = "_METHOD"
    elif any(x in full_context for x in ["DECISION", "HTA", "PAYER", "REIMBURSEMENT", "APPRAISAL", "VALUE", "ASSESSMENT", "AUTHORITY", "UNCERTAINTY"]):
        domain_suffix = "_DECISION"
    elif any(x in full_context for x in ["IMPLEMENT", "FEASIBIL", "PRACTICE", "ROUTINE", "CLINICAL", "HOSPITAL", "RESOURCE", "WORKFLOW", "ADOPTION", "COST", "INFRASTRUCTURE"]):
        domain_suffix = "_IMPLEMENTATION"

    action_prefix = "RELATED_TO"
    if any(v in verb for v in ["HINDER", "LIMIT", "CHALLENGE", "IMPEDE", "PREVENT", "RESTRICT", "BARRIER", "PROBLEM", "DIFFICULT", "BLOCK"]):
        action_prefix = "HINDERS"
    elif any(v in verb for v in ["LACK", "MISSING", "NEED", "ABSENCE", "VOID", "INSUFFICIENT", "GAP"]):
        action_prefix = "HAS_GAP"
    elif any(v in verb for v in ["ADDRESS", "MITIGATE", "SOLVE", "RESOLVE", "FIX", "RECTIFY", "OVERCOME"]):
        action_prefix = "MITIGATES"
    elif any(v in verb for v in ["SUPPORT", "ENABLE", "IMPROVE", "ENHANCE", "FACILITATE", "ALLOW", "PROMOTE", "BENEFIT"]):
        action_prefix = "FACILITATES"
    elif any(v in verb for v in ["RECOMMEND", "SUGGEST", "PROPOSE", "GUIDE", "ADVISE", "SHOULD", "MUST", "PROVIDE GUIDANCE"]):
        action_prefix = "RECOMMENDS"
    elif any(v in verb for v in ["MANDATE", "REQUIRE", "GOVERN", "COMPLY", "ADHERE", "OBLIGATE"]):
        action_prefix = "REGULATES"
    elif any(v in verb for v in ["LEAD", "RESULT", "CAUSE", "TRIGGER", "GENERATE", "DRIVE"]):
        action_prefix = "CAUSES"

    if action_prefix == "RELATED_TO" and domain_suffix != "":
        return f"RELATED_TO{domain_suffix}"
    if domain_suffix:
        return f"{action_prefix}{domain_suffix}"
    return action_prefix

