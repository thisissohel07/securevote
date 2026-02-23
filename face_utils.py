import json
import numpy as np
import cv2
from deepface import DeepFace


def b64_to_bgr(base64_data: str) -> np.ndarray:
    # base64_data like "data:image/jpeg;base64,...."
    if "," in base64_data:
        base64_data = base64_data.split(",", 1)[1]
    import base64
    img_bytes = base64.b64decode(base64_data)
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    return img

def get_embedding_from_bgr(bgr_img: np.ndarray, model_name="Facenet512") -> list[float]:
    # DeepFace expects RGB in many cases; convert.
    rgb = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)

    reps = DeepFace.represent(
        img_path=rgb,
        model_name=model_name,
        enforce_detection=True
    )
    # DeepFace returns list of dicts
    emb = reps[0]["embedding"]
    return emb

def cosine_distance(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    denom = (np.linalg.norm(va) * np.linalg.norm(vb)) + 1e-9
    sim = float(np.dot(va, vb) / denom)
    return 1.0 - sim

def emb_to_text(emb: list[float]) -> str:
    return json.dumps(emb)

def text_to_emb(text: str) -> list[float]:
    return json.loads(text)