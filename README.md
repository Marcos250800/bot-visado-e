# 🎓 Bot Vigilancia Citas Visado de Estudios

Detecta automáticamente cuando hay citas de **Visado de Estudios** disponibles en el Consulado General de España en La Habana (Cuba) y avisa por **Telegram con captura de pantalla**.

Funciona 100% en la nube con **GitHub Actions** — sin servidor, sin dejar el PC encendido.

---

## 🔧 Cómo funciona

El bot reproduce el flujo de 5 pasos que haría una persona:

1. Abre la página del Ministerio (`exteriores.gob.es`)
2. Hace clic en el enlace **"Reservar cita de visado estudio"**
3. Acepta el popup *Welcome / Bienvenido*
4. Pulsa el botón verde *Continue / Continuar*
5. Lee el calendario y comprueba si aparece **"Hueco libre"** o **"Huecos libres"**

Si encuentra huecos → te manda mensaje a Telegram con captura.
Si no → silencio (no hace ruido).

Frecuencia: **cada 5 minutos**, 24/7.

---

## 🚀 Instalación paso a paso

### 1️⃣ Crear el repositorio en GitHub

1. Entra en [github.com](https://github.com) → **New repository**
2. Nombre: `bot-visado-estudios-habana`
3. Marca **Private** (recomendado)
4. Crear repositorio (sin README)

### 2️⃣ Subir los archivos

Hay dos formas:

**Opción A — Web (más fácil):**
- En el repo, dale a **"uploading an existing file"**
- Arrastra TODOS los archivos del proyecto (incluida la carpeta `.github`)
- Commit changes

**Opción B — Git desde tu PC:**
```bash
git init
git add .
git commit -m "primer commit"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/bot-visado-estudios-habana.git
git push -u origin main
```

### 3️⃣ Configurar los Secrets

En el repo de GitHub:
**Settings → Secrets and variables → Actions → New repository secret**

Añade estos 2 secrets:

| Nombre | Valor |
|---|---|
| `TELEGRAM_BOT_TOKEN_VISADO` | Tu token de @BotFather (ej: `8530...:AAGs0...`) |
| `TELEGRAM_CHAT_ID_VISADO` | Tu chat ID (ej: `8755956593`) |

### 4️⃣ Activar GitHub Actions

1. Ve a la pestaña **Actions** del repo
2. Si pide confirmar permisos para ejecutar workflows → **Acepta**
3. Verás el workflow **"🎓 Vigilar Citas Visado Estudios"**

### 5️⃣ Hacer una prueba manual

1. En **Actions**, entra al workflow
2. Botón **"Run workflow"** → **Run workflow** (en la rama `main`)
3. Espera 1-2 min y mira el log
4. Si todo va bien → silencio (no hay citas) o mensaje en Telegram (si las hay)

---

## 📁 Estructura del proyecto

```
bot-visado-estudios-habana/
├── monitor_visado.py              # Script principal del bot
├── requirements.txt               # Dependencias Python
├── ultimo_estado.txt              # Memoria entre ejecuciones
├── .gitignore
├── README.md
└── .github/
    └── workflows/
        └── check.yml              # Configuración GitHub Actions
```

---

## ⚙️ Personalización

### Cambiar la frecuencia

Edita `.github/workflows/check.yml`, línea del cron:

```yaml
- cron: "*/5 * * * *"     # cada 5 min (actual)
- cron: "*/10 * * * *"    # cada 10 min
- cron: "*/30 * * * *"    # cada 30 min
- cron: "0 */1 * * *"     # cada hora
```

### Detener temporalmente

Settings → Actions → Workflows → desactiva el workflow.

---

## 🐛 Si algo falla

- **Mira los logs** en la pestaña Actions → workflow → último run
- **Descarga las capturas** del run (artifact `capturas-XXXXX`) para ver qué vio el bot
- Si Telegram no recibe nada y los logs dicen "ok" → revisa que le diste `/start` al bot desde tu número
- Si aparece un error de Cloudflare → escenario pesimista, hay que cambiar de estrategia (ver sección abajo)

---

## ☁️ Sobre Cloudflare

El sitio `citaconsular.es` usa Cloudflare antibot. La estrategia es entrar **siempre desde `exteriores.gob.es` primero** para que Cloudflare nos vea como tráfico legítimo.

Si en algún momento empieza a fallar por Cloudflare, hay 3 alternativas:
- **Proxy residencial** (BrightData, IPRoyal): ~5-10€/mes
- **Solver de Captcha** (2Captcha, CapSolver): ~3$/1000 checks
- **Ejecutar en local** desde tu PC (con tu IP real): gratis pero requiere PC encendido

El bot ya envía aviso por Telegram si detecta el escenario pesimista, así sabes cuándo cambiar.
