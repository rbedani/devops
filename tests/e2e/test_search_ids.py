"""E2E tests for multi-ID search on the STATUS tab (SEARCH-IDS-01/02/03).

Verifica que el campo Search de la solapa STATUS:
1. Busca varios IDs separados por ESPACIO ("2514 2475 2473") y devuelve los
   3 avisos (semantica OR para tokens numericos).
2. Funciona identico separando por COMA ("2514, 2475, 2473").
3. Combina palabra + ID ("madrid 2514"): la palabra mantiene AND y el ID
   matchea por id exacto.

Patron tomado de test_scan_salary.py: DB aislada de sesion, seed directo
via sqlite3, Playwright headless contra el server uvicorn del conftest.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from playwright.sync_api import sync_playwright

ID_FIXTURES = [
    (2514, "Tecnico/a De IT",        "http://x/e2e-2514", "Madrid",    "Emp1"),
    (2475, "Soporte Service Desk",   "http://x/e2e-2475", "Remote",    "Emp2"),
    (2473, "Consultor Dynamics 365", "http://x/e2e-2473", "Barcelona", "Emp3"),
    (9999, "Unrelated Dev",          "http://x/e2e-9999", "Madrid",    "Emp4"),
]


def seed_jobs(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM jobs")
    conn.executemany(
        "INSERT INTO jobs (id, source, title, url, company, location, tags, scraped_at, status) "
        "VALUES (?, ?, ?, ?, ?, ?, '[]', datetime('now'), '')",
        [(i, "tecnoempleo", t, u, c, l) for i, t, u, c, l in ID_FIXTURES],
    )
    conn.commit()
    conn.close()


def _open_status_tab(page, server_url: str) -> None:
    page.goto(f"{server_url}/")
    page.wait_for_selector("button[data-tab='status']", timeout=15000)
    page.click("button[data-tab='status']")
    # Espera el swap async de hx-get=/status/panel (clase .htmx-request sale
    # cuando el swap termina; el input de search debe existir).
    page.wait_for_function(
        "!document.querySelector('.htmx-request') && "
        "document.querySelector('#search-input') !== null",
        timeout=15000,
    )
    # Espera el load inicial de la tabla (hx-trigger='load') para partir de
    # un estado estable: las 4 filas sembradas.
    page.wait_for_function(
        "document.querySelectorAll('.job-row').length === 4",
        timeout=15000,
    )


def _type_search_and_wait(page, query: str) -> None:
    """Type the query with REAL key events (page.keyboard.type; htmx escucha
    keyup con debounce de 2s — page.type() no dispara keyup) and wait until
    the table shows exactly the 3 ID rows and hides the unrelated one."""
    page.fill("#search-input", "")
    page.keyboard.type(query, delay=50)
    page.wait_for_function(
        """
        () => {
            const ids = [...document.querySelectorAll('.cell-id')]
                .map(td => td.textContent.trim());
            const text = document.body.textContent;
            return ids.length === 3
                && ids.includes('2514')
                && ids.includes('2475')
                && ids.includes('2473')
                && !text.includes('Unrelated Dev');
        }
        """,
        timeout=20000,
    )


def _visible_ids(page) -> list[str]:
    cells = page.query_selector_all(".cell-id")
    return [c.text_content().strip() for c in cells]


class TestMultiIDSearchUI:
    def test_multi_id_search_space_separated(self, server_url: str, db_path: Path) -> None:
        """SEARCH-IDS-01: '2514 2475 2473' (espacios) muestra los 3 avisos."""
        print("\n" + "=" * 60)
        print("TEST: search '2514 2475 2473' (espacios)")
        print(f"{'='*60}")

        seed_jobs(db_path)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            _open_status_tab(page, server_url)

            _type_search_and_wait(page, "2514 2475 2473")
            ids = _visible_ids(page)
            print(f"  IDs visibles: {ids}")
            assert sorted(ids) == ["2473", "2475", "2514"], f"IDs esperados 2473/2475/2514, got {ids}"

            titles = page.text_content("#table-container")
            assert "Tecnico/a De IT" in titles
            assert "Soporte Service Desk" in titles
            assert "Consultor Dynamics 365" in titles
            print("  Los 3 avisos (2514, 2475, 2473) visibles en la tabla")
            print("=" * 60 + "\n")
            browser.close()

    def test_multi_id_search_comma_separated(self, server_url: str, db_path: Path) -> None:
        """SEARCH-IDS-02: '2514, 2475, 2473' (comas) idem a espacios."""
        print("\n" + "=" * 60)
        print("TEST: search '2514, 2475, 2473' (comas)")
        print(f"{'='*60}")

        seed_jobs(db_path)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            _open_status_tab(page, server_url)

            _type_search_and_wait(page, "2514, 2475, 2473")
            ids = _visible_ids(page)
            print(f"  IDs visibles: {ids}")
            assert sorted(ids) == ["2473", "2475", "2514"], f"IDs esperados 2473/2475/2514, got {ids}"
            print("  La variante con comas devuelve los mismos 3 avisos")
            print("=" * 60 + "\n")
            browser.close()

    def test_multi_id_search_mixed_word_and_id(self, server_url: str, db_path: Path) -> None:
        """SEARCH-IDS-03: 'madrid 2514' → palabra AND + ID exacto."""
        print("\n" + "=" * 60)
        print("TEST: search 'madrid 2514' (palabra + ID)")
        print(f"{'='*60}")

        seed_jobs(db_path)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            _open_status_tab(page, server_url)

            page.fill("#search-input", "")
            page.keyboard.type("madrid 2514", delay=50)
            page.wait_for_function(
                """
                () => {
                    const ids = [...document.querySelectorAll('.cell-id')]
                        .map(td => td.textContent.trim());
                    const text = document.body.textContent;
                    return ids.length === 1
                        && ids.includes('2514')
                        && !text.includes('Unrelated Dev')
                        && !text.includes('Consultor Dynamics 365');
                }
                """,
                timeout=20000,
            )
            ids = _visible_ids(page)
            print(f"  IDs visibles: {ids}")
            assert ids == ["2514"], f"Solo id 2514 esperado, got {ids}"
            print("  'madrid 2514' deja solo el aviso 2514 (Madrid + id)")
            print("=" * 60 + "\n")
            browser.close()
