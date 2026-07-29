import json
from typing import List
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

def get_embedding_from_bgr(bgr_img: np.ndarray, model_name="Facenet512") -> List[float]:
    # DeepFace expects RGB in many cases; convert.
    rgb = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)

    last_error = None
    # Try standard opencv detector first, then fallback backends if detector fails or cv2 is missing attributes
    for backend in ["opencv", "ssd", "opencv", "skip"]:
        try:
            reps = DeepFace.represent(
                img_path=rgb,
                model_name=model_name,
                detector_backend=backend,
                enforce_detection=True if backend != "skip" else False
            )
            if reps and len(reps) > 0:
                return reps[0]["embedding"]
        except Exception as e:
            last_error = e
            continue

    if last_error:
        raise last_error
    raise Exception("Face detection failed.")

def cosine_distance(a: List[float], b: List[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    denom = (np.linalg.norm(va) * np.linalg.norm(vb)) + 1e-9
    sim = float(np.dot(va, vb) / denom)
    return 1.0 - sim

def emb_to_text(emb: List[float]) -> str:
    return json.dumps(emb)

def text_to_emb(text: str) -> List[float]:
    return json.loads(text)
