import requests
import os
import numpy as np
import hashlib
from django.core.cache import cache

def encode_texts(texts):
    """
    Genera embeddings usando la API de Inferencia de Hugging Face,
    optimizada con el caché de Django.
    """
    
    if isinstance(texts, str):
        texts = [texts]

    # --- 1. Lógica de Caché ---
    # Creamos una clave de caché única basada en el contenido de los textos
    # Usamos hash para mantener la clave corta y consistente
    text_hash = hashlib.md5(str(texts).encode('utf-8')).hexdigest()
    cache_key = f"embedding_{text_hash}"
    
    # Intentamos obtener el resultado del caché
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        # ¡Encontrado! Devolvemos el resultado cacheado
        return cached_result

    # --- 2. Si no está en caché, llamar a la API ---
    
    # Obtenemos el API Token de las variables de entorno
    api_token = os.environ.get("HF_API_TOKEN")
    if not api_token:
        raise ValueError("La variable de entorno HF_API_TOKEN no está configurada.")

    # Definimos el modelo y la URL de la API
    model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    api_url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{model_name}"
    headers = {"Authorization": f"Bearer {api_token}"}

    try:
        response = requests.post(
            api_url,
            headers=headers,
            json={
                "inputs": texts,
                "options": {"wait_for_model": True}
            }
        )
        response.raise_for_status() # Lanza error si la API falla (4xx, 5xx)
        
        results = response.json()

        # --- 3. Procesar y Normalizar (Igual que antes) ---
        if isinstance(results, list):
            embeddings = np.array(results)
            
            # Replicamos F.normalize(embeddings, p=2, dim=1) con numpy
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            # Evitar división por cero si un vector es nulo
            norms = np.where(norms == 0, 1e-9, norms) 
            normalized_embeddings = embeddings / norms
            
            # --- 4. Guardar en Caché antes de devolver ---
            # Guardamos el resultado por 24 horas (86400 segundos)
            cache.set(cache_key, normalized_embeddings, timeout=86400)
            
            return normalized_embeddings
        
        elif 'error' in results:
            raise Exception(f"Error en la API de Hugging Face: {results.get('error')}")
        else:
            raise Exception(f"Respuesta inesperada de la API: {results}")

    except requests.exceptions.RequestException as e:
        print(f"Error al contactar la API de Hugging Face: {e}")
        raise