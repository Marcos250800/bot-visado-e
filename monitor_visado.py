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
Versión optimista: Playwright con stealth + flujo de 5 pasos.
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
    """Envía un mensaje de texto al chat configurado."""
    if not TG_TOKEN or not TG_CHAT:
        print("⚠️ Faltan secrets de Telegram, no se puede notificar.")
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
        print(f"❌ Error enviando texto a Telegram: {e}")


def enviar_telegram_foto(ruta: Path, caption: str) -> None:
    """Envía una imagen con texto al chat."""
    if not TG_TOKEN or not TG_CHAT:
        return
    if not ruta.exists():
        print(f"⚠️ No existe la captura {ruta}, envío solo texto.")
        enviar_telegram(caption)
        return
    try:
        with open(ruta, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                data={
                    "chat_id": TG_CHAT,
                    "caption": caption,
                    "parse_mode": "HTML",
                },
                files={"photo": f},
                timeout=30,
            )
        print(f"📤 Telegram foto: {r.status_code}")
    except Exception as e:
        print(f"❌ Error enviando foto a Telegram: {e}")


# ===== Estado (para no repetir el mismo aviso) =====
def leer_estado() -> str:
    if ESTADO_FILE.exists():
        return ESTADO_FILE.read_text(encoding="utf-8").strip()
    return ""


def guardar_estado(valor: str) -> None:
    ESTADO_FILE.write_text(valor, encoding="utf-8")


# ===== Lógica principal =====
async def comprobar_citas() -> None:
    async with async_playwright() as p:
        # User agent realista de Chrome en Windows
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

        # Inyectar script anti-detección antes de cualquier navegación
        await context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['es-ES', 'es', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = { runtime: {} };
            """
        )

        page = await context.new_page()

        try:
            # ─── PASO 1: abrir página del Ministerio ───
            print("📄 Paso 1: abriendo exteriores.gob.es ...")
            await page.goto(URL_MINISTERIO, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(2_000)

            # ─── PASO 2: clic en "Reservar cita de visado estudio" ───
            print("🔗 Paso 2: buscando enlace 'Reservar cita de visado estudio' ...")
            enlace = page.get_by_role("link", name="Reservar cita de visado estudio")

            # Esa página abre el enlace en pestaña nueva → escuchamos popup
            async with context.expect_page(timeout=30_000) as nueva_pagina_info:
                await enlace.click()
            cita_page = await nueva_pagina_info.value
            await cita_page.wait_for_load_state("domcontentloaded", timeout=60_000)
            await cita_page.wait_for_timeout(3_000)
            print(f"   ✓ Pestaña nueva: {cita_page.url}")

            # ─── PASO 3: aceptar el popup "Welcome / Bienvenido" ───
            # Es un alert/dialog del navegador → se maneja distinto si es JS dialog,
            # pero en este caso es un modal HTML normal con botón "Aceptar".
            print("🟡 Paso 3: aceptando popup Welcome/Bienvenido ...")
            try:
                # JS dialog (alert)
                cita_page.on("dialog", lambda d: asyncio.create_task(d.accept()))
                await cita_page.wait_for_timeout(2_000)
                # Por si es un modal HTML normal:
                boton_aceptar = cita_page.get_by_role("button", name="Aceptar")
                if await boton_aceptar.count() > 0:
                    await boton_aceptar.first.click()
                    await cita_page.wait_for_timeout(2_000)
            except Exception as e:
                print(f"   (popup no encontrado o ya cerrado: {e})")

            # ─── PASO 4: clic en "Continue / Continuar" ───
            print("🟢 Paso 4: pulsando Continue/Continuar ...")
            boton_continuar = cita_page.get_by_role(
                "button", name="Continue / Continuar"
            )
            if await boton_continuar.count() == 0:
                # Fallback: buscar por texto parcial
                boton_continuar = cita_page.locator("text=/Continue.*Continuar/i")
            await boton_continuar.first.click()
            await cita_page.wait_for_timeout(5_000)

            # ─── PASO 5: leer el calendario ───
            print("📅 Paso 5: analizando calendario ...")
            await cita_page.wait_for_load_state("networkidle", timeout=30_000)
            await cita_page.wait_for_timeout(2_000)

            contenido = await cita_page.content()
            await cita_page.screenshot(path=str(CAPTURA), full_page=True)

            # Detectar Cloudflare (escenario pesimista)
            if "Verificación de seguridad" in contenido or "Cloudflare" in contenido:
                print("🛑 Cloudflare bloqueando — escenario pesimista.")
                await cita_page.screenshot(path=str(CAPTURA_ERROR), full_page=True)
                enviar_telegram_foto(
                    CAPTURA_ERROR,
                    "🛑 <b>Cloudflare bloqueando el bot</b>\n\n"
                    "GitHub Actions ha sido detectado como datacenter. "
                    "Habrá que usar proxy residencial o ejecutar desde tu PC.",
                )
                return

            # Detectar huecos libres
            tiene_hueco = (
                "Hueco libre" in contenido or "Huecos libres" in contenido
            )

            if tiene_hueco:
                # Contar huecos aproximados
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
                        f"🟢 Detectados {total} bloques con huecos libres\n\n"
                        f"⚡ <b>Reserva ya antes de que las cojan:</b>\n"
                        f'<a href="{URL_MINISTERIO}">Ir a la página del Ministerio</a>',
                    )
                    guardar_estado(estado_actual)
                else:
                    print(f"⏸ Citas ya notificadas anteriormente ({total} bloques).")
            else:
                print("💤 Sin citas disponibles.")
                # Si antes había y ahora no, resetear estado
                if leer_estado().startswith("CITAS:"):
                    guardar_estado("SIN_CITAS")

        except Exception as e:
            print(f"❌ Error durante la comprobación: {e}")
            try:
                await page.screenshot(path=str(CAPTURA_ERROR), full_page=True)
            except Exception:
                pass
            enviar_telegram_foto(
                CAPTURA_ERROR,
                f"⚠️ <b>Error en el bot de visados</b>\n\n<code>{str(e)[:300]}</code>",
            )
        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    if not TG_TOKEN or not TG_CHAT:
        print("❌ Faltan secrets TELEGRAM_BOT_TOKEN_VISADO y TELEGRAM_CHAT_ID_VISADO")
        sys.exit(1)
    asyncio.run(comprobar_citas())
