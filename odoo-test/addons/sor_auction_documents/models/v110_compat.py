# ── LOCAL 19.0.1.1.0 RECONSTRUCTION (Cimelium, 2-Jul-2026) ────────────────────
# The April-test database was created by sor_auction_documents 19.0.1.1.0;
# available source is 19.0.1.0.0. Recovered from ir_model_fields + stored view
# archs: consignor company / receipt number / VAT-margin snapshots on the lot,
# the settings toggle, and the pending-document smart-button counters on the
# auction event form.
from odoo import fields, models


class SorLotDocsV110(models.Model):
    _inherit = 'sor.lot'

    consignor_company = fields.Char(string='Consignor Company')
    sor_receipt_number = fields.Char(string='SOR Receipt Number', copy=False)
    vat_margin_scheme = fields.Boolean(string='VAT Margin Scheme')


class ResConfigSettingsDocsV110(models.TransientModel):
    _inherit = 'res.config.settings'

    vat_margin_scheme = fields.Boolean(
        related='company_id.vat_margin_scheme', readonly=False,
        string='VAT Margin Scheme')


class SorEventDocsV110(models.Model):
    _inherit = 'sor.event'

    psa_pending_count = fields.Integer(compute='_compute_doc_pending_counts')
    posa_pending_count = fields.Integer(compute='_compute_doc_pending_counts')
    vss_pending_count = fields.Integer(compute='_compute_doc_pending_counts')

    def _compute_doc_pending_counts(self):
        Lot = self.env['sor.lot']
        for event in self:
            lots = Lot.search([('auction_id', '=', event.id)]) if event.id else Lot
            event.psa_pending_count = sum(1 for l in lots if not l.pre_sale_advice_id)
            event.posa_pending_count = sum(1 for l in lots if not l.post_sale_advice_id)
            event.vss_pending_count = sum(1 for l in lots if not l.vendor_settlement_id)
