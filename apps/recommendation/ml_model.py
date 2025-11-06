import os
import numpy as np
import hashlib
from huggingface_hub import InferenceClient
from django.conf import settings
from django.core.cache import cache

# ============================================================================
# Cliente de HF API - Versión simplificada sin singleton
# ============================================================================

MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

def get_hf_client():
    """
    Crea y retorna un cliente de HF API
    Es liviano, no necesita singleton
    """
    try:
        token = settings.HF_API_TOKEN
    except AttributeError:
        raise ImportError(
            "La variable HF_API_TOKEN no está definida en settings.py o en el .env"
        )
    
    return InferenceClient(model=MODEL_ID, token=token)

def encode_texts(texts):
    """
    Genera embeddings usando la API de Hugging Face
    Con caché para evitar llamadas repetidas a la API
    """
    client = get_hf_client()
    
    # Normalizar entrada a lista
    if isinstance(texts, str):
        texts = [texts]
    
    embeddings_list = []
    
    for text in texts:
        # Generar hash del texto para caché
        text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        cache_key = f"embedding_{text_hash}"
        
        # Intentar obtener del caché
        cached_embedding = cache.get(cache_key)
        
        if cached_embedding is not None:
            embeddings_list.append(cached_embedding)
        else:
            # Llamar a la API de HF
            try:
                embedding = client.feature_extraction(text)
                
                # Convertir a numpy array si es necesario
                if not isinstance(embedding, np.ndarray):
                    embedding = np.array(embedding)
                
                # Guardar en caché (por 24 horas)
                cache.set(cache_key, embedding, 60 * 60 * 24)
                
                embeddings_list.append(embedding)
            except Exception as e:
                print(f"Error al generar embedding para texto: {text[:50]}...")
                print(f"Error: {str(e)}")
                raise
    
    # Convertir lista a array de numpy
    embeddings = np.array(embeddings_list)
    
    # Normalizar embeddings (igual que sentence-transformers)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / np.maximum(norms, 1e-9)
    
    return embeddings

def encode_texts_batch(texts, batch_size=32):
    """
    Versión optimizada para procesar muchos textos
    Procesa en batches para mejor rendimiento
    """
    if isinstance(texts, str):
        texts = [texts]
    
    all_embeddings = []
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        batch_embeddings = encode_texts(batch)
        all_embeddings.append(batch_embeddings)
    
    return np.vstack(all_embeddings) if all_embeddings else np.array([])