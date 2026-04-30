"""
Monitor de citas - Visado Nacional de Estudios
Consulado General de España en La Habana (Cuba)

Flujo:
1. Abre la página informativa del Ministerio (exteriores.gob.es)
2. Hace clic en "Reservar cita de visado estudio" → abre citaconsular.es
3. Pulsa "Aceptar" en el popup Welcome/Bienvenido
4. Pulsa "Continue / Continuar" (botón verde)
5. Lee el calendario y detecta huecos libres

Si hay huecos, avisa por Telegram con captura.
v2: corregido manejo de pestaña nueva + selector del botón.
"""

import os
import sys
import asyncio
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

CAPTURA = Path("captura.png")
CAPTURA_ERROR = Path("captura_error.png")
ESTADO_FILE = Path("ultimo_estado.txt")


# ===== Telegram =====
def enviar_telegram(texto: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        print("⚠️ Faltan secrets de Telegram.")
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data={
                "chat_id": TG_CHAT,
                "text": texto,
                "parse_mode": "HTML",
                "disable_web_page_preview": "false",
            },
            timeout=20,
        )
        print(f"📤 Telegram texto: {r.status_code}")
    except Exception as e:
        print(f"❌ Error Telegram texto: {e}")


def enviar_telegram_foto(ruta: Path, caption: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        return
    if not ruta.exists() or ruta.stat().st_size < 1000:
        print(f"⚠️ Captura no válida, envío solo texto.")
        enviar_telegram(caption)
        return
    try:
        with open(ruta, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                data={
                    "chat_id": TG_CHAT,
                    "caption": caption[:1024],
                    "parse_mode": "HTML",
                },
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


# ===== Lógica principal =====
async def comprobar_citas() -> None:
    async with async_playwright() as p:
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
            ],
        )
        context = await browser.new_context(
            user_agent=user_agent,
            locale="es-ES",
            timezone_id="Europe/Madrid",
            viewport={"width": 1366, "height": 768},
        )

        await context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['es-ES', 'es', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = { runtime: {} };
            """
        )

        # Handler global para dialogs JS (el popup Welcome/Bienvenido es un alert)
        def handle_dialog(dialog):
            print(f"   💬 Dialog: '{dialog.message}' → aceptando")
            asyncio.create_task(dialog.accept())

        page = await context.new_page()
        page.on("dialog", handle_dialog)

        cita_page = None

        try:
            # ─── PASO 1: abrir página del Ministerio ───
            print("📄 Paso 1: abriendo exteriores.gob.es ...")
            await page.goto(URL_MINISTERIO, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(3_000)
            print("   ✓ Página del Ministerio cargada")

            # ─── PASO 2: clic en enlace que abre citaconsular.es ───
            print("🔗 Paso 2: buscando enlace 'Reservar cita de visado estudio' ...")

            enlace = page.locator("a:has-text('Reservar cita de visado estudio')")
            count = await enlace.count()
            print(f"   Encontrados {count} enlace(s)")

            if count == 0:
                enlace = page.locator("a[href*='citaconsular']")
                count = await enlace.count()
                print(f"   Fallback citaconsular: {count} enlace(s)")

            if count == 0:
                raise Exception("No se encontró el enlace de reservar cita")

            # Escuchar nueva pestaña ANTES de hacer clic
            async with context.expect_page(timeout=30_000) as nueva_pagina_info:
                await enlace.first.click()

            cita_page = await nueva_pagina_info.value

            # ¡IMPORTANTE! Registrar handler de dialog en la NUEVA página
            cita_page.on("dialog", handle_dialog)

            print(f"   ✓ Pestaña nueva: {cita_page.url}")

            # Esperar a que cargue
            await cita_page.wait_for_load_state("domcontentloaded", timeout=60_000)
            await cita_page.wait_for_timeout(5_000)

            # ─── PASO 3: popup Welcome/Bienvenido ───
            # Es un alert() JS → handle_dialog ya lo acepta automáticamente
            # Pero esperamos un poco para que se procese
            print("🟡 Paso 3: esperando popup Welcome/Bienvenido ...")
            await cita_page.wait_for_timeout(3_000)
            print(f"   URL ahora: {cita_page.url}")

            # Captura de debug para ver qué hay
            await cita_page.screenshot(path="debug_paso3.png", full_page=True)
            print(f"   📸 Debug paso 3: {Path('debug_paso3.png').stat().st_size} bytes")

            # ─── PASO 4: clic en "Continue / Continuar" ───
            print("🟢 Paso 4: buscando botón Continue/Continuar ...")

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
                '[class*="continuar"]',
            ]

            boton_encontrado = False
            for selector in selectores:
                try:
                    loc = cita_page.locator(selector).first
                    if await loc.count() > 0 and await loc.is_visible():
                        print(f"   ✓ Encontrado: {selector}")
                        await loc.click(timeout=10_000)
                        boton_encontrado = True
                        break
                except Exception:
                    pass

            if not boton_encontrado:
                # Último intento: buscar cualquier elemento visible con texto "Continuar"
                print("   Intentando búsqueda amplia de texto Continuar...")
                try:
                    continuar_text = cita_page.get_by_text("Continuar", exact=False)
                    if await continuar_text.count() > 0:
                        print(f"   ✓ Encontrado por get_by_text ({await continuar_text.count()} resultados)")
                        await continuar_text.first.click(timeout=10_000)
                        boton_encontrado = True
                except Exception as e:
                    print(f"   ✗ get_by_text falló: {e}")

            if not boton_encontrado:
                # Verificar si ya estamos en el calendario
                contenido_check = await cita_page.content()
                if "Hueco libre" in contenido_check or "Huecos libres" in contenido_check:
                    print("   ✓ Ya estamos en el calendario sin necesidad del botón")
                elif "Cambiar de" in contenido_check or "datetime" in cita_page.url:
                    print("   ✓ Parece que estamos en la vista del calendario")
                else:
                    await cita_page.screenshot(path=str(CAPTURA_ERROR), full_page=True)
                    enviar_telegram_foto(
                        CAPTURA_ERROR,
                        "⚠️ <b>Bot no encontró el botón Continuar</b>\n\n"
                        "Revisa la captura adjunta para ver en qué se quedó.",
                    )
                    return

            # ─── PASO 5: leer el calendario ───
            print("📅 Paso 5: esperando calendario ...")
            await cita_page.wait_for_timeout(5_000)

            try:
                await cita_page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                pass

            await cita_page.wait_for_timeout(2_000)
            contenido = await cita_page.content()
            await cita_page.screenshot(path=str(CAPTURA), full_page=True)
            print(f"   📸 Captura calendario: {CAPTURA.stat().st_size} bytes")
            print(f"   URL final: {cita_page.url}")

            # Cloudflare check
            if "Verificación de seguridad" in contenido or "challenge-platform" in contenido:
                print("🛑 Cloudflare detectado")
                enviar_telegram_foto(
                    CAPTURA,
                    "🛑 <b>Cloudflare bloqueando el bot</b>\n\n"
                    "Habrá que usar proxy o ejecutar desde tu PC.",
                )
                return

            # Detectar huecos libres
            tiene_hueco = "Hueco libre" in contenido or "Huecos libres" in contenido

            if tiene_hueco:
                num_singular = contenido.count("Hueco libre")
                num_plural = contenido.count("Huecos libres")
                total = num_singular + num_plural

                estado_actual = f"CITAS:{total}"
                estado_anterior = leer_estado()

                if estado_actual != estado_anterior:
                    print(f"🎉 ¡Citas detectadas! ({total} bloques)")
                    enviar_telegram_foto(
                        CAPTURA,
                        f"🎉 <b>¡HAY CITAS DISPONIBLES!</b>\n\n"
                        f"📌 Visado de Estudios - Consulado La Habana\n"
                        f"🟢 {total} bloques con huecos libres\n\n"
                        f"⚡ Reserva ya antes de que las cojan",
                    )
                    guardar_estado(estado_actual)
                else:
                    print(f"⏸ Citas ya notificadas ({total} bloques).")
            else:
                print("💤 Sin citas disponibles.")
                if leer_estado().startswith("CITAS:"):
                    enviar_telegram(
                        "💤 <b>Las citas ya no están disponibles</b>\n\n"
                        "Se han agotado. Seguiré vigilando."
                    )
                    guardar_estado("SIN_CITAS")

        except Exception as e:
            print(f"❌ Error: {e}")
            target = cita_page if cita_page else page
            try:
                await target.screenshot(path=str(CAPTURA_ERROR), full_page=True)
            except Exception:
                pass
            enviar_telegram_foto(
                CAPTURA_ERROR,
                f"⚠️ <b>Error en bot visados</b>\n\n<code>{str(e)[:300]}</code>",
            )
        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    if not TG_TOKEN or not TG_CHAT:
        print("❌ Faltan secrets TELEGRAM_BOT_TOKEN_VISADO y TELEGRAM_CHAT_ID_VISADO")
        sys.exit(1)
    asyncio.run(comprobar_citas())
