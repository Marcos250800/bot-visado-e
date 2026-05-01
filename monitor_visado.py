"""
Monitor de citas - Visado Nacional de Estudios
Consulado General de España en La Habana (Cuba)

v7 FINAL: Llamada directa a la API de Bookitit
- Sin navegador, sin Playwright, sin Cloudflare
- Consulta el endpoint datetime/ que devuelve fechas con huecos
- state=1 + times con freeSlots = HAY CITAS
- state=0 + times vacío = SIN CITAS
"""

import os
import sys
import json
import re
import requests
from datetime import datetime, timedelta

# ===== Configuración =====
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN_VISADO")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID_VISADO")

PUBLIC_KEY = "2ac9fec388c03f817a21771d720ff4261"
SERVICE_ID = "bkt873070"
AGENDA_ID = "bkt285318"

API_URL = "https://www.citaconsular.es/onlinebookings/datetime/"
ESTADO_FILE = "ultimo_estado.txt"


def log(msg):
    print(f"[{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] {msg}", flush=True)


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
        log(f"✅ Telegram: {r.status_code}")
    except Exception as e:
        log(f"⚠ Error Telegram: {e}")


def leer_estado():
    try:
        with open(ESTADO_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def guardar_estado(valor):
    with open(ESTADO_FILE, "w") as f:
        f.write(valor)


def consultar_api():
    """Llama al endpoint datetime/ y devuelve los Slots parseados."""
    hoy = datetime.now()
    inicio = hoy.strftime("%Y-%m-%d")
    fin = (hoy + timedelta(days=60)).strftime("%Y-%m-%d")

    params = {
        "callback": "cb",
        "type": "default",
        "publickey": PUBLIC_KEY,
        "lang": "es",
        "services[]": SERVICE_ID,
        "agendas[]": AGENDA_ID,
        "version": "4",
        "src": f"https://www.citaconsular.es/es/hosteds/widgetdefault/{PUBLIC_KEY}/{SERVICE_ID}",
        "srvsrc": "https://www.citaconsular.es",
        "start": inicio,
        "end": fin,
        "selectedPeople": "1",
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://www.citaconsular.es/",
        "Accept": "*/*",
    }

    log(f"📡 Consultando API: {inicio} → {fin}")
    r = requests.get(API_URL, params=params, headers=headers, timeout=20)
    log(f"  Status: {r.status_code} | {len(r.text)} chars")

    if r.status_code != 200:
        raise Exception(f"API devolvió status {r.status_code}: {r.text[:200]}")

    # Extraer JSON del wrapper JSONP: cb({...});
    texto = r.text.strip()
    match = re.search(r'cb\((.*)\);?\s*$', texto, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    # Si no tiene wrapper, intentar parsear directo
    return json.loads(texto)


def analizar_slots(datos):
    """
    Analiza los Slots devueltos por la API.
    Devuelve lista de fechas con citas disponibles.
    Cada elemento: {"fecha": "2026-05-07", "horas": [{"time": "09:30", "freeSlots": 2}, ...]}
    """
    fechas_con_citas = []

    slots = datos.get("Slots", [])
    for slot in slots:
        fecha = slot.get("date", "")
        state = slot.get("state", 0)
        times = slot.get("times", {})

        # state=1 y times con contenido = HAY CITAS
        if state == 1 and isinstance(times, dict) and len(times) > 0:
            horas = []
            total_huecos = 0
            for minuto, info in times.items():
                hora = info.get("time", "??:??")
                free = info.get("freeSlots", 0)
                horas.append({"time": hora, "freeSlots": free})
                total_huecos += free

            if horas:
                fechas_con_citas.append({
                    "fecha": fecha,
                    "horas": sorted(horas, key=lambda x: x["time"]),
                    "total_huecos": total_huecos,
                })

    return fechas_con_citas


def formatear_mensaje(fechas_con_citas):
    """Formatea el mensaje de Telegram con las fechas y horas disponibles."""
    total_fechas = len(fechas_con_citas)
    total_huecos = sum(f["total_huecos"] for f in fechas_con_citas)

    msg = (
        "🚨 <b>¡¡CITAS DISPONIBLES!!</b> 🚨\n\n"
        "📌 <b>Visado de Estudios</b>\n"
        "🏛 Consulado de España en La Habana\n\n"
        f"📅 {total_fechas} fecha(s) con {total_huecos} huecos libres:\n\n"
    )

    for f in fechas_con_citas[:5]:  # Máximo 5 fechas para no saturar
        # Formatear fecha bonita
        try:
            dt = datetime.strptime(f["fecha"], "%Y-%m-%d")
            fecha_bonita = dt.strftime("%A %d/%m/%Y").capitalize()
        except Exception:
            fecha_bonita = f["fecha"]

        primera = f["horas"][0]["time"]
        ultima = f["horas"][-1]["time"]

        msg += (
            f"  📆 <b>{fecha_bonita}</b>\n"
            f"     ⏰ {primera} - {ultima} ({f['total_huecos']} huecos)\n\n"
        )

    if total_fechas > 5:
        msg += f"  ... y {total_fechas - 5} fecha(s) más\n\n"

    msg += (
        "⚡ <b>Reserva YA antes de que las cojan</b>\n\n"
        f"⏰ {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )

    return msg


def main():
    log("🚀 Monitor de Visado de Estudios — API directa (sin navegador)")

    try:
        datos = consultar_api()
    except Exception as e:
        log(f"❌ Error consultando API: {e}")
        enviar_telegram(f"⚠️ <b>Error API</b>\n\n<code>{str(e)[:300]}</code>")
        return

    fechas_con_citas = analizar_slots(datos)

    if fechas_con_citas:
        # Crear un hash del estado actual para no repetir notificaciones
        estado_actual = "|".join(
            f"{f['fecha']}:{f['total_huecos']}" for f in fechas_con_citas
        )
        estado_anterior = leer_estado()

        if estado_actual != estado_anterior:
            log(f"🎉 ¡CITAS DETECTADAS! {len(fechas_con_citas)} fechas")
            for f in fechas_con_citas:
                log(f"  📆 {f['fecha']}: {f['total_huecos']} huecos ({len(f['horas'])} horarios)")

            mensaje = formatear_mensaje(fechas_con_citas)
            enviar_telegram(mensaje)
            guardar_estado(estado_actual)
        else:
            log(f"⏸ Ya notificado ({len(fechas_con_citas)} fechas, sin cambios)")
    else:
        log("💤 Sin citas disponibles")
        if leer_estado() and not leer_estado().startswith("SIN"):
            enviar_telegram(
                f"💤 <b>Citas agotadas</b>\n"
                f"⏰ {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
                f"Seguiré vigilando."
            )
        guardar_estado("SIN_CITAS")

    log("✅ Finalizado")


if __name__ == "__main__":
    if not TG_TOKEN or not TG_CHAT:
        log("❌ Faltan secrets TELEGRAM_BOT_TOKEN_VISADO y TELEGRAM_CHAT_ID_VISADO")
        sys.exit(1)
    main()
