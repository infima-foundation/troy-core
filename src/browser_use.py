# ─────────────────────────────────────────────────
# TROY — Módulo de Browser Use
# Infima Foundation A.C.
# ─────────────────────────────────────────────────

import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from playwright.async_api import async_playwright

async def navegar_y_extraer(url: str) -> str:
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.goto(url, wait_until="networkidle", timeout=20000)
            await page.wait_for_timeout(4000)

            texto = await page.evaluate("""() => {
                const elementos = document.querySelectorAll(
                    'p, h1, h2, h3, h4, li, td, th, span, div'
                );
                const textos = [];
                for (const el of elementos) {
                    const t = el.innerText?.trim();
                    if (t && t.length > 20 && t.length < 500) {
                        textos.push(t);
                    }
                }
                return [...new Set(textos)].slice(0, 80).join('\\n');
            }""")

            await browser.close()
            return texto[:4000] if texto else "No se pudo extraer contenido."

    except Exception as e:
        return f"Error navegando {url}: {e}"

async def buscar_en_google(query: str) -> str:
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)

            resultados = await page.evaluate("""() => {
                const items = document.querySelectorAll('div.g');
                const datos = [];
                for (const item of items) {
                    const titulo = item.querySelector('h3')?.innerText;
                    const descripcion = item.querySelector('div[data-sncf]')?.innerText
                                     || item.querySelector('.VwiC3b')?.innerText;
                    const enlace = item.querySelector('a')?.href;
                    if (titulo && enlace) {
                        datos.push({ titulo, descripcion, enlace });
                    }
                }
                return datos.slice(0, 5);
            }""")

            await browser.close()

            if not resultados:
                return "No se encontraron resultados."

            texto = ""
            for r in resultados:
                texto += f"📌 {r.get('titulo', '')}\n"
                if r.get('descripcion'):
                    texto += f"   {r['descripcion'][:200]}\n"
                texto += f"   🔗 {r.get('enlace', '')}\n\n"

            return texto.strip()

    except Exception as e:
        return f"Error buscando en Google: {e}"

async def buscar_reciente(query: str) -> str:
    """
    Busca información actual en Google via Playwright.
    Útil para noticias, resultados, precios y eventos recientes.
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            url = f"https://www.google.com/search?q={query.replace(' ', '+')}&hl=es"
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)

            # Extraer el bloque de resultado deportivo de Google
            contenido = await page.evaluate("""() => {
                const textos = [];
                // Bloque de marcador de Google
                const bloques = document.querySelectorAll(
                    '[data-attrid], .imso-hov, .imso_mh, ' +
                    '.BNeawe, .kno-rdesc, .LGOjhe, ' +
                    'div[role="heading"], .card-section'
                );
                for (const b of bloques) {
                    const t = b.innerText?.trim();
                    if (t && t.length > 2 && t.length < 300) {
                        textos.push(t);
                    }
                }
                // También extraer texto general
                const general = document.querySelectorAll('div.g, .BNeawe');
                for (const g of general) {
                    const t = g.innerText?.trim();
                    if (t && t.length > 10 && t.length < 400) {
                        textos.push(t);
                    }
                }
                return [...new Set(textos)].slice(0, 30).join('\\n');
            }""")

            await browser.close()
            return contenido[:3000] if contenido else ""

    except Exception as e:
        return f"Error buscando resultado: {e}"

def navegar(url: str) -> str:
    return asyncio.run(navegar_y_extraer(url))

def buscar_google(query: str) -> str:
    return asyncio.run(buscar_en_google(query))

def buscar_resultado(query: str) -> str:
    return asyncio.run(buscar_reciente(query))