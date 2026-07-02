import json

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    asset_paradigm = fields.Selection(
        selection=[('standard', 'Standard')],
        string='Asset Paradigm',
        default=False,
        index=True,
        tracking=True,
        help="Governs which inventory UI elements are suppressed for this product. "
             "Set automatically by the asset type bridge; do not change manually.",
    )

    def is_element_suppressed(self, element_key):
        """Return True if element_key is actively suppressed for this product's asset_paradigm.

        Called by bridge computed fields to drive view invisible expressions.
        Returns False if no paradigm is set, if the debug param is enabled,
        or if no active rule exists for this paradigm + element_key combination.
        """
        self.ensure_one()
        if not self.asset_paradigm:
            return False
        debug = self.env['ir.config_parameter'].sudo().get_param(
            'sor_asset_paradigm.debug_show_quant_ui', 'False',
        ) == 'True'
        if debug:
            return False
        return bool(self.env['sor.asset.paradigm.rule'].search_count([
            ('paradigm', '=', self.asset_paradigm),
            ('element_key', '=', element_key),
            ('active', '=', True),
        ]))

    def _serialize_quant_snapshot(self):
        """Return a JSON string of current stock.quant rows for this product.

        Captured at the moment asset_paradigm changes, for audit purposes.
        """
        self.ensure_one()
        quants = self.env['stock.quant'].sudo().search([
            ('product_id', 'in', self.product_variant_ids.ids),
        ])
        snapshot = [
            {
                'location': q.location_id.complete_name,
                'lot': q.lot_id.name if q.lot_id else None,
                'quantity': q.quantity,
                'reserved_quantity': q.reserved_quantity,
            }
            for q in quants
        ]
        return json.dumps(snapshot)

    def write(self, vals):
        if 'asset_paradigm' in vals:
            for rec in self:
                # Guard removed once sor_asset_paradigm_log model is available (T-implement-change-log)
                if 'sor.asset.paradigm.log' in self.env:
                    self.env['sor.asset.paradigm.log'].sudo().create({
                        'product_tmpl_id': rec.id,
                        'old_paradigm': rec.asset_paradigm or '',
                        'new_paradigm': vals['asset_paradigm'] or '',
                        'changed_by': self.env.uid,
                        'changed_at': fields.Datetime.now(),
                        'quant_snapshot': rec._serialize_quant_snapshot(),
                    })
        return super().write(vals)
