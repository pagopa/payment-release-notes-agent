"""PDF Exporter"""

import logging
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from src.models import RiskLevel

logger = logging.getLogger(__name__)


class NumberedCanvas(canvas.Canvas):
    """Canvas class to add page numbers"""
    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_content_object = None

    def showPage(self):
        self._saved_content_object = self._contentobject
        self._contentobject = canvas.ContentObject()
        
    def save(self):
        num_pages = self.getPageNumber()
        for page_num in range(1, num_pages + 1):
            self.setPageCompression(0)
            self.setFont("Helvetica", 9)
            self.drawRightString(7.5*inch, 0.5*inch, f"Page {page_num} of {num_pages}")
        canvas.Canvas.save(self)


class PDFExporter:
    """Export release notes to PDF"""
    
    def __init__(self, title="Release Notes", author="Release Notes Agent"):
        self.title = title
        self.author = author
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Setup custom paragraph styles"""
        # Title style
        self.styles.add(ParagraphStyle(
            name='CustomHeading1',
            parent=self.styles['Heading1'],
            fontSize=28,
            textColor=colors.HexColor('#1f77b4'),
            spaceAfter=12,
            spaceBefore=12,
            alignment=1,  # Center
        ))
        
        # Section heading style
        self.styles.add(ParagraphStyle(
            name='CustomHeading2',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.white,
            spaceAfter=10,
            spaceBefore=10,
            backColor=colors.HexColor('#2ca02c'),
            leftIndent=6,
            rightIndent=6,
            topPadding=4,
            bottomPadding=4,
        ))
        
        # Risk section styles
        self.styles.add(ParagraphStyle(
            name='RiskCritical',
            parent=self.styles['Heading2'],
            fontSize=12,
            textColor=colors.white,
            backColor=colors.HexColor('#d62728'),
            leftIndent=6,
            rightIndent=6,
        ))
        
        self.styles.add(ParagraphStyle(
            name='RiskHigh',
            parent=self.styles['Heading2'],
            fontSize=12,
            textColor=colors.white,
            backColor=colors.HexColor('#ff7f0e'),
            leftIndent=6,
            rightIndent=6,
        ))
        
        self.styles.add(ParagraphStyle(
            name='RiskMedium',
            parent=self.styles['Heading2'],
            fontSize=12,
            textColor=colors.white,
            backColor=colors.HexColor('#ffbb78'),
            leftIndent=6,
            rightIndent=6,
        ))
        
        # Subsection heading style
        self.styles.add(ParagraphStyle(
            name='CustomHeading3',
            parent=self.styles['Heading3'],
            fontSize=12,
            textColor=colors.HexColor('#1f77b4'),
            spaceAfter=8,
            spaceBefore=8,
        ))
        
        # Change item style
        self.styles.add(ParagraphStyle(
            name='ChangeItem',
            parent=self.styles['BodyText'],
            fontSize=10,
            spaceAfter=8,
            leftIndent=20,
            bulletIndent=10,
        ))
        
        # Summary style
        self.styles.add(ParagraphStyle(
            name='SummaryText',
            parent=self.styles['BodyText'],
            fontSize=11,
            spaceAfter=12,
            textColor=colors.HexColor('#333333'),
        ))
        
        # Metadata style
        self.styles.add(ParagraphStyle(
            name='MetadataText',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#666666'),
            leftIndent=20,
        ))
    
    def export(self, release_notes, filepath: str):
        """Export release notes to PDF
        
        Args:
            release_notes: ReleaseNotes object
            filepath: Output file path
        """
        doc = SimpleDocTemplate(
            filepath,
            pagesize=letter,
            title=self.title,
            author=self.author,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch,
            leftMargin=0.75*inch,
            rightMargin=0.75*inch,
        )
        
        story = []
        
        # === TITLE PAGE ===
        story.append(Spacer(1, 0.5*inch))
        
        # Main title
        story.append(Paragraph(release_notes.title, self.styles['CustomHeading1']))
        story.append(Spacer(1, 0.1*inch))
        
        # Subtitle with PR info
        if release_notes.pr_number:
            subtitle = f"Pull Request #{release_notes.pr_number}"
            story.append(Paragraph(subtitle, self.styles['Heading3']))
        
        story.append(Spacer(1, 0.3*inch))
        
        # === RISK LEVEL INDICATOR ===
        risk_color = self._get_risk_color(release_notes.overall_risk_level)
        risk_style = {
            RiskLevel.CRITICAL: self.styles['RiskCritical'],
            RiskLevel.HIGH: self.styles['RiskHigh'],
            RiskLevel.MEDIUM: self.styles['RiskMedium'],
        }.get(release_notes.overall_risk_level, self.styles['CustomHeading2'])
        
        risk_emoji = {
            RiskLevel.CRITICAL: "🚨",
            RiskLevel.HIGH: "⚠️",
            RiskLevel.MEDIUM: "⚡",
            RiskLevel.LOW: "✅",
        }.get(release_notes.overall_risk_level, "ℹ️")
        
        story.append(Paragraph(f"{risk_emoji} Overall Risk Level: {release_notes.overall_risk_level.value.upper()}", risk_style))
        story.append(Spacer(1, 0.2*inch))
        
        # === METADATA TABLE ===
        metadata = [
            ["Release Version:", release_notes.version],
            ["Release Date:", release_notes.release_date.strftime('%B %d, %Y at %H:%M:%S')],
            ["PR URL:", release_notes.pr_url],
        ]
        
        metadata_table = Table(metadata, colWidths=[1.8*inch, 4.2*inch])
        metadata_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f4f8')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#cccccc')),
        ]))
        
        story.append(metadata_table)
        story.append(Spacer(1, 0.3*inch))
        
        # === STATISTICS SECTION ===
        story.append(Paragraph("📊 Statistics", self.styles['CustomHeading2']))
        
        stats_data = [
            ["Total Changes", str(release_notes.total_changes)],
            ["Files Changed", str(release_notes.files_changed)],
            ["Lines Added", f"+{release_notes.additions}"],
            ["Lines Deleted", f"-{release_notes.deletions}"],
        ]
        
        stats_table = Table(stats_data, colWidths=[2.5*inch, 2.5*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2ca02c')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f0f0f0')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#cccccc')),
        ]))
        
        story.append(stats_table)
        story.append(Spacer(1, 0.3*inch))
        
        # === SUMMARY SECTION ===
        if release_notes.summary:
            story.append(Paragraph("📝 Summary", self.styles['CustomHeading2']))
            story.append(Paragraph(release_notes.summary, self.styles['SummaryText']))
            story.append(Spacer(1, 0.2*inch))
        
        # === CHANGES CONTENT ===
        story.append(PageBreak())
        story.append(Paragraph("📋 Changes & Risk Assessment", self.styles['Heading2']))
        story.append(Spacer(1, 0.2*inch))
        
        # Breaking Changes
        if release_notes.breaking_changes:
            story.append(Paragraph("🚨 Breaking Changes", self.styles['CustomHeading2']))
            for change in release_notes.breaking_changes:
                story.extend(self._build_change_detail(change))
            story.append(Spacer(1, 0.2*inch))
        
        # Features
        if release_notes.features:
            story.append(Paragraph("✨ Features", self.styles['CustomHeading2']))
            for change in release_notes.features:
                story.extend(self._build_change_detail(change))
            story.append(Spacer(1, 0.2*inch))
        
        # Bug Fixes
        if release_notes.bugfixes:
            story.append(Paragraph("🐛 Bug Fixes", self.styles['CustomHeading2']))
            for change in release_notes.bugfixes:
                story.extend(self._build_change_detail(change))
            story.append(Spacer(1, 0.2*inch))
        
        # Security Fixes
        if release_notes.security_fixes:
            story.append(Paragraph("🔒 Security", self.styles['CustomHeading2']))
            for change in release_notes.security_fixes:
                story.extend(self._build_change_detail(change))
            story.append(Spacer(1, 0.2*inch))
        
        # Performance Improvements
        if release_notes.performance_improvements:
            story.append(Paragraph("⚡ Performance Improvements", self.styles['CustomHeading2']))
            for change in release_notes.performance_improvements:
                story.extend(self._build_change_detail(change))
            story.append(Spacer(1, 0.2*inch))
        
        # Documentation
        if release_notes.documentation:
            story.append(Paragraph("📚 Documentation", self.styles['CustomHeading2']))
            for change in release_notes.documentation:
                story.extend(self._build_change_detail(change))
            story.append(Spacer(1, 0.2*inch))
        
        # Refactoring
        if release_notes.refactoring:
            story.append(Paragraph("🔧 Refactoring", self.styles['CustomHeading2']))
            for change in release_notes.refactoring:
                story.extend(self._build_change_detail(change))
            story.append(Spacer(1, 0.2*inch))
        
        # Chores
        if release_notes.chores:
            story.append(Paragraph("🧹 Chores", self.styles['CustomHeading2']))
            for change in release_notes.chores:
                story.extend(self._build_change_detail(change))
            story.append(Spacer(1, 0.2*inch))
        
        # === CONTRIBUTORS PAGE ===
        if release_notes.contributors:
            story.append(PageBreak())
            story.append(Paragraph("👥 Contributors", self.styles['CustomHeading2']))
            story.append(Spacer(1, 0.2*inch))
            
            contributors_data = [["Name", "Contributions"]]
            for contributor in release_notes.contributors:
                contributors_data.append([
                    contributor.name,
                    str(contributor.contributions)
                ])
            
            contributors_table = Table(contributors_data, colWidths=[3*inch, 2*inch])
            contributors_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2ca02c')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f9f9f9')),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#cccccc')),
            ]))
            
            story.append(contributors_table)
        
        # Build PDF
        doc.build(story, onFirstPage=self._add_header, onLaterPages=self._add_header)
        logger.info(f"PDF exported to: {filepath}")
        return filepath
    
    def _build_change_detail(self, change):
        """Build detailed change information with risk assessment
        
        Returns a list of flowable elements
        """
        elements = []
        
        # Change title
        elements.append(Paragraph(f"<b>{change.title}</b>", self.styles['ChangeItem']))
        
        # Change description
        if change.description:
            elements.append(Paragraph(change.description, self.styles['MetadataText']))
        
        # Commit info
        elements.append(Paragraph(f"<i>Commit: {change.commit_hash[:7] if change.commit_hash else 'N/A'} by {change.author}</i>", self.styles['MetadataText']))
        
        # File changes
        if change.files:
            elements.append(Paragraph("<u>Files Changed:</u>", self.styles['MetadataText']))
            for file in change.files[:5]:  # Show max 5 files
                elements.append(Paragraph(f"• {file.path} ({file.status})", self.styles['MetadataText']))
            if len(change.files) > 5:
                elements.append(Paragraph(f"• ... and {len(change.files) - 5} more files", self.styles['MetadataText']))
        
        # Risk assessment
        if change.risk_assessment:
            elements.append(Spacer(1, 0.1*inch))
            risk_level = change.risk_assessment.risk_level
            risk_emoji = {
                RiskLevel.CRITICAL: "🚨",
                RiskLevel.HIGH: "⚠️",
                RiskLevel.MEDIUM: "⚡",
                RiskLevel.LOW: "✅",
            }.get(risk_level, "ℹ️")
            
            elements.append(Paragraph(f"<b>{risk_emoji} Risk: {risk_level.value.upper()}</b>", self.styles['MetadataText']))
            
            if change.risk_assessment.risk_factors:
                elements.append(Paragraph("<u>Risk Factors:</u>", self.styles['MetadataText']))
                for factor in change.risk_assessment.risk_factors[:3]:
                    elements.append(Paragraph(f"• {factor}", self.styles['MetadataText']))
            
            if change.risk_assessment.affected_components:
                elements.append(Paragraph("<u>Affected Components:</u>", self.styles['MetadataText']))
                components = ", ".join([c.value for c in change.risk_assessment.affected_components[:3]])
                elements.append(Paragraph(f"• {components}", self.styles['MetadataText']))
            
            if change.risk_assessment.testing_recommendations:
                elements.append(Paragraph("<u>Testing Recommendations:</u>", self.styles['MetadataText']))
                for rec in change.risk_assessment.testing_recommendations[:2]:
                    elements.append(Paragraph(f"• {rec}", self.styles['MetadataText']))
            
            if change.risk_assessment.deployment_notes:
                elements.append(Paragraph(f"<b>Deployment Notes:</b> {change.risk_assessment.deployment_notes}", self.styles['MetadataText']))
        
        elements.append(Spacer(1, 0.2*inch))
        
        return elements
    
    def _get_risk_color(self, risk_level: RiskLevel) -> str:
        """Get color for risk level"""
        colors_map = {
            RiskLevel.CRITICAL: '#d62728',
            RiskLevel.HIGH: '#ff7f0e',
            RiskLevel.MEDIUM: '#ffbb78',
            RiskLevel.LOW: '#2ca02c',
        }
        return colors_map.get(risk_level, '#cccccc')
    
    def _add_header(self, canvas, doc):
        """Add header to each page"""
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 10)
        canvas.setFillColor(colors.HexColor('#1f77b4'))
        canvas.drawString(0.75*inch, letter[1] - 0.5*inch, self.title)
        canvas.restoreState()
