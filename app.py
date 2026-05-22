"""
╔══════════════════════════════════════════════════════╗
║           VIORA — Backend Flask                      ║
║  Sistema de Disciplina Personal                      ║
║                                                      ║
║  Endpoints:                                          ║
║  • Tareas (CRUD + completar)                         ║
║  • Hábitos (CRUD + log diario)                       ║
║  • Finanzas (CRUD)                                   ║
║  • Apuesta mock (activar / verificar / devolver)     ║
║  • Comunidad (posts + votos)                         ║
║  • Verificación foto gym con Hugging Face CLIP       ║
╚══════════════════════════════════════════════════════╝
"""

import json, os, base64, uuid, io
from datetime import datetime, date, timedelta
from functools import wraps
from urllib.parse import urlencode
import jwt
from werkzeug.security import generate_password_hash, check_password_hash
import requests
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from flask import Flask, request, jsonify, send_from_directory, redirect, make_response
from flask_cors import CORS
try:
    from supabase import create_client, Client
except Exception:
    create_client = None
    Client = None
try:
    from postgrest.exceptions import APIError
except Exception:
    APIError = Exception

# ── APP ────────────────────────────────────────────────
app = Flask(__name__)

cors_origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5000",
    "http://127.0.0.1:5000",
]
env_cors = os.environ.get("CORS_ORIGINS", "").strip()
if env_cors:
    cors_origins = [origin.strip() for origin in env_cors.split(",") if origin.strip()]

CORS(app, origins=cors_origins, supports_credentials=True)

BASE_DIR = os.path.dirname(__file__)

def load_env_file():
    env_path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    except Exception:
        pass

load_env_file()

# ── PHOTO VERIFICATION AI ──────────────────────────────
HF_TOKEN = os.environ.get("HF_TOKEN", "").strip()
HF_ZERO_SHOT_MODEL = os.environ.get("HF_ZERO_SHOT_MODEL", "openai/clip-vit-base-patch32").strip()
HF_IMAGE_CLASSIFICATION_MODEL = os.environ.get("HF_IMAGE_CLASSIFICATION_MODEL", "microsoft/resnet-50").strip()
PHOTO_VERIFY_PROVIDER = os.environ.get("VIORA_PHOTO_VERIFY_PROVIDER", "places365").strip().lower()
PHOTO_VERIFY_DEMO = (
    os.environ.get("VIORA_PHOTO_VERIFY_DEMO", "").strip().lower() in {"1", "true", "yes"}
)

PLACES365_DIR = os.path.join(BASE_DIR, "data", "models", "places365")
PLACES365_WEIGHTS = os.environ.get(
    "PLACES365_WEIGHTS",
    os.path.join(PLACES365_DIR, "resnet18_places365.pth.tar"),
).strip()
PLACES365_CATEGORIES = os.environ.get(
    "PLACES365_CATEGORIES",
    os.path.join(PLACES365_DIR, "categories_places365.txt"),
).strip()
PLACES365_GYM_THRESHOLD = float(os.environ.get("PLACES365_GYM_THRESHOLD", "0.045"))

# ── SUPABASE ─────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    or os.environ.get("SUPABASE_KEY", "").strip()
)
SUPABASE_ANON_KEY = (
    os.environ.get("SUPABASE_ANON_KEY", "").strip()
    or os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
)
DEFAULT_USER_ID = os.environ.get("VIORA_USER_ID", "11111111-1111-1111-1111-111111111111")
TASK_CATEGORIES = {"gym", "social", "habitos", "salud_mental"}

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()
APP_BASE_URL = os.environ.get("APP_BASE_URL", "").strip()
JWT_SECRET = os.environ.get("JWT_SECRET", "").strip()
if not JWT_SECRET and not os.environ.get("VERCEL"):
    JWT_SECRET = "viora-local-dev-secret"
JWT_TTL_MINUTES = int(os.environ.get("JWT_TTL_MINUTES", "10080"))

supabase = None
supabase_auth = None
SUPABASE_ENABLED = False
SUPABASE_AUTH_ENABLED = False
SUPABASE_ERROR = ""
if create_client and SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        SUPABASE_ENABLED = True
    except Exception as exc:
        SUPABASE_ERROR = str(exc)
        SUPABASE_ENABLED = False
elif not create_client:
    SUPABASE_ERROR = "No se pudo importar el paquete supabase"
elif not SUPABASE_URL or not SUPABASE_KEY:
    SUPABASE_ERROR = "SUPABASE_URL o SUPABASE_KEY no configurados"

if create_client and SUPABASE_URL and SUPABASE_ANON_KEY:
    try:
        supabase_auth = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        SUPABASE_AUTH_ENABLED = True
    except Exception:
        SUPABASE_AUTH_ENABLED = False

# ── DATA FILES (almacenamiento JSON persistente) ────────
DATA_DIR = os.environ.get("VIORA_DATA_DIR")
if not DATA_DIR:
    DATA_DIR = "/tmp/viora_data" if os.environ.get("VERCEL") else os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

TASKS_FILE    = os.path.join(DATA_DIR, "tasks.json")
HABITS_FILE   = os.path.join(DATA_DIR, "habits.json")
FINANCES_FILE = os.path.join(DATA_DIR, "finances.json")
BET_FILE      = os.path.join(DATA_DIR, "bet.json")
COMMUNITY_FILE= os.path.join(DATA_DIR, "community.json")
COMMUNITY_COMMENTS_FILE = os.path.join(DATA_DIR, "community_comments.json")
USERS_FILE    = os.path.join(DATA_DIR, "users.json")
AUTH_USERS_FILE = os.path.join(DATA_DIR, "auth_users.json")

# ── HELPERS ───────────────────────────────────────────
def read_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_auth_store():
    if SUPABASE_ENABLED and supabase and has_privileged_supabase_key():
        try:
            res = supabase.table("auth_users").select("email, name, password_hash, created_at").execute()
            return {
                (row.get("email") or "").strip().lower(): row
                for row in (res.data or [])
                if (row.get("email") or "").strip()
            }
        except Exception:
            pass

    data = read_json(AUTH_USERS_FILE, {})
    if isinstance(data, list):
        normalized = {}
        for item in data:
            email = (item.get("email") or "").strip().lower()
            if email:
                normalized[email] = item
        return normalized
    if isinstance(data, dict):
        return data
    return {}

def save_auth_store(store):
    if SUPABASE_ENABLED and supabase and has_privileged_supabase_key():
        try:
            rows = []
            for email, user in store.items():
                rows.append({
                    "email": email,
                    "name": user.get("name") or email.split("@")[0],
                    "password_hash": user.get("password_hash", ""),
                    "created_at": user.get("created_at") or now_str(),
                })
            if rows:
                supabase.table("auth_users").upsert(rows, on_conflict="email").execute()
                return True
        except APIError as exc:
            message = getattr(exc, "message", "") or str(exc)
            if "permission denied" in message.lower():
                app.logger.error(
                    "No se pudo guardar auth_users: la clave del backend no tiene permisos. "
                    "Configura SUPABASE_SERVICE_ROLE_KEY con la service_role key."
                )
            else:
                app.logger.exception("No se pudo guardar auth_users en Supabase")
            return False
        except Exception:
            app.logger.exception("No se pudo guardar auth_users en Supabase")
            return False

    write_json(AUTH_USERS_FILE, store)
    return True

def today_str():
    return date.today().isoformat()

def now_str():
    return datetime.now().isoformat(timespec="seconds")

def get_supabase_key_role():
    if not SUPABASE_KEY:
        return "missing"
    try:
        payload = jwt.decode(SUPABASE_KEY, options={"verify_signature": False})
        return payload.get("role") or "unknown"
    except Exception:
        if SUPABASE_KEY.startswith("sb_secret_"):
            return "secret"
        return "unknown"

def has_privileged_supabase_key():
    return get_supabase_key_role() in {"service_role", "secret"}

def _is_schema_cache_error(exc):
    s = str(exc)
    return "PGRST204" in s or "schema cache" in s.lower()

def _extract_bad_column(exc):
    import re
    m = re.search(r"Could not find the '(\w+)' column", str(exc))
    return m.group(1) if m else None

def _sb_insert(table, payload, required_keys):
    current = dict(payload)
    for _ in range(12):
        try:
            return supabase.table(table).insert(current).execute()
        except Exception as e:
            if _is_schema_cache_error(e):
                col = _extract_bad_column(e)
                if col and col not in required_keys and col in current:
                    current.pop(col)
                    continue
            raise
    raise Exception("Insert fallido tras múltiples reintentos de esquema")

def _sb_update(table, updates, required_keys, eq_filters):
    def _run(upd):
        q = supabase.table(table).update(upd)
        for col, val in eq_filters.items():
            q = q.eq(col, val)
        return q.execute()
    current = dict(updates)
    for _ in range(12):
        try:
            return _run(current)
        except Exception as e:
            if _is_schema_cache_error(e):
                col = _extract_bad_column(e)
                if col and col not in required_keys and col in current:
                    current.pop(col)
                    continue
            raise
    return None

def week_dates(reference=None):
    base = reference or date.today()
    monday = base - timedelta(days=base.weekday())
    return [monday + timedelta(days=i) for i in range(7)]

def map_task_row(row):
    category = normalize_task_category(
        row.get("category") or row.get("cat") or ("gym" if row.get("requiresPhoto", row.get("requires_photo", False)) else "habitos")
    )
    target = float(row.get("target", 1) or 1)
    current = float(row.get("current", target if row.get("done") else 0) or 0)
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "category": category,
        "description": row.get("description", ""),
        "unit": row.get("unit", "veces"),
        "target": target,
        "frequency": row.get("frequency") or row.get("period", "diaria"),
        "current": current,
        "status": "completed" if bool(row.get("done", False)) else "active",
        "period": row.get("period", "diaria"),
        "done": bool(row.get("done", False)),
        "requiresPhoto": category == "gym",
        "verified": bool(row.get("verified", False)),
        "createdAt": row.get("createdAt") or row.get("created_at"),
    }

def normalize_task_category(value):
    raw = str(value or "habitos").strip().lower()
    raw = raw.replace("-", "_").replace(" ", "_").replace("á", "a")
    if raw in {"mental", "saludmental", "salud_mental"}:
        raw = "salud_mental"
    return raw if raw in TASK_CATEGORIES else "habitos"

def task_requires_camera_verification(task):
    return normalize_task_category(task.get("category") or task.get("cat")) == "gym"

def map_habit_row(row, week=None):
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "icon": row.get("icon", "🔥"),
        "streak": int(row.get("streak", 0)),
        "week": week if week is not None else [False] * 7,
        "createdAt": row.get("created_at"),
    }

def map_finance_row(row):
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "type": row.get("type"),
        "amount": float(row.get("amount", 0)),
        "date": row.get("transaction_date") or row.get("date"),
        "createdAt": row.get("created_at"),
    }

def map_post_row(row, user_name=None):
    return {
        "id": row.get("id"),
        "user": user_name or row.get("user") or "Usuario",
        "cat": row.get("cat", "general"),
        "text": row.get("text"),
        "votes": int(row.get("votes", 0)),
        "comments": int(row.get("comments_count", row.get("comments", 0))),
        "createdAt": row.get("created_at"),
    }

def map_comment_row(row, user_name=None):
    return {
        "id": row.get("id"),
        "postId": row.get("post_id") or row.get("postId"),
        "user": user_name or row.get("user") or "Usuario",
        "text": row.get("text"),
        "createdAt": row.get("created_at") or row.get("createdAt"),
    }

def map_bet_row(row):
    if not row:
        return {}
    return {
        "active": bool(row.get("active", False)),
        "amount": float(row.get("amount", 0)),
        "date": row.get("bet_date") or row.get("date"),
        "completed": bool(row.get("completed", False)),
        "refunded": bool(row.get("refunded", False)),
        "transactionRef": row.get("transaction_ref") or row.get("transactionRef"),
        "createdAt": row.get("created_at"),
        "completedAt": row.get("completed_at") or row.get("completedAt"),
        "cancelledAt": row.get("cancelled_at") or row.get("cancelledAt"),
    }

def extract_json_object(text):
    cleaned = (text or "").replace("```json", "").replace("```", "").strip()
    if not cleaned:
        return {}
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start:end + 1]
    return json.loads(cleaned)

def normalize_photo_verification_result(result):
    detected = result.get("detectedItems") or result.get("detected_items") or []
    if isinstance(detected, str):
        detected = [item.strip() for item in detected.split(",") if item.strip()]
    if not isinstance(detected, list):
        detected = []

    confidence = int(float(result.get("confidence", 0) or 0))
    confidence = max(0, min(confidence, 100))
    approved = bool(result.get("approved")) and confidence >= 70

    return {
        "approved": approved,
        "confidence": confidence,
        "detectedItems": [str(item)[:32] for item in detected[:6]],
        "reason": str(result.get("reason") or "No se pudo justificar la verificación")[:180],
        "mode": result.get("mode") or ("demo" if result.get("demo") else "ai"),
    }

GYM_POSITIVE_LABELS = [
    "a photo inside a gym with exercise machines",
    "a photo of dumbbells or free weights",
    "a photo of weightlifting equipment",
    "a photo of a person exercising in a gym",
    "a photo of cardio equipment in a gym",
    "a photo of a barbell rack or weight bench",
]

GYM_NEGATIVE_LABELS = [
    "a selfie or portrait without gym equipment",
    "a bedroom or living room",
    "food or a meal",
    "a street or outdoor scene",
    "a screenshot or document",
    "an office or classroom",
]

GYM_IMAGE_CLASSIFICATION_KEYWORDS = [
    "dumbbell",
    "barbell",
    "horizontal bar",
    "parallel bars",
    "punching bag",
    "medicine ball",
    "basketball",
    "volleyball",
    "racket",
    "jersey",
]

PLACES365_GYM_SCENES = [
    "gymnasium/indoor",
    "gymnasium/outdoor",
    "exercise_room",
    "weight_room",
    "martial_arts_gym",
]

_places365_cache = {"model": None, "categories": None, "device": None, "error": None}

def _load_places365():
    if _places365_cache["model"] is not None:
        return _places365_cache["model"], _places365_cache["categories"], _places365_cache["device"]
    if _places365_cache["error"]:
        raise RuntimeError(_places365_cache["error"])
    if not os.path.exists(PLACES365_WEIGHTS) or not os.path.exists(PLACES365_CATEGORIES):
        raise RuntimeError("Modelo Places365 no instalado. Ejecuta scripts/setup_places365.py")

    try:
        import torch
        from torchvision import models
    except Exception as exc:
        raise RuntimeError("Faltan dependencias locales para Places365: torch, torchvision y pillow") from exc

    try:
        categories = []
        with open(PLACES365_CATEGORIES, "r", encoding="utf-8") as f:
            for line in f:
                scene = line.strip().split(" ")[0].lstrip("/")
                if scene:
                    categories.append(scene)

        model = models.resnet18(num_classes=365)
        checkpoint = torch.load(PLACES365_WEIGHTS, map_location="cpu")
        state_dict = checkpoint.get("state_dict", checkpoint)
        clean_state = {}
        for key, value in state_dict.items():
            key = key.replace("module.", "")
            clean_state[key] = value
        model.load_state_dict(clean_state)
        model.eval()

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(device)
        _places365_cache.update({"model": model, "categories": categories, "device": device, "error": None})
        return model, categories, device
    except Exception as exc:
        _places365_cache["error"] = str(exc)
        raise

def call_places365_scene_classification(image_bytes):
    try:
        import torch
        from PIL import Image
        from torchvision import transforms
    except Exception as exc:
        return normalize_photo_verification_result({
            "approved": False,
            "confidence": 0,
            "detectedItems": ["places365 dependencias faltantes"],
            "reason": "Places365 no disponible: instale torch, torchvision y pillow.",
            "mode": "places365-local",
        })

    try:
        model, categories, device = _load_places365()
    except Exception as exc:
        return normalize_photo_verification_result({
            "approved": False,
            "confidence": 0,
            "detectedItems": ["places365 no instalado"],
            "reason": f"Places365 no disponible: {str(exc)}",
            "mode": "places365-local",
        })

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        preprocess = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ])
        tensor = preprocess(image).unsqueeze(0).to(device)

        with torch.no_grad():
            probs = torch.nn.functional.softmax(model(tensor), dim=1)[0]
            scores, indexes = probs.topk(8)

        predictions = [
            {"label": categories[int(idx)] if int(idx) < len(categories) else str(int(idx)), "score": float(score)}
            for score, idx in zip(scores.cpu(), indexes.cpu())
        ]
        gym_matches = [
            item for item in predictions
            if any(scene in item["label"] for scene in PLACES365_GYM_SCENES)
        ]
        best_gym = max(gym_matches, key=lambda item: item["score"], default={"label": "", "score": 0})

        approved = best_gym["score"] >= PLACES365_GYM_THRESHOLD
        confidence = 0
        if approved:
            confidence = round(min(100, 70 + (best_gym["score"] / PLACES365_GYM_THRESHOLD - 1) * 30))
        elif best_gym["score"]:
            confidence = round(min(69, best_gym["score"] / PLACES365_GYM_THRESHOLD * 69))

        detected = [
            f"{item['label']} ({round(item['score'] * 100)}%)"
            for item in (gym_matches or predictions[:4])
        ]
        reason = (
            "Places365 clasificó la escena como gimnasio o sala de ejercicio."
            if approved
            else "Places365 no clasificó la escena como gimnasio."
        )

        return normalize_photo_verification_result({
            "approved": approved,
            "confidence": confidence,
            "detectedItems": detected,
            "reason": reason,
            "mode": "places365-local",
        })
    except Exception as exc:
        return normalize_photo_verification_result({
            "approved": False,
            "confidence": 0,
            "detectedItems": ["places365 error interno"],
            "reason": f"Places365 produjo un error interno: {str(exc)}",
            "mode": "places365-local",
        })

def call_hugging_face_zero_shot(image_b64):
    if not HF_TOKEN:
        return err("HF_TOKEN no configurado para verificar fotos con Hugging Face", 503)

    api_url = f"https://router.huggingface.co/hf-inference/models/{HF_ZERO_SHOT_MODEL}"
    labels = GYM_POSITIVE_LABELS + GYM_NEGATIVE_LABELS
    response = requests.post(
        api_url,
        headers={"Authorization": f"Bearer {HF_TOKEN}"},
        json={
            "inputs": image_b64,
            "parameters": {
                "candidate_labels": labels,
            },
            "options": {
                "wait_for_model": True,
            },
        },
        timeout=45,
    )

    if response.status_code == 503:
        return err("El modelo de Hugging Face se está cargando. Intenta otra vez en unos segundos.", 503)
    if response.status_code == 401:
        return err("HF_TOKEN inválido o sin permiso de Inference API", 401)
    if response.status_code >= 400:
        detail = response.text[:180]
        if "not supported by provider" in detail.lower():
            return {"fallback": "image-classification", "reason": detail}
        return err(f"Error Hugging Face: {detail}", 502)

    predictions = response.json()
    if isinstance(predictions, dict) and "error" in predictions:
        return err(f"Error Hugging Face: {predictions.get('error')}", 502)
    if not isinstance(predictions, list):
        return err("Respuesta inesperada de Hugging Face", 502)

    scored = [
        {"label": str(item.get("label", "")), "score": float(item.get("score", 0) or 0)}
        for item in predictions
        if isinstance(item, dict)
    ]
    positive = [item for item in scored if item["label"] in GYM_POSITIVE_LABELS]
    negative = [item for item in scored if item["label"] in GYM_NEGATIVE_LABELS]
    best_positive = max(positive, key=lambda item: item["score"], default={"label": "", "score": 0})
    best_negative = max(negative, key=lambda item: item["score"], default={"label": "", "score": 0})

    confidence = round(best_positive["score"] * 100)
    approved = best_positive["score"] >= 0.45 and best_positive["score"] >= (best_negative["score"] + 0.12)
    detected = [
        item["label"].replace("a photo of ", "").replace("a photo inside ", "").replace("a photo ", "")
        for item in positive
        if item["score"] >= 0.18
    ][:4]

    reason = (
        "La imagen coincide con contexto de gimnasio."
        if approved
        else "No hay suficiente evidencia visual de gimnasio o entrenamiento."
    )
    return normalize_photo_verification_result({
        "approved": approved,
        "confidence": confidence,
        "detectedItems": detected or [best_positive["label"]],
        "reason": reason,
        "mode": "huggingface",
    })

def call_hugging_face_image_classification(image_bytes, media_type="image/jpeg"):
    if not HF_TOKEN:
        return err("HF_TOKEN no configurado para verificar fotos con Hugging Face", 503)

    api_url = f"https://router.huggingface.co/hf-inference/models/{HF_IMAGE_CLASSIFICATION_MODEL}"
    response = requests.post(
        api_url,
        headers={
            "Authorization": f"Bearer {HF_TOKEN}",
            "Content-Type": media_type or "image/jpeg",
        },
        data=image_bytes,
        timeout=45,
    )

    if response.status_code == 503:
        return err("El modelo de Hugging Face se está cargando. Intenta otra vez en unos segundos.", 503)
    if response.status_code == 401:
        return err("HF_TOKEN inválido o sin permiso de Inference API", 401)
    if response.status_code >= 400:
        detail = response.text[:180]
        return err(f"Error Hugging Face: {detail}", 502)

    predictions = response.json()
    if isinstance(predictions, dict) and "error" in predictions:
        return err(f"Error Hugging Face: {predictions.get('error')}", 502)
    if not isinstance(predictions, list):
        return err("Respuesta inesperada de Hugging Face", 502)

    scored = [
        {"label": str(item.get("label", "")), "score": float(item.get("score", 0) or 0)}
        for item in predictions
        if isinstance(item, dict)
    ]
    best = max(scored, key=lambda item: item["score"], default={"label": "", "score": 0})
    gym_matches = [
        item for item in scored
        if any(keyword in item["label"].lower() for keyword in GYM_IMAGE_CLASSIFICATION_KEYWORDS)
    ]
    best_gym = max(gym_matches, key=lambda item: item["score"], default={"label": "", "score": 0})

    confidence = round(best_gym["score"] * 100)
    approved = best_gym["score"] >= 0.18 or (best_gym["score"] >= 0.12 and best_gym["score"] >= best["score"] * 0.7)
    detected = [item["label"] for item in gym_matches[:4]] or [best["label"]]
    reason = (
        "La imagen muestra objetos compatibles con entrenamiento o gimnasio."
        if approved
        else "No detecté objetos claros de gimnasio en la imagen."
    )

    return normalize_photo_verification_result({
        "approved": approved,
        "confidence": confidence,
        "detectedItems": detected,
        "reason": reason,
        "mode": "huggingface-image-classification",
    })

def ok(data=None, msg="ok", **kwargs):
    res = {"success": True, "message": msg}
    if data is not None:
        res["data"] = data
    res.update(kwargs)
    return jsonify(res), 200

def err(msg, code=400, **kwargs):
    res = {"success": False, "error": msg}
    res.update(kwargs)
    return jsonify(res), code

def is_request_secure():
    if request.is_secure:
        return True
    return request.headers.get("X-Forwarded-Proto", "").lower() == "https"

def get_google_redirect_uri():
    if GOOGLE_REDIRECT_URI:
        return GOOGLE_REDIRECT_URI
    base = request.url_root.rstrip("/")
    return f"{base}/api/auth/google/callback"

def decode_auth_token(token):
    if not token or not JWT_SECRET:
        return None
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_iat": False, "verify_aud": False},
        )
        if payload.get("aud") != "viora-app" or payload.get("ver") != 2:
            return None
        return payload
    except Exception:
        return None

def get_or_create_user_by_email(email, name, user_id=None):
    if not SUPABASE_ENABLED or not supabase:
        clean_email = (email or "").strip().lower()
        display_name = name or (clean_email.split("@")[0] if clean_email else "Usuario")
        users = read_json(USERS_FILE, [])

        for user in users:
            if user_id and user.get("id") == user_id:
                return user.get("id"), user.get("name") or display_name
            if clean_email and (user.get("email") or "").strip().lower() == clean_email:
                return user.get("id"), user.get("name") or display_name

        new_user = {
            "id": user_id or str(uuid.uuid4()),
            "name": display_name,
            "email": clean_email,
            "streak": 0,
            "totalTasks": 0,
            "totalRecovered": 0,
            "createdAt": now_str(),
        }
        users.append(new_user)
        write_json(USERS_FILE, users)
        return new_user["id"], new_user["name"]
    try:
        if user_id:
            existing_by_id = supabase.table("users").select("id, name, email").eq("id", user_id).limit(1).execute()
            if existing_by_id.data:
                row = existing_by_id.data[0]
                return row.get("id"), row.get("name") or name

        existing = supabase.table("users").select("id, name, email").eq("email", email).limit(1).execute()
        if existing.data:
            row = existing.data[0]
            return row.get("id"), row.get("name") or name

        payload = {
            "name": name or email.split("@")[0],
            "email": email,
            "streak": 0,
            "total_tasks": 0,
            "total_recovered": 0,
        }
        if user_id:
            payload["id"] = user_id

        inserted = supabase.table("users").insert(payload).execute()
        row = (inserted.data or [payload])[0]
        return row.get("id"), row.get("name")
    except Exception:
        return None, name

def verify_supabase_access_token(token):
    if not token:
        return None
    client = supabase if SUPABASE_ENABLED else None
    if not client and SUPABASE_AUTH_ENABLED:
        client = supabase_auth
    if not client:
        return None
    try:
        res = client.auth.get_user(token)
        user = getattr(res, "user", None)
        if not user:
            return None

        metadata = getattr(user, "user_metadata", None) or {}
        email = getattr(user, "email", None) or metadata.get("email")
        auth_user_id = getattr(user, "id", None)
        name = metadata.get("name") or metadata.get("full_name") or (email.split("@")[0] if email else "Usuario")
        if not email or not auth_user_id:
            return None

        profile_id, display_name = get_or_create_user_by_email(email, name, user_id=auth_user_id)
        if not profile_id:
            return None

        return {
            "sub": profile_id,
            "auth_sub": auth_user_id,
            "email": email,
            "name": display_name or name,
            "provider": "supabase",
        }
    except Exception:
        return None

def get_auth_payload():
    cookie_token = request.cookies.get("viora_token")
    cookie_payload = decode_auth_token(cookie_token)
    if cookie_payload:
        return cookie_payload

    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        payload = verify_supabase_access_token(token)
        if payload:
            return payload
        payload = decode_auth_token(token)
        if payload:
            return payload
    return None

def get_current_user_id():
    payload = get_auth_payload() or {}
    return payload.get("sub") or DEFAULT_USER_ID

def api_auth_required_in_this_environment():
    return SUPABASE_ENABLED or SUPABASE_AUTH_ENABLED

PUBLIC_API_ENDPOINTS = {
    "client_config",
    "google_login",
    "google_callback",
    "email_register",
    "email_login",
    "auth_me",
    "auth_logout",
    "health",
}

@app.before_request
def require_authenticated_private_api():
    if request.method == "OPTIONS":
        return None
    if not request.path.startswith("/api/"):
        return None
    if request.endpoint in PUBLIC_API_ENDPOINTS:
        return None
    if api_auth_required_in_this_environment() and not get_auth_payload():
        return err("Sesion requerida", 401, errorCode="auth_required")
    return None

def issue_auth_token(user_id, email=None, name=None):
    if not JWT_SECRET:
        return None
    now = datetime.utcnow()
    payload = {
        "aud": "viora-app",
        "ver": 2,
        "sub": user_id,
        "email": email,
        "name": name,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=JWT_TTL_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def build_auth_response(user_id, email, name):
    token = issue_auth_token(user_id, email=email, name=name)
    if not token:
        return err("JWT_SECRET no configurado", 500)
    response = make_response(
        jsonify({"success": True, "data": {"id": user_id, "email": email, "name": name}}),
        200,
    )
    response.set_cookie(
        "viora_token",
        token,
        httponly=True,
        secure=is_request_secure(),
        samesite="Lax",
        max_age=JWT_TTL_MINUTES * 60,
    )
    return response

# ── STATIC PAGES ─────────────────────────────────────
@app.route("/")
def serve_index2():
    return send_from_directory(BASE_DIR, "index.html")

@app.route("/chat")
def serve_index():
    return send_from_directory(BASE_DIR, "index.html")

@app.route("/api/config", methods=["GET"])
def client_config():
    return ok({
        "supabaseUrl": SUPABASE_URL,
        "supabaseAnonKey": SUPABASE_ANON_KEY,
        "supabaseAuthEnabled": bool(SUPABASE_URL and SUPABASE_ANON_KEY),
    })

@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory(BASE_DIR, filename)

# ══════════════════════════════════════════════════════
#  AUTH
# ══════════════════════════════════════════════════════

@app.route("/api/auth/google/login", methods=["GET"])
def google_login():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return err("Google OAuth no configurado", 500)

    state = uuid.uuid4().hex
    redirect_uri = get_google_redirect_uri()
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    response = redirect(auth_url)
    response.set_cookie(
        "viora_oauth_state",
        state,
        httponly=True,
        secure=is_request_secure(),
        samesite="Lax",
        max_age=600,
    )
    return response

@app.route("/api/auth/google/callback", methods=["GET"])
def google_callback():
    error = request.args.get("error")
    if error:
        return err(f"Google OAuth error: {error}", 400)

    state = request.args.get("state")
    cookie_state = request.cookies.get("viora_oauth_state")
    if not state or not cookie_state or state != cookie_state:
        return err("Estado OAuth invalido", 400)

    code = request.args.get("code")
    if not code:
        return err("Codigo OAuth faltante", 400)

    token_res = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": get_google_redirect_uri(),
            "grant_type": "authorization_code",
        },
        timeout=10,
    )

    if token_res.status_code != 200:
        return err("No se pudo canjear el token con Google", 502)

    token_data = token_res.json()
    raw_id_token = token_data.get("id_token")
    if not raw_id_token:
        return err("Google no devolvio id_token", 502)

    try:
        info = id_token.verify_oauth2_token(
            raw_id_token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except Exception:
        return err("id_token invalido", 401)

    email = info.get("email")
    name = info.get("name") or info.get("given_name") or email
    if not email:
        return err("Google no devolvio email", 401)

    user_id, display_name = get_or_create_user_by_email(email, name)
    if not user_id:
        return err("No se pudo crear el perfil en Supabase. Revisa la tabla users y permisos.", 502)

    redirect_target = APP_BASE_URL or request.url_root
    response = redirect(redirect_target)
    token = issue_auth_token(user_id, email=email, name=display_name)
    if not token:
        return err("JWT_SECRET no configurado", 500)
    response.set_cookie(
        "viora_token",
        token,
        httponly=True,
        secure=is_request_secure(),
        samesite="Lax",
        max_age=JWT_TTL_MINUTES * 60,
    )
    response.set_cookie("viora_oauth_state", "", expires=0)
    return response

@app.route("/api/auth/email/register", methods=["POST"])
def email_register():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    name = (body.get("name") or "").strip()

    if not email or not password:
        return err("Email y password son requeridos", 400)

    store = load_auth_store()
    if email in store:
        existing = store.get(email) or {}
        if check_password_hash(existing.get("password_hash", ""), password):
            user_id, display_name = get_or_create_user_by_email(email, existing.get("name") or name or email.split("@")[0])
            if not user_id:
                return err("No se pudo cargar el perfil en Supabase. Revisa la tabla users y permisos.", 502)
            return build_auth_response(user_id, email, display_name)
        return err(
            "Ya existe una cuenta con este email. Usa Ingresar o prueba otra contrasena.",
            409,
            code="email_already_registered",
        )

    store[email] = {
        "email": email,
        "name": name or email.split("@")[0],
        "password_hash": generate_password_hash(password),
        "created_at": now_str(),
    }
    if not save_auth_store(store):
        return err("No se pudo guardar el usuario de autenticacion en Supabase. Revisa la tabla auth_users y permisos.", 502)

    user_id, display_name = get_or_create_user_by_email(email, name or store[email]["name"])
    if not user_id:
        return err("No se pudo crear el perfil en Supabase. Revisa la tabla users y permisos.", 502)
    return build_auth_response(user_id, email, display_name)

@app.route("/api/auth/email/login", methods=["POST"])
def email_login():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""

    if not email or not password:
        return err("Email y password son requeridos", 400)

    store = load_auth_store()
    user = store.get(email)
    if not user or not check_password_hash(user.get("password_hash", ""), password):
        return err("Credenciales invalidas", 401)

    name = user.get("name") or email.split("@")[0]
    user_id, display_name = get_or_create_user_by_email(email, name)
    if not user_id:
        return err("No se pudo cargar el perfil en Supabase. Revisa la tabla users y permisos.", 502)
    return build_auth_response(user_id, email, display_name)

@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    payload = get_auth_payload()
    if not payload:
        return ok({}, "no-auth", authenticated=False)
    return ok(
        {
            "id": payload.get("sub"),
            "email": payload.get("email"),
            "name": payload.get("name"),
        },
        authenticated=True,
    )

@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    response = make_response(jsonify({"success": True, "message": "logout"}), 200)
    response.delete_cookie("viora_token", path="/", secure=is_request_secure(), samesite="Lax")
    response.set_cookie(
        "viora_token",
        "",
        expires=0,
        max_age=0,
        httponly=True,
        secure=is_request_secure(),
        samesite="Lax",
        path="/",
    )
    return response

# ── SEED DATA (solo si no existe) ─────────────────────
def seed():
    if SUPABASE_ENABLED:
        return
    if not os.path.exists(TASKS_FILE):
        write_json(TASKS_FILE, [
            {"id":"1","name":"Ejemplo: Leer 10 minutos","category":"habitos","period":"diaria","done":False,"requiresPhoto":False,"verified":False,"createdAt":now_str()},
        ])
    if not os.path.exists(HABITS_FILE):
        write_json(HABITS_FILE, [
            {"id":"1","name":"Meditación","icon":"🧠","streak":0,"week":[False,False,False,False,False,False,False],"createdAt":now_str()},
            {"id":"2","name":"Agua 2L","icon":"💧","streak":0,"week":[False,False,False,False,False,False,False],"createdAt":now_str()},
            {"id":"3","name":"Sin redes","icon":"📵","streak":0,"week":[False,False,False,False,False,False,False],"createdAt":now_str()},
        ])
    if not os.path.exists(FINANCES_FILE):
        write_json(FINANCES_FILE, [])
    if not os.path.exists(BET_FILE):
        write_json(BET_FILE, {"active":False,"amount":0,"date":None,"completed":False,"refunded":False})
    if not os.path.exists(COMMUNITY_FILE):
        write_json(COMMUNITY_FILE, [
            {"id":"1","user":"CarlosMV","cat":"gym","text":"Semana 3 sin fallar un día 💪 La clave: prepara el kit la noche anterior.","votes":24,"comments":5,"createdAt":now_str()},
            {"id":"2","user":"SaraD","cat":"finanzas","text":"Tip 50/30/20: ingresos → 50% fijos, 30% ahorro, 20% libre. Funciona perfecto 💰","votes":41,"comments":12,"createdAt":now_str()},
            {"id":"3","user":"FelipeR","cat":"habitos","text":"21 días cambian el cerebro. No saltes ni uno en las primeras 3 semanas 🔥","votes":67,"comments":8,"createdAt":now_str()},
        ])
    if not os.path.exists(COMMUNITY_COMMENTS_FILE):
        write_json(COMMUNITY_COMMENTS_FILE, [])
    if not os.path.exists(USERS_FILE):
        write_json(USERS_FILE, [
            {"id":"1","name":"Usuario Prueba","email":"test@viora.app","streak":0,"totalTasks":0,"totalRecovered":0,"createdAt":now_str()}
        ])

seed()

# ══════════════════════════════════════════════════════
#  TAREAS
# ══════════════════════════════════════════════════════

@app.route("/api/tasks", methods=["GET"])
def get_tasks():
    """Lista todas las tareas."""
    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table("tasks").select("*").eq("user_id", get_current_user_id()).order("created_at", desc=False).execute()
            tasks = [map_task_row(row) for row in (res.data or [])]
            return ok(tasks)
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    tasks = [map_task_row(row) for row in read_json(TASKS_FILE, [])]
    return ok(tasks)

@app.route("/api/tasks", methods=["POST"])
def create_task():
    """Crea una nueva tarea.
    Body: { name, category, period }
    """
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return err("El campo 'name' es requerido")
    category = normalize_task_category(body.get("category") or body.get("cat") or ("gym" if body.get("requiresPhoto") else "habitos"))
    requires_photo = category == "gym"

    if SUPABASE_ENABLED and supabase:
        payload = {
            "user_id": get_current_user_id(),
            "name": name,
            "category": category,
            "period": body.get("period", "diaria"),
            "done": False,
            "requires_photo": requires_photo,
            "verified": False,
            "unit": body.get("unit", "veces"),
            "target": float(body.get("target", 1) or 1),
            "current": 0,
        }
        core = {"user_id", "name"}
        try:
            res = _sb_insert("tasks", payload, core)
            row = (res.data or [payload])[0]
            return ok(map_task_row(row), "Tarea creada")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    task = {
        "id": str(uuid.uuid4()),
        "name": name,
        "category": category,
        "description": body.get("description", ""),
        "unit": body.get("unit", "veces"),
        "target": float(body.get("target", 1) or 1),
        "frequency": body.get("frequency") or body.get("period", "diaria"),
        "current": 0,
        "period": body.get("period", "diaria"),   # diaria | semanal | unica
        "done": False,
        "requiresPhoto": requires_photo,
        "verified": False,
        "createdAt": now_str(),
    }
    tasks = read_json(TASKS_FILE, [])
    tasks.append(task)
    write_json(TASKS_FILE, tasks)
    return ok(task, "Tarea creada")

@app.route("/api/tasks/<task_id>", methods=["PUT"])
def update_task(task_id):
    """Actualiza nombre / período de una tarea."""
    body = request.get_json(silent=True) or {}

    if SUPABASE_ENABLED and supabase:
        update_fields = {}
        if "name" in body:
            update_fields["name"] = body["name"]
        if "period" in body:
            update_fields["period"] = body["period"]
        if "category" in body or "cat" in body:
            category = normalize_task_category(body.get("category") or body.get("cat"))
            update_fields["category"] = category
            update_fields["requires_photo"] = category == "gym"
            update_fields["verified"] = False
            if category != "gym":
                update_fields["done"] = False
        if not update_fields:
            return err("Sin cambios para actualizar")
        try:
            res = _sb_update("tasks", update_fields, set(), {"id": task_id, "user_id": get_current_user_id()})
            if not res or not res.data:
                return err("Tarea no encontrada", 404)
            return ok(map_task_row(res.data[0]), "Tarea actualizada")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    tasks = read_json(TASKS_FILE, [])
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return err("Tarea no encontrada", 404)

    for field in ("name", "period"):
        if field in body:
            task[field] = body[field]
    if "category" in body or "cat" in body:
        category = normalize_task_category(body.get("category") or body.get("cat"))
        task["category"] = category
        task["requiresPhoto"] = category == "gym"
        task["verified"] = False
        if category != "gym":
            task["done"] = False
    write_json(TASKS_FILE, tasks)
    return ok(task, "Tarea actualizada")

@app.route("/api/tasks/<task_id>", methods=["DELETE"])
def delete_task(task_id):
    """Elimina una tarea."""
    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table("tasks").delete().eq("id", task_id).eq("user_id", get_current_user_id()).execute()
            if not res.data:
                return err("Tarea no encontrada", 404)
            return ok(msg="Tarea eliminada")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    tasks = read_json(TASKS_FILE, [])
    new_tasks = [t for t in tasks if t["id"] != task_id]
    if len(new_tasks) == len(tasks):
        return err("Tarea no encontrada", 404)
    write_json(TASKS_FILE, new_tasks)
    return ok(msg="Tarea eliminada")

@app.route("/api/tasks/<task_id>/complete", methods=["POST"])
def complete_task(task_id):
    """Marca/desmarca una tarea como completada.
    Body (opcional): { done: bool }
    """
    body = request.get_json(silent=True) or {}

    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table("tasks").select("*").eq("id", task_id).eq("user_id", get_current_user_id()).limit(1).execute()
            if not res.data:
                return err("Tarea no encontrada", 404)
            current = res.data[0]
            if "current" in body:
                raw_current = float(body.get("current"))
                new_done = body.get("done", raw_current >= float(current.get("target", 1) or 1))
                updates = {"done": bool(new_done), "current": raw_current}
            else:
                new_done = body.get("done", not current.get("done", False))
                updates = {"done": bool(new_done)}

            mapped_current = map_task_row(current)
            if bool(new_done) and task_requires_camera_verification(mapped_current) and not mapped_current.get("verified"):
                return err("Las tareas de gym requieren una foto tomada con cámara y verificada por IA", 403)

            upd = _sb_update("tasks", updates, set(), {"id": task_id, "user_id": get_current_user_id()})
            task = map_task_row(upd.data[0]) if (upd and upd.data) else map_task_row({**current, "done": new_done})

            tasks_res = supabase.table("tasks").select("done").eq("user_id", get_current_user_id()).execute()
            bet_check = _check_bet(tasks_res.data or [])
            return ok({"task": task, "betWon": bet_check}, "Estado actualizado")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    tasks = read_json(TASKS_FILE, [])
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return err("Tarea no encontrada", 404)

    if "current" in body:
        task["current"] = float(body["current"])
        new_done = body.get("done", task["current"] >= float(task.get("target", 1) or 1))
    else:
        new_done = body.get("done", not task.get("done", False))

    mapped_task = map_task_row(task)
    if bool(new_done) and task_requires_camera_verification(mapped_task) and not mapped_task.get("verified"):
        return err("Las tareas de gym requieren una foto tomada con cámara y verificada por IA", 403)
    task["done"] = new_done
    write_json(TASKS_FILE, tasks)

    # Verificar si la apuesta se ganó
    bet_check = _check_bet(tasks)
    return ok({"task": task, "betWon": bet_check}, "Estado actualizado")

@app.route("/api/tasks/<task_id>/add", methods=["POST"])
def add_task_progress(task_id):
    """Agrega progreso a una tarea o la completa si el esquema es simple."""
    body = request.get_json(silent=True) or {}
    amount = float(body.get("amount", 1) or 1)

    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table("tasks").select("*").eq("id", task_id).eq("user_id", get_current_user_id()).limit(1).execute()
            if not res.data:
                return err("Tarea no encontrada", 404)

            current = res.data[0]
            mapped_current = map_task_row(current)
            if task_requires_camera_verification(mapped_current) and not mapped_current.get("verified"):
                return err("Las tareas de gym requieren una foto tomada con cámara y verificada por IA", 403)
            upd = supabase.table("tasks").update({"done": True}).eq("id", task_id).eq("user_id", get_current_user_id()).execute()
            task = map_task_row(upd.data[0]) if upd.data else map_task_row({**current, "done": True})

            tasks_res = supabase.table("tasks").select("done").eq("user_id", get_current_user_id()).execute()
            bet_check = _check_bet(tasks_res.data or [])
            return ok({"task": task, "completed": True, "progress": 100, "betWon": bet_check}, "Progreso actualizado")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    tasks = read_json(TASKS_FILE, [])
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return err("Tarea no encontrada", 404)
    mapped_task = map_task_row(task)
    if task_requires_camera_verification(mapped_task) and not mapped_task.get("verified"):
        return err("Las tareas de gym requieren una foto tomada con cámara y verificada por IA", 403)

    if "target" in task:
        task["current"] = float(task.get("current", 0) or 0) + amount
        completed = task["current"] >= float(task.get("target", 1) or 1)
        task["done"] = completed
        task["status"] = "completed" if completed else "active"
        progress = min(round(task["current"] / float(task.get("target", 1) or 1) * 100, 2), 100)
    else:
        task["done"] = True
        completed = True
        progress = 100

    write_json(TASKS_FILE, tasks)
    bet_check = _check_bet(tasks)
    return ok({"task": task, "completed": completed, "progress": progress, "betWon": bet_check}, "Progreso actualizado")

def _check_bet(tasks):
    """Devuelve True si se completaron >= 3 tareas y la apuesta estaba activa."""
    if SUPABASE_ENABLED and supabase:
        try:
            bet_res = supabase.table("bets").select("*").eq("user_id", get_current_user_id()).order("created_at", desc=True).limit(1).execute()
            bet_row = bet_res.data[0] if bet_res.data else None
            if not bet_row or not bet_row.get("active") or bet_row.get("completed"):
                return False
            done_count = sum(1 for t in tasks if t.get("done"))
            if done_count >= 3:
                supabase.table("bets").update({
                    "completed": True,
                    "refunded": True,
                    "completed_at": now_str(),
                }).eq("id", bet_row["id"]).execute()
                return True
            return False
        except Exception:
            return False

    bet = read_json(BET_FILE, {})
    if not bet.get("active") or bet.get("completed"):
        return False
    done_count = sum(1 for t in tasks if t.get("done"))
    if done_count >= 3:
        bet["completed"] = True
        bet["refunded"]  = True   # Mock: en producción llamar PSE/Wompi aquí
        bet["completedAt"] = now_str()
        write_json(BET_FILE, bet)
        return True
    return False

# ══════════════════════════════════════════════════════
#  VERIFICACIÓN DE FOTO CON IA (Hugging Face CLIP)
# ══════════════════════════════════════════════════════

@app.route("/api/tasks/<task_id>/verify-photo", methods=["POST"])
def verify_photo(task_id):
    """Verifica una foto con Hugging Face CLIP para aprobar la tarea.
    Body: { image: "<base64>", mediaType: "image/jpeg" }
    """
    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table("tasks").select("*").eq("id", task_id).eq("user_id", get_current_user_id()).limit(1).execute()
            if not res.data:
                return err("Tarea no encontrada", 404)
            task = map_task_row(res.data[0])
            if not task_requires_camera_verification(task):
                return err("Solo las tareas de gym requieren verificación por foto")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)
    else:
        tasks = read_json(TASKS_FILE, [])
        task = next((t for t in tasks if t["id"] == task_id), None)
        if not task:
            return err("Tarea no encontrada", 404)
        mapped_task = map_task_row(task)
        if not task_requires_camera_verification(mapped_task):
            return err("Solo las tareas de gym requieren verificación por foto")

    body = request.get_json(silent=True) or {}
    image_b64  = body.get("image", "")
    media_type = body.get("mediaType", "image/jpeg")
    image_raw = b""

    if not image_b64:
        # Soporte multipart/form-data (envío de archivo directo)
        file = request.files.get("photo")
        if not file:
            return err("Se requiere imagen (campo 'image' en base64 o multipart 'photo')")
        raw = file.read()
        image_raw = raw
        image_b64  = base64.b64encode(raw).decode()
        media_type = file.content_type or "image/jpeg"
    else:
        try:
            image_raw = base64.b64decode(image_b64)
        except Exception:
            return err("Imagen base64 inválida")

    on_vercel = bool(os.environ.get("VERCEL"))

    if PHOTO_VERIFY_DEMO:
        result = normalize_photo_verification_result({
            "approved": True,
            "confidence": 86,
            "detectedItems": ["modo demo", "equipo de gym simulado"],
            "reason": "Modo demo: verificación aprobada.",
            "mode": "demo",
        })
    else:
        if PHOTO_VERIFY_PROVIDER == "places365":
            result = call_places365_scene_classification(image_raw)
            p365_unavailable = (
                result.get("mode") == "places365-local"
                and result.get("confidence") == 0
                and result.get("approved") is False
            )
            if p365_unavailable:
                if HF_TOKEN:
                    result = call_hugging_face_zero_shot(image_b64)
                elif on_vercel:
                    result = normalize_photo_verification_result({
                        "approved": True,
                        "confidence": 80,
                        "detectedItems": ["verificación automática"],
                        "reason": "Places365 no disponible en Vercel. Configura HF_TOKEN para verificación real.",
                        "mode": "demo",
                    })
            elif isinstance(result, dict) and result.get("fallback") == "huggingface":
                if HF_TOKEN:
                    result = call_hugging_face_zero_shot(image_b64)
                elif on_vercel:
                    result = normalize_photo_verification_result({
                        "approved": True,
                        "confidence": 80,
                        "detectedItems": ["verificación automática"],
                        "reason": "Verificación IA no disponible en Vercel. Configura HF_TOKEN para verificación real.",
                        "mode": "demo",
                    })
                else:
                    return err("La verificación Places365 falló; no se usará Hugging Face.", 503)
        else:
            result = call_hugging_face_zero_shot(image_b64)
        if isinstance(result, dict) and result.get("fallback") == "image-classification":
            result = call_hugging_face_image_classification(image_raw, media_type)
        if isinstance(result, tuple):
            return result

    # Si aprobada → marcar tarea como verificada y completada
    if result.get("approved"):
        if SUPABASE_ENABLED and supabase:
            try:
                _sb_update("tasks", {"verified": True, "done": True}, set(), {"id": task_id, "user_id": get_current_user_id()})
                tasks_res = supabase.table("tasks").select("done").eq("user_id", get_current_user_id()).execute()
                bet_won = _check_bet(tasks_res.data or [])
                result["betWon"] = bet_won
            except Exception as e:
                return err(f"Error Supabase: {str(e)}", 502)
        else:
            task["verified"] = True
            task["done"]     = True
            write_json(TASKS_FILE, tasks)
            bet_won = _check_bet(tasks)
            result["betWon"] = bet_won

    return ok(result, "Verificación completada")

# ══════════════════════════════════════════════════════
#  HÁBITOS
# ══════════════════════════════════════════════════════

@app.route("/api/habits", methods=["GET"])
def get_habits():
    if SUPABASE_ENABLED and supabase:
        try:
            habits_res = supabase.table("habits").select("*").eq("user_id", get_current_user_id()).order("created_at", desc=False).execute()
            habits = habits_res.data or []

            habit_ids = [h.get("id") for h in habits if h.get("id")]
            week = week_dates()
            week_strs = [d.isoformat() for d in week]
            logs_by_habit = {hid: {d: False for d in week_strs} for hid in habit_ids}

            if habit_ids:
                logs_res = supabase.table("habit_logs").select("habit_id, log_date, done").in_("habit_id", habit_ids).in_("log_date", week_strs).execute()
                for row in (logs_res.data or []):
                    hid = row.get("habit_id")
                    d = row.get("log_date")
                    if hid in logs_by_habit and d in logs_by_habit[hid]:
                        logs_by_habit[hid][d] = bool(row.get("done", False))

            mapped = []
            for habit in habits:
                hid = habit.get("id")
                week_flags = [logs_by_habit.get(hid, {}).get(d.isoformat(), False) for d in week]
                mapped.append(map_habit_row(habit, week_flags))

            return ok(mapped)
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    return ok(read_json(HABITS_FILE, []))

@app.route("/api/habits", methods=["POST"])
def create_habit():
    """Crea un nuevo hábito.
    Body: { name, icon }
    """
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return err("El campo 'name' es requerido")

    if SUPABASE_ENABLED and supabase:
        payload = {
            "user_id": get_current_user_id(),
            "name": name,
            "icon": body.get("icon", "🔥"),
            "streak": 0,
        }
        try:
            res = supabase.table("habits").insert(payload).execute()
            row = (res.data or [payload])[0]
            return ok(map_habit_row(row, [False] * 7), "Hábito creado")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    habit = {
        "id": str(uuid.uuid4()),
        "name": name,
        "icon": body.get("icon", "🔥"),
        "streak": 0,
        "week": [False] * 7,
        "createdAt": now_str(),
    }
    habits = read_json(HABITS_FILE, [])
    habits.append(habit)
    write_json(HABITS_FILE, habits)
    return ok(habit, "Hábito creado")

@app.route("/api/habits/<habit_id>", methods=["DELETE"])
def delete_habit(habit_id):
    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table("habits").delete().eq("id", habit_id).eq("user_id", get_current_user_id()).execute()
            if not res.data:
                return err("Hábito no encontrado", 404)
            return ok(msg="Hábito eliminado")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    habits = read_json(HABITS_FILE, [])
    new_habits = [h for h in habits if h["id"] != habit_id]
    if len(new_habits) == len(habits):
        return err("Hábito no encontrado", 404)
    write_json(HABITS_FILE, new_habits)
    return ok(msg="Hábito eliminado")

@app.route("/api/habits/<habit_id>/log", methods=["POST"])
def log_habit(habit_id):
    """Registra si se cumplió el hábito un día específico.
    Body: { day: 0-6 (0=lunes), done: bool }
    """
    body = request.get_json(silent=True) or {}
    day  = body.get("day")
    done = bool(body.get("done", True))

    if day is None or not (0 <= int(day) <= 6):
        return err("'day' debe ser un número entre 0 y 6")

    if SUPABASE_ENABLED and supabase:
        try:
            habit_res = supabase.table("habits").select("*").eq("id", habit_id).eq("user_id", get_current_user_id()).limit(1).execute()
            if not habit_res.data:
                return err("Hábito no encontrado", 404)

            week = week_dates()
            target_date = week[int(day)].isoformat()

            supabase.table("habit_logs").upsert({
                "habit_id": habit_id,
                "log_date": target_date,
                "done": done,
            }, on_conflict="habit_id,log_date").execute()

            logs_res = supabase.table("habit_logs").select("log_date, done").eq("habit_id", habit_id).in_("log_date", [d.isoformat() for d in week]).execute()
            done_map = {row.get("log_date"): bool(row.get("done", False)) for row in (logs_res.data or [])}
            week_flags = [done_map.get(d.isoformat(), False) for d in week]
            streak = sum(1 for flag in week_flags if flag)

            supabase.table("habits").update({"streak": streak}).eq("id", habit_id).execute()

            habit = map_habit_row(habit_res.data[0], week_flags)
            habit["streak"] = streak
            return ok(habit, "Hábito registrado")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    habits = read_json(HABITS_FILE, [])
    habit = next((h for h in habits if h["id"] == habit_id), None)
    if not habit:
        return err("Hábito no encontrado", 404)

    habit["week"][int(day)] = done
    habit["streak"] = sum(1 for d in habit["week"] if d)
    write_json(HABITS_FILE, habits)
    return ok(habit, "Hábito registrado")

# ══════════════════════════════════════════════════════
#  FINANZAS
# ══════════════════════════════════════════════════════

@app.route("/api/finances", methods=["GET"])
def get_finances():
    """Lista movimientos. Query params: ?type=income|expense&month=YYYY-MM"""
    ftype  = request.args.get("type")
    month  = request.args.get("month")

    if SUPABASE_ENABLED and supabase:
        try:
            query = supabase.table("finances").select("*").eq("user_id", get_current_user_id())
            if ftype:
                query = query.eq("type", ftype)
            if month:
                start = f"{month}-01"
                year, mon = month.split("-")
                next_month = datetime(int(year), int(mon), 1) + timedelta(days=32)
                end = datetime(next_month.year, next_month.month, 1) - timedelta(days=1)
                query = query.gte("transaction_date", start).lte("transaction_date", end.date().isoformat())

            res = query.order("transaction_date", desc=True).execute()
            items = [map_finance_row(row) for row in (res.data or [])]
            income = sum(item["amount"] for item in items if item.get("type") == "income")
            expense = sum(item["amount"] for item in items if item.get("type") == "expense")
            return ok({
                "items": items,
                "summary": {
                    "income": income,
                    "expense": expense,
                    "balance": income - expense,
                }
            })
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    finances = read_json(FINANCES_FILE, [])
    if ftype:
        finances = [f for f in finances if f.get("type") == ftype]
    if month:
        finances = [f for f in finances if f.get("date", "").startswith(month)]

    income  = sum(f["amount"] for f in finances if f.get("type") == "income")
    expense = sum(f["amount"] for f in finances if f.get("type") == "expense")

    return ok({
        "items": finances,
        "summary": {
            "income": income,
            "expense": expense,
            "balance": income - expense,
        }
    })

@app.route("/api/finances", methods=["POST"])
def create_finance():
    """Registra un ingreso o gasto.
    Body: { name, type, amount }
    """
    body = request.get_json(silent=True) or {}
    name   = (body.get("name") or "").strip()
    ftype  = body.get("type", "expense")
    amount = body.get("amount", 0)

    if not name:
        return err("El campo 'name' es requerido")
    if ftype not in ("income", "expense"):
        return err("'type' debe ser 'income' o 'expense'")
    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return err("'amount' debe ser un número positivo")

    if SUPABASE_ENABLED and supabase:
        payload = {
            "user_id": get_current_user_id(),
            "name": name,
            "type": ftype,
            "amount": amount,
            "transaction_date": today_str(),
        }
        try:
            res = supabase.table("finances").insert(payload).execute()
            row = (res.data or [payload])[0]
            return ok(map_finance_row(row), "Movimiento registrado")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    item = {
        "id": str(uuid.uuid4()),
        "name": name,
        "type": ftype,
        "amount": amount,
        "date": today_str(),
        "createdAt": now_str(),
    }
    finances = read_json(FINANCES_FILE, [])
    finances.append(item)
    write_json(FINANCES_FILE, finances)
    return ok(item, "Movimiento registrado")

@app.route("/api/finances/<fin_id>", methods=["DELETE"])
def delete_finance(fin_id):
    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table("finances").delete().eq("id", fin_id).eq("user_id", get_current_user_id()).execute()
            if not res.data:
                return err("Movimiento no encontrado", 404)
            return ok(msg="Movimiento eliminado")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    finances = read_json(FINANCES_FILE, [])
    new = [f for f in finances if f["id"] != fin_id]
    if len(new) == len(finances):
        return err("Movimiento no encontrado", 404)
    write_json(FINANCES_FILE, new)
    return ok(msg="Movimiento eliminado")

# ══════════════════════════════════════════════════════
#  APUESTA (Mock PSE/Wompi)
# ══════════════════════════════════════════════════════

@app.route("/api/bet", methods=["GET"])
def get_bet():
    """Estado actual de la apuesta."""
    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table("bets").select("*").eq("user_id", get_current_user_id()).order("created_at", desc=True).limit(1).execute()
            row = res.data[0] if res.data else None
            return ok(map_bet_row(row))
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    return ok(read_json(BET_FILE, {}))

@app.route("/api/bet", methods=["POST"])
def create_bet():
    """Activa una apuesta del día.
    Body: { amount: número en COP }
    Mock: simula cobro PSE, devuelve referencia de transacción.
    """
    body = request.get_json(silent=True) or {}
    amount = body.get("amount", 10000)
    try:
        amount = float(amount)
        if amount < 1000:
            raise ValueError
    except (TypeError, ValueError):
        return err("Monto mínimo: $1.000 COP")

    if SUPABASE_ENABLED and supabase:
        try:
            existing = supabase.table("bets").select("*").eq("user_id", get_current_user_id()).eq("active", True).eq("bet_date", today_str()).limit(1).execute()
            if existing.data:
                return err("Ya tienes una apuesta activa para hoy")

            payload = {
                "user_id": get_current_user_id(),
                "active": True,
                "amount": amount,
                "bet_date": today_str(),
                "completed": False,
                "refunded": False,
                "transaction_ref": f"VIORA-MOCK-{uuid.uuid4().hex[:8].upper()}",
            }
            res = supabase.table("bets").insert(payload).execute()
            row = (res.data or [payload])[0]
            return ok(map_bet_row(row), f"Apuesta de ${amount:,.0f} COP activada (mock PSE)")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    bet = read_json(BET_FILE, {})
    if bet.get("active") and bet.get("date") == today_str():
        return err("Ya tienes una apuesta activa para hoy")

    bet = {
        "active": True,
        "amount": amount,
        "date": today_str(),
        "completed": False,
        "refunded": False,
        "transactionRef": f"VIORA-MOCK-{uuid.uuid4().hex[:8].upper()}",
        "createdAt": now_str(),
    }
    write_json(BET_FILE, bet)
    return ok(bet, f"Apuesta de ${amount:,.0f} COP activada (mock PSE)")

@app.route("/api/bet/status", methods=["GET"])
def bet_status():
    """Verifica si la apuesta se ganó según las tareas completadas."""
    if SUPABASE_ENABLED and supabase:
        try:
            bet_res = supabase.table("bets").select("*").eq("user_id", get_current_user_id()).order("created_at", desc=True).limit(1).execute()
            bet_row = bet_res.data[0] if bet_res.data else None
            tasks_res = supabase.table("tasks").select("done").eq("user_id", get_current_user_id()).execute()
            done = sum(1 for t in (tasks_res.data or []) if t.get("done"))

            return ok({
                "bet": map_bet_row(bet_row),
                "tasksCompleted": done,
                "tasksRequired": 3,
                "won": done >= 3 and (bet_row or {}).get("active", False),
            })
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    bet   = read_json(BET_FILE, {})
    tasks = read_json(TASKS_FILE, [])
    done  = sum(1 for t in tasks if t.get("done"))

    return ok({
        "bet": bet,
        "tasksCompleted": done,
        "tasksRequired": 3,
        "won": done >= 3 and bet.get("active", False),
    })

@app.route("/api/bet/cancel", methods=["POST"])
def cancel_bet():
    """Cancela la apuesta activa (pierde el dinero)."""
    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table("bets").select("*").eq("user_id", get_current_user_id()).eq("active", True).order("created_at", desc=True).limit(1).execute()
            if not res.data:
                return err("No hay apuesta activa")
            bet_row = res.data[0]
            upd = supabase.table("bets").update({
                "active": False,
                "completed": False,
                "refunded": False,
                "cancelled_at": now_str(),
            }).eq("id", bet_row["id"]).execute()
            return ok(map_bet_row(upd.data[0] if upd.data else bet_row), "Apuesta cancelada")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    bet = read_json(BET_FILE, {})
    if not bet.get("active"):
        return err("No hay apuesta activa")
    bet["active"]    = False
    bet["completed"] = False
    bet["refunded"]  = False
    bet["cancelledAt"] = now_str()
    write_json(BET_FILE, bet)
    return ok(bet, "Apuesta cancelada")

# ══════════════════════════════════════════════════════
#  COMUNIDAD
# ══════════════════════════════════════════════════════

@app.route("/api/community", methods=["GET"])
def get_posts():
    """Lista posts. Query: ?cat=gym|finanzas|habitos|general"""
    cat = request.args.get("cat")

    if SUPABASE_ENABLED and supabase:
        try:
            query = supabase.table("community_posts").select("*")
            if cat and cat != "all":
                query = query.eq("cat", cat)
            res = query.order("votes", desc=True).execute()
            posts = res.data or []

            user_ids = list({p.get("user_id") for p in posts if p.get("user_id")})
            users_map = {}
            if user_ids:
                users_res = supabase.table("users").select("id, name").in_("id", user_ids).execute()
                users_map = {u["id"]: u.get("name") for u in (users_res.data or [])}

            mapped = [map_post_row(p, users_map.get(p.get("user_id"))) for p in posts]
            return ok(mapped)
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    posts = read_json(COMMUNITY_FILE, [])
    if cat and cat != "all":
        posts = [p for p in posts if p.get("cat") == cat]
    posts = sorted(posts, key=lambda p: p.get("votes", 0), reverse=True)
    return ok(posts)

@app.route("/api/community", methods=["POST"])
def create_post():
    """Publica un nuevo post.
    Body: { user, cat, text }
    """
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return err("El campo 'text' es requerido")
    if len(text) > 500:
        return err("Máximo 500 caracteres")

    if SUPABASE_ENABLED and supabase:
        payload = {
            "user_id": get_current_user_id(),
            "cat": body.get("cat", "general"),
            "text": text,
            "votes": 0,
            "comments_count": 0,
        }
        try:
            res = supabase.table("community_posts").insert(payload).execute()
            row = (res.data or [payload])[0]
            user_res = supabase.table("users").select("name").eq("id", get_current_user_id()).limit(1).execute()
            user_name = user_res.data[0].get("name") if user_res.data else "Usuario"
            return ok(map_post_row(row, user_name), "Post publicado")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    payload = get_auth_payload() or {}
    post_user = payload.get("name") or body.get("user") or "Usuario"
    post = {
        "id": str(uuid.uuid4()),
        "user": post_user,
        "cat": body.get("cat", "general"),
        "text": text,
        "votes": 0,
        "comments": 0,
        "createdAt": now_str(),
    }
    posts = read_json(COMMUNITY_FILE, [])
    posts.insert(0, post)
    write_json(COMMUNITY_FILE, posts)
    return ok(post, "Post publicado")

@app.route("/api/community/<post_id>/comments", methods=["GET"])
def get_comments(post_id):
    """Lista comentarios de un post."""
    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table("community_comments").select("*").eq("post_id", post_id).order("created_at", desc=False).execute()
            comments = res.data or []
            user_ids = list({c.get("user_id") for c in comments if c.get("user_id")})
            users_map = {}
            if user_ids:
                users_res = supabase.table("users").select("id, name").in_("id", user_ids).execute()
                users_map = {u["id"]: u.get("name") for u in (users_res.data or [])}
            return ok([map_comment_row(c, users_map.get(c.get("user_id"))) for c in comments])
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    comments = read_json(COMMUNITY_COMMENTS_FILE, [])
    comments = [c for c in comments if str(c.get("postId")) == str(post_id)]
    return ok(sorted(comments, key=lambda c: c.get("createdAt", "")))

@app.route("/api/community/<post_id>/comments", methods=["POST"])
def create_comment(post_id):
    """Comenta un post.
    Body: { text }
    """
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return err("El comentario no puede estar vacío")
    if len(text) > 300:
        return err("Máximo 300 caracteres")

    if SUPABASE_ENABLED and supabase:
        try:
            post_res = supabase.table("community_posts").select("id, comments_count").eq("id", post_id).limit(1).execute()
            if not post_res.data:
                return err("Post no encontrado", 404)
            payload = {
                "post_id": post_id,
                "user_id": get_current_user_id(),
                "text": text,
            }
            res = supabase.table("community_comments").insert(payload).execute()
            post = post_res.data[0]
            new_count = int(post.get("comments_count", 0) or 0) + 1
            supabase.table("community_posts").update({"comments_count": new_count}).eq("id", post_id).execute()
            user_res = supabase.table("users").select("name").eq("id", get_current_user_id()).limit(1).execute()
            user_name = user_res.data[0].get("name") if user_res.data else "Usuario"
            return ok(map_comment_row((res.data or [payload])[0], user_name), "Comentario publicado")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    posts = read_json(COMMUNITY_FILE, [])
    post = next((p for p in posts if str(p.get("id")) == str(post_id)), None)
    if not post:
        return err("Post no encontrado", 404)

    payload = get_auth_payload() or {}
    comment = {
        "id": str(uuid.uuid4()),
        "postId": post_id,
        "user": payload.get("name") or body.get("user") or "Usuario",
        "text": text,
        "createdAt": now_str(),
    }
    comments = read_json(COMMUNITY_COMMENTS_FILE, [])
    comments.append(comment)
    write_json(COMMUNITY_COMMENTS_FILE, comments)
    post["comments"] = int(post.get("comments", 0) or 0) + 1
    write_json(COMMUNITY_FILE, posts)
    return ok(comment, "Comentario publicado")

@app.route("/api/community/<post_id>/vote", methods=["POST"])
def vote_post(post_id):
    """Vota un post (toggle).
    Body: { action: 'up'|'down' }
    """
    body   = request.get_json(silent=True) or {}
    action = body.get("action", "up")

    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table("community_posts").select("*").eq("id", post_id).limit(1).execute()
            if not res.data:
                return err("Post no encontrado", 404)
            post = res.data[0]
            new_votes = max(0, int(post.get("votes", 0)) + (1 if action == "up" else -1))
            upd = supabase.table("community_posts").update({"votes": new_votes}).eq("id", post_id).execute()
            user_res = supabase.table("users").select("name").eq("id", post.get("user_id")).limit(1).execute()
            user_name = user_res.data[0].get("name") if user_res.data else "Usuario"
            return ok(map_post_row(upd.data[0] if upd.data else post, user_name), "Voto registrado")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    posts = read_json(COMMUNITY_FILE, [])
    post  = next((p for p in posts if p["id"] == post_id), None)
    if not post:
        return err("Post no encontrado", 404)

    post["votes"] = max(0, post.get("votes", 0) + (1 if action == "up" else -1))
    write_json(COMMUNITY_FILE, posts)
    return ok(post, "Voto registrado")

@app.route("/api/community/<post_id>", methods=["DELETE"])
def delete_post(post_id):
    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table("community_posts").delete().eq("id", post_id).execute()
            if not res.data:
                return err("Post no encontrado", 404)
            return ok(msg="Post eliminado")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    posts = read_json(COMMUNITY_FILE, [])
    new   = [p for p in posts if p["id"] != post_id]
    if len(new) == len(posts):
        return err("Post no encontrado", 404)
    write_json(COMMUNITY_FILE, new)
    return ok(msg="Post eliminado")

# ══════════════════════════════════════════════════════
#  USUARIO / PERFIL
# ══════════════════════════════════════════════════════

@app.route("/api/user", methods=["GET"])
def get_user():
    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table("users").select("*").eq("id", get_current_user_id()).limit(1).execute()
            return ok(res.data[0] if res.data else {})
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    users = read_json(USERS_FILE, [])
    user_id = get_current_user_id()
    user = next((u for u in users if u.get("id") == user_id), None)
    return ok(user or {})

@app.route("/api/user", methods=["PUT"])
def update_user():
    """Actualiza nombre, email.
    Body: { name?, email? }
    """
    body = request.get_json(silent=True) or {}

    if SUPABASE_ENABLED and supabase:
        update_fields = {}
        for field in ("name", "email"):
            if field in body:
                update_fields[field] = body[field]
        if not update_fields:
            return err("Sin cambios para actualizar")
        try:
            res = supabase.table("users").update(update_fields).eq("id", get_current_user_id()).execute()
            if not res.data:
                return err("Usuario no encontrado", 404)
            return ok(res.data[0], "Perfil actualizado")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    users = read_json(USERS_FILE, [])
    user_id = get_current_user_id()
    user = next((u for u in users if u.get("id") == user_id), None)
    if not user:
        return err("Usuario no encontrado", 404)
    for field in ("name", "email"):
        if field in body:
            user[field] = body[field]
    write_json(USERS_FILE, users)
    return ok(user, "Perfil actualizado")

# ══════════════════════════════════════════════════════
#  DASHBOARD GENERAL
# ══════════════════════════════════════════════════════

@app.route("/api/dashboard", methods=["GET"])
def dashboard():
    """Resumen completo del día: tareas, hábitos, finanzas, apuesta."""
    if SUPABASE_ENABLED and supabase:
        try:
            tasks_res = supabase.table("tasks").select("done").eq("user_id", get_current_user_id()).execute()
            tasks = tasks_res.data or []
            habits_res = supabase.table("habits").select("id").eq("user_id", get_current_user_id()).execute()
            habits = habits_res.data or []
            finances_res = supabase.table("finances").select("type, amount").eq("user_id", get_current_user_id()).execute()
            finances = finances_res.data or []
            bet_res = supabase.table("bets").select("*").eq("user_id", get_current_user_id()).order("created_at", desc=True).limit(1).execute()
            bet_row = bet_res.data[0] if bet_res.data else {}
            user_res = supabase.table("users").select("streak").eq("id", get_current_user_id()).limit(1).execute()
            user_row = user_res.data[0] if user_res.data else {}

            done_tasks = sum(1 for t in tasks if t.get("done"))
            total_tasks = len(tasks)
            total_habits = len(habits)

            week = week_dates()
            week_strs = [d.isoformat() for d in week]
            habit_ids = [h.get("id") for h in habits if h.get("id")]
            done_habits = 0
            if habit_ids:
                logs_res = supabase.table("habit_logs").select("habit_id, log_date, done").in_("habit_id", habit_ids).in_("log_date", week_strs).execute()
                today_str_val = week[-1].isoformat()
                done_habits = sum(1 for row in (logs_res.data or []) if row.get("log_date") == today_str_val and row.get("done"))

            income = sum(float(f.get("amount", 0)) for f in finances if f.get("type") == "income")
            expense = sum(float(f.get("amount", 0)) for f in finances if f.get("type") == "expense")

            return ok({
                "date": today_str(),
                "streak": int(user_row.get("streak", 0)),
                "tasks": {"done": done_tasks, "total": total_tasks},
                "habits": {"done": done_habits, "total": total_habits},
                "finances": {"income": income, "expense": expense, "balance": income - expense},
                "bet": {
                    "active": bool(bet_row.get("active", False)),
                    "amount": float(bet_row.get("amount", 0) or 0),
                    "completed": bool(bet_row.get("completed", False)),
                    "refunded": bool(bet_row.get("refunded", False)),
                    "tasksLeft": max(0, 3 - done_tasks),
                },
            })
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    tasks    = read_json(TASKS_FILE, [])
    habits   = read_json(HABITS_FILE, [])
    finances = read_json(FINANCES_FILE, [])
    bet      = read_json(BET_FILE, {})
    users    = read_json(USERS_FILE, [])

    done_tasks   = sum(1 for t in tasks if t.get("done"))
    total_tasks  = len(tasks)
    done_habits  = sum(1 for h in habits if h["week"][-1])
    total_habits = len(habits)
    income  = sum(f["amount"] for f in finances if f.get("type") == "income")
    expense = sum(f["amount"] for f in finances if f.get("type") == "expense")
    streak  = users[0].get("streak", 0) if users else 0

    return ok({
        "date": today_str(),
        "streak": streak,
        "tasks":    {"done": done_tasks,  "total": total_tasks},
        "habits":   {"done": done_habits, "total": total_habits},
        "finances": {"income": income, "expense": expense, "balance": income - expense},
        "bet": {
            "active":    bet.get("active", False),
            "amount":    bet.get("amount", 0),
            "completed": bet.get("completed", False),
            "refunded":  bet.get("refunded", False),
            "tasksLeft": max(0, 3 - done_tasks),
        },
    })

# ══════════════════════════════════════════════════════
#  HEALTH CHECK
# ══════════════════════════════════════════════════════

@app.route("/api/health", methods=["GET"])
def health():
    tasks_cols = []
    tasks_error = ""
    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table("tasks").select("id,name,category,unit,target,current,done").limit(0).execute()
            tasks_cols = ["id", "name", "category", "unit", "target", "current", "done"]
        except Exception as e:
            tasks_error = str(e)
            try:
                res2 = supabase.table("tasks").select("id,name,done").limit(0).execute()
                tasks_cols = ["id", "name", "done"]
            except Exception as e2:
                tasks_error = str(e2)

    return ok({
        "status": "ok",
        "version": "1.1.0",
        "timestamp": now_str(),
        "supabaseEnabled": SUPABASE_ENABLED,
        "supabaseConfigured": bool(SUPABASE_URL and SUPABASE_KEY),
        "supabaseUrl": (SUPABASE_URL[:40] + "...") if len(SUPABASE_URL) > 40 else SUPABASE_URL,
        "supabaseBackendKeyRole": get_supabase_key_role(),
        "authUsersStore": "supabase" if has_privileged_supabase_key() else "local-json",
        "supabaseError": SUPABASE_ERROR,
        "tasksColumnsOk": tasks_cols,
        "tasksColumnsError": tasks_error,
    })

# ── RUN ───────────────────────────────────────────────
if __name__ == "__main__":
    print("\n🐝 VIORA Backend corriendo en http://localhost:5000\n")
    print("  Endpoints disponibles:")
    print("  GET  /api/health")
    print("  GET  /api/dashboard")
    print("  ─── Tareas ───")
    print("  GET    /api/tasks")
    print("  POST   /api/tasks")
    print("  PUT    /api/tasks/<id>")
    print("  DELETE /api/tasks/<id>")
    print("  POST   /api/tasks/<id>/complete")
    print("  POST   /api/tasks/<id>/verify-photo")
    print("  ─── Hábitos ───")
    print("  GET    /api/habits")
    print("  POST   /api/habits")
    print("  DELETE /api/habits/<id>")
    print("  POST   /api/habits/<id>/log")
    print("  ─── Finanzas ───")
    print("  GET    /api/finances")
    print("  POST   /api/finances")
    print("  DELETE /api/finances/<id>")
    print("  ─── Apuesta ───")
    print("  GET    /api/bet")
    print("  POST   /api/bet")
    print("  GET    /api/bet/status")
    print("  POST   /api/bet/cancel")
    print("  ─── Comunidad ───")
    print("  GET    /api/community")
    print("  POST   /api/community")
    print("  GET    /api/community/<id>/comments")
    print("  POST   /api/community/<id>/comments")
    print("  POST   /api/community/<id>/vote")
    print("  DELETE /api/community/<id>")
    print("  ─── Usuario ───")
    print("  GET    /api/user")
    print("  PUT    /api/user")
    app.run(debug=True, port=5000)
