// ==========================================
// API BASE
// ==========================================

const authIsLocalHost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
const API_BASE = authIsLocalHost
    ? (window.location.port && window.location.port !== '8000' ? '/api' : `${window.location.protocol}//${window.location.hostname}:5000/api`)
    : '/api';

window.vioraSupabaseReady = window.vioraSupabaseReady || (async () => null)();

async function getVioraAccessToken() {
    const client = await window.vioraSupabaseReady;
    if (!client) return null;
    const { data } = await client.auth.getSession();
    return data.session?.access_token || null;
}

async function apiFetch(url, options = {}) {
    const token = await getVioraAccessToken();
    return fetch(url, {
        credentials: 'include',
        ...options,
        headers: {
            ...(options.headers || {}),
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
    });
}

function isEmailRateLimit(error) {
    const message = (error?.message || '').toLowerCase();
    return message.includes('rate limit') || message.includes('email rate limit');
}

function isAlreadyRegistered(error) {
    const message = (error?.message || '').toLowerCase();
    return message.includes('already registered') || message.includes('already been registered');
}

function isEmailNotConfirmed(error) {
    const message = (error?.message || '').toLowerCase();
    return message.includes('email not confirmed') || message.includes('not confirmed');
}

function getLoginErrorMessage(error, fallbackError) {
    if (isEmailNotConfirmed(error)) {
        return 'Tu cuenta existe, pero falta confirmar el correo. Confirma el email o desactiva Confirm email en Supabase durante pruebas.';
    }
    return fallbackError?.message || error?.message || 'No se pudo iniciar sesion';
}

async function fallbackEmailAuth(action, body) {
    const client = await window.vioraSupabaseReady;
    await client?.auth.signOut({ scope: 'local' }).catch(() => {});
    clearSupabaseAuthStorage();
    const response = await fetch(`${API_BASE}/auth/email/${action}`, {
        credentials: 'include',
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.success) {
        const error = new Error(payload.error || 'No se pudo autenticar con el backend');
        error.status = response.status;
        error.code = payload.code;
        throw error;
    }
    return payload.data;
}

// ==========================================
// AUTH - SUPABASE EMAIL/PASSWORD
// ==========================================

const loginBtn = document.getElementById('btn-login');
const logoutBtn = document.getElementById('btn-logout');
const userBadge = document.getElementById('user-badge');
const authScreen = document.getElementById('auth-screen');
const authLoginForm = document.getElementById('auth-form-login');
const authRegisterForm = document.getElementById('auth-form-register');
const authLoginTab = document.getElementById('auth-mode-login');
const authRegisterTab = document.getElementById('auth-mode-register');
const authError = document.getElementById('auth-error');
const greetingName = document.getElementById('greeting-name');
const profileLogoutEmail = document.getElementById('profile-logout-email');
let isSigningOut = false;

function clearSupabaseAuthStorage() {
    try {
        Object.keys(localStorage)
            .filter((key) => key.startsWith('sb-') || key.includes('supabase'))
            .forEach((key) => localStorage.removeItem(key));
        Object.keys(sessionStorage)
            .filter((key) => key.startsWith('sb-') || key.includes('supabase'))
            .forEach((key) => sessionStorage.removeItem(key));
    } catch (_error) {}
}

function userFromSupabaseSession(session) {
    const user = session?.user;
    if (!user) return null;
    const metadata = user.user_metadata || {};
    const name = metadata.name || metadata.full_name || metadata.user_name || user.email?.split('@')[0];
    return {
        id: user.id,
        email: user.email,
        name,
    };
}

function setAuthUI(user) {
    if (!user || !user.id) {
        if (typeof window.setVioraUser === 'function') window.setVioraUser(null);
        userBadge?.classList.add('hidden');
        logoutBtn?.classList.add('hidden');
        loginBtn?.classList.remove('hidden');
        authScreen?.classList.remove('hidden');
        if (greetingName) greetingName.textContent = 'Hola 👋';
        if (profileLogoutEmail) profileLogoutEmail.textContent = 'Sin sesión activa';
        return;
    }

    userBadge.textContent = user.name || user.email || 'Usuario';
    if (profileLogoutEmail) profileLogoutEmail.textContent = user.email || user.name || 'Sesión actual';
    if (typeof window.setVioraUser === 'function') window.setVioraUser(user);
    userBadge?.classList.remove('hidden');
    logoutBtn?.classList.remove('hidden');
    loginBtn?.classList.add('hidden');
    authScreen?.classList.add('hidden');
    if (greetingName) greetingName.textContent = `Hola, ${user.name || 'Usuario'} 👋`;
}

function setAuthMode(mode) {
    const isLogin = mode === 'login';
    authLoginTab?.classList.toggle('active', isLogin);
    authRegisterTab?.classList.toggle('active', !isLogin);
    authLoginForm?.classList.toggle('active', isLogin);
    authRegisterForm?.classList.toggle('active', !isLogin);
    if (authError) authError.textContent = '';
}

async function handleAuthResponse(response) {
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.success) {
        if (authError) authError.textContent = payload.error || 'Error de autenticacion';
        return;
    }
    await refreshAuth();
}

async function refreshAuth() {
    if (isSigningOut) return;
    try {
        const client = await window.vioraSupabaseReady;
        const { data: sessionData } = client ? await client.auth.getSession() : { data: {} };
        const response = await apiFetch(`${API_BASE}/auth/me`);
        const payload = await response.json();
        const user = payload?.data || null;
        const authenticated = Boolean(payload?.authenticated && user?.id);
        setAuthUI(authenticated ? user : null);
        if (typeof window.loadVioraData === 'function') {
            await window.loadVioraData();
        }
    } catch (error) {
        setAuthUI(null);
    }
}

loginBtn?.addEventListener('click', () => {
    authScreen?.classList.remove('hidden');
});

async function logoutViora() {
    isSigningOut = true;
    try {
        const client = await window.vioraSupabaseReady;
        await fetch(`${API_BASE}/auth/logout`, { method: 'POST', credentials: 'include' });
        await client?.auth.signOut({ scope: 'local' });
        clearSupabaseAuthStorage();
    } finally {
        isSigningOut = false;
        setAuthUI(null);
        if (typeof window.resetPrivateState === 'function') {
            window.resetPrivateState();
        }
        if (typeof window.loadVioraData === 'function') {
            await window.loadVioraData();
        }
        if (typeof window.navTo === 'function') {
            window.navTo('home');
        }
    }
}

window.vioraLogout = logoutViora;
logoutBtn?.addEventListener('click', logoutViora);

authLoginTab?.addEventListener('click', () => setAuthMode('login'));
authRegisterTab?.addEventListener('click', () => setAuthMode('register'));

authLoginForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (authError) authError.textContent = '';
    const email = document.getElementById('auth-login-email')?.value || '';
    const password = document.getElementById('auth-login-password')?.value || '';
    const client = await window.vioraSupabaseReady;
    if (!client) {
        try {
            const user = await fallbackEmailAuth('login', { email, password });
            setAuthUI(user);
            await refreshAuth();
        } catch (fallbackError) {
            if (authError) authError.textContent = fallbackError.message || 'No se pudo iniciar sesion local';
        }
        return;
    }
    const { error } = await client.auth.signInWithPassword({ email, password });
    if (error) {
        try {
            await fallbackEmailAuth('login', { email, password });
        } catch (fallbackError) {
            if (authError) authError.textContent = getLoginErrorMessage(error, fallbackError);
            return;
        }
    }
    await refreshAuth();
});

authRegisterForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (authError) authError.textContent = '';
    const name = document.getElementById('auth-register-name')?.value || '';
    const email = document.getElementById('auth-register-email')?.value || '';
    const password = document.getElementById('auth-register-password')?.value || '';
    const client = await window.vioraSupabaseReady;
    if (!client) {
        try {
            const user = await fallbackEmailAuth('register', { name, email, password });
            setAuthUI(user);
            await refreshAuth();
        } catch (fallbackError) {
            if (fallbackError.status === 409 || fallbackError.code === 'email_already_registered') {
                setAuthMode('login');
            }
            if (authError) authError.textContent = fallbackError.message || 'No se pudo crear la cuenta local';
        }
        return;
    }
    const { data, error } = await client.auth.signUp({
        email,
        password,
        options: { data: { name } },
    });
    const existingSupabaseUser = data?.user && Array.isArray(data.user.identities) && data.user.identities.length === 0;
    if (error) {
        if (isAlreadyRegistered(error)) {
            const { error: loginError } = await client.auth.signInWithPassword({ email, password });
            if (!loginError) {
                await refreshAuth();
                return;
            }
            if (authError) authError.textContent = 'Ya existe una cuenta con este email. Usa Ingresar o prueba otra contrasena.';
            setAuthMode('login');
            return;
        }
        if (!isEmailRateLimit(error)) {
            if (authError) authError.textContent = error.message || 'No se pudo crear la cuenta';
            return;
        }
        try {
            await fallbackEmailAuth('register', { name, email, password });
            await refreshAuth();
            return;
        } catch (fallbackError) {
            if (fallbackError.status === 409 || fallbackError.code === 'email_already_registered') {
                try {
                    await fallbackEmailAuth('login', { email, password });
                    await refreshAuth();
                    return;
                } catch (_ignored) {
                    if (authError) authError.textContent = fallbackError.message || 'Ya existe una cuenta con este email. Usa Ingresar.';
                    return;
                }
            }
            if (authError) authError.textContent = fallbackError.message || error.message || 'No se pudo crear la cuenta';
            return;
        }
    }
    if (existingSupabaseUser) {
        if (authError) authError.textContent = 'Ya existe una cuenta con este email. Usa Ingresar o prueba otra contrasena.';
        setAuthMode('login');
        return;
    }
    if (!data.session) {
        if (authError) authError.textContent = 'Cuenta creada. Revisa tu correo para confirmar antes de ingresar.';
        return;
    }
    await refreshAuth();
});

window.vioraSupabaseReady.then(async (client) => {
    if (client) {
        await client.auth.signOut({ scope: 'local' }).catch(() => {});
        clearSupabaseAuthStorage();
    }
    client?.auth.onAuthStateChange(() => {
        if (!isSigningOut) refreshAuth();
    });
    refreshAuth();
});

// ==========================================
// VIORA – CREATIVE & DYNAMIC LOGIC
// ==========================================

// Navigation with animations
const navItems = document.querySelectorAll('.nav-item');
const views = document.querySelectorAll('.view');

navItems.forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        
        // Remove active from all nav items
        navItems.forEach(nav => nav.classList.remove('active'));
        
        // Add active to clicked item
        item.classList.add('active');
        
        // Hide all views
        views.forEach(view => view.classList.remove('active'));
        
        // Show selected view with animation
        const viewId = item.dataset.view + '-view';
        const selectedView = document.getElementById(viewId);
        if (selectedView) {
            selectedView.classList.add('active');
            // Trigger animation
            selectedView.style.animation = 'none';
            setTimeout(() => {
                selectedView.style.animation = '';
            }, 10);
            
            // Cargar datos si es necesario
            if (item.dataset.view === 'tasks') {
                loadTasks();
            }
        }
    });
});

// ==========================================
// TASKS - MODAL & FORM
// ==========================================

const taskModal = document.getElementById('task-modal');
const btnNewTask = document.getElementById('btn-new-task');
const closeTaskModal = document.getElementById('close-task-modal');
const taskForm = document.getElementById('task-form');
const progressModal = document.getElementById('task-progress-modal');
const closeProgressModal = document.getElementById('close-progress-modal');
const progressForm = document.getElementById('task-progress-form');
const progressAmountInput = document.getElementById('task-progress-amount');
const progressUnitLabel = document.getElementById('task-progress-unit');
let activeTaskId = null;

function isTimeUnit(unit) {
    return unit === 'horas' || unit === 'minutos';
}

function getTimerKey(taskId) {
    return `viora_timer_${taskId}`;
}

function getStoredTimer(taskId) {
    const value = localStorage.getItem(getTimerKey(taskId));
    return value ? parseInt(value, 10) : null;
}

function startTimer(taskId) {
    localStorage.setItem(getTimerKey(taskId), Date.now().toString());
}

function stopTimer(task) {
    const startedAt = getStoredTimer(task.id);
    if (!startedAt) return 0;

    localStorage.removeItem(getTimerKey(task.id));

    const elapsedMs = Date.now() - startedAt;
    const elapsedMinutes = elapsedMs / 60000;
    const elapsedValue = task.unit === 'horas'
        ? elapsedMinutes / 60
        : elapsedMinutes;

    return Math.max(0.01, parseFloat(elapsedValue.toFixed(2)));
}

function completeTaskAmount(task) {
    const target = Number(task.target || 1);
    const current = Number(task.current || (task.done ? target : 0));
    return Math.max(0, parseFloat((target - current).toFixed(2)));
}

btnNewTask?.addEventListener('click', () => {
    taskModal.classList.remove('hidden');
});

closeTaskModal?.addEventListener('click', () => {
    taskModal.classList.add('hidden');
    taskForm.reset();
});

taskModal?.addEventListener('click', (e) => {
    if (e.target === taskModal) {
        taskModal.classList.add('hidden');
        taskForm.reset();
    }
});

closeProgressModal?.addEventListener('click', () => {
    progressModal.classList.add('hidden');
    progressForm.reset();
    activeTaskId = null;
});

progressModal?.addEventListener('click', (e) => {
    if (e.target === progressModal) {
        progressModal.classList.add('hidden');
        progressForm.reset();
        activeTaskId = null;
    }
});

progressForm?.addEventListener('submit', async (e) => {
    e.preventDefault();

    if (!activeTaskId) return;
    const amount = parseFloat(progressAmountInput.value || '0');
    if (!amount || amount <= 0) return;

    await addToTask(activeTaskId, amount);
    await loadTasks();

    progressModal.classList.add('hidden');
    progressForm.reset();
    activeTaskId = null;
});

taskForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const task = {
        name: document.getElementById('task-name').value,
        description: document.getElementById('task-description').value,
        target: parseFloat(document.getElementById('task-target').value),
        unit: document.getElementById('task-unit').value,
        frequency: document.getElementById('task-frequency').value,
    };
    
    try {
        const response = await apiFetch(`${API_BASE}/tasks`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(task)
        });
        
        if (response.ok) {
            const newTask = await response.json();
            taskForm.reset();
            taskModal.classList.add('hidden');
            
            // Celebración
            createCelebration();
            
            // Cargar tareas actualizadas
            await loadTasks();
        }
    } catch (error) {
        console.error('Error creando tarea:', error);
        alert('Error al crear la tarea');
    }
});

// ==========================================
// TASKS - CARGAR DESDE BACKEND
// ==========================================

async function loadTasks() {
    try {
        const response = await apiFetch(`${API_BASE}/tasks`);
        const payload = await response.json();
        const tasks = payload?.success ? (payload.data || []) : payload;
        
        const tasksList = document.getElementById('tasks-list');
        if (!tasksList) return;
        
        if (tasks.length === 0) {
            tasksList.innerHTML = '<p style="text-align: center; color: var(--color-text-muted); padding: 40px 20px;">No hay tareas. ¡Crea una! 🚀</p>';
            return;
        }
        
        tasksList.innerHTML = tasks.map(task => {
            const target = Number(task.target || 1);
            const current = Number(task.current || (task.done ? target : 0));
            const unit = task.unit || 'veces';
            const frequency = task.frequency || task.period || 'diaria';
            const progress = target > 0 ? (current / target * 100) : 0;
            const isCompleted = Boolean(task.done || current >= target);
            const isRunning = getStoredTimer(task.id) !== null;
            const timeControls = isTimeUnit(unit)
                ? `
                    <button class="btn-task-secondary btn-start-timer" data-task-id="${task.id}">${isRunning ? '⏸️ Pausar' : '▶️ Iniciar'}</button>
                    <button class="btn-task-secondary btn-stop-timer" data-task-id="${task.id}">⏹️ Detener</button>
                    <button class="btn-task-primary btn-complete-task" data-task-id="${task.id}">✅ Completar</button>
                  `
                : '';
            const timerStatus = isRunning ? 'Cronometro activo' : '';
            
            return `
                <div class="task-card ${isCompleted ? 'completed' : 'pending'}" data-task-id="${task.id}">
                    <div class="task-checkbox">${isCompleted ? '✓' : '○'}</div>
                    <div class="task-info" style="flex: 1;">
                        <h4>${task.name}</h4>
                        <p class="task-meta">${task.description || `${frequency}`}</p>
                        ${timerStatus ? `<p class="task-meta" style="color: var(--color-yellow);">${timerStatus}</p>` : ''}
                        <div style="margin-top: 8px;">
                            <div class="progress-bar" style="margin-bottom: 6px;">
                                <div class="progress-fill" style="width: ${progress}%"></div>
                            </div>
                            <p style="font-size: 12px; color: var(--color-text-muted);">
                                ${current.toFixed(1)} / ${target} ${unit}
                            </p>
                        </div>
                        ${timeControls ? `<div class="task-actions">${timeControls}</div>` : ''}
                    </div>
                    <div style="display: flex; gap: 8px; margin-left: 16px;">
                        <button class="btn-add-task" data-task-id="${task.id}">+</button>
                        <button class="btn-delete-task" data-task-id="${task.id}">🗑️</button>
                    </div>
                </div>
            `;
        }).join('');
        
        // Agregar event listeners a botones
        document.querySelectorAll('.btn-add-task').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const taskId = e.target.dataset.taskId;
                const task = tasks.find(t => t.id === taskId);
                if (!task) return;

                activeTaskId = taskId;
                progressAmountInput.value = '1';
                progressUnitLabel.textContent = `Unidad: ${task.unit || 'veces'}`;
                progressModal.classList.remove('hidden');
            });
        });
        
        document.querySelectorAll('.btn-delete-task').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const taskId = e.target.dataset.taskId;
                if (confirm('¿Eliminar tarea?')) {
                    await deleteTask(taskId);
                    await loadTasks();
                }
            });
        });

        document.querySelectorAll('.btn-start-timer').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const taskId = e.target.dataset.taskId;
                const task = tasks.find(t => t.id === taskId);
                if (!task) return;

                if (getStoredTimer(taskId)) {
                    const elapsed = stopTimer(task);
                    if (elapsed > 0) {
                        await addToTask(taskId, elapsed);
                    }
                } else {
                    startTimer(taskId);
                }

                await loadTasks();
            });
        });

        document.querySelectorAll('.btn-stop-timer').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const taskId = e.target.dataset.taskId;
                const task = tasks.find(t => t.id === taskId);
                if (!task) return;

                const elapsed = stopTimer(task);
                if (elapsed > 0) {
                    await addToTask(taskId, elapsed);
                }

                await loadTasks();
            });
        });

        document.querySelectorAll('.btn-complete-task').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const taskId = e.target.dataset.taskId;
                const task = tasks.find(t => t.id === taskId);
                if (!task) return;

                const amount = completeTaskAmount(task);
                if (amount > 0) {
                    await addToTask(taskId, amount);
                    await loadTasks();
                }
            });
        });
        
    } catch (error) {
        console.error('Error cargando tareas:', error);
    }
}

async function addToTask(taskId, amount) {
    try {
        const response = await apiFetch(`${API_BASE}/tasks/${taskId}/add`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount })
        });
        
        const payload = await response.json();
        const data = payload?.success ? (payload.data || {}) : payload;
        
        if (data.completed) {
            createCelebration();
            addMessage('🎉 ¡¡TAREA COMPLETADA!! ¡¡Increíble!!', 'agent', 'epic');
        }
    } catch (error) {
        console.error('Error agregando a tarea:', error);
    }
}

async function deleteTask(taskId) {
    try {
        await apiFetch(`${API_BASE}/tasks/${taskId}`, { method: 'DELETE' });
    } catch (error) {
        console.error('Error eliminando tarea:', error);
    }
}

// ==========================================
// CREATIVE CHAT RESPONSES
// ==========================================

const vioraResponses = [
    { text: "🔥 ¡ESO ES! ¡Así se hace! Mantén ese nivel.", emotion: "epic" },
    { text: "📈 Excelente. Eso te acerca a tus metas. Sigue.", emotion: "positive" },
    { text: "⚠️ Espera... ¿eso estaba en tu plan? Revisa tus objetivos.", emotion: "warning" },
    { text: "💪 Increíble consistencia. Así se construye disciplina.", emotion: "epic" },
    { text: "🎯 Buena ejecución. Pero hay margen de mejora.", emotion: "neutral" },
    { text: "🚨 Ojo con eso. El gasto está subiendo más de lo normal.", emotion: "warning" },
    { text: "✨ Perfecto. Así es como se ve la disciplina en acción.", emotion: "epic" },
    { text: "🐝 Estás construyendo tu miel. Sigue la consistencia.", emotion: "positive" },
    { text: "⚡ Impresionante. Así se rompen los límites.", emotion: "epic" },
    { text: "🎖️ Racha confirmada. No la cagues ahora.", emotion: "positive" },
];

function sendMessage() {
    const messageInput = document.getElementById('chat-input');
    const message = messageInput.value.trim();
    
    if (!message) return;
    
    // Add user message
    addMessage(message, 'user');
    
    // Clear input
    messageInput.value = '';
    messageInput.focus();
    
    // Create celebratory effect
    createCelebration();
    
    // Simulate agent response with delay
    setTimeout(() => {
        const randomResponse = vioraResponses[
            Math.floor(Math.random() * vioraResponses.length)
        ];
        addMessage(randomResponse.text, 'agent', randomResponse.emotion);
    }, 600);
}

function addMessage(text, sender, emotion = 'neutral') {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}-message`;
    if (emotion) messageDiv.setAttribute('data-emotion', emotion);
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.textContent = text;
    
    messageDiv.appendChild(contentDiv);
    const chatMessages = document.getElementById('chat-messages');
    chatMessages.appendChild(messageDiv);
    
    // Scroll to bottom smoothly
    setTimeout(() => {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }, 50);
}

function createCelebration() {
    const container = document.querySelector('.chat-messages');
    const confettiCount = 12;
    
    for (let i = 0; i < confettiCount; i++) {
        const confetti = document.createElement('div');
        confetti.innerHTML = ['🎉', '✨', '🔥', '⭐', '💪'][Math.floor(Math.random() * 5)];
        confetti.style.cssText = `
            position: fixed;
            left: ${Math.random() * 100}%;
            top: 50%;
            font-size: 24px;
            pointer-events: none;
            animation: confetti 1s ease-out forwards;
            transform: translateY(-50%);
            z-index: 9999;
        `;
        document.body.appendChild(confetti);
        
        setTimeout(() => confetti.remove(), 1000);
    }
}

// ==========================================
// CHAT FUNCTIONALITY
// ==========================================

const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');

sendBtn?.addEventListener('click', sendMessage);
chatInput?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

// ==========================================
// INTERACTIVE ELEMENTS
// ==========================================

// Make habit cards clickable and celebratory
document.addEventListener('click', function(e) {
    if (e.target.closest('.habit-card')) {
        const card = e.target.closest('.habit-card');
        card.style.animation = 'shake 0.3s ease-in-out';
        setTimeout(() => {
            card.style.animation = '';
        }, 300);
        
        // Add visual feedback
        createMiniCelebration(e.pageX, e.pageY);
    }
});

function createMiniCelebration(x, y) {
    for (let i = 0; i < 5; i++) {
        const particle = document.createElement('div');
        particle.innerHTML = '✨';
        particle.style.cssText = `
            position: fixed;
            left: ${x}px;
            top: ${y}px;
            font-size: 16px;
            pointer-events: none;
            z-index: 9999;
            opacity: 1;
            animation: confetti ${0.6 + Math.random() * 0.4}s ease-out forwards;
        `;
        document.body.appendChild(particle);
        
        setTimeout(() => particle.remove(), 1000);
    }
}

// ==========================================
// AGENT CHAT
// ==========================================

let agentHistory = [];
let agentTotalTokens = 0;

function openAgentChat() {
    const overlay = document.getElementById('agentOverlay');
    if (!overlay) { console.error('agentOverlay no encontrado'); return; }
    overlay.classList.add('open');
    setTimeout(() => document.getElementById('agentInput')?.focus(), 350);
}
window.openAgentChat = openAgentChat;

function _updateTokenBar(usage) {
    if (!usage) return;
    agentTotalTokens += usage.total_tokens || 0;
    const bar = document.getElementById('agentTokenBar');
    const label = document.getElementById('agentTokenLabel');
    if (!bar || !label) return;
    bar.style.display = 'flex';
    label.textContent = `↑${usage.input_tokens} ↓${usage.output_tokens} · sesión: ${agentTotalTokens.toLocaleString()} tokens`;
}

function closeAgentChat() {
    document.getElementById('agentOverlay').classList.remove('open');
}

function _appendAgentMessage(role, text, tools, usage) {
    const container = document.getElementById('agentMessages');
    const div = document.createElement('div');
    div.className = `agent-msg agent-msg--${role === 'user' ? 'user' : 'bot'}`;
    let inner = `<div class="agent-bubble">${text.replace(/\n/g, '<br>')}</div>`;
    if (tools && tools.length) {
        const labels = tools.map(t => {
            if (t.tool === 'complete_habit') return `✅ ${t.input.habit_name}`;
            if (t.tool === 'complete_task') return `✅ ${t.input.task_name}`;
            if (t.tool === 'create_task') return `➕ tarea: ${t.input.name}`;
            if (t.tool === 'create_habit') return `➕ hábito: ${t.input.name}`;
            if (t.tool === 'log_finance') return `💰 ${t.input.type === 'income' ? 'ingreso' : 'gasto'}: $${Number(t.input.amount).toLocaleString()}`;
            return t.tool;
        });
        inner += `<div style="margin-top:4px">${labels.map(l => `<span class="agent-tool-badge">${l}</span>`).join(' ')}</div>`;
    }
    if (role !== 'user' && usage) {
        inner += `<div class="agent-token-hint">↑${usage.input_tokens} ↓${usage.output_tokens} tokens</div>`;
    }
    div.innerHTML = inner;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function _showAgentTyping() {
    const container = document.getElementById('agentMessages');
    const div = document.createElement('div');
    div.className = 'agent-msg agent-msg--bot';
    div.id = 'agentTyping';
    div.innerHTML = '<div class="agent-bubble agent-typing"><span></span><span></span><span></span></div>';
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function _removeAgentTyping() {
    const el = document.getElementById('agentTyping');
    if (el) el.remove();
}

async function sendAgentMessage() {
    const input = document.getElementById('agentInput');
    const btn = document.getElementById('agentSendBtn');
    const status = document.getElementById('agentStatus');
    const text = input.value.trim();
    if (!text) return;

    input.value = '';
    btn.disabled = true;
    _appendAgentMessage('user', text);
    agentHistory.push({ role: 'user', content: text });

    status.textContent = 'pensando...';
    _showAgentTyping();

    try {
        const res = await apiFetch(`${API_BASE}/agent/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, history: agentHistory.slice(-12) }),
        });
        const data = await res.json();
        _removeAgentTyping();

        if (data.success) {
            const reply = data.data.reply;
            const tools = data.data.toolsUsed || [];
            const usage = data.data.usage;
            _appendAgentMessage('bot', reply, tools, usage);
            _updateTokenBar(usage);
            agentHistory.push({ role: 'assistant', content: reply });
            if (tools.length) {
                showToast('Avance registrado 💪', 'success');
                loadVioraData();
            }
            status.textContent = 'listo para ayudarte';
        } else {
            _appendAgentMessage('bot', data.error || 'Ocurrió un error, intenta de nuevo.');
            status.textContent = 'error';
        }
    } catch (e) {
        _removeAgentTyping();
        _appendAgentMessage('bot', 'No pude conectarme al servidor. ¿Está corriendo el backend?');
        status.textContent = 'sin conexión';
    } finally {
        btn.disabled = false;
        input.focus();
    }
}

document.getElementById('agentInput')?.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendAgentMessage();
    }
});

// ==========================================
// INIT
// ==========================================

refreshAuth();

console.log('%c🐝 VIORA - PERSONAL DISCIPLINE SYSTEM', 'font-size: 20px; color: #F4B315; font-weight: bold; text-shadow: 0 0 10px #E59312;');
console.log('%cDisciplina > Perfección', 'font-size: 14px; color: #D3AF85;');
console.log('%cLa consistencia es tu superpoder 💪', 'font-size: 12px; color: #8E5915;');
