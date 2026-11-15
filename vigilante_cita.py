import os
import re

import requests
from playwright.sync_api import sync_playwright

URL = "https://www.juntadeandalucia.es/justicia/citaprevia/?idCliente=4"
OFICINA = "REGISTRO CIVIL EXCLUSIVO DE MÁLAGA"
TRAMITE = os.environ["TRAMITE"]


def avisar(titulo, mensaje):
    sid = os.environ["TWILIO_SID"]
    requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        auth=(sid, os.environ["TWILIO_TOKEN"]),
        data={
            "From": os.environ["TWILIO_FROM"],
            "To": os.environ["MI_MOVIL"],
            "Body": f"{titulo} {mensaje}",
        },
        timeout=15,
    )


def listar_opciones(page):
    for sel in page.locator("select").all():
        if sel.is_visible():
            ops = [(o.inner_text() or "").strip() for o in sel.locator("option").all()]
            print("Opciones disponibles:", ops)


def elegir_opcion(page, texto):
    texto_l = texto.lower()
    for sel in page.locator("select").all():
        if not sel.is_visible():
            continue
        for opt in sel.locator("option").all():
            t = (opt.inner_text() or "").strip()
            if texto_l in t.lower():
                sel.select_option(label=t)
                page.wait_for_timeout(2500)
                return True
    return False


def hay_citas():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle", timeout=60000)

        if not elegir_opcion(page, OFICINA):
            raise RuntimeError(f"No encuentro la oficina '{OFICINA}'")
        listar_opciones(page)
        if not elegir_opcion(page, TRAMITE):
            raise RuntimeError(f"No encuentro el trámite '{TRAMITE}'")

        try:
            campo = page.get_by_label(re.compile("solicitantes", re.I)).first
            if campo.evaluate("e => e.tagName") == "SELECT":
                campo.select_option(label="1")
            else:
                campo.fill("1")
        except Exception:
            pass

        page.get_by_role(
            "button", name=re.compile(r"siguiente|continuar|aceptar", re.I)
        ).first.click()
        page.wait_for_timeout(3000)

        page.screenshot(path="paso2.png", full_page=True)
        open("paso2.html", "w", encoding="utf-8").write(page.content())

        dias = page.locator(
            ".ui-datepicker-calendar td:not(.ui-state-disabled):not(.ui-datepicker-unselectable) a"
        ).count()
        if dias > 0:
            return True, f"{dias} día(s) con hueco disponible"

        cuerpo = page.inner_text("body").lower()
        if re.search(r"no hay (citas|disponibilidad|huecos)|no existen|sin disponibilidad|no dispone", cuerpo):
            return False, "sin citas"
        if re.search(r"\b\d{1,2}:\d{2}\b", cuerpo) and "paso 2" in cuerpo:
            return True, "parece que hay horas disponibles"
        return False, "sin señales de disponibilidad"


ok, detalle = hay_citas()
print(detalle)
if ok:
    avisar("¡HAY CITA DISPONIBLE!", f"{detalle}. Entra ya: {URL}")
