from transformers import AutoTokenizer, AutoModel
import torch
import torch.nn.functional as F

# ============================================================================
# Singleton para el modelo - Carga UNA SOLA VEZ con transformers
# ============================================================================
class ModelSingleton:
    _instance = None
    _model = None
    _tokenizer = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelSingleton, cls).__new__(cls)
        return cls._instance
    
    def get_model(self):
        if self._model is None:
            print("Loading transformers model (one-time operation)...")
            model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            self._tokenizer = AutoTokenizer.from_pretrained(model_name)
            self._model = AutoModel.from_pretrained(model_name)
            print("Transformers model loaded successfully")
        return self._model, self._tokenizer

_model_singleton = ModelSingleton()

def get_transformer_model():
    return _model_singleton.get_model()

def encode_texts(texts):
    """
    Reemplaza model.encode() de sentence-transformers
    """
    model, tokenizer = get_transformer_model()
    
    if isinstance(texts, str):
        texts = [texts]
    
    # Tokenizar
    encoded_input = tokenizer(
        texts, 
        padding=True, 
        truncation=True, 
        return_tensors='pt',
        max_length=512
    )
    
    # Generar embeddings
    with torch.no_grad():
        model_output = model(**encoded_input)
    
    # Mean pooling (igual que sentence-transformers)
    embeddings = mean_pooling(model_output, encoded_input['attention_mask'])
    embeddings = F.normalize(embeddings, p=2, dim=1)
    
    return embeddings.numpy()

def mean_pooling(model_output, attention_mask):
    """Implementación de mean pooling igual a sentence-transformers"""
    token_embeddings = model_output[0]
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)