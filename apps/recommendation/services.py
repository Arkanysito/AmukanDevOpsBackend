import numpy as np
from django.db.models import Prefetch
from apps.users.models import CustomUser, UserInterest
from apps.location.models import Place
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

def get_user_vector(user: CustomUser) -> np.ndarray:
    """Construye vector de usuario promediando embeddings de sus intereses."""
    interests = UserInterest.objects.filter(user_id=user.id)\
                  .select_related("interest_id")
    
    if not interests:
        return None
    
    model = SentenceTransformer("all-MiniLM-L6-v2")
    
    interest_embeddings = []
    for interest in interests:
        text = interest.interest_id.name
        emb = model.encode(text)
        weighted_emb = emb * float(interest.weight)
        interest_embeddings.append(weighted_emb)
    
    user_embedding = np.mean(interest_embeddings, axis=0)
    return user_embedding  # Solo retorna el embedding, no una tupla

def recommend_places(user: CustomUser, top_k: int = 10):
    try:
        u_vec = get_user_vector(user)
        
        print(f"User vector type: {type(u_vec)}")
        if isinstance(u_vec, np.ndarray):
            print(f"User vector shape: {u_vec.shape}")
        
        # Verificación MUY segura
        if (u_vec is None or 
            (isinstance(u_vec, np.ndarray) and u_vec.size == 0) or
            (hasattr(u_vec, '__len__') and len(u_vec) == 0)):
            print("Using fallback: invalid user vector")
            return Place.objects.order_by("-rating")[:top_k]

        candidates = Place.objects.exclude(embedding=None)
        print(f"Candidates count: {candidates.count()}")
        
        results = []
        
        for i, p in enumerate(candidates):
            # Debug para los primeros 3 lugares
            if i < 3:
                print(f"Place {p.place_id} - embedding type: {type(p.embedding)}")
                if hasattr(p.embedding, '__len__'):
                    print(f"Place {p.place_id} - embedding length: {len(p.embedding)}")
            
            # Saltar si es None
            if p.embedding is None:
                continue
                
            # Convertir a lista si es necesario
            if isinstance(p.embedding, np.ndarray):
                embedding_data = p.embedding.tolist()
            else:
                embedding_data = p.embedding
                
            # Verificar que sea una lista válida
            if (not isinstance(embedding_data, list) or 
                len(embedding_data) == 0 or 
                len(embedding_data) != len(u_vec)):
                if i < 3:  # Debug para los primeros
                    print(f"Skipping place {p.place_id} - invalid embedding")
                continue
                
            # Calcular similitud
            place_embedding = np.array(embedding_data, dtype=np.float32)
            score = cosine_similarity([u_vec], [place_embedding])[0][0]
            results.append((score, p))
            
            if i < 3:  # Debug para los primeros
                print(f"Place {p.place_id} - score: {score}")
        
        print(f"Total results: {len(results)}")
        
        if not results:
            return Place.objects.order_by("-rating")[:top_k]
        
        results.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in results[:top_k]]
        
    except Exception as e:
        print(f"Error in recommend_places: {e}")
        import traceback
        traceback.print_exc()
        return Place.objects.order_by("-rating")[:top_k]