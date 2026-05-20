# 🐝 VIORA – Sistema de Disciplina Personal

> Disciplina > Perfección

---

## 📋 Descripción General

Viora es un **sistema inteligente de gestión personal** que ayuda a los usuarios a mantener disciplina en:
- 📝 **Tareas** con unidades y periodicidad flexible
- 🔄 **Hábitos** con racha de consistencia
- 💰 **Finanzas** con tracking de ingresos y gastos

El sistema es completamente **funcional** con:
- ✅ **Backend Flask** con API REST real
- ✅ **Frontend HTML/CSS/JS** con UI épica y animaciones
- ✅ **Almacenamiento persistente** en JSON o Supabase
- ✅ **CORS** para comunicación frontend-backend

---

## ☁️ Vercel + Supabase

La app ya esta conectada a **Vercel** y puede usar **Supabase** como base de datos.

### Variables de entorno en Vercel

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` (recomendado para el backend) o `SUPABASE_KEY` como compatibilidad
- `SUPABASE_ANON_KEY` o `SUPABASE_PUBLISHABLE_KEY` (clave publica para Supabase Auth en el navegador)
- `JWT_SECRET` (requerido para sesiones/login)
- `VIORA_USER_ID` (opcional, por defecto: `11111111-1111-1111-1111-111111111111`)

Para probar autenticacion sin Google, activa en Supabase `Authentication > Providers > Email`.
Si quieres que el registro entre de inmediato durante desarrollo, desactiva temporalmente
`Confirm email`; si lo dejas activo, el usuario debe confirmar el correo antes de iniciar sesion.

En local puedes copiar `.env.example` a `.env` y completar los valores.

### Esquema de base de datos (Supabase)

Tambien esta disponible como archivo ejecutable en `supabase_schema.sql`.

```sql
-- 1. Extensión para UUIDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. users
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name VARCHAR(255) NOT NULL,
  email VARCHAR(255) UNIQUE NOT NULL,
  streak INT DEFAULT 0,
  total_tasks INT DEFAULT 0,
  total_recovered NUMERIC(10, 2) DEFAULT 0.00,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. tasks
CREATE TABLE tasks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  period VARCHAR(50) DEFAULT 'diaria',
  done BOOLEAN DEFAULT FALSE,
  requires_photo BOOLEAN DEFAULT FALSE,
  verified BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. auth_users (login por email de Viora)
CREATE TABLE auth_users (
  email VARCHAR(255) PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE auth_users ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON auth_users FROM anon, authenticated;
GRANT ALL ON auth_users TO service_role;

-- 5. habits
CREATE TABLE habits (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  icon VARCHAR(10) DEFAULT '🔥',
  streak INT DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. habit_logs
CREATE TABLE habit_logs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  habit_id UUID NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
  log_date DATE NOT NULL DEFAULT CURRENT_DATE,
  done BOOLEAN DEFAULT FALSE,
  UNIQUE (habit_id, log_date)
);

-- 7. finances
CREATE TABLE finances (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  type VARCHAR(20) CHECK (type IN ('income', 'expense')) NOT NULL,
  amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
  transaction_date DATE NOT NULL DEFAULT CURRENT_DATE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 8. bets
CREATE TABLE bets (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  active BOOLEAN DEFAULT TRUE,
  amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 1000),
  bet_date DATE NOT NULL DEFAULT CURRENT_DATE,
  completed BOOLEAN DEFAULT FALSE,
  refunded BOOLEAN DEFAULT FALSE,
  transaction_ref VARCHAR(100),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMP WITH TIME ZONE,
  cancelled_at TIMESTAMP WITH TIME ZONE
);

-- 9. community_posts
CREATE TABLE community_posts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  cat VARCHAR(50) DEFAULT 'general',
  text VARCHAR(500) NOT NULL,
  votes INT DEFAULT 0,
  comments_count INT DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 10. community_comments
CREATE TABLE community_comments (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  post_id UUID NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  text VARCHAR(300) NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Usuario por defecto
INSERT INTO users (id, name, email)
VALUES ('11111111-1111-1111-1111-111111111111', 'Usuario Prueba', 'test@viora.app')
ON CONFLICT DO NOTHING;
```

---

## 🚀 Inicio Rápido

### Requisitos:
- Python 3.8+
- Flask (`pip install Flask Flask-CORS`)

### Paso 1: Instalar dependencias
```bash
cd /home/tomate/Viora_PWA
pip install Flask Flask-CORS
```

### Paso 2: Iniciar backend (Puerto 5000)
```bash
python3 app.py
```

El servidor estará disponible en: `http://localhost:5000`

### Paso 3: Iniciar servidor web (Puerto 8000)
```bash
cd /home/tomate/Viora_PWA
python3 -m http.server 8000
```

### Paso 4: Abrir en navegador
```
http://localhost:8000
```

---

## 🏗️ Estructura del Proyecto

```
Viora_PWA/
├── index.html          # UI principal
├── styles.css          # Diseño y animaciones
├── script.js           # Lógica frontend
├── app.py              # Backend Flask
├── viora_data.json     # Base de datos (JSON)
├── requirements.txt    # Dependencias
└── viora_memory.md     # Documentación del proyecto
```

---

## 🔌 Endpoints Backend

### TAREAS (Tasks)

#### GET `/api/tasks`
Obtiene todas las tareas
```json
Response: [
  {
    "id": "uuid",
    "name": "Tomar agua",
    "description": "Mantente hidratado",
    "unit": "litros",
    "target": 1000,
    "frequency": "weekly",
    "current": 0,
    "status": "active",
    "created_at": "ISO timestamp",
    "last_reset": "ISO timestamp"
  }
]
```

#### POST `/api/tasks`
Crea una nueva tarea
```json
Request: {
  "name": "Tomar agua",
  "description": "Mantente hidratado",
  "unit": "litros",
  "target": 1000,
  "frequency": "weekly"
}

Response: { id, name, description, unit, target, frequency, current, status, created_at, last_reset }
```

#### PUT `/api/tasks/<id>`
Actualiza una tarea
```json
Request: {
  "current": 250,
  "name": "Nuevo nombre",
  "target": 500
}
```

#### POST `/api/tasks/<id>/add`
Agrega cantidad a una tarea
```json
Request: { "amount": 250 }

Response: {
  "task": { ...task data... },
  "completed": true/false,
  "progress": 25.5
}
```

#### POST `/api/tasks/<id>/reset`
Reinicia el contador de la tarea

#### DELETE `/api/tasks/<id>`
Elimina una tarea

### HÁBITOS (Habits)

#### GET `/api/habits`
Obtiene todos los hábitos

#### POST `/api/habits`
Crea un nuevo hábito
```json
Request: {
  "name": "Gimnasio",
  "description": "Entrenar",
  "frequency": "daily"
}
```

#### POST `/api/habits/<id>/complete`
Marca un hábito como completado (incrementa racha)

### GASTOS (Expenses)

#### GET `/api/expenses`
Obtiene todos los gastos

#### POST `/api/expenses`
Registra un nuevo gasto
```json
Request: {
  "category": "comida",
  "amount": 35000,
  "description": "Almuerzo"
}
```

### RESUMEN (Summary)

#### GET `/api/summary`
Obtiene un resumen del sistema
```json
Response: {
  "tasks_total": 5,
  "tasks_completed": 3,
  "habits_total": 4,
  "habits_completed": 2,
  "month_expenses": 850000,
  "tasks": [...],
  "habits": [...]
}
```

### HEALTH

#### GET `/api/health`
Verifica que el servidor está activo

---

## 💡 Ejemplos de Uso

### Crear Tarea: "Tomar 1000 litros de agua a la semana"
```bash
curl -X POST http://localhost:5000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Tomar agua",
    "description": "Mantente hidratado",
    "unit": "litros",
    "target": 1000,
    "frequency": "weekly"
  }'
```

### Agregar 250 litros
```bash
curl -X POST http://localhost:5000/api/tasks/UUID/add \
  -H "Content-Type: application/json" \
  -d '{ "amount": 250 }'
```

### Crear Tarea: "Cronometrar horas fuera de casa"
```bash
curl -X POST http://localhost:5000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Horas fuera",
    "description": "Cronometrar tiempo fuera de casa",
    "unit": "horas",
    "target": 8,
    "frequency": "daily"
  }'
```

---

## 🎨 Unidades Disponibles

- repeticiones
- litros
- horas
- minutos
- km
- páginas
- minutos de meditación
- calorías
- dinero ($)

*Se pueden agregar más en `app.py` y `index.html`*

---

## 🔄 Frecuencias Disponibles

- `daily` - Diaria (se resetea cada 24h)
- `weekly` - Semanal (se resetea cada 7 días)
- `monthly` - Mensual (se resetea cada mes)

---

## 🎨 Características Frontend

### Diseño
- 🌈 **Gradientes dinámicos** amarillo → naranja
- ✨ **Animaciones fluidas** con cubic-bezier
- 🎆 **Confeti celebratorio** al completar tareas
- 📊 **Progress bars** con indicadores visuales
- 🔥 **Hover effects** épicos

### Navegación
- 💬 **Chat** - Interfaz conversacional
- 📊 **Dashboard** - Resumen de métricas
- ✓ **Tasks** - Gestión de tareas dinámicas
- 🔄 **Habits** - Tracking de hábitos
- 💰 **Finance** - Control financiero

### Modal de Tareas
- Campo de nombre
- Campo de cantidad objetivo
- Selector de unidad (9 opciones)
- Selector de frecuencia (3 opciones)
- Campo de descripción
- Validación completa

---

## 📊 Almacenamiento

Los datos se guardan en `viora_data.json` con estructura:

```json
{
  "tasks": [
    { id, name, description, unit, target, frequency, current, status, created_at, last_reset }
  ],
  "habits": [
    { id, name, description, frequency, streak, completed_today, last_completed, created_at }
  ],
  "expenses": [
    { id, category, amount, description, date }
  ],
  "income": []
}
```

---

## 🔧 Desarrollo

### Agregar nueva unidad
1. Ir a `index.html` línea ~150
2. Agregar `<option value="nueva_unidad">Nueva Unidad</option>`

### Cambiar colores
1. Editar variables en `styles.css`:
   ```css
   --color-yellow: #F4B315;
   --color-orange: #E59312;
   --color-primary-bg: #1A141A;
   ```

### Agregar endpoint
1. Crear ruta en `app.py`:
   ```python
   @app.route('/api/nuevo', methods=['GET', 'POST'])
   def nuevo():
       data = load_data()
       # lógica
       save_data(data)
       return jsonify(response)
   ```

---

## 🚨 Troubleshooting

### Error: "Cannot connect to backend"
- Verificar que `python3 app.py` está corriendo en puerto 5000
- Verificar que el frontend está en `http://localhost:8000`

### Error: "CORS"
- Asegurar que `Flask-CORS` está instalado
- Verificar que `CORS(app)` está en `app.py`

### Datos no se guardan
- Verificar permisos en carpeta `Viora_PWA`
- Verificar que `viora_data.json` existe

---

## 📝 TODO / Roadmap

- [ ] Autenticación de usuarios
- [ ] Sincronización en la nube
- [ ] Notificaciones push
- [ ] Integración con IA para análisis de patrones
- [ ] Aplicación móvil
- [ ] Predicción de fracasos
- [ ] Sistema de puntos y recompensas

---

## 🎯 Filosofía

> Viora no es solo una app de productividad. Es un **sistema de disciplina** que se asegura de que **REALMENTE** cumplas tus objetivos.

No importa si es tomar 1000 litros de agua, correr 50 km, o ahorrar dinero. Viora te mantiene **consistente**, **enfocado** y **motivado**.

---

## 📞 Contacto

Desarrollado como parte del proyecto **Viora PWA** - Mayo 2026

---

**Made with 🐝 by Team Viora**
