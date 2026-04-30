"""
Monitor de citas - Visado Nacional de Estudios
Consulado General de España en La Habana (Cuba)

v3: Máxima anti-detección
- Tiempos de espera humanos (aleatorios)
- Scroll gradual antes de hacer clic
- Movimiento de ratón simulado
- Headers y cookies realistas
- Captura en CADA paso para debug total
"""

import os
import sys
import asyncio
import random
import requests
from pathlib import Path
from playwright.async_api import async_playwright

# ===== Configuración =====
URL_MINISTERIO = (
    "https://www.exteriores.gob.es/Consulados/lahabana/es/"
    "ServiciosConsulares/Paginas/index.aspx"
    "?scco=Cuba&scd=166&scca=Visados&scs=Visados+Nacionales+-+Visado+de+estudios"
)

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN_VISADO")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID_VISADO")

ESTADO_FILE = Path("ultimo_estado.txt")


# ===== Utilidades =====
def espera_humana(minimo=2, maximo=5):
    """Genera un tiempo de espera aleatorio como haría un humano."""
    return random.uniform(minimo, maximo)


# ===== Telegram =====
def enviar_telegram(texto: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        print("⚠️ Faltan secrets de Telegram.")
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data={"chat_id": TG_CHAT, "text": texto, "parse_mode": "HTML"},
            timeout=20,
        )
        print(f"📤 Telegram texto: {r.status_code}")
    except Exception as e:
        print(f"❌ Error Telegram: {e}")


def enviar_telegram_foto(ruta: Path, caption: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        return
    if not ruta.exists() or ruta.stat().st_size < 1000:
        enviar_telegram(caption)
        return
    try:
        with open(ruta, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                data={"chat_id": TG_CHAT, "caption": caption[:1024], "parse_mode": "HTML"},
                files={"photo": ("captura.png", f, "image/png")},
                timeout=30,
            )
        print(f"📤 Telegram foto: {r.status_code}")
    except Exception as e:
        print(f"❌ Error Telegram foto: {e}")


# ===== Estado =====
def leer_estado() -> str:
    if ESTADO_FILE.exists():
        return ESTADO_FILE.read_text(encoding="utf-8").strip()
    return ""


def guardar_estado(valor: str) -> None:
    ESTADO_FILE.write_text(valor, encoding="utf-8")


# ===== Simular comportamiento humano =====
async def scroll_gradual(page, pasos=5):
    """Scroll suave hacia abajo como un humano leyendo."""
    for i in range(pasos):
        await page.mouse.wheel(0, random.randint(150, 400))
        await page.wait_for_timeout(int(espera_humana(0.3, 0.8) * 1000))


async def mover_raton_aleatorio(page):
    """Mueve el ratón a una posición aleatoria."""
    x = random.randint(100, 1200)
    y = random.randint(100, 600)
    await page.mouse.move(x, y, steps=random.randint(5, 15))


async def log_cookies(context, label):
    """Imprime las cookies actuales para debug."""
    cookies = await context.cookies()
    print(f"   🍪 Cookies ({label}): {len(cookies)}")
    for c in cookies[:10]:  # Max 10 para no llenar el log
        print(f"      {c['domain']}: {c['name']}={c['value'][:30]}...")


# ===== Lógica principal =====
async def comprobar_citas() -> None:
    async with async_playwright() as p:
        # User agent realista — Chrome 131 en Windows 10
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--window-size=1366,768",
            ],
        )
        context = await browser.new_context(
            user_agent=user_agent,
            locale="es-ES",
            timezone_id="America/Havana",  # Zona horaria de Cuba, más realista
            viewport={"width": 1366, "height": 768},
            # Geolocalización falsa: La Habana
            geolocation={"latitude": 23.1136, "longitude": -82.3666},
            permissions=["geolocation"],
            # Headers extra realistas
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            },
        )

        # Anti-detección avanzada
        await context.add_init_script("""
            // Ocultar webdriver
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            delete navigator.__proto__.webdriver;

            // Idiomas realistas
            Object.defineProperty(navigator, 'languages', { get: () => ['es-ES', 'es', 'en-US', 'en'] });
            Object.defineProperty(navigator, 'language', { get: () => 'es-ES' });

            // Plugins falsos (Chrome real tiene estos)
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const plugins = [
                        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                        { name: 'Native Client', filename: 'internal-nacl-plugin' },
                    ];
                    plugins.length = 3;
                    return plugins;
                }
            });

            // Platform
            Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
            Object.defineProperty(navigator, 'vendor', { get: () => 'Google Inc.' });

            // Chrome object
            window.chrome = {
                runtime: {},
                loadTimes: function() { return {}; },
                csi: function() { return {}; },
                app: { isInstalled: false, InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' } },
            };

            // Permisos
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) =>
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters);

            // WebGL
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                return getParameter.call(this, parameter);
            };

            // Connection
            Object.defineProperty(navigator, 'connection', {
                get: () => ({ effectiveType: '4g', rtt: 50, downlink: 10, saveData: false })
            });

            // Hardware concurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });

            // Device memory
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

            // Max touch points (0 = no touch screen = desktop)
            Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
        """)

        # Handler para dialogs JS
        def handle_dialog(dialog):
            print(f"   💬 Dialog: '{dialog.message}' → aceptando")
            asyncio.create_task(dialog.accept())

        page = await context.new_page()
        page.on("dialog", handle_dialog)

        cita_page = None

        try:
            # ─── PASO 1: abrir página del Ministerio ───
            print("📄 Paso 1: abriendo exteriores.gob.es ...")
            await page.goto(URL_MINISTERIO, wait_until="load", timeout=60_000)

            # Esperar como un humano que lee
            wait_ms = int(espera_humana(3, 6) * 1000)
            print(f"   ⏱ Esperando {wait_ms}ms (simulando lectura)...")
            await page.wait_for_timeout(wait_ms)

            # Mover ratón y scroll como un humano
            await mover_raton_aleatorio(page)
            await scroll_gradual(page, pasos=3)
            await page.wait_for_timeout(int(espera_humana(1, 3) * 1000))

            # Scroll más abajo (el enlace está en la parte baja de la página)
            await scroll_gradual(page, pasos=8)
            await page.wait_for_timeout(int(espera_humana(2, 4) * 1000))

            await page.screenshot(path="debug_paso1.png", full_page=False)
            print(f"   📸 Captura paso 1: {Path('debug_paso1.png').stat().st_size} bytes")
            await log_cookies(context, "después de paso 1")
            print("   ✓ Página del Ministerio cargada y leída")

            # ─── PASO 2: clic en enlace de reservar cita ───
            print("🔗 Paso 2: buscando enlace 'Reservar cita de visado estudio' ...")

            enlace = page.locator("a:has-text('Reservar cita de visado estudio')")
            count = await enlace.count()
            print(f"   Encontrados {count} enlace(s)")

            if count == 0:
                enlace = page.locator("a[href*='citaconsular']")
                count = await enlace.count()
                print(f"   Fallback: {count} enlace(s) con href citaconsular")

            if count == 0:
                raise Exception("No se encontró el enlace de reservar cita")

            # Scroll hasta el enlace para que sea visible
            await enlace.first.scroll_into_view_if_needed()
            await page.wait_for_timeout(int(espera_humana(1, 2) * 1000))

            # Mover ratón hacia el enlace antes de hacer clic
            box = await enlace.first.bounding_box()
            if box:
                await page.mouse.move(
                    box["x"] + box["width"] / 2,
                    box["y"] + box["height"] / 2,
                    steps=random.randint(10, 25)
                )
                await page.wait_for_timeout(int(espera_humana(0.5, 1.5) * 1000))

            # Hacer clic y esperar nueva pestaña
            async with context.expect_page(timeout=30_000) as nueva_pagina_info:
                await enlace.first.click()

            cita_page = await nueva_pagina_info.value
            cita_page.on("dialog", handle_dialog)

            print(f"   ✓ Pestaña nueva: {cita_page.url}")

            # Esperar carga completa
            await cita_page.wait_for_load_state("load", timeout=60_000)

            # Espera humana larga — dejar que Cloudflare procese
            wait_ms = int(espera_humana(5, 8) * 1000)
            print(f"   ⏱ Esperando {wait_ms}ms (dejando que Cloudflare procese)...")
            await cita_page.wait_for_timeout(wait_ms)

            await cita_page.screenshot(path="debug_paso2.png", full_page=True)
            print(f"   📸 Captura paso 2: {Path('debug_paso2.png').stat().st_size} bytes")
            await log_cookies(context, "después de paso 2")

            # ─── Verificar si Cloudflare bloqueó ───
            contenido_p2 = await cita_page.content()
            if "Verificación de seguridad" in contenido_p2 or "challenge-platform" in contenido_p2:
                print("🛑 Cloudflare detectado en paso 2")

                # Intentar esperar a que Cloudflare se resuelva solo
                print("   ⏱ Esperando 15s por si Cloudflare se resuelve automáticamente...")
                await cita_page.wait_for_timeout(15_000)

                contenido_retry = await cita_page.content()
                if "Verificación de seguridad" in contenido_retry or "challenge-platform" in contenido_retry:
                    print("   🛑 Cloudflare sigue bloqueando tras espera")
                    await cita_page.screenshot(path="captura_error.png", full_page=True)
                    enviar_telegram_foto(
                        Path("captura_error.png"),
                        "🛑 <b>Cloudflare bloqueando</b>\n\n"
                        "Incluso con anti-detección avanzada. "
                        "Habrá que ejecutar el bot desde tu PC.",
                    )
                    return
                else:
                    print("   ✓ ¡Cloudflare se resolvió solo!")

            # ─── PASO 3: popup Welcome/Bienvenido ───
            print("🟡 Paso 3: esperando popup Welcome/Bienvenido ...")
            await cita_page.wait_for_timeout(int(espera_humana(3, 5) * 1000))

            await cita_page.screenshot(path="debug_paso3.png", full_page=True)
            print(f"   📸 Captura paso 3: {Path('debug_paso3.png').stat().st_size} bytes")
            print(f"   URL: {cita_page.url}")

            # ─── PASO 4: clic en "Continue / Continuar" ───
            print("🟢 Paso 4: buscando botón Continue/Continuar ...")

            # Esperar a que aparezca algún botón o texto relevante
            try:
                await cita_page.wait_for_selector(
                    'text=/Continue|Continuar/i',
                    timeout=15_000,
                )
                print("   ✓ Texto Continue/Continuar detectado en la página")
            except Exception:
                print("   ⚠️ No apareció texto Continue/Continuar en 15s")

            await cita_page.screenshot(path="debug_paso4_pre.png", full_page=True)

            selectores = [
                'button:has-text("Continue / Continuar")',
                'button:has-text("Continuar")',
                'button:has-text("Continue")',
                'a:has-text("Continue / Continuar")',
                'a:has-text("Continuar")',
                'a:has-text("Continue")',
                'input[value*="Continuar"]',
                'input[value*="Continue"]',
                '#idContinuar',
                '.btn-continuar',
                '[class*="continue"]',
                'div:has-text("Continue / Continuar")',
            ]

            boton_encontrado = False
            for selector in selectores:
                try:
                    loc = cita_page.locator(selector).first
                    if await loc.count() > 0 and await loc.is_visible():
                        print(f"   ✓ Encontrado: {selector}")
                        # Mover ratón al botón antes de hacer clic
                        box = await loc.bounding_box()
                        if box:
                            await cita_page.mouse.move(
                                box["x"] + box["width"] / 2,
                                box["y"] + box["height"] / 2,
                                steps=random.randint(5, 15),
                            )
                            await cita_page.wait_for_timeout(int(espera_humana(0.5, 1) * 1000))
                        await loc.click(timeout=10_000)
                        boton_encontrado = True
                        break
                except Exception:
                    pass

            if not boton_encontrado:
                try:
                    loc = cita_page.get_by_text("Continuar", exact=False)
                    if await loc.count() > 0:
                        print(f"   ✓ Encontrado por get_by_text")
                        await loc.first.click(timeout=10_000)
                        boton_encontrado = True
                except Exception:
                    pass

            if not boton_encontrado:
                contenido_check = await cita_page.content()
                if "Hueco libre" in contenido_check or "Huecos libres" in contenido_check:
                    print("   ✓ Ya en el calendario")
                elif "Cambiar de" in contenido_check or "datetime" in cita_page.url:
                    print("   ✓ Parece que estamos en el calendario")
                else:
                    await cita_page.screenshot(path="captura_error.png", full_page=True)
                    enviar_telegram_foto(
                        Path("captura_error.png"),
                        "⚠️ <b>No encontró botón Continuar</b>\n\nRevisa la captura.",
                    )
                    return

            # ─── PASO 5: leer calendario ───
            print("📅 Paso 5: esperando calendario ...")
            await cita_page.wait_for_timeout(int(espera_humana(4, 7) * 1000))

            try:
                await cita_page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                pass

            await cita_page.wait_for_timeout(2_000)
            contenido = await cita_page.content()
            await cita_page.screenshot(path="captura.png", full_page=True)
            print(f"   📸 Captura calendario: {Path('captura.png').stat().st_size} bytes")
            print(f"   URL final: {cita_page.url}")

            # Cloudflare check final
            if "Verificación de seguridad" in contenido or "challenge-platform" in contenido:
                print("🛑 Cloudflare en paso final")
                enviar_telegram_foto(
                    Path("captura.png"),
                    "🛑 <b>Cloudflare bloqueando</b>\n\nHabrá que usar tu PC.",
                )
                return

            # Detectar huecos
            tiene_hueco = "Hueco libre" in contenido or "Huecos libres" in contenido

            if tiene_hueco:
                num = contenido.count("Hueco libre") + contenido.count("Huecos libres")
                estado_actual = f"CITAS:{num}"

                if estado_actual != leer_estado():
                    print(f"🎉 ¡Citas detectadas! ({num} bloques)")
                    enviar_telegram_foto(
                        Path("captura.png"),
                        f"🎉 <b>¡HAY CITAS DISPONIBLES!</b>\n\n"
                        f"📌 Visado de Estudios - Consulado La Habana\n"
                        f"🟢 {num} bloques con huecos libres\n\n"
                        f"⚡ Reserva ya antes de que las cojan",
                    )
                    guardar_estado(estado_actual)
                else:
                    print(f"⏸ Ya notificado ({num} bloques).")
            else:
                print("💤 Sin citas disponibles.")
                if leer_estado().startswith("CITAS:"):
                    enviar_telegram("💤 <b>Citas agotadas</b>. Seguiré vigilando.")
                    guardar_estado("SIN_CITAS")

        except Exception as e:
            print(f"❌ Error: {e}")
            target = cita_page if cita_page else page
            try:
                await target.screenshot(path="captura_error.png", full_page=True)
            except Exception:
                pass
            enviar_telegram_foto(
                Path("captura_error.png"),
                f"⚠️ <b>Error en bot</b>\n\n<code>{str(e)[:300]}</code>",
            )
        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    if not TG_TOKEN or not TG_CHAT:
        print("❌ Faltan secrets")
        sys.exit(1)
    asyncio.run(comprobar_citas())
