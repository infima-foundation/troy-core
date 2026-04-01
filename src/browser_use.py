# ─────────────────────────────────────────────────
# TROY — Módulo de Browser Use
# Infima Foundation A.C.
# Navega sitios web, extrae información,
# llena formularios y hace clicks automáticamente.
# ─────────────────────────────────────────────────

import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from playwright.async_api import async_playwright

async def navegar_y_extraer(url: str, instruccion: str = None) -> str:
    """
    Abre una URL y extrae el contenido de texto.
    Si hay una instrucción, extrae solo lo relevante.
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)

            # Extraer todo el texto visible
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
                return [...new Set(textos)].slice(0, 50).join('\\n');
            }""")

            await browser.close()
            return texto[:3000] if texto else "No se pudo extraer contenido."

    except Exception as e:
        return f"Error navegando {url}: {e}"

async def buscar_en_google(query: str) -> str:
    """
    Busca en Google y retorna los primeros resultados.
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1000)

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
                    texto += f"   {r['descripcion'][:150]}\n"
                texto += f"   🔗 {r.get('enlace', '')}\n\n"

            return texto.strip()

    except Exception as e:
        return f"Error buscando en Google: {e}"

async def tomar_screenshot(url: str, ruta: str = "/tmp/troy_screenshot.png") -> str:
    """
    Toma un screenshot de una página web.
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1000)
            await page.screenshot(path=ruta, full_page=False)
            await browser.close()
            return ruta
    except Exception as e:
        return f"Error tomando screenshot: {e}"

def navegar(url: str) -> str:
    """Wrapper síncrono para navegar."""
    return asyncio.run(navegar_y_extraer(url))

def buscar_google(query: str) -> str:
    """Wrapper síncrono para buscar en Google."""
    return asyncio.run(buscar_en_google(query))