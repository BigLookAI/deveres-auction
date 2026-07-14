from odoo import api, models


class SorLot(models.Model):
    _inherit = 'sor.lot'

    def _assign_consignor_subtype(self):
        """Assign the Consignor earned sub-type to consignor_id partners.

        Idempotent — does not assign duplicates. Does not remove the sub-type
        when consignor_id changes. sor_contact_roles is guaranteed to be
        installed as a module dependency.
        """
        consignor_subtype = self.env['sor.contact.type'].search(
            [('code', '=', 'consignor'), ('parent_type_id', '!=', False)],
            limit=1,
        )
        if not consignor_subtype:
            return
        for lot in self:
            if not lot.consignor_id:
                continue
            partner = lot.consignor_id
            if consignor_subtype not in partner.contact_subtypes:
                partner.contact_subtypes = [(4, consignor_subtype.id)]

    def _assign_buyer_subtype(self):
        """Assign the Buyer earned sub-type to buyer_id partners.

        Idempotent — does not assign duplicates. Does not remove the sub-type
        when buyer_id changes. Assigns the Contact parent type automatically
        alongside the Buyer sub-type. Only meaningful in deployments without
        sor_bidding; when sor_bidding is installed, buyer_id is hidden from
        the lot form and this method is a no-op.
        """
        buyer_subtype = self.env['sor.contact.type'].search(
            [('code', '=', 'buyer'), ('parent_type_id', '!=', False)],
            limit=1,
        )
        if not buyer_subtype:
            return
        contact_type = self.env['sor.contact.type'].search(
            [('code', '=', 'contact'), ('parent_type_id', '=', False)],
            limit=1,
        )
        for lot in self:
            if not lot.buyer_id:
                continue
            partner = lot.buyer_id
            if contact_type and contact_type not in partner.contact_types:
                partner.contact_types = [(4, contact_type.id)]
            if buyer_subtype not in partner.contact_subtypes:
                partner.contact_subtypes = [(4, buyer_subtype.id)]

    @api.model_create_multi
    def create(self, vals_list):
        lots = super().create(vals_list)
        lots._assign_consignor_subtype()
        lots._assign_buyer_subtype()
        return lots

    def write(self, vals):
        result = super().write(vals)
        if 'consignor_id' in vals:
            self._assign_consignor_subtype()
        if 'buyer_id' in vals:
            self._assign_buyer_subtype()
        return result
