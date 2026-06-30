"""Confluence Exporter — crea una pagina nativa in Confluence Storage Format."""

import html
import logging
import re
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Mappa risk_level → colore status-macro Confluence
_RISK_COLOURS = {
    "CRITICO":  "Red",
    "ALTO":     "Red",
    "MEDIO":    "Yellow",
    "BASSO":    "Green",
    "CRITICAL": "Red",
    "HIGH":     "Red",
    "MEDIUM":   "Yellow",
    "LOW":      "Green",
}


class ConfluenceExporter:
    def __init__(self, url: str, user: str, token: str):
        self.base_url = url.rstrip("/")
        from atlassian import Confluence
        self.confluence = Confluence(
            url=self.base_url,
            username=user,
            password=token,
            cloud=True,
        )

    def export(
        self,
        release_notes,
        space: str,
        parent_page: Optional[str] = None,
        page_title: Optional[str] = None,
        placeholder: bool = False,
        error_message: Optional[str] = None,
    ) -> str:
        title     = page_title or f"Release Notes — {release_notes.repo_full_name} PR#{release_notes.pr_number}"
        body      = self._build_body(release_notes, placeholder=placeholder, error_message=error_message)
        parent_id = self._resolve_parent_id(space, parent_page)

        if parent_id:
            result = self.confluence.update_or_create(
                parent_id=parent_id,
                title=title,
                body=body,
                representation="storage",
            )
        else:
            # Nessun padre: aggiorna se esiste, altrimenti crea in radice
            existing = self.confluence.get_page_by_title(space=space, title=title)
            if existing:
                result = self.confluence.update_page(
                    page_id=existing["id"],
                    title=title,
                    body=body,
                    representation="storage",
                )
            else:
                result = self.confluence.create_page(
                    space=space,
                    title=title,
                    body=body,
                )

        links = result.get("_links", {})
        base = links.get("base") or (self.base_url.rstrip("/") + "/wiki")
        page_url = base.rstrip("/") + links.get("webui", "")
        logger.info("Confluence: pagina creata/aggiornata → %s", page_url)
        return page_url

    def _resolve_parent_id(self, space: str, parent_page: Optional[str]) -> Optional[str]:
        if not parent_page:
            return None
        # ID numerico passato direttamente (es. dall'URL /folder/1590690001)
        if str(parent_page).strip().isdigit():
            return str(parent_page).strip()
        # Ricerca per titolo
        page = self.confluence.get_page_by_title(space=space, title=parent_page)
        if page:
            return page["id"]
        logger.warning("Pagina padre '%s' non trovata nello spazio %s — creo in radice", parent_page, space)
        return None

    # ── Body builder ──────────────────────────────────────────────────────────

    def _build_body(self, rn, placeholder: bool = False, error_message: Optional[str] = None) -> str:
        parts = []
        parts.append(self._metadata_table(rn))

        if error_message:
            parts.append(
                '<ac:structured-macro ac:name="warning"><ac:rich-text-body>'
                f'<p><strong>Generazione del documento non riuscita.</strong></p>'
                f'<p>{_e(error_message)}</p>'
                '</ac:rich-text-body></ac:structured-macro>'
            )
            return "\n".join(p for p in parts if p)

        if placeholder:
            parts.append(
                '<ac:structured-macro ac:name="info"><ac:rich-text-body>'
                '<p>⏳ <strong>Generazione del documento in corso…</strong></p>'
                '<p>Questa pagina verrà aggiornata automaticamente al termine '
                'dell\'analisi della Pull Request.</p>'
                '</ac:rich-text-body></ac:structured-macro>'
            )
            return "\n".join(p for p in parts if p)

        parts.append(self._section("1. Sommario Esecutivo",      rn.summary))
        parts.append(self._section("2. Motivazione e Contesto",  rn.motivation_and_context))
        parts.append(self._section("3. Dettaglio delle Modifiche", rn.change_details_narrative))
        if rn.risk_matrix_items:
            parts.append(self._risk_matrix(rn.risk_matrix_items))
        parts.append(self._deployment_section(rn))
        parts.append(self._rollback_section(rn))
        parts.append(self._post_deploy_section(rn))
        return "\n".join(p for p in parts if p)

    # ── Cover metadata ────────────────────────────────────────────────────────

    def _metadata_table(self, rn) -> str:
        doc_date = datetime.now().strftime("%d/%m/%Y")
        pr_date  = rn.release_date.strftime("%d/%m/%Y") if rn.release_date else "N/A"
        envs     = ", ".join(rn.environments_affected).upper() if rn.environments_affected else "N/A"
        labels   = ", ".join(rn.pr_labels) if rn.pr_labels else "—"
        rows = [
            ("Repository",          rn.repo_full_name or "N/A"),
            ("Pull Request",        f'<a href="{_e(rn.pr_url)}">#{rn.pr_number}</a>'),
            ("Branch sorgente",     rn.source_branch or "N/A"),
            ("Branch target",       rn.target_branch or "N/A"),
            ("Autore",              rn.pr_author or "N/A"),
            ("Data creazione PR",   pr_date),
            ("Data documento",      doc_date),
            ("Ambienti coinvolti",  envs),
            ("Dominio",             rn.domain or "N/A"),
            ("Impatto utenti",      rn.user_impact or "N/A"),
            ("Versione",            rn.version),
            ("Label",               labels),
        ]
        cells = "\n".join(
            f"<tr><th>{_e(k)}</th><td>{v}</td></tr>"
            for k, v in rows
        )
        return f"<table><tbody>{cells}</tbody></table>"

    # ── Generic text section ──────────────────────────────────────────────────

    def _section(self, title: str, text: str) -> str:
        if not text:
            return ""
        parts = [f"<h2>{_e(title)}</h2>"]
        # Split on fenced code blocks
        segments = re.split(r'(```[^\n]*\n.*?```)', text, flags=re.DOTALL)
        for seg in segments:
            if seg.startswith("```"):
                lang = re.match(r'```([^\n]*)', seg)
                language = lang.group(1).strip() if lang else ""
                code = re.sub(r'^```[^\n]*\n?', '', seg)
                code = re.sub(r'\n?```$', '', code)
                parts.append(_code_macro(code, language))
            else:
                parts.extend(self._render_text(seg))
        return "\n".join(parts)

    def _render_text(self, text: str) -> list:
        """Converte testo markdown-like in elementi Storage Format, linea per linea."""
        els = []
        para_lines: list = []
        bullet_lines: list = []

        def flush_para():
            if para_lines:
                els.append(f"<p>{_inline(' '.join(para_lines))}</p>")
                para_lines.clear()

        def flush_bullets():
            if bullet_lines:
                items = "".join(f"<li>{_inline(b)}</li>" for b in bullet_lines)
                els.append(f"<ul>{items}</ul>")
                bullet_lines.clear()

        for line in text.splitlines():
            s = line.strip()
            if not s:
                flush_para(); flush_bullets(); continue

            # --- **Stack: heading** o semplice separatore ---
            if s.startswith("---"):
                flush_para(); flush_bullets()
                heading = re.sub(r'^-+\s*', '', s).strip()
                heading = re.sub(r'^\*\*(.*)\*\*$', r'\1', heading).strip()
                els.append(f"<h3>{_e(heading)}</h3>" if heading else "<hr/>")
                continue

            if s.startswith("### "):
                flush_para(); flush_bullets()
                els.append(f"<h4>{_e(s[4:])}</h4>"); continue
            if s.startswith("## "):
                flush_para(); flush_bullets()
                els.append(f"<h3>{_e(s[3:])}</h3>"); continue

            if re.match(r'^[-*]\s+', s):
                flush_para()
                bullet_lines.append(re.sub(r'^[-*]\s+', '', s))
                continue

            flush_bullets()
            para_lines.append(s)

        flush_para(); flush_bullets()
        return els

    # ── Risk matrix ───────────────────────────────────────────────────────────

    def _risk_matrix(self, items: list) -> str:
        header = (
            "<tr>"
            "<th>Componente</th><th>Rischio</th>"
            "<th>Descrizione</th><th>Impatto</th><th>Mitigazione</th>"
            "</tr>"
        )
        rows = []
        for item in items:
            risk = item.get("risk_level", "BASSO").upper()
            colour = _RISK_COLOURS.get(risk, "Grey")
            status = _status_macro(risk, colour)
            rows.append(
                f"<tr>"
                f"<td><strong>{_e(item.get('component',''))}</strong></td>"
                f"<td>{status}</td>"
                f"<td>{_e(item.get('description',''))}</td>"
                f"<td>{_e(item.get('impact',''))}</td>"
                f"<td>{_e(item.get('mitigation',''))}</td>"
                f"</tr>"
            )
        return (
            "<h2>4. Matrice dei Rischi</h2>"
            f"<table><tbody>{header}{''.join(rows)}</tbody></table>"
        )

    # ── Deployment section ────────────────────────────────────────────────────

    def _deployment_section(self, rn) -> str:
        parts = ["<h2>5. Piano di Deployment</h2>"]

        if rn.deployment_prerequisites:
            parts.append("<h3>5.1 Pre-requisiti</h3><ul>")
            parts.extend(f"<li>{_e(p)}</li>" for p in rn.deployment_prerequisites)
            parts.append("</ul>")

        for idx, (env, steps) in enumerate(
            (rn.deployment_steps_by_env or {}).items(), start=2
        ):
            parts.append(f"<h3>5.{idx} Deployment — {_e(env.upper())}</h3>")
            parts.append(self._steps_table(steps))

        return "\n".join(parts)

    def _steps_table(self, steps: list) -> str:
        if not steps:
            return ""
        header = "<tr><th>#</th><th>Azione</th><th>Responsabile</th><th>Note</th></tr>"
        rows = "".join(
            f"<tr>"
            f"<td>{_e(str(s.get('order','')))}</td>"
            f"<td>{_e(s.get('action',''))}</td>"
            f"<td>{_e(s.get('responsible',''))}</td>"
            f"<td>{_e(s.get('notes','') or '')}</td>"
            f"</tr>"
            for s in steps
        )
        return f"<table><tbody>{header}{rows}</tbody></table>"

    # ── Rollback section ──────────────────────────────────────────────────────

    def _rollback_section(self, rn) -> str:
        parts = ["<h2>6. Piano di Rollback</h2>"]
        if rn.rollback_note:
            parts.append(f"<ac:structured-macro ac:name=\"warning\"><ac:rich-text-body><p>{_e(rn.rollback_note)}</p></ac:rich-text-body></ac:structured-macro>")
        if rn.rollback_plan_items:
            header = "<tr><th>#</th><th>Azione</th><th>Ambiente</th><th>Responsabile</th><th>Note</th></tr>"
            rows = "".join(
                f"<tr>"
                f"<td>{_e(str(i.get('order','')))}</td>"
                f"<td>{_e(i.get('action',''))}</td>"
                f"<td>{_e(i.get('environment',''))}</td>"
                f"<td>{_e(i.get('responsible',''))}</td>"
                f"<td>{_e(i.get('notes','') or '')}</td>"
                f"</tr>"
                for i in rn.rollback_plan_items
            )
            parts.append(f"<table><tbody>{header}{rows}</tbody></table>")
        return "\n".join(parts)

    # ── Post-deploy section ───────────────────────────────────────────────────

    def _post_deploy_section(self, rn) -> str:
        parts = ["<h2>7. Verifica Post-Deploy</h2>"]
        if rn.post_deploy_health_checks:
            parts.append("<h3>7.1 Health Check</h3>")
            header = "<tr><th>Verifica</th><th>Metodo</th><th>Esito atteso</th></tr>"
            rows = "".join(
                f"<tr>"
                f"<td>{_e(c.get('check',''))}</td>"
                f"<td>{_e(c.get('method',''))}</td>"
                f"<td>{_e(c.get('expected',''))}</td>"
                f"</tr>"
                for c in rn.post_deploy_health_checks
            )
            parts.append(f"<table><tbody>{header}{rows}</tbody></table>")
        if rn.monitoring_notes:
            parts.append(
                f"<h3>7.2 Monitoring</h3>"
                f"<ac:structured-macro ac:name=\"info\"><ac:rich-text-body>"
                f"<p>{_e(rn.monitoring_notes)}</p>"
                f"</ac:rich-text-body></ac:structured-macro>"
            )
        return "\n".join(parts)


# ── Storage Format helpers ────────────────────────────────────────────────────

def _e(text: str) -> str:
    """HTML-escape una stringa per il Storage Format."""
    return html.escape(str(text)) if text else ""


def _inline(text: str) -> str:
    """Converte markdown inline in Confluence Storage Format.

    Ordine: escape HTML → inline code → bold → italic.
    """
    text = html.escape(str(text))
    text = re.sub(r'`([^`]+)`',        r'<code>\1</code>',           text)
    text = re.sub(r'\*\*(.+?)\*\*',    r'<strong>\1</strong>',       text, flags=re.DOTALL)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)
    return text


def _status_macro(title: str, colour: str) -> str:
    return (
        f'<ac:structured-macro ac:name="status">'
        f'<ac:parameter ac:name="colour">{colour}</ac:parameter>'
        f'<ac:parameter ac:name="title">{_e(title)}</ac:parameter>'
        f'</ac:structured-macro>'
    )


def _code_macro(code: str, language: str = "") -> str:
    lang_param = (
        f'<ac:parameter ac:name="language">{_e(language)}</ac:parameter>'
        if language else ""
    )
    return (
        f'<ac:structured-macro ac:name="code">'
        f'{lang_param}'
        f'<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>'
        f'</ac:structured-macro>'
    )
