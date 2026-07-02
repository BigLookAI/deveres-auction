import base64
import io

from PIL import (  # noqa: F401 — WebPImagePlugin import registers WEBP in Image.OPEN
    Image,
    WebPImagePlugin,
)

from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    logo_pdf = fields.Binary(
        compute='_compute_logo_pdf',
        store=False,
        help='PNG version of the company logo for use in PDF reports. '
             'wkhtmltopdf does not support WebP (the format Odoo 19 uses for '
             'stored images), so this field converts logo_web to PNG on demand.',
    )

    def _compute_logo_pdf(self):
        """Convert logo_web (WebP in Odoo 19) to PNG for wkhtmltopdf compatibility.

        wkhtmltopdf 0.12.6 does not support WebP images, which is the format
        Odoo 19 uses for all stored images. This method converts logo_web to PNG
        so the company logo renders correctly in PDF reports.

        bin_size=False is required: without it, PDF render requests (which carry
        bin_size=True in the HTTP context) cause Binary fields to return a
        human-readable size string (e.g. b'7.24 KB') instead of the actual image
        bytes.  base64.b64decode silently produces garbage from a size string,
        and PIL raises UnidentifiedImageError.  Forcing bin_size=False here
        ensures we always receive the real base64-encoded image bytes from the DB.
        """
        for company in self:
            data = company.with_context(bin_size=False).logo_web
            if not data:
                company.logo_pdf = False
                continue
            raw = base64.b64decode(data)
            img = Image.open(io.BytesIO(raw))
            buf = io.BytesIO()
            img.convert('RGBA').save(buf, format='PNG')
            company.logo_pdf = base64.b64encode(buf.getvalue())

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        for company in companies:
            self.env['ir.sequence'].create({
                'name': f'SOR Agreement ({company.name})',
                'code': 'sor.agreement',
                'prefix': 'AGR/%(year)s/',
                'padding': 5,
                'number_increment': 1,
                'number_next': 1,
                'company_id': company.id,
            })
        return companies
