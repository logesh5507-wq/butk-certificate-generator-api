from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfgen import canvas


def create_certificate_pdf(
    output_path: Path,
    recipient_name: str,
    course: str,
    event_name: str,
    issue_date: str,
    organization: str,
) -> None:
    """Create one simple landscape PDF certificate using a fixed, predefined template."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    page_width, page_height = landscape(A4)
    pdf = canvas.Canvas(str(output_path), pagesize=(page_width, page_height))
    pdf.setTitle(f"Certificate - {recipient_name}")
    margin = 28
    pdf.setStrokeColor(colors.HexColor("#244a73"))
    pdf.setLineWidth(3)
    pdf.rect(margin, margin, page_width - 2 * margin, page_height - 2 * margin)
    pdf.setStrokeColor(colors.HexColor("#c59d48"))
    pdf.setLineWidth(1)
    pdf.rect(margin + 9, margin + 9, page_width - 2 * (margin + 9), page_height - 2 * (margin + 9))

    pdf.setFillColor(colors.HexColor("#244a73"))
    pdf.setFont("Helvetica-Bold", 27)
    pdf.drawCentredString(page_width / 2, page_height - 95, "CERTIFICATE OF COMPLETION")
    pdf.setFillColor(colors.HexColor("#555555"))
    pdf.setFont("Helvetica", 13)
    pdf.drawCentredString(page_width / 2, page_height - 135, "This certificate is proudly presented to")

    pdf.setFillColor(colors.HexColor("#172b4d"))
    pdf.setFont("Helvetica-Bold", 30)
    pdf.drawCentredString(page_width / 2, page_height - 185, recipient_name[:70])

    pdf.setFillColor(colors.HexColor("#333333"))
    pdf.setFont("Helvetica", 13)
    pdf.drawCentredString(page_width / 2, page_height - 225, "for successfully completing")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawCentredString(page_width / 2, page_height - 255, course[:90])
    pdf.setFont("Helvetica", 12)
    pdf.drawCentredString(page_width / 2, page_height - 282, f"Event: {event_name[:100]}")
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawCentredString(page_width / 2, 86, organization[:100])
    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(page_width / 2, 65, f"Issued on {issue_date}")
    pdf.save()
