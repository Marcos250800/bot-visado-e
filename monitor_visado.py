"""
Monitor de citas - Visado Nacional de Estudios
Consulado General de España en La Habana (Cuba)

v5: Manejo correcto del popup alert() en pestaña nueva
- El enlace abre pestaña nueva como consecuencia del clic
- El handler de dialog se registra en el CONTEXTO (aplica a todas las páginas)
- Después de aceptar el popup, pulsa "Continue / Continuar"
- Lee calendario y detecta huecos libres
"""

import os
import sys
import asyncio
import requests
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright

# ===== Configuración =====
URL_INICIO = (
    "https://www.exteriores.gob.es/Consulados/lahabana/es/"
    "ServiciosConsulares/Paginas/index.aspx"
    "?scco=Cuba&scd=166&scca=Visados&scs=Visados+Nacionales+-+Visado+de+estudios"
)

TEXTO_ENLACE = "Reservar cita de visado estudio"

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN_VISADO")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID_VISADO")

CAPTURA = Path("captura.png")
CAPTURA_ERROR = Path("captura_error.png")
ESTADO_FILE = Path("ultimo_estado.txt")


# ===== Utilidades =====
def log(msg):
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    print(f"[{ahora}] {msg}", flush=True)


def enviar_telegram(texto):
    if not TG_TOKEN or not TG_CHAT:
        log("⚠ Token Telegram no configurado")
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data={"chat_id": TG_CHAT, "text": texto, "parse_mode": "HTML"},
            timeout=15,
        )
        log(f"✅ Telegram texto: {r.status_code}")
    except Exception as e:
        log(f"⚠ Error Telegram: {e}")


def enviar_foto(ruta, caption=""):
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
        log(f"✅ Telegram foto: {r.status_code}")
    except Exception as e:
        log(f"⚠ Error Telegram foto: {e}")


def leer_estado():
    if ESTADO_FILE.exists():
        return ESTADO_FILE.read_text(encoding="utf-8").strip()
    return ""


def guardar_estado(valor):
    ESTADO_FILE.write_text(valor, encoding="utf-8")


# ===== Bot principal =====
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="es-ES",
            viewport={"width": 1366, "height": 768},
        )

        # Anti-detección
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['es-ES', 'es', 'en'] });
            window.chrome = { runtime: {} };
        """)

        # CLAVE: registrar handler de dialog en el CONTEXTO
        # Así aplica a TODAS las páginas, incluidas las nuevas que se abran
        dialog_aceptado = False

        def on_page(nueva_pagina):
            """Se ejecuta cada vez que se abre una nueva página/pestaña."""
            async def handle_dialog(dialog):
                nonlocal dialog_aceptado
                log(f"  💬 Dialog en nueva página: '{dialog.message}' → Aceptar")
                await dialog.accept()
                dialog_aceptado = True
            nueva_pagina.on("dialog", lambda d: asyncio.ensure_future(handle_dialog(d)))

        context.on("page", on_page)

        page = await context.new_page()

        # También registrar en la página principal por si acaso
        async def handle_dialog_main(dialog):
            nonlocal dialog_aceptado
            log(f"  💬 Dialog en página principal: '{dialog.message}' → Aceptar")
            await dialog.accept()
            dialog_aceptado = True

        page.on("dialog", lambda d: asyncio.ensure_future(handle_dialog_main(d)))

        try:
            # ─── PASO 1: abrir página del Ministerio ───
            log("📄 Paso 1: abriendo exteriores.gob.es ...")
            await page.goto(URL_INICIO, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(3_000)
            log(f"  ✓ Cargada: {page.url}")

            # ─── PASO 2: clic en enlace → se abre pestaña nueva ───
            log(f"🔗 Paso 2: buscando enlace '{TEXTO_ENLACE}' ...")

            enlace = page.locator(f"a:has-text('{TEXTO_ENLACE}')")
            count = await enlace.count()
            log(f"  Encontrados {count} enlace(s)")

            if count == 0:
                raise Exception("No se encontró el enlace de reservar cita")

            # Esperar pestaña nueva como consecuencia del clic
            async with context.expect_page(timeout=30_000) as nueva_info:
                await enlace.first.click()

            nueva = await nueva_info.value
            log(f"  ✓ Nueva pestaña abierta (consecuencia del clic)")

            # Registrar handler de dialog TAMBIÉN directamente en la nueva página
            async def handle_dialog_nueva(dialog):
                nonlocal dialog_aceptado
                log(f"  💬 Dialog nueva pestaña: '{dialog.message}' → Aceptar")
                await dialog.accept()
                dialog_aceptado = True

            nueva.on("dialog", lambda d: asyncio.ensure_future(handle_dialog_nueva(d)))

            # Esperar a que cargue y el dialog se dispare
            await nueva.wait_for_load_state("domcontentloaded", timeout=60_000)
            await nueva.wait_for_timeout(5_000)
            log(f"  URL nueva pestaña: {nueva.url}")

            # ─── PASO 3: popup Welcome/Bienvenido ───
            log("🟡 Paso 3: popup Welcome/Bienvenido ...")

            if dialog_aceptado:
                log("  ✓ Popup aceptado automáticamente")
            else:
                # Esperar un poco más por si tarda
                log("  Esperando popup...")
                await nueva.wait_for_timeout(5_000)
                if dialog_aceptado:
                    log("  ✓ Popup aceptado (tardó un poco)")
                else:
                    log("  ⚠ No se detectó popup, continuando...")

            await nueva.wait_for_timeout(2_000)
            await nueva.screenshot(path="debug_paso3.png", full_page=True)
            log(f"  📸 Debug paso 3: {Path('debug_paso3.png').stat().st_size} bytes")

            # ─── PASO 4: botón verde "Continue / Continuar" ───
            log("🟢 Paso 4: buscando botón Continue / Continuar ...")

            boton_encontrado = False

            # Esperar a que aparezca
            try:
                await nueva.wait_for_selector('text=/Continue|Continuar/i', timeout=15_000)
                log("  ✓ Texto Continue/Continuar visible")
            except Exception:
                log("  ⚠ Texto no apareció en 15s")

            selectores = [
                'button:has-text("Continue / Continuar")',
                'button:has-text("Continuar")',
                'button:has-text("Continue")',
                'a:has-text("Continue / Continuar")',
                'a:has-text("Continuar")',
                'a:has-text("Continue")',
                'input[value*="Continuar"]',
                'input[value*="Continue"]',
            ]

            for sel in selectores:
                try:
                    loc = nueva.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        await loc.click(timeout=8_000)
                        log(f"  ✓ Clic en: {sel}")
                        boton_encontrado = True
                        break
                except Exception:
                    continue

            if not boton_encontrado:
                try:
                    loc = nueva.get_by_text("Continuar", exact=False)
                    if await loc.count() > 0:
                        await loc.first.click(timeout=8_000)
                        log("  ✓ Clic por get_by_text")
                        boton_encontrado = True
                except Exception:
                    pass

            if not boton_encontrado:
                log("  ⚠ No se encontró botón Continuar")
                await nueva.screenshot(path=str(CAPTURA_ERROR), full_page=True)
                enviar_foto(CAPTURA_ERROR, "⚠️ <b>No se encontró botón Continuar</b>\nRevisa la captura.")

            await nueva.wait_for_timeout(5_000)

            # ─── PASO 5: leer calendario ───
            log("📅 Paso 5: analizando resultado ...")

            try:
                await nueva.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass

            await nueva.wait_for_timeout(2_000)
            contenido = await nueva.content()
            contenido_lower = contenido.lower()
            await nueva.screenshot(path=str(CAPTURA), full_page=True)
            log(f"  📸 Captura: {CAPTURA.stat().st_size} bytes")
            log(f"  URL final: {nueva.url}")
            log(f"  Contenido: {len(contenido)} chars")

            # Cloudflare
            if "verificación de seguridad" in contenido_lower or "challenge-platform" in contenido_lower:
                log("  🛑 Cloudflare detectado")
                enviar_foto(CAPTURA, "🛑 <b>Cloudflare bloqueando</b>")
                return

            # ¿Hay citas?
            tiene_hueco = "hueco libre" in contenido_lower or "huecos libres" in contenido_lower

            if tiene_hueco:
                num = contenido_lower.count("hueco libre") + contenido_lower.count("huecos libres")
                estado_actual = f"CITAS:{num}"

                if estado_actual != leer_estado():
                    log(f"  🎉 ¡CITAS DETECTADAS! ({num} bloques)")
                    enviar_foto(
                        CAPTURA,
                        f"🎉 <b>¡HAY CITAS DISPONIBLES!</b>\n\n"
                        f"📌 Visado de Estudios - Consulado La Habana\n"
                        f"🟢 {num} bloques con huecos libres\n\n"
                        f"⚡ Reserva ya antes de que las cojan",
                    )
                    guardar_estado(estado_actual)
                else:
                    log(f"  ⏸ Ya notificado ({num} bloques)")
            else:
                log("  💤 Sin citas disponibles")
                if leer_estado().startswith("CITAS:"):
                    enviar_telegram("💤 <b>Citas agotadas</b>. Seguiré vigilando.")
                    guardar_estado("SIN_CITAS")

        except Exception as e:
            log(f"❌ Error: {e}")
            try:
                await page.screenshot(path=str(CAPTURA_ERROR), full_page=True)
            except Exception:
                pass
            enviar_foto(CAPTURA_ERROR, f"⚠️ <b>Error</b>\n\n<code>{str(e)[:300]}</code>")
        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    if not TG_TOKEN or not TG_CHAT:
        log("❌ Faltan secrets TELEGRAM_BOT_TOKEN_VISADO y TELEGRAM_CHAT_ID_VISADO")
        sys.exit(1)
    asyncio.run(main())
