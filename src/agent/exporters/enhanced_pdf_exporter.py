"""Enhanced PDF Exporter — structure mirrors the reference .docx release document."""

import html
import logging
import os
import re
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak,
    Preformatted, Table, TableStyle, HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from src.models import RiskLevel

logger = logging.getLogger(__name__)

# ── Colour palette ────────────────────────────────────────────────────────────
C_BLUE       = colors.HexColor("#1f4e79")
C_BLUE_LIGHT = colors.HexColor("#2e75b6")
C_HEADER_BG  = colors.HexColor("#dce6f1")
C_ROW_ALT    = colors.HexColor("#f2f7fc")
C_GREEN      = colors.HexColor("#375623")
C_GREEN_BG   = colors.HexColor("#e2efda")
C_RED        = colors.HexColor("#c00000")
C_RED_BG     = colors.HexColor("#fce4d6")
C_ORANGE     = colors.HexColor("#ed7d31")
C_ORANGE_BG  = colors.HexColor("#fce4d6")
C_YELLOW_BG  = colors.HexColor("#ffff99")
C_GREY       = colors.HexColor("#595959")
C_GREY_LIGHT = colors.HexColor("#f2f2f2")
C_BLACK      = colors.black
C_WHITE      = colors.white

RISK_COLOURS = {
    "CRITICO": (C_RED,    C_RED_BG),
    "ALTO":    (C_ORANGE, C_ORANGE_BG),
    "MEDIO":   (C_ORANGE, C_YELLOW_BG),
    "BASSO":   (C_GREEN,  C_GREEN_BG),
    "CRITICAL":(C_RED,    C_RED_BG),
    "HIGH":    (C_ORANGE, C_ORANGE_BG),
    "MEDIUM":  (C_ORANGE, C_YELLOW_BG),
    "LOW":     (C_GREEN,  C_GREEN_BG),
}

PAGE_W, PAGE_H = A4
MARGIN = 2 * cm
CONTENT_W = PAGE_W - 2 * MARGIN


def _inline_pdf(text: str) -> str:
    """Converte markdown inline in markup ReportLab XML.

    Ordine: escape XML → inline code → bold.
    """
    text = html.escape(str(text))
    text = re.sub(r'`([^`]+)`',     r'<font name="Courier" fontSize="8">\1</font>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text, flags=re.DOTALL)
    return text


class EnhancedPDFExporter:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.department = os.getenv("DEPARTMENT_NAME", "")
        self._add_styles()

    # ── Style setup ───────────────────────────────────────────────────────────

    def _add_styles(self):
        s = self.styles

        def add(name, **kw):
            if name not in s:
                s.add(ParagraphStyle(name=name, **kw))

        add("DocTitle",   parent=s["Normal"], fontName="Helvetica-Bold",
            fontSize=20, textColor=C_WHITE, alignment=1, spaceAfter=4)
        add("DocSubtitle",parent=s["Normal"], fontName="Helvetica-Bold",
            fontSize=13, textColor=C_WHITE, alignment=1, spaceAfter=2)
        add("SectionNum", parent=s["Normal"], fontName="Helvetica-Bold",
            fontSize=13, textColor=C_BLUE, spaceBefore=14, spaceAfter=4)
        add("SubSection", parent=s["Normal"], fontName="Helvetica-Bold",
            fontSize=11, textColor=C_BLUE_LIGHT, spaceBefore=8, spaceAfter=3)
        add("Body",       parent=s["Normal"], fontSize=9,
            leading=14, spaceAfter=4, textColor=C_BLACK)
        add("BodyBold",   parent=s["Normal"], fontName="Helvetica-Bold",
            fontSize=9, leading=14, spaceAfter=4)
        add("Bullet",     parent=s["Normal"], fontSize=9,
            leading=13, leftIndent=14, spaceAfter=2, bulletIndent=6)
        add("Code",       parent=s["Normal"], fontName="Courier",
            fontSize=8, leading=11, leftIndent=10, backColor=C_GREY_LIGHT,
            spaceAfter=2)
        add("TableHeader",parent=s["Normal"], fontName="Helvetica-Bold",
            fontSize=9, textColor=C_WHITE, alignment=1)
        add("TableCell",  parent=s["Normal"], fontSize=8, leading=12)
        add("TableCellB", parent=s["Normal"], fontName="Helvetica-Bold",
            fontSize=8, leading=12)
        add("FooterText", parent=s["Normal"], fontSize=8,
            textColor=C_GREY, alignment=1)
        add("MetaLabel",  parent=s["Normal"], fontName="Helvetica-Bold",
            fontSize=9, textColor=C_BLUE)
        add("MetaValue",  parent=s["Normal"], fontSize=9)

    # ── Public entry point ────────────────────────────────────────────────────

    def export(self, release_notes, filepath: str) -> str:
        doc = SimpleDocTemplate(
            filepath,
            pagesize=A4,
            topMargin=MARGIN, bottomMargin=MARGIN,
            leftMargin=MARGIN, rightMargin=MARGIN,
        )
        story = self._build_story(release_notes)
        doc.build(story, onFirstPage=self._page_header, onLaterPages=self._page_header)
        logger.info(f"PDF exported to: {filepath}")
        return filepath

    # ── Story builder ─────────────────────────────────────────────────────────

    def _build_story(self, rn):
        story = []

        story += self._cover_page(rn)
        story.append(PageBreak())

        story += self._section("1. Sommario Esecutivo", rn.summary)
        story += self._section("2. Motivazione e Contesto", rn.motivation_and_context)

        if rn.change_details_narrative:
            story += self._section("3. Dettaglio delle Modifiche", rn.change_details_narrative)

        if rn.risk_matrix_items:
            story += self._risk_matrix_section(rn.risk_matrix_items)

        story += self._deployment_section(rn)
        story += self._rollback_section(rn)
        story += self._post_deploy_section(rn)
        story += self._references_section(rn)

        return story

    # ── Cover page ────────────────────────────────────────────────────────────

    def _cover_page(self, rn):
        els = []

        # Title banner
        banner_data = [[Paragraph("DOCUMENTAZIONE DI RILASCIO", self.styles["DocTitle"])],
                       [Paragraph(rn.title, self.styles["DocSubtitle"])]]
        banner = Table(banner_data, colWidths=[CONTENT_W])
        banner.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_BLUE),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ]))
        els.append(banner)
        els.append(Spacer(1, 0.4 * cm))

        # Metadata table
        pr_status = "Draft — in revisione" if rn.pr_draft else rn.pr_author
        envs = ", ".join(rn.environments_affected).upper() if rn.environments_affected else "N/A"
        doc_date = datetime.now().strftime("%d/%m/%Y")
        pr_date  = rn.release_date.strftime("%d %B %Y") if rn.release_date else "N/A"
        labels   = ", ".join(rn.pr_labels) if rn.pr_labels else "—"

        rows = [
            ["Repository",        rn.repo_full_name or "N/A"],
            ["Pull Request",       f"#{rn.pr_number}"],
            ["Branch sorgente",   rn.source_branch or "N/A"],
            ["Branch target",     rn.target_branch or "N/A"],
            ["Autore",            rn.pr_author or "N/A"],
            ["Data creazione PR", pr_date],
            ["Data documento",    doc_date],
            ["Stato PR",          "Draft — in revisione" if rn.pr_draft else (rn.pr_author and "Aperta" or "N/A")],
            ["Ambienti coinvolti",envs],
            ["Dominio",           rn.domain or "N/A"],
            ["Impatto utenti",    rn.user_impact or "N/A"],
            ["Label",             labels],
        ]

        meta_rows = [
            [Paragraph(label, self.styles["MetaLabel"]),
             Paragraph(str(value), self.styles["MetaValue"])]
            for label, value in rows
        ]
        meta_table = Table(meta_rows, colWidths=[4.5 * cm, CONTENT_W - 4.5 * cm])
        meta_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, -1), C_HEADER_BG),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#aaaaaa")),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
            ("ROWBACKGROUNDS",(0, 0), (-1, -1), [C_WHITE, C_ROW_ALT]),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ]))
        els.append(meta_table)
        return els

    # ── Generic text section ──────────────────────────────────────────────────

    def _section(self, title: str, text: str):
        if not text:
            return []
        els = [Paragraph(title, self.styles["SectionNum"]),
               HRFlowable(width=CONTENT_W, thickness=1, color=C_BLUE_LIGHT, spaceAfter=6)]

        # Separa i blocchi di codice dal testo narrativo
        parts = re.split(r'(```[^\n]*\n.*?```)', text, flags=re.DOTALL)
        for part in parts:
            if part.startswith("```"):
                code = re.sub(r'^```[^\n]*\n?', '', part)
                code = re.sub(r'\n?```$', '', code)
                els += self._code_block(code)
            else:
                els += self._render_text_pdf(part)

        els.append(Spacer(1, 0.3 * cm))
        return els

    def _render_text_pdf(self, text: str) -> list:
        """Converte testo markdown-like in elementi PDF, linea per linea."""
        els = []
        para_lines: list = []
        bullet_lines: list = []

        def flush_para():
            if para_lines:
                els.append(Paragraph(_inline_pdf(" ".join(para_lines)), self.styles["Body"]))
                para_lines.clear()

        def flush_bullets():
            for b in bullet_lines:
                els.append(Paragraph(f"• {_inline_pdf(b)}", self.styles["Bullet"]))
            bullet_lines.clear()

        for line in text.splitlines():
            s = line.strip()
            if not s:
                flush_para(); flush_bullets(); continue

            # --- **Stack: heading** o semplice separatore
            if s.startswith("---"):
                flush_para(); flush_bullets()
                heading = re.sub(r'^-+\s*', '', s).strip()
                heading = re.sub(r'^\*\*(.*)\*\*$', r'\1', heading).strip()
                if heading:
                    els.append(Paragraph(heading, self.styles["SubSection"]))
                else:
                    els.append(HRFlowable(width=CONTENT_W, thickness=0.5,
                                          color=C_GREY_LIGHT, spaceAfter=4))
                continue

            if s.startswith("### "):
                flush_para(); flush_bullets()
                els.append(Paragraph(s[4:], self.styles["SubSection"])); continue
            if s.startswith("## "):
                flush_para(); flush_bullets()
                els.append(Paragraph(s[3:], self.styles["SubSection"])); continue

            if re.match(r'^[-*]\s+', s):
                flush_para()
                bullet_lines.append(re.sub(r'^[-*]\s+', '', s))
                continue

            flush_bullets()
            para_lines.append(s)

        flush_para(); flush_bullets()
        return els

    def _code_block(self, code: str):
        """Render a fenced code block as a monospace box."""
        lines = code.rstrip("\n").split("\n")
        if not lines:
            return []
        pre = Preformatted(
            "\n".join(lines),
            ParagraphStyle(
                "CodePre",
                fontName="Courier",
                fontSize=8,
                leading=11,
                textColor=C_BLACK,
            ),
        )
        box = Table([[pre]], colWidths=[CONTENT_W])
        box.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), C_GREY_LIGHT),
            ("BOX",           (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return [Spacer(1, 0.15 * cm), box, Spacer(1, 0.15 * cm)]

    # ── Risk matrix ───────────────────────────────────────────────────────────

    def _risk_matrix_section(self, risk_items: list):
        els = [
            Paragraph("4. Matrice dei Rischi", self.styles["SectionNum"]),
            HRFlowable(width=CONTENT_W, thickness=1, color=C_BLUE_LIGHT, spaceAfter=6),
        ]

        col_w = [CONTENT_W * p for p in (0.18, 0.10, 0.24, 0.24, 0.24)]
        header = [
            Paragraph("Componente",  self.styles["TableHeader"]),
            Paragraph("Rischio",     self.styles["TableHeader"]),
            Paragraph("Descrizione", self.styles["TableHeader"]),
            Paragraph("Impatto",     self.styles["TableHeader"]),
            Paragraph("Mitigazione", self.styles["TableHeader"]),
        ]
        data = [header]
        row_styles = []

        for i, item in enumerate(risk_items, start=1):
            risk_key = item.get("risk_level", "BASSO").upper()
            fg, bg = RISK_COLOURS.get(risk_key, (C_GREY, C_GREY_LIGHT))
            row = [
                Paragraph(item.get("component", ""), self.styles["TableCellB"]),
                Paragraph(risk_key,                   self.styles["TableCellB"]),
                Paragraph(item.get("description", ""),self.styles["TableCell"]),
                Paragraph(item.get("impact", ""),     self.styles["TableCell"]),
                Paragraph(item.get("mitigation", ""), self.styles["TableCell"]),
            ]
            data.append(row)
            row_styles.append(("BACKGROUND", (1, i), (1, i), bg))
            row_styles.append(("TEXTCOLOR",  (1, i), (1, i), fg))

        table = Table(data, colWidths=col_w, repeatRows=1)
        base_style = TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), C_BLUE),
            ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#aaaaaa")),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_ROW_ALT]),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 5),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ] + row_styles)
        table.setStyle(base_style)
        els.append(table)
        els.append(Spacer(1, 0.3 * cm))
        return els

    # ── Deployment section ────────────────────────────────────────────────────

    def _deployment_section(self, rn):
        els = [
            Paragraph("5. Piano di Deployment", self.styles["SectionNum"]),
            HRFlowable(width=CONTENT_W, thickness=1, color=C_BLUE_LIGHT, spaceAfter=6),
        ]

        if rn.deployment_prerequisites:
            els.append(Paragraph("5.1 Pre-requisiti", self.styles["SubSection"]))
            for prereq in rn.deployment_prerequisites:
                els.append(Paragraph(f"• {prereq}", self.styles["Bullet"]))
            els.append(Spacer(1, 0.2 * cm))

        steps_by_env = rn.deployment_steps_by_env or {}
        for idx, (env, steps) in enumerate(steps_by_env.items(), start=2):
            env_label = env.upper()
            els.append(Paragraph(f"5.{idx} Passi di Deployment — {env_label}", self.styles["SubSection"]))
            els += self._steps_table(steps)
            els.append(Spacer(1, 0.2 * cm))

        return els

    def _steps_table(self, steps: list):
        if not steps:
            return []
        col_w = [CONTENT_W * p for p in (0.06, 0.46, 0.26, 0.22)]
        header = [
            Paragraph("#",            self.styles["TableHeader"]),
            Paragraph("Azione",       self.styles["TableHeader"]),
            Paragraph("Responsabile", self.styles["TableHeader"]),
            Paragraph("Note",         self.styles["TableHeader"]),
        ]
        data = [header]
        for step in steps:
            data.append([
                Paragraph(str(step.get("order", "")),       self.styles["TableCell"]),
                Paragraph(step.get("action", ""),           self.styles["TableCell"]),
                Paragraph(step.get("responsible", ""),      self.styles["TableCell"]),
                Paragraph(step.get("notes", "") or "",      self.styles["TableCell"]),
            ])
        table = Table(data, colWidths=col_w, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), C_BLUE_LIGHT),
            ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#aaaaaa")),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_ROW_ALT]),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 5),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ]))
        return [table]

    # ── Rollback section ──────────────────────────────────────────────────────

    def _rollback_section(self, rn):
        els = [
            Paragraph("6. Piano di Rollback", self.styles["SectionNum"]),
            HRFlowable(width=CONTENT_W, thickness=1, color=C_BLUE_LIGHT, spaceAfter=6),
        ]

        if rn.rollback_note:
            els.append(Paragraph(rn.rollback_note, self.styles["Body"]))
            els.append(Spacer(1, 0.2 * cm))

        if rn.rollback_plan_items:
            col_w = [CONTENT_W * p for p in (0.06, 0.42, 0.20, 0.20, 0.12)]
            header = [
                Paragraph("#",           self.styles["TableHeader"]),
                Paragraph("Azione di Rollback", self.styles["TableHeader"]),
                Paragraph("Ambiente",    self.styles["TableHeader"]),
                Paragraph("Responsabile",self.styles["TableHeader"]),
                Paragraph("Note",        self.styles["TableHeader"]),
            ]
            data = [header]
            for item in rn.rollback_plan_items:
                data.append([
                    Paragraph(str(item.get("order", "")),        self.styles["TableCell"]),
                    Paragraph(item.get("action", ""),            self.styles["TableCell"]),
                    Paragraph(item.get("environment", ""),       self.styles["TableCell"]),
                    Paragraph(item.get("responsible", ""),       self.styles["TableCell"]),
                    Paragraph(item.get("notes", "") or "",       self.styles["TableCell"]),
                ])
            table = Table(data, colWidths=col_w, repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, 0), C_RED),
                ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
                ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#aaaaaa")),
                ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_ROW_ALT]),
                ("TOPPADDING",    (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING",   (0, 0), (-1, -1), 5),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
                ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ]))
            els.append(table)

        els.append(Spacer(1, 0.3 * cm))
        return els

    # ── Post-deploy section ───────────────────────────────────────────────────

    def _post_deploy_section(self, rn):
        els = [
            Paragraph("7. Verifica Post-Deploy", self.styles["SectionNum"]),
            HRFlowable(width=CONTENT_W, thickness=1, color=C_BLUE_LIGHT, spaceAfter=6),
        ]

        if rn.post_deploy_health_checks:
            els.append(Paragraph("7.1 Health Check", self.styles["SubSection"]))
            col_w = [CONTENT_W * p for p in (0.32, 0.34, 0.34)]
            header = [
                Paragraph("Verifica",       self.styles["TableHeader"]),
                Paragraph("Metodo",         self.styles["TableHeader"]),
                Paragraph("Esito atteso",   self.styles["TableHeader"]),
            ]
            data = [header]
            for item in rn.post_deploy_health_checks:
                data.append([
                    Paragraph(item.get("check", ""),    self.styles["TableCell"]),
                    Paragraph(item.get("method", ""),   self.styles["TableCell"]),
                    Paragraph(item.get("expected", ""), self.styles["TableCell"]),
                ])
            table = Table(data, colWidths=col_w, repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, 0), C_BLUE_LIGHT),
                ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
                ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#aaaaaa")),
                ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_ROW_ALT]),
                ("TOPPADDING",    (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING",   (0, 0), (-1, -1), 5),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
                ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ]))
            els.append(table)
            els.append(Spacer(1, 0.2 * cm))

        if rn.monitoring_notes:
            els.append(Paragraph("7.2 Monitoring", self.styles["SubSection"]))
            els.append(Paragraph(rn.monitoring_notes, self.styles["Body"]))

        els.append(Spacer(1, 0.3 * cm))
        return els

    # ── References section ────────────────────────────────────────────────────

    def _references_section(self, rn):
        els = [
            Paragraph("8. Riferimenti", self.styles["SectionNum"]),
            HRFlowable(width=CONTENT_W, thickness=1, color=C_BLUE_LIGHT, spaceAfter=6),
        ]

        rows = [
            ["Pull Request",    rn.pr_url],
            ["Branch",         rn.source_branch or "N/A"],
            ["Repository",     rn.repo_full_name or "N/A"],
            ["Autore",         rn.pr_author or "N/A"],
            ["Versione",       rn.version],
            ["Data documento", datetime.now().strftime("%d/%m/%Y")],
        ]
        if rn.pr_labels:
            rows.append(["Label", ", ".join(rn.pr_labels)])

        data = [
            [Paragraph(k, self.styles["MetaLabel"]),
             Paragraph(v, self.styles["MetaValue"])]
            for k, v in rows
        ]
        col_w = [4 * cm, CONTENT_W - 4 * cm]
        table = Table(data, colWidths=col_w)
        table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, -1), C_HEADER_BG),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#aaaaaa")),
            ("ROWBACKGROUNDS",(0, 0), (-1, -1), [C_WHITE, C_ROW_ALT]),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ]))
        els.append(table)
        return els

    # ── Page header/footer ────────────────────────────────────────────────────

    def _page_header(self, canvas, doc):
        canvas.saveState()
        canvas.setFillColor(C_BLUE)
        canvas.rect(MARGIN, PAGE_H - 1.2 * cm, CONTENT_W, 0.7 * cm, fill=1, stroke=0)
        canvas.setFillColor(C_WHITE)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(MARGIN + 4, PAGE_H - 0.9 * cm, "DOCUMENTAZIONE DI RILASCIO")
        if self.department:
            canvas.setFont("Helvetica", 8)
            canvas.drawCentredString(PAGE_W / 2, PAGE_H - 0.9 * cm, self.department)
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 0.9 * cm, f"Pag. {doc.page}")
        canvas.restoreState()
