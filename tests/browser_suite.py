"""Smoke E2E sull'app avviata con tests/browser_app.py e dati temporanei.

STRATO_BROWSER_URL, STRATO_BROWSER_OUTPUT e STRATO_BROWSER_EXECUTABLE sono opzionali.
Avvio: python tests/browser_suite.py
"""
import os
import re
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, expect, sync_playwright
import trimesh


URL = os.environ.get("STRATO_BROWSER_URL", "http://127.0.0.1:8511")
OUTPUT = Path(os.environ.get("STRATO_BROWSER_OUTPUT", "/tmp/strato-browser-results"))


def verifica_maiuscole(elementi):
    # Controlla il testo renderizzato: un figlio può sovrascrivere lo stile del widget.
    risultati = elementi.evaluate_all("""elements => elements.flatMap(root =>
        [root, ...root.querySelectorAll('*')].filter(el =>
            el.getClientRects().length && [...el.childNodes].some(node =>
                node.nodeType === Node.TEXT_NODE && node.textContent.trim()))
            .map(el => ({text: el.textContent.trim(), transform: getComputedStyle(el).textTransform})))""")
    assert risultati, "Nessun testo visibile da verificare"
    assert all(r["transform"] == "capitalize" for r in risultati), risultati


def verifica_istruzioni_nascoste(page):
    expect(page.locator('[data-testid="InputInstructions"]:visible')).to_have_count(0)


def verifica_pagina(page, nome):
    expect(page.locator('.stApp')).to_have_attribute('data-test-script-state', 'notRunning')
    expect(page.locator('[data-stale="true"]')).to_have_count(0)
    page.evaluate("document.fonts.ready")
    page.wait_for_function("""() => Array.from(document.images)
        .filter(img => img.getClientRects().length)
        .every(img => img.complete && img.naturalWidth > 0)""", timeout=15000)
    expect(page.locator('[data-testid="stException"]')).to_have_count(0)
    verifica_istruzioni_nascoste(page)
    assert page.locator(".stApp").evaluate(
        "el => getComputedStyle(el).backgroundColor") == "rgb(248, 249, 250)"
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), nome
    sezione = page.locator('.sezione-intestazione:visible')
    if sezione.count():
        testata = page.locator('[class*="st-key-header_"]:visible').first.bounding_box()
        titolo_sezione = sezione.bounding_box()
        distanza = titolo_sezione['y'] - (testata['y'] + testata['height'])
        attesa = 26 if page.viewport_size['width'] <= 600 else 20
        assert abs(distanza - attesa) <= 1, (nome, distanza, attesa)
    if page.viewport_size['width'] <= 600:
        for modulo in ('.st-key-wizard_main', '.st-key-diario_form', '.st-key-bobine_form',
                       '.st-key-impostazioni_ai'):
            righe = page.locator(f'{modulo}:visible [data-testid="stHorizontalBlock"]')
            assert righe.evaluate_all("elements => elements.every(el => getComputedStyle(el).flexDirection === 'column')"), nome
    titolo = page.locator("h1:visible").first
    expect(titolo).to_be_visible()
    assert "Plus Jakarta Sans" in titolo.evaluate("el => getComputedStyle(el).fontFamily")
    expect(titolo).to_have_css("font-size", "28px")
    expect(titolo).to_have_css("font-weight", "700")
    note = page.locator('[data-testid="stCaptionContainer"] p:visible')
    assert note.evaluate_all("es => es.every(el => getComputedStyle(el).fontSize === '12px')")
    if nome.endswith("-impostazioni"):
        percorsi = page.get_by_text("Percorsi dello slicer", exact=True)
        percorsi.click()
        valori = page.locator(".strato-technical code")
        expect(valori).to_have_count(2)
        expect(valori.first).to_be_visible()
        assert valori.evaluate_all("""es => es.every(el => {
            const s = getComputedStyle(el);
            return s.fontFamily.includes('monospace') && s.fontSize === '12px'
                && s.fontWeight === '400' && el.parentElement.scrollWidth <= el.parentElement.clientWidth + 1;
        })""")
        assert percorsi.evaluate("el => getComputedStyle(el).fontSize") == "14px"
        page.screenshot(path=str(OUTPUT / f"{nome}-percorsi.png"), full_page=True)
        percorsi.click()
    page.screenshot(path=str(OUTPUT / f"{nome}.png"), full_page=True)
    principale = page.locator('[data-testid="stMain"]')
    if principale.evaluate("el => el.scrollHeight > el.clientHeight + 1"):
        principale.evaluate("el => el.scrollTop = el.scrollHeight")
        if page.viewport_size['width'] > 900:
            expect(page.get_by_role('link', name='STRATO — Torna alla home')).to_be_in_viewport()
        else:
            expect(page.get_by_role('link', name='Analisi', exact=True)).to_be_in_viewport()
        page.screenshot(path=str(OUTPUT / f"{nome}-fondo.png"))
        principale.evaluate("el => el.scrollTop = 0")


def verifica_url_e_refresh(browser):
    pagina = browser.new_page()
    for larghezza in (1500, 390):
        pagina.set_viewport_size({"width": larghezza, "height": 1000})
        for nome, percorso in (("Analisi", ""), ("Diario", "diario"), ("Bobine", "bobine"),
                               ("Storico", "storico"), ("Impostazioni", "impostazioni")):
            pagina.goto(f"{URL.rstrip('/')}/{percorso}")
            attivo = pagina.locator(".st-key-nav_attiva").get_by_role("link", name=nome, exact=True)
            expect(attivo).to_be_visible()
            pagina.reload()
            expect(attivo).to_be_visible()
            expect(pagina.locator('[data-testid="stException"]')).to_have_count(0)
            expect(pagina.locator('.st-key-modello_box')).to_have_count(1 if nome == "Analisi" else 0)
            assert pagina.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        pagina.get_by_role("link", name="Diario", exact=True).click()
        expect(pagina).to_have_url(re.compile("/diario$"))
        pagina.get_by_role("link", name="Bobine", exact=True).click()
        expect(pagina).to_have_url(re.compile("/bobine$"))
        pagina.go_back()
        expect(pagina.locator(".st-key-nav_attiva").get_by_role("link", name="Diario", exact=True)).to_be_visible()
        pagina.go_forward()
        expect(pagina.locator(".st-key-nav_attiva").get_by_role("link", name="Bobine", exact=True)).to_be_visible()
    pagina.close()


def principale():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    modello = OUTPUT / "staffa-prova.stl"
    trimesh.creation.box(extents=[20, 10, 5]).export(modello)
    with sync_playwright() as p:
        opzioni = {"headless": True}
        if eseguibile := os.environ.get("STRATO_BROWSER_EXECUTABLE"):
            opzioni["executable_path"] = eseguibile
        browser = p.chromium.launch(**opzioni)
        verifica_url_e_refresh(browser)
        page = browser.new_page(viewport={"width": 1500, "height": 1320})
        page.set_default_timeout(60000)
        page.goto(URL)
        expect(page.get_by_role("heading", name="Carica il modello 3D")).to_be_visible()
        expect(page.get_by_role("button", name="Continua a Utilizzo →")).to_be_disabled()
        verifica_pagina(page, "desktop-caricamento")

        page.locator('input[type="file"]').first.set_input_files(modello)
        expect(page.get_by_role("button", name="Continua a Utilizzo →")).to_be_enabled()
        verifica_pagina(page, "desktop-caricato")
        page.get_by_role("button", name="Continua a Utilizzo →").click()
        campo_scopo = page.get_by_role("textbox", name="A cosa serve, dove va montato")
        campo_scopo.fill("Staffa per il motore · prova browser")
        verifica_istruzioni_nascoste(page)
        page.get_by_role("textbox", name="Altro (lato da tenere bello, problemi avuti, ecc.)").fill("Nota browser")
        verifica_istruzioni_nascoste(page)
        page.get_by_role("button", name="Continua a Priorità →").click()
        expect(page.get_by_role("radio", name="Poco materiale", exact=False)).to_be_visible()
        page.locator('[data-testid="stRadioOption"]').filter(has_text="Poco materiale").click()
        verifica_maiuscole(page.locator('[data-testid="stRadioOption"] p'))
        verifica_pagina(page, "desktop-priorita")
        page.get_by_role("button", name="Vai al riepilogo →").click()
        expect(page.get_by_text("Staffa per il motore · prova browser", exact=True)).to_be_visible()
        verifica_pagina(page, "desktop-riepilogo")
        page.get_by_role("button", name="← Indietro", exact=True).click()
        expect(page.get_by_role("radio", name="Poco materiale", exact=False)).to_be_checked()
        page.get_by_role("button", name="← Indietro", exact=True).click()
        expect(campo_scopo).to_have_value("Staffa per il motore · prova browser")
        for larghezza, altezza in ((1500, 1320), (390, 844)):
            page.set_viewport_size({"width": larghezza, "height": altezza})
            valori_select = page.locator('[data-testid="stSelectbox"] input:visible')
            assert valori_select.count() > 0
            assert valori_select.evaluate_all("elements => elements.every(el => el.value && getComputedStyle(el).textTransform === 'capitalize')")
            verifica_maiuscole(page.locator('[data-testid="stMultiSelect"] :is([data-tag], [data-baseweb="tag"]) span[title]'))
            verifica_maiuscole(page.locator('[data-testid="stCheckbox"] p'))
            page.get_by_role("combobox", name="Tipo di pezzo", exact=True).click()
            expect(page.get_by_role("option", name="estetico", exact=True)).to_be_visible()
            verifica_maiuscole(page.get_by_role("option"))
            page.keyboard.press("Escape")
            page.get_by_role("combobox", name="Condizioni d'uso", exact=True).press("ArrowDown")
            expect(page.get_by_role("option", name="caldo oltre 50 °C", exact=True)).to_be_visible()
            verifica_maiuscole(page.get_by_role("option"))
            page.keyboard.press("Escape")
        page.set_viewport_size({"width": 1500, "height": 1320})
        verifica_pagina(page, "desktop-utilizzo")

        for larghezza, altezza in ((1500, 1320), (768, 1024), (390, 844)):
            page.set_viewport_size({"width": larghezza, "height": altezza})
            for nome in ("Analisi", "Diario", "Bobine", "Storico", "Impostazioni"):
                page.get_by_role("link", name=nome, exact=True).click()
                expect(page.locator(".st-key-nav_attiva").get_by_role("link", name=nome, exact=True)).to_be_visible()
                verifica_pagina(page, f"{larghezza}-{nome.lower()}")
                if nome != "Analisi":
                    expect(page).to_have_url(re.compile(f"/{nome.lower()}$"))


        page.set_viewport_size({"width": 1500, "height": 1320})
        page.get_by_role("link", name="Diario", exact=True).click()
        page.get_by_role("textbox", name="Pezzo", exact=True).fill("Stampa browser")
        verifica_istruzioni_nascoste(page)
        page.get_by_role("textbox", name="Com’è andata", exact=True).fill("Ultimo campo prima di salvare")
        verifica_istruzioni_nascoste(page)
        page.get_by_role("button", name="Salva nel diario", exact=True).click()
        expect(page.get_by_text("Salvato.", exact=True)).to_be_visible()
        expect(page.get_by_text("Stampa browser", exact=False).first).to_be_visible()
        verifica_pagina(page, "desktop-diario-salvato")

        page.get_by_role("link", name="Bobine", exact=True).click()
        page.get_by_role("textbox", name="Nome bobina", exact=True).fill("Bobina browser")
        page.get_by_role("textbox", name="Marca", exact=True).fill("Ultimo campo")
        page.get_by_role("button", name="Aggiungi bobina", exact=True).click()
        expect(page.get_by_role("button", name="Sottrai dal residuo", exact=True)).to_be_visible()
        grammi = page.get_by_label("Grammi consumati", exact=True)
        expect(grammi).to_have_value("0")
        grammi.fill("25")
        expect(page.locator('[data-testid="stNumberInput"] [data-testid="InputInstructions"]:visible')).to_have_count(0)
        page.get_by_role("button", name="Sottrai dal residuo", exact=True).click()
        verifica_pagina(page, "desktop-bobine-salvata")

        page.get_by_role("link", name="Analisi", exact=True).click()
        page.get_by_role("button", name="01 · Pezzo", exact=True).click()
        page.get_by_role("button", name="Rimuovi modello", exact=True).click()
        expect(page.get_by_role("button", name="Continua a Utilizzo →")).to_be_disabled()
        expect(page.get_by_role("button", name="02 · Utilizzo", exact=True)).to_be_disabled()
        verifica_pagina(page, "desktop-modello-rimosso")

        # Calcolo geometrico reale; lo slicing dipende dallo slicer locale.
        page.locator('input[type="file"]').first.set_input_files(modello)
        page.get_by_role("button", name="Continua a Utilizzo →").click()
        page.get_by_role("button", name="Continua a Priorità →").click()
        page.get_by_role("button", name="Vai al riepilogo →").click()
        page.get_by_role("button", name=re.compile(r"^(Avvia analisi →|Rifai l'analisi da capo)$")).click()
        caricamento = page.locator('.st-key-analisi_avanzamento')
        try:
            caricamento.wait_for(timeout=10000)
        except PlaywrightTimeoutError:
            expect(page.locator('.st-key-risultati_pagine')).to_be_visible(timeout=180000)
        else:
            verifica_pagina(page, "desktop-elaborazione")
        expect(page.locator('.st-key-risultati_pagine')).to_be_visible(timeout=180000)
        for nome in ("Risultato", "Orientamenti", "Varianti", "Controlli", "Consiglio e apprendimento"):
            page.get_by_role("tab", name=nome, exact=True).click()
            verifica_pagina(page, f"desktop-risultati-{nome.lower().replace(' ', '-')}")
        page.set_viewport_size({"width": 390, "height": 844})
        page.get_by_role("tab", name="Risultato", exact=True).click()
        verifica_pagina(page, "390-risultato")
        page.locator('[data-testid="stMain"]').evaluate("el => el.scrollTop = 0")
        page.get_by_role('link', name='STRATO — Torna alla home').click()
        expect(page.get_by_role('heading', name='Carica il modello 3D')).to_be_visible()
        expect(page.get_by_role('button', name='Continua a Utilizzo →')).to_be_disabled()
        browser.close()
    print(f"E2E completato. Screenshot: {OUTPUT}")


if __name__ == "__main__":
    principale()
