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
import jwt
from werkzeug.security import generate_password_hash, check_password_hash
import requests
from flask import Flask, request, jsonify, send_from_directory, make_response
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
                k = key.strip()
                v = value.strip().strip('"').strip("'")
                if v:
                    os.environ.setdefault(k, v)
    except Exception:
        pass

load_env_file()

# ── PHOTO VERIFICATION AI ──────────────────────────────
HF_TOKEN = os.environ.get("HF_TOKEN", "").strip()
HF_ZERO_SHOT_MODEL = os.environ.get("HF_ZERO_SHOT_MODEL", "openai/clip-vit-base-patch32").strip()
HF_IMAGE_CLASSIFICATION_MODEL = os.environ.get("HF_IMAGE_CLASSIFICATION_MODEL", "microsoft/resnet-50").strip()
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_VISION_MODEL = os.environ.get(
    "ANTHROPIC_VISION_MODEL",
    os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
).strip()
PHOTO_VERIFY_PROVIDER = os.environ.get("VIORA_PHOTO_VERIFY_PROVIDER", "auto").strip().lower()
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
TASK_CATEGORIES = {
    "gym",
    "social",
    "habitos",
    "salud_mental",
    "salud",
    "procrastinacion",
    "estudio",
    "trabajo",
    "hogar",
}
COMMUNITY_BLOCKED_TEXTS = {
    "La mala para esa María Fernanda Sánchez Durán",
}

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
TASKS_TABLE = "habits"
ROUTINES_TABLE = "habit_routines"
ROUTINE_LOGS_TABLE = "habit_routine_logs"

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
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "description": row.get("description") or "",
        "due_date": row.get("due_date"),
        "period": row.get("period") or "diaria",
        "done": bool(row.get("done", False)),
        "createdAt": row.get("createdAt") or row.get("created_at"),
    }

def _normalize_habit_category(value):
    raw = str(value or "habitos").strip().lower().replace("-","_").replace(" ","_")
    for c in "áéíóúñ": raw = raw.replace(c, "aeioun"["áéíóúñ".index(c)])
    return raw if raw in TASK_CATEGORIES else "habitos"

def normalize_habit_week(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = None
    if not isinstance(value, list):
        return None
    return [bool(x) for x in value[:7]] + [False] * max(0, 7 - len(value))

def encode_habit_period(period, week=None):
    clean_period = period or "diaria"
    if clean_period == "semanal" and isinstance(week, list) and len(week) == 7:
        return "semanal:" + "".join("1" if day else "0" for day in week)
    return clean_period

def decode_habit_period(raw_period):
    period = raw_period or "diaria"
    encoded_week = None
    if isinstance(period, str) and period.startswith("semanal:"):
        bits = period.split(":", 1)[1][:7]
        encoded_week = [(char == "1") for char in bits] + [False] * max(0, 7 - len(bits))
        period = "semanal"
    return period, encoded_week

def map_habit_row(row, week=None):
    category = _normalize_habit_category(row.get("category"))
    period, encoded_week = decode_habit_period(row.get("period", "diaria"))
    target = float(row.get("target", 1) or 1)
    current = float(row.get("current", target if row.get("done") else 0) or 0)
    saved_week = row.get("week")
    if isinstance(saved_week, str):
        try:
            saved_week = json.loads(saved_week)
        except Exception:
            saved_week = None
    if not isinstance(saved_week, list):
        saved_week = None
    if isinstance(saved_week, list) and len(saved_week) == 7:
        saved_week = [bool(x) for x in saved_week]
    else:
        saved_week = None
    saved_week = saved_week or encoded_week
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "category": category,
        "period": period,
        "target": target,
        "current": current,
        "unit": row.get("unit", "veces"),
        "done": bool(row.get("done", False)),
        "week": saved_week,
        "requiresPhoto": category == "gym",
        "verified": bool(row.get("verified", False)),
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

def map_comment_row(row, user_name=None, current_user_id=None):
    comment_user_id = row.get("user_id") or row.get("userId")
    return {
        "id": row.get("id"),
        "postId": row.get("post_id") or row.get("postId"),
        "user": user_name or row.get("user") or "Usuario",
        "text": row.get("text"),
        "createdAt": row.get("created_at") or row.get("createdAt"),
        "canDelete": bool(current_user_id and comment_user_id and str(comment_user_id) == str(current_user_id)),
    }

def is_blocked_community_text(text):
    normalized = " ".join(str(text or "").split()).casefold()
    return any(normalized == " ".join(blocked.split()).casefold() for blocked in COMMUNITY_BLOCKED_TEXTS)

def cleanup_reported_community_content():
    if SUPABASE_ENABLED and supabase:
        for text in COMMUNITY_BLOCKED_TEXTS:
            try:
                supabase.table("community_comments").delete().eq("text", text).execute()
            except Exception:
                pass
            try:
                supabase.table("community_posts").delete().eq("text", text).execute()
            except Exception:
                pass
        return

    posts = read_json(COMMUNITY_FILE, [])
    filtered_posts = [p for p in posts if not is_blocked_community_text(p.get("text"))]
    if len(filtered_posts) != len(posts):
        write_json(COMMUNITY_FILE, filtered_posts)

    comments = read_json(COMMUNITY_COMMENTS_FILE, [])
    filtered_comments = [c for c in comments if not is_blocked_community_text(c.get("text"))]
    if len(filtered_comments) != len(comments):
        write_json(COMMUNITY_COMMENTS_FILE, filtered_comments)

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
    "weight",
    "treadmill",
    "exercise",
]

PHOTO_VERIFY_PROVIDER_ALIASES = {
    "": "auto",
    "claude": "anthropic",
    "hf": "huggingface",
    "hugging-face": "huggingface",
    "huggingface-zero-shot": "huggingface",
    "local": "places365",
}

SUPPORTED_IMAGE_MEDIA_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

def normalize_image_media_type(media_type):
    cleaned = (media_type or "image/jpeg").split(";", 1)[0].strip().lower()
    if cleaned == "image/jpg":
        cleaned = "image/jpeg"
    return cleaned if cleaned in SUPPORTED_IMAGE_MEDIA_TYPES else "image/jpeg"

def _places365_assets_available():
    return os.path.exists(PLACES365_WEIGHTS) and os.path.exists(PLACES365_CATEGORIES)

def _photo_provider_order():
    provider = PHOTO_VERIFY_PROVIDER_ALIASES.get(PHOTO_VERIFY_PROVIDER, PHOTO_VERIFY_PROVIDER)
    if provider == "auto":
        order = []
        if ANTHROPIC_API_KEY:
            order.append("anthropic")
        if HF_TOKEN:
            order.append("huggingface")
        if _places365_assets_available():
            order.append("places365")
        return order or ["anthropic", "huggingface", "places365"]
    fallback_order = ["anthropic", "huggingface", "places365"]
    order = [provider] if provider in fallback_order else []
    return order + [item for item in fallback_order if item not in order]

def _json_error_from_response(result):
    if not isinstance(result, tuple):
        return ""
    response = result[0]
    try:
        payload = response.get_json(silent=True) if hasattr(response, "get_json") else {}
        return str((payload or {}).get("error") or (payload or {}).get("message") or "")
    except Exception:
        return ""

def _photo_result_is_provider_error(result):
    if not isinstance(result, dict):
        return True
    reason = str(result.get("reason") or "").lower()
    detected = " ".join(str(item) for item in (result.get("detectedItems") or [])).lower()
    return any(marker in reason or marker in detected for marker in [
        "no disponible",
        "no instalado",
        "dependencias",
        "error interno",
        "not configured",
        "no configurado",
    ])

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

def _prediction_label_score(item):
    if isinstance(item, dict):
        return str(item.get("label", "")), float(item.get("score", 0) or 0)
    return str(getattr(item, "label", "")), float(getattr(item, "score", 0) or 0)

def _normalize_gym_zero_shot_predictions(predictions):
    scored = []
    for item in predictions or []:
        label, score = _prediction_label_score(item)
        if label:
            scored.append({"label": label, "score": score})

    positive = [item for item in scored if item["label"] in GYM_POSITIVE_LABELS]
    negative = [item for item in scored if item["label"] in GYM_NEGATIVE_LABELS]
    best_positive = max(positive, key=lambda item: item["score"], default={"label": "", "score": 0})
    best_negative = max(negative, key=lambda item: item["score"], default={"label": "", "score": 0})

    margin = best_positive["score"] - best_negative["score"]
    approved = best_positive["score"] >= 0.28 and margin >= 0.06
    if approved:
        confidence = round(min(98, max(70, 70 + min(margin, 0.35) / 0.35 * 28)))
    else:
        confidence = round(min(69, max(0, best_positive["score"]) / 0.28 * 69))

    detected = [
        item["label"].replace("a photo of ", "").replace("a photo inside ", "").replace("a photo ", "")
        for item in positive
        if item["score"] >= max(0.12, best_positive["score"] * 0.45)
    ][:4]
    reason = (
        "La imagen coincide con contexto de gimnasio."
        if approved
        else "No hay suficiente evidencia visual de gimnasio o entrenamiento."
    )
    return normalize_photo_verification_result({
        "approved": approved,
        "confidence": confidence,
        "detectedItems": detected or [best_positive["label"] or "sin coincidencias de gym"],
        "reason": reason,
        "mode": "huggingface-zero-shot",
    })

def call_hugging_face_zero_shot(image_bytes, media_type="image/jpeg", image_b64=None):
    if not HF_TOKEN:
        return err("HF_TOKEN no configurado para verificar fotos con Hugging Face", 503)

    labels = GYM_POSITIVE_LABELS + GYM_NEGATIVE_LABELS
    try:
        from huggingface_hub import InferenceClient
        client = InferenceClient(
            provider="hf-inference",
            api_key=HF_TOKEN,
            timeout=45,
        )
        predictions = client.zero_shot_image_classification(
            image=image_bytes,
            candidate_labels=labels,
            model=HF_ZERO_SHOT_MODEL,
        )
        return _normalize_gym_zero_shot_predictions(predictions)
    except ImportError:
        pass
    except Exception as exc:
        detail = str(exc)[:180]
        if "not supported" not in detail.lower() and "404" not in detail:
            return err(f"Error Hugging Face: {detail}", 502)

    api_url = f"https://router.huggingface.co/hf-inference/models/{HF_ZERO_SHOT_MODEL}"
    response = requests.post(
        api_url,
        headers={"Authorization": f"Bearer {HF_TOKEN}"},
        json={
            "inputs": image_b64 or base64.b64encode(image_bytes).decode(),
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

    return _normalize_gym_zero_shot_predictions(predictions)

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

def call_anthropic_photo_verification(image_b64, media_type="image/jpeg"):
    if not ANTHROPIC_API_KEY:
        return err("ANTHROPIC_API_KEY no configurado para verificar fotos con Claude", 503)

    try:
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=ANTHROPIC_VISION_MODEL,
            max_tokens=300,
            temperature=0,
            system=(
                "Eres un verificador visual estricto para una app de habitos. "
                "Aprueba solo si la imagen muestra evidencia clara de gimnasio, "
                "maquinas de ejercicio, pesas, zona de entrenamiento o una persona "
                "entrenando en ese contexto. No apruebes selfies, habitaciones, "
                "oficinas, comida, documentos ni escenas ambiguas."
            ),
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": normalize_image_media_type(media_type),
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Responde solo JSON valido con este formato: "
                            "{\"approved\": boolean, \"confidence\": 0-100, "
                            "\"detectedItems\": [\"item\"], \"reason\": \"texto breve\"}."
                        ),
                    },
                ],
            }],
        )
        text = "\n".join(
            getattr(block, "text", "")
            for block in (getattr(response, "content", []) or [])
            if getattr(block, "text", "")
        )
        parsed = extract_json_object(text)
        parsed["mode"] = "anthropic-vision"
        return normalize_photo_verification_result(parsed)
    except Exception as exc:
        return err(f"Error Claude Vision: {str(exc)[:180]}", 502)

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
            {"id":"1","name":"Ejemplo: Leer 10 minutos","description":"","due_date":None,"done":False,"createdAt":now_str()},
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
            res = supabase.table(TASKS_TABLE).select("*").eq("user_id", get_current_user_id()).order("created_at", desc=False).execute()
            tasks = [map_task_row(row) for row in (res.data or [])]
            return ok(tasks)
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    tasks = [map_task_row(row) for row in read_json(TASKS_FILE, [])]
    return ok(tasks)

@app.route("/api/tasks", methods=["POST"])
def create_task():
    """Crea una nueva tarea.
    Body: { name, description?, due_date? }
    """
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return err("El campo 'name' es requerido")

    if SUPABASE_ENABLED and supabase:
        payload = {
            "user_id": get_current_user_id(),
            "name": name,
            "description": body.get("description") or None,
            "due_date": body.get("due_date") or None,
            "period": body.get("period") or "diaria",
            "done": False,
        }
        core = {"user_id", "name"}
        try:
            res = supabase.table(TASKS_TABLE).insert(payload).execute()
            row = (res.data or [payload])[0]
            return ok(map_task_row(row), "Tarea creada")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    task = {
        "id": str(uuid.uuid4()),
        "name": name,
        "description": body.get("description") or "",
        "due_date": body.get("due_date") or None,
        "period": body.get("period") or "diaria",
        "done": False,
        "createdAt": now_str(),
    }
    tasks = read_json(TASKS_FILE, [])
    tasks.append(task)
    write_json(TASKS_FILE, tasks)
    return ok(task, "Tarea creada")

@app.route("/api/tasks/<task_id>", methods=["PUT"])
def update_task(task_id):
    """Actualiza una tarea.
    Body: { name?, description?, due_date?, done? }
    """
    body = request.get_json(silent=True) or {}

    if SUPABASE_ENABLED and supabase:
        update_fields = {k: body[k] for k in ("name", "description", "due_date", "period", "done") if k in body}
        if not update_fields:
            return err("Sin cambios para actualizar")
        try:
            res = supabase.table(TASKS_TABLE).update(update_fields).eq("id", task_id).eq("user_id", get_current_user_id()).execute()
            if not res.data:
                return err("Tarea no encontrada", 404)
            return ok(map_task_row(res.data[0]), "Tarea actualizada")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    tasks = read_json(TASKS_FILE, [])
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return err("Tarea no encontrada", 404)
    for field in ("name", "description", "due_date", "period", "done"):
        if field in body:
            task[field] = body[field]
    write_json(TASKS_FILE, tasks)
    return ok(task, "Tarea actualizada")

@app.route("/api/tasks/<task_id>", methods=["DELETE"])
def delete_task(task_id):
    """Elimina una tarea."""
    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table(TASKS_TABLE).delete().eq("id", task_id).eq("user_id", get_current_user_id()).execute()
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
            res = supabase.table(TASKS_TABLE).select("*").eq("id", task_id).eq("user_id", get_current_user_id()).limit(1).execute()
            if not res.data:
                return err("Tarea no encontrada", 404)
            current = res.data[0]
            new_done = body.get("done", not current.get("done", False))
            upd = supabase.table(TASKS_TABLE).update({"done": bool(new_done)}).eq("id", task_id).eq("user_id", get_current_user_id()).execute()
            task = map_task_row(upd.data[0]) if upd.data else map_task_row({**current, "done": new_done})
            return ok({"task": task, "betWon": False}, "Estado actualizado")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    tasks = read_json(TASKS_FILE, [])
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return err("Tarea no encontrada", 404)
    task["done"] = body.get("done", not task.get("done", False))
    write_json(TASKS_FILE, tasks)
    return ok({"task": task, "betWon": False}, "Estado actualizado")

@app.route("/api/tasks/<task_id>/add", methods=["POST"])
def add_task_progress(task_id):
    """Agrega progreso a una tarea o la completa si el esquema es simple."""
    body = request.get_json(silent=True) or {}
    amount = float(body.get("amount", 1) or 1)

    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table(TASKS_TABLE).select("*").eq("id", task_id).eq("user_id", get_current_user_id()).limit(1).execute()
            if not res.data:
                return err("Tarea no encontrada", 404)

            current = res.data[0]
            upd = supabase.table(TASKS_TABLE).update({"done": True}).eq("id", task_id).eq("user_id", get_current_user_id()).execute()
            task = map_task_row(upd.data[0]) if upd.data else map_task_row({**current, "done": True})
            return ok({"task": task, "completed": True, "betWon": False}, "Tarea completada")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    tasks = read_json(TASKS_FILE, [])
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return err("Tarea no encontrada", 404)
    task["done"] = True
    write_json(TASKS_FILE, tasks)
    return ok({"task": map_task_row(task), "completed": True, "betWon": False}, "Tarea completada")

def _habit_is_scheduled_today(row):
    habit = map_habit_row(row)
    week = habit.get("week")
    if habit.get("period") == "semanal" and isinstance(week, list) and len(week) == 7:
        return bool(week[date.today().weekday()])
    return habit.get("period") == "diaria" or not habit.get("period")

def _completed_habit_count(habits):
    return sum(1 for h in habits if h.get("done"))

def _check_bet(habits):
    """Devuelve True si se completaron >= 3 hábitos de hoy y la apuesta estaba activa."""
    if SUPABASE_ENABLED and supabase:
        try:
            bet_res = supabase.table("bets").select("*").eq("user_id", get_current_user_id()).order("created_at", desc=True).limit(1).execute()
            bet_row = bet_res.data[0] if bet_res.data else None
            if not bet_row or not bet_row.get("active") or bet_row.get("completed"):
                return False
            done_count = _completed_habit_count(habits)
            if done_count >= 3:
                supabase.table("bets").update({
                    "active": False,
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
    done_count = _completed_habit_count(habits)
    if done_count >= 3:
        bet["active"] = False
        bet["completed"] = True
        bet["refunded"]  = True   # Mock: en producción llamar PSE/Wompi aquí
        bet["completedAt"] = now_str()
        write_json(BET_FILE, bet)
        return True
    return False

# ══════════════════════════════════════════════════════
#  VERIFICACIÓN DE FOTO CON IA (Hugging Face CLIP)
# ══════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════
#  HÁBITOS
# ══════════════════════════════════════════════════════

@app.route("/api/habits", methods=["GET"])
def get_habits():
    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table(ROUTINES_TABLE).select("*").eq("user_id", get_current_user_id()).order("created_at", desc=False).execute()
            return ok([map_habit_row(r) for r in (res.data or [])])
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)
    return ok([map_habit_row(r) for r in read_json(HABITS_FILE, [])])

@app.route("/api/habits", methods=["POST"])
def create_habit():
    """Crea un nuevo hábito medible.
    Body: { name, category?, period?, target?, unit? }
    """
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return err("El campo 'name' es requerido")
    category = _normalize_habit_category(body.get("category") or body.get("cat"))
    requires_photo = category == "gym"
    period = body.get("period", "diaria")
    week = normalize_habit_week(body.get("week"))

    if SUPABASE_ENABLED and supabase:
        payload = {
            "user_id": get_current_user_id(),
            "name": name,
            "category": category,
            "period": encode_habit_period(period, week),
            "target": float(body.get("target", 1) or 1),
            "current": 0,
            "unit": body.get("unit", "veces"),
            "done": False,
            "requires_photo": requires_photo,
            "verified": False,
        }
        if week is not None:
            payload["week"] = week
        try:
            res = _sb_insert(ROUTINES_TABLE, payload, {"user_id", "name"})
            row = (res.data or [payload])[0]
            return ok(map_habit_row(row), "Hábito creado")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    habit = {
        "id": str(uuid.uuid4()),
        "name": name,
        "category": category,
        "period": period,
        "target": float(body.get("target", 1) or 1),
        "current": 0,
        "unit": body.get("unit", "veces"),
        "done": False,
        "requiresPhoto": requires_photo,
        "verified": False,
        "createdAt": now_str(),
    }
    if week is not None:
        habit["week"] = week
    habits = read_json(HABITS_FILE, [])
    habits.append(habit)
    write_json(HABITS_FILE, habits)
    return ok(habit, "Hábito creado")

@app.route("/api/habits/<habit_id>", methods=["PUT"])
def update_habit(habit_id):
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return err("El campo 'name' es requerido")
    category = _normalize_habit_category(body.get("category") or body.get("cat"))
    period = body.get("period", "diaria")
    target = float(body.get("target", 1) or 1)
    unit = body.get("unit", "veces")
    week = normalize_habit_week(body.get("week"))

    if SUPABASE_ENABLED and supabase:
        try:
            payload = {
                "name": name,
                "category": category,
                "period": encode_habit_period(period, week),
                "target": target,
                "unit": unit,
            }
            if week is not None:
                payload["week"] = week
            res = _sb_update(
                ROUTINES_TABLE,
                payload,
                {"name", "period"},
                {"id": habit_id, "user_id": get_current_user_id()},
            )
            if not res.data:
                return err("Hábito no encontrado", 404)
            return ok(map_habit_row(res.data[0]), "Hábito actualizado")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    habits = read_json(HABITS_FILE, [])
    habit = next((h for h in habits if h["id"] == habit_id), None)
    if not habit:
        return err("Hábito no encontrado", 404)
    habit["name"] = name
    habit["category"] = category
    habit["period"] = period
    habit["target"] = target
    habit["unit"] = unit
    if week is not None:
        habit["week"] = week
    write_json(HABITS_FILE, habits)
    return ok(map_habit_row(habit), "Hábito actualizado")

@app.route("/api/habits/<habit_id>", methods=["DELETE"])
def delete_habit(habit_id):
    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table(ROUTINES_TABLE).delete().eq("id", habit_id).eq("user_id", get_current_user_id()).execute()
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

@app.route("/api/habits/<habit_id>/reset", methods=["POST"])
def reset_habit_progress(habit_id):
    """Limpia el progreso diario de un hábito sin eliminarlo."""
    reset_fields = {"current": 0, "done": False, "verified": False}

    if SUPABASE_ENABLED and supabase:
        try:
            res = _sb_update(
                ROUTINES_TABLE,
                reset_fields,
                set(),
                {"id": habit_id, "user_id": get_current_user_id()},
            )
            if not res or not res.data:
                return err("Hábito no encontrado", 404)
            return ok(map_habit_row(res.data[0]), "Progreso diario reiniciado")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    habits = read_json(HABITS_FILE, [])
    habit = next((h for h in habits if h["id"] == habit_id), None)
    if not habit:
        return err("Hábito no encontrado", 404)
    habit.update(reset_fields)
    write_json(HABITS_FILE, habits)
    return ok(map_habit_row(habit), "Progreso diario reiniciado")

@app.route("/api/habits/<habit_id>/complete", methods=["POST"])
def complete_habit(habit_id):
    """Suma progreso o completa un hábito.
    Body: { amount?: float, done?: bool }
    """
    body = request.get_json(silent=True) or {}

    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table(ROUTINES_TABLE).select("*").eq("id", habit_id).eq("user_id", get_current_user_id()).limit(1).execute()
            if not res.data:
                return err("Hábito no encontrado", 404)
            current = res.data[0]
            mapped = map_habit_row(current)
            if mapped["requiresPhoto"] and not mapped["verified"]:
                return err("Este hábito requiere verificación de foto antes de completar", 403)
            amount = float(body.get("amount", 1) or 1)
            new_current = min(float(current.get("current", 0) or 0) + amount, mapped["target"])
            new_done = new_current >= mapped["target"]
            upd = supabase.table(ROUTINES_TABLE).update({"current": new_current, "done": new_done}).eq("id", habit_id).eq("user_id", get_current_user_id()).execute()
            habit = map_habit_row(upd.data[0]) if upd.data else map_habit_row({**current, "current": new_current, "done": new_done})
            habits_res = supabase.table(ROUTINES_TABLE).select("*").eq("user_id", get_current_user_id()).execute()
            bet_check = _check_bet(habits_res.data or [])
            return ok({"habit": habit, "completed": new_done, "betWon": bet_check}, "Progreso guardado")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    habits = read_json(HABITS_FILE, [])
    habit = next((h for h in habits if h["id"] == habit_id), None)
    if not habit:
        return err("Hábito no encontrado", 404)
    mapped = map_habit_row(habit)
    if mapped["requiresPhoto"] and not mapped.get("verified"):
        return err("Este hábito requiere verificación de foto antes de completar", 403)
    amount = float(body.get("amount", 1) or 1)
    habit["current"] = min(float(habit.get("current", 0) or 0) + amount, mapped["target"])
    habit["done"] = habit["current"] >= mapped["target"]
    write_json(HABITS_FILE, habits)
    bet_check = _check_bet(habits)
    return ok({"habit": map_habit_row(habit), "completed": habit["done"], "betWon": bet_check}, "Progreso guardado")

@app.route("/api/habits/<habit_id>/verify-photo", methods=["POST"])
def verify_habit_photo(habit_id):
    """Verifica foto de gym para un hábito.
    Body: { image: '<base64>', mediaType: 'image/jpeg' }
    """
    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table(ROUTINES_TABLE).select("*").eq("id", habit_id).eq("user_id", get_current_user_id()).limit(1).execute()
            if not res.data:
                return err("Hábito no encontrado", 404)
            habit = map_habit_row(res.data[0])
            if not habit["requiresPhoto"]:
                return err("Solo los hábitos de gym requieren verificación por foto")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)
    else:
        habits = read_json(HABITS_FILE, [])
        h = next((x for x in habits if x["id"] == habit_id), None)
        if not h:
            return err("Hábito no encontrado", 404)
        if not map_habit_row(h)["requiresPhoto"]:
            return err("Solo los hábitos de gym requieren verificación por foto")

    body = request.get_json(silent=True) or {}
    image_b64 = body.get("image", "")
    media_type = normalize_image_media_type(body.get("mediaType", "image/jpeg"))
    image_raw = b""

    if not image_b64:
        file = request.files.get("photo")
        if not file:
            return err("Se requiere imagen (campo 'image' en base64 o multipart 'photo')")
        image_raw = file.read()
        image_b64 = base64.b64encode(image_raw).decode()
        media_type = normalize_image_media_type(file.content_type or "image/jpeg")
    else:
        try:
            image_raw = base64.b64decode(image_b64)
        except Exception:
            return err("Imagen base64 inválida")

    if PHOTO_VERIFY_DEMO:
        result = normalize_photo_verification_result({"approved": True, "confidence": 86, "detectedItems": ["modo demo"], "reason": "Modo demo activado.", "mode": "demo"})
    else:
        result = None
        provider_errors = []
        for provider in _photo_provider_order():
            if provider == "anthropic":
                attempt = call_anthropic_photo_verification(image_b64, media_type)
            elif provider == "huggingface":
                attempt = call_hugging_face_zero_shot(image_raw, media_type, image_b64)
                if isinstance(attempt, dict) and attempt.get("fallback") == "image-classification":
                    attempt = call_hugging_face_image_classification(image_raw, media_type)
            elif provider == "places365":
                attempt = call_places365_scene_classification(image_raw)
            else:
                continue

            if isinstance(attempt, tuple):
                provider_errors.append(f"{provider}: {_json_error_from_response(attempt) or 'no disponible'}")
                continue
            if provider == "places365" and _photo_result_is_provider_error(attempt):
                provider_errors.append(f"{provider}: {attempt.get('reason', 'no disponible')}")
                continue
            result = attempt
            break

        if result is None:
            detail = "; ".join(provider_errors) or "sin proveedor de IA configurado"
            return err(f"No pude verificar la foto con IA en este deploy: {detail}", 503)

    bet_won = False
    if result.get("approved"):
        if SUPABASE_ENABLED and supabase:
            try:
                _sb_update(
                    ROUTINES_TABLE,
                    {"verified": True, "done": True, "current": habit["target"]},
                    {"done"},
                    {"id": habit_id, "user_id": get_current_user_id()},
                )
                habits_res = supabase.table(ROUTINES_TABLE).select("*").eq("user_id", get_current_user_id()).execute()
                bet_won = _check_bet(habits_res.data or [])
            except Exception as e:
                return err(f"Error Supabase: {str(e)}", 502)
        else:
            habits = read_json(HABITS_FILE, [])
            h = next((x for x in habits if x["id"] == habit_id), None)
            if h:
                mapped_habit = map_habit_row(h)
                h["verified"] = True
                h["done"] = True
                h["current"] = mapped_habit["target"]
                write_json(HABITS_FILE, habits)
                bet_won = _check_bet(habits)

    result["betWon"] = bet_won
    return ok(result, "Verificación completada")

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
            habit_res = supabase.table(ROUTINES_TABLE).select("*").eq("id", habit_id).eq("user_id", get_current_user_id()).limit(1).execute()
            if not habit_res.data:
                return err("Hábito no encontrado", 404)

            week = week_dates()
            target_date = week[int(day)].isoformat()

            supabase.table(ROUTINE_LOGS_TABLE).upsert({
                "habit_id": habit_id,
                "log_date": target_date,
                "done": done,
            }, on_conflict="habit_id,log_date").execute()

            logs_res = supabase.table(ROUTINE_LOGS_TABLE).select("log_date, done").eq("habit_id", habit_id).in_("log_date", [d.isoformat() for d in week]).execute()
            done_map = {row.get("log_date"): bool(row.get("done", False)) for row in (logs_res.data or [])}
            week_flags = [done_map.get(d.isoformat(), False) for d in week]
            streak = sum(1 for flag in week_flags if flag)

            supabase.table(ROUTINES_TABLE).update({"streak": streak}).eq("id", habit_id).execute()

            habit = map_habit_row(habit_res.data[0], week_flags)
            habit["streak"] = streak
            return ok(habit, "Hábito registrado")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    habits = read_json(HABITS_FILE, [])
    habit = next((h for h in habits if h["id"] == habit_id), None)
    if not habit:
        return err("Hábito no encontrado", 404)

    if not isinstance(habit.get("week"), list) or len(habit.get("week")) != 7:
        habit["week"] = [False] * 7

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
            if row and row.get("active") and not row.get("completed"):
                habits_res = supabase.table(ROUTINES_TABLE).select("*").eq("user_id", get_current_user_id()).execute()
                if _check_bet(habits_res.data or []):
                    refreshed = supabase.table("bets").select("*").eq("id", row.get("id")).limit(1).execute()
                    row = refreshed.data[0] if refreshed.data else row
            return ok(map_bet_row(row))
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    bet = read_json(BET_FILE, {})
    if bet.get("active") and not bet.get("completed"):
        _check_bet(read_json(HABITS_FILE, []))
        bet = read_json(BET_FILE, bet)
    return ok(bet)

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
            habits_res = supabase.table(ROUTINES_TABLE).select("*").eq("user_id", get_current_user_id()).execute()
            if _check_bet(habits_res.data or []):
                refreshed = supabase.table("bets").select("*").eq("id", row.get("id")).limit(1).execute()
                row = (refreshed.data or [row])[0]
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
    _check_bet(read_json(HABITS_FILE, []))
    bet = read_json(BET_FILE, bet)
    return ok(bet, f"Apuesta de ${amount:,.0f} COP activada (mock PSE)")

@app.route("/api/bet/status", methods=["GET"])
def bet_status():
    """Verifica si la apuesta se ganó según las tareas completadas."""
    if SUPABASE_ENABLED and supabase:
        try:
            bet_res = supabase.table("bets").select("*").eq("user_id", get_current_user_id()).order("created_at", desc=True).limit(1).execute()
            bet_row = bet_res.data[0] if bet_res.data else None
            habits_res = supabase.table(ROUTINES_TABLE).select("*").eq("user_id", get_current_user_id()).execute()
            done = _completed_habit_count(habits_res.data or [])

            return ok({
                "bet": map_bet_row(bet_row),
                "habitsCompleted": done,
                "habitsRequired": 3,
                "won": done >= 3 and ((bet_row or {}).get("active", False) or (bet_row or {}).get("completed", False)),
            })
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    bet   = read_json(BET_FILE, {})
    habits = read_json(HABITS_FILE, [])
    done  = _completed_habit_count(habits)

    return ok({
        "bet": bet,
        "habitsCompleted": done,
        "habitsRequired": 3,
        "won": done >= 3 and (bet.get("active", False) or bet.get("completed", False)),
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
    cleanup_reported_community_content()

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
    if is_blocked_community_text(text):
        return err("Ese contenido fue removido de la comunidad", 403)

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
    cleanup_reported_community_content()
    if SUPABASE_ENABLED and supabase:
        try:
            res = supabase.table("community_comments").select("*").eq("post_id", post_id).order("created_at", desc=False).execute()
            comments = res.data or []
            user_ids = list({c.get("user_id") for c in comments if c.get("user_id")})
            users_map = {}
            if user_ids:
                users_res = supabase.table("users").select("id, name").in_("id", user_ids).execute()
                users_map = {u["id"]: u.get("name") for u in (users_res.data or [])}
            current_user_id = get_current_user_id()
            return ok([map_comment_row(c, users_map.get(c.get("user_id")), current_user_id) for c in comments])
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    comments = read_json(COMMUNITY_COMMENTS_FILE, [])
    comments = [c for c in comments if str(c.get("postId")) == str(post_id)]
    current_user_id = get_current_user_id()
    return ok([map_comment_row(c, current_user_id=current_user_id) for c in sorted(comments, key=lambda c: c.get("createdAt", ""))])

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
    if is_blocked_community_text(text):
        return err("Ese contenido fue removido de la comunidad", 403)

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
            return ok(map_comment_row((res.data or [payload])[0], user_name, get_current_user_id()), "Comentario publicado")
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
        "userId": get_current_user_id(),
        "user": payload.get("name") or body.get("user") or "Usuario",
        "text": text,
        "createdAt": now_str(),
    }
    comments = read_json(COMMUNITY_COMMENTS_FILE, [])
    comments.append(comment)
    write_json(COMMUNITY_COMMENTS_FILE, comments)
    post["comments"] = int(post.get("comments", 0) or 0) + 1
    write_json(COMMUNITY_FILE, posts)
    return ok(map_comment_row(comment, current_user_id=get_current_user_id()), "Comentario publicado")

@app.route("/api/community/<post_id>/comments/<comment_id>", methods=["DELETE"])
def delete_comment(post_id, comment_id):
    """Elimina un comentario propio."""
    current_user_id = get_current_user_id()

    if SUPABASE_ENABLED and supabase:
        try:
            comment_res = (
                supabase.table("community_comments")
                .select("id, post_id, user_id")
                .eq("id", comment_id)
                .eq("post_id", post_id)
                .limit(1)
                .execute()
            )
            if not comment_res.data:
                return err("Comentario no encontrado", 404)
            comment = comment_res.data[0]
            if str(comment.get("user_id")) != str(current_user_id):
                return err("Solo puedes borrar tus propios comentarios", 403)

            post_res = supabase.table("community_posts").select("comments_count").eq("id", post_id).limit(1).execute()
            delete_res = (
                supabase.table("community_comments")
                .delete()
                .eq("id", comment_id)
                .eq("post_id", post_id)
                .eq("user_id", current_user_id)
                .execute()
            )
            if not delete_res.data:
                return err("Comentario no encontrado", 404)

            if post_res.data:
                current_count = int(post_res.data[0].get("comments_count", 0) or 0)
                supabase.table("community_posts").update({"comments_count": max(0, current_count - 1)}).eq("id", post_id).execute()
            return ok(msg="Comentario eliminado")
        except Exception as e:
            return err(f"Error Supabase: {str(e)}", 502)

    comments = read_json(COMMUNITY_COMMENTS_FILE, [])
    comment = next((c for c in comments if str(c.get("id")) == str(comment_id) and str(c.get("postId")) == str(post_id)), None)
    if not comment:
        return err("Comentario no encontrado", 404)

    payload = get_auth_payload() or {}
    comment_user_id = comment.get("userId") or comment.get("user_id")
    owns_comment = bool(comment_user_id and str(comment_user_id) == str(current_user_id))
    if not owns_comment and not comment_user_id:
        owns_comment = (comment.get("user") or "Usuario") == (payload.get("name") or "Usuario")
    if not owns_comment:
        return err("Solo puedes borrar tus propios comentarios", 403)

    comments = [c for c in comments if not (str(c.get("id")) == str(comment_id) and str(c.get("postId")) == str(post_id))]
    write_json(COMMUNITY_COMMENTS_FILE, comments)

    posts = read_json(COMMUNITY_FILE, [])
    post = next((p for p in posts if str(p.get("id")) == str(post_id)), None)
    if post:
        post["comments"] = max(0, int(post.get("comments", 0) or 0) - 1)
        write_json(COMMUNITY_FILE, posts)
    return ok(msg="Comentario eliminado")

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
#  AGENTE IA (Claude)
# ══════════════════════════════════════════════════════

def _get_anthropic_key():
    return (os.environ.get("ANTHROPIC_API_KEY") or "").strip()

def _build_agent_context(user_id):
    habits_lines, tasks_lines, finances_lines = [], [], []
    try:
        if SUPABASE_ENABLED and supabase:
            h_res = supabase.table(ROUTINES_TABLE).select("*").eq("user_id", user_id).execute()
            for h in (h_res.data or []):
                m = map_habit_row(h)
                status = "✅" if m["done"] else f"{m['current']}/{m['target']} {m['unit']}"
                habits_lines.append(f"- [{m['id']}] {m['name']} ({m['category']}) → {status}")
            t_res = supabase.table(TASKS_TABLE).select("*").eq("user_id", user_id).execute()
            for t in (t_res.data or []):
                m = map_task_row(t)
                status = "✅" if m["done"] else "pendiente"
                tasks_lines.append(f"- [{m['id']}] {m['name']} → {status}")
            f_res = supabase.table("finances").select("*").eq("user_id", user_id).execute()
            income = sum(f["amount"] for f in (f_res.data or []) if f.get("type") == "income")
            expense = sum(f["amount"] for f in (f_res.data or []) if f.get("type") == "expense")
            finances_lines.append(f"Ingresos: ${income:.0f} | Gastos: ${expense:.0f} | Balance: ${income - expense:.0f}")
    except Exception:
        pass
    return {
        "habits_text": "\n".join(habits_lines) or "Sin hábitos registrados",
        "tasks_text": "\n".join(tasks_lines) or "Sin tareas registradas",
        "finances_text": "\n".join(finances_lines) or "Sin movimientos este mes",
    }

def _execute_agent_tool(tool_name, tool_input, user_id):
    try:
        if tool_name == "complete_habit":
            habit_id = tool_input.get("habit_id", "")
            amount = float(tool_input.get("amount", 1) or 1)
            if SUPABASE_ENABLED and supabase:
                res = supabase.table(ROUTINES_TABLE).select("*").eq("id", habit_id).eq("user_id", user_id).limit(1).execute()
                if not res.data:
                    return "Hábito no encontrado"
                current = res.data[0]
                mapped = map_habit_row(current)
                new_current = min(float(current.get("current", 0) or 0) + amount, mapped["target"])
                new_done = new_current >= mapped["target"]
                supabase.table(ROUTINES_TABLE).update({"current": new_current, "done": new_done}).eq("id", habit_id).eq("user_id", user_id).execute()
                return f"Progreso guardado: {new_current}/{mapped['target']} {mapped['unit']}. {'¡Completado!' if new_done else 'Sigue así.'}"
            return "Supabase no disponible"

        elif tool_name == "complete_task":
            task_id = tool_input.get("task_id", "")
            if SUPABASE_ENABLED and supabase:
                res = supabase.table(TASKS_TABLE).update({"done": True}).eq("id", task_id).eq("user_id", user_id).execute()
                if not res.data:
                    return "Tarea no encontrada"
                return "Tarea marcada como completada"
            return "Supabase no disponible"

        elif tool_name == "create_task":
            name = (tool_input.get("name") or "").strip()
            if not name:
                return "El nombre de la tarea es requerido"
            payload = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "name": name,
                "description": tool_input.get("description") or None,
                "due_date": tool_input.get("due_date") or None,
                "done": False,
            }
            if SUPABASE_ENABLED and supabase:
                res = supabase.table(TASKS_TABLE).insert(payload).execute()
                row = (res.data or [payload])[0]
                return f"Tarea '{row.get('name', name)}' creada correctamente."
            return "Supabase no disponible"

        elif tool_name == "create_habit":
            name = (tool_input.get("name") or "").strip()
            if not name:
                return "El nombre del hábito es requerido"
            category = tool_input.get("category", "habitos")
            if category not in TASK_CATEGORIES:
                category = "habitos"
            payload = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "name": name,
                "category": category,
                "period": tool_input.get("period", "diaria"),
                "unit": tool_input.get("unit", "veces"),
                "target": float(tool_input.get("target", 1) or 1),
                "current": 0,
                "done": False,
                "requires_photo": False,
                "verified": False,
            }
            if SUPABASE_ENABLED and supabase:
                res = supabase.table(ROUTINES_TABLE).insert(payload).execute()
                row = (res.data or [payload])[0]
                return f"Hábito '{row.get('name', name)}' creado ({category}, meta {payload['target']} {payload['unit']})."
            return "Supabase no disponible"

        elif tool_name == "log_finance":
            ftype = tool_input.get("type", "expense")
            if ftype not in ("income", "expense"):
                ftype = "expense"
            amount = float(tool_input.get("amount", 0) or 0)
            if amount <= 0:
                return "El monto debe ser mayor a 0"
            description = (tool_input.get("description") or "Sin descripción").strip()
            payload = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "type": ftype,
                "amount": amount,
                "description": description,
                "date": date.today().isoformat(),
            }
            if SUPABASE_ENABLED and supabase:
                supabase.table("finances").insert(payload).execute()
                label = "Ingreso" if ftype == "income" else "Gasto"
                return f"{label} de ${amount:,.0f} ({description}) registrado."
            return "Supabase no disponible"

    except Exception as e:
        return f"Error al ejecutar acción: {str(e)}"
    return "Herramienta desconocida"

@app.route("/api/agent/chat", methods=["POST"])
def agent_chat():
    """Chat con el agente IA Viora.
    Body: { message: str, history?: [{role, content}] }
    """
    ANTHROPIC_API_KEY = _get_anthropic_key()
    if not ANTHROPIC_API_KEY:
        return err("ANTHROPIC_API_KEY no configurado", 503)
    body = request.get_json(silent=True) or {}
    user_message = (body.get("message") or "").strip()
    history = body.get("history") or []
    if not user_message:
        return err("Mensaje vacío")

    user_id = get_current_user_id()
    ctx = _build_agent_context(user_id)

    system_prompt = f"""Eres Viora Coach, el asistente personal de disciplina dentro de la app Viora.
Eres directo, honesto y motivador. Sabes cuándo felicitar y cuándo exigir más.

ESTADO ACTUAL DEL USUARIO:

HÁBITOS:
{ctx['habits_text']}

TAREAS:
{ctx['tasks_text']}

FINANZAS:
{ctx['finances_text']}

Cuando el usuario mencione que hizo algo (ej: "me tomé un vaso de agua", "fui al gym", "terminé el reporte"), identifica si coincide con un hábito o tarea y registra el avance usando las herramientas disponibles.
Siempre confirma al usuario qué registraste. Sé breve (2-3 oraciones máximo salvo que pidan más detalle).
Responde SIEMPRE en español."""

    tools = [
        {
            "name": "complete_habit",
            "description": "Registra progreso en un hábito del usuario cuando menciona haberlo realizado.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "habit_id": {"type": "string", "description": "ID exacto del hábito (del listado)"},
                    "habit_name": {"type": "string", "description": "Nombre del hábito"},
                    "amount": {"type": "number", "description": "Cantidad a sumar al progreso (default 1)"}
                },
                "required": ["habit_id", "habit_name"]
            }
        },
        {
            "name": "complete_task",
            "description": "Marca una tarea como completada cuando el usuario menciona haberla terminado.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "ID exacto de la tarea"},
                    "task_name": {"type": "string", "description": "Nombre de la tarea"}
                },
                "required": ["task_id", "task_name"]
            }
        },
        {
            "name": "create_task",
            "description": "Crea una nueva tarea cuando el usuario pide agregar una meta o tarea.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nombre de la tarea"},
                    "description": {"type": "string", "description": "Descripción opcional"},
                    "due_date": {"type": "string", "description": "Fecha límite opcional en formato YYYY-MM-DD"}
                },
                "required": ["name"]
            }
        },
        {
            "name": "create_habit",
            "description": "Crea un nuevo hábito cuando el usuario quiere agregar una rutina o hábito.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nombre del hábito"},
                    "category": {"type": "string", "description": "Categoría: gym, social, habitos, salud_mental, salud, procrastinacion, estudio, trabajo, hogar"},
                    "unit": {"type": "string", "description": "Unidad de medida, ej: vasos, km, minutos, veces"},
                    "target": {"type": "number", "description": "Meta diaria numérica, ej: 8 (vasos de agua)"},
                    "period": {"type": "string", "description": "Frecuencia: diaria, semanal"}
                },
                "required": ["name"]
            }
        },
        {
            "name": "log_finance",
            "description": "Registra un ingreso o gasto cuando el usuario menciona dinero que ganó o gastó.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "'income' para ingresos, 'expense' para gastos"},
                    "amount": {"type": "number", "description": "Monto en pesos colombianos"},
                    "description": {"type": "string", "description": "Descripción del movimiento"}
                },
                "required": ["type", "amount", "description"]
            }
        }
    ]

    try:
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        messages = []
        for h in history[-12:]:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({"role": h["role"], "content": str(h["content"])})
        messages.append({"role": "user", "content": user_message})

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )

        total_input = response.usage.input_tokens
        total_output = response.usage.output_tokens

        tool_results_meta = []
        if response.stop_reason == "tool_use":
            tool_result_blocks = []
            for block in response.content:
                if block.type == "tool_use":
                    result_text = _execute_agent_tool(block.name, block.input, user_id)
                    tool_results_meta.append({
                        "tool": block.name,
                        "input": block.input,
                        "result": result_text,
                    })
                    tool_result_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    })

            follow_messages = messages + [
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": tool_result_blocks},
            ]
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system=system_prompt,
                tools=tools,
                messages=follow_messages,
            )
            total_input += response.usage.input_tokens
            total_output += response.usage.output_tokens

        reply = " ".join(b.text for b in response.content if hasattr(b, "text")).strip()
        return ok({
            "reply": reply,
            "toolsUsed": tool_results_meta,
            "usage": {
                "input_tokens": total_input,
                "output_tokens": total_output,
                "total_tokens": total_input + total_output,
            },
        })

    except Exception as e:
        return err(f"Error del agente: {str(e)}", 502)

# ══════════════════════════════════════════════════════
#  DASHBOARD GENERAL
# ══════════════════════════════════════════════════════

@app.route("/api/dashboard", methods=["GET"])
def dashboard():
    """Resumen completo del día: tareas, hábitos, finanzas, apuesta."""
    if SUPABASE_ENABLED and supabase:
        try:
            tasks_res = supabase.table(TASKS_TABLE).select("done").eq("user_id", get_current_user_id()).execute()
            tasks = tasks_res.data or []
            habits_res = supabase.table(ROUTINES_TABLE).select("*").eq("user_id", get_current_user_id()).execute()
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

            done_habits = _completed_habit_count(habits)

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
                    "habitsLeft": max(0, 3 - done_habits),
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
    done_habits  = _completed_habit_count(habits)
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
            "habitsLeft": max(0, 3 - done_habits),
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
    print("  DELETE /api/community/<id>/comments/<comment_id>")
    print("  POST   /api/community/<id>/vote")
    print("  DELETE /api/community/<id>")
    print("  ─── Usuario ───")
    print("  GET    /api/user")
    print("  PUT    /api/user")
    app.run(debug=True, port=5000)
