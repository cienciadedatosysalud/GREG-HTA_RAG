import os
import ollama
from falkordb import FalkorDB
import lancedb
from dotenv import load_dotenv

load_dotenv()

# MODEL PARAMETERS.
OLLAMA_HOST = os.getenv("OLLAMA_HOST")

MODEL_NAME = os.getenv("MODEL_EXTRACTOR") 
TEMPERATURE_EXTRACTOR = float(os.getenv("TEMPERATURE_EXTRACTOR",0.0))

TEMPERATURE_METADATA=float(os.getenv("TEMPERATURE_METADATA",0.0))

NUM_CTX = int(os.getenv("NUM_CTX",16384))

REPEAT_PENALTY = float(os.getenv("REPEAT_PENALTY",1.1))

EMBEDDING_MODEL = os.getenv("MODEL_EMBEDDING", "nomic-embed-text")
EMBEDDING_DIM = 768  # Dimensión fija para Nomic

FALKOR_HOST = os.getenv("FALKOR_HOST", "falkordb")
FALKOR_PORT = int(os.getenv("FALKOR_PORT", 6379))
GRAPH_NAME = os.getenv("GRAPH_NAME", "rwe_knowledge_graph")




# INGESTION PARAMETERS.
MIN_PARENT_SIZE = int(os.getenv("MIN_PARENT_SIZE",7000))
MAX_PARENT_SIZE = int(os.getenv("MAX_PARENT_SIZE",13000))
CHILD_SIZE = int(os.getenv("CHILD_SIZE",1000))
CHILD_OVERLAP = int(os.getenv("CHILD_OVERLAP",2))



# --- Clientes ---
client_ollama = ollama.Client(host=OLLAMA_HOST)
falkor_client = FalkorDB(host=FALKOR_HOST, port=FALKOR_PORT)

def get_graph():
    """Retorna la instancia del grafo de FalkorDB"""
    return falkor_client.select_graph(GRAPH_NAME)

def get_lance_db():
    """Retorna la conexión a LanceDB"""
    # Usamos la ruta interna del contenedor
    return lancedb.connect("/app/data/lancedb")