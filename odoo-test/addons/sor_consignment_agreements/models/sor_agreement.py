from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SorAgreement(models.Model):
    _inherit = 'sor.agreement'

    agreement_type = fields.Selection(
        selection_add=[
            ('consignment_in', 'Consignment In'),
            ('consignment_out', 'Consignment Out'),
        ],
        ondelete={
            'consignment_in': 'set null',
            'consignment_out': 'set null',
        },
    )

    source_consignment_id = fields.Many2one(
        comodel_name='sor.agreement',
        string='Source Consignment',
        domain=[('agreement_type', '=', 'consignment_in')],
        help=(
            'The originating Consignment In agreement. For traceability only — '
            'does not link or inherit movements. Optional — standalone Out agreements are valid.'
        ),
    )

    move_ids = fields.One2many(
        comodel_name='stock.move',
        string='Product Lines',
        compute='_compute_move_ids',
        store=False,
    )

    sor_compound_status = fields.Char(
        string='Consignment Status',
        compute='_compute_sor_compound_status',
        store=False,
    )

    picking_count = fields.Integer(
        string='Movements',
        compute='_compute_picking_count',
        store=False,
    )

    @api.depends('picking_ids')
    def _compute_picking_count(self):
        for agreement in self:
            agreement.picking_count = len(agreement.picking_ids)

    @api.depends('picking_ids.move_ids')
    def _compute_move_ids(self):
        for agreement in self:
            agreement.move_ids = agreement.picking_ids.move_ids

    @api.depends('agreement_type', 'state')
    def _compute_sor_compound_status(self):
        for agreement in self:
            if agreement.agreement_type == 'consignment_in' and agreement.state == 'active':
                out_agreements = self.env['sor.agreement'].search([
                    ('source_consignment_id', '=', agreement.id),
                    ('agreement_type', '=', 'consignment_out'),
                ])
                confirmed = out_agreements.mapped('picking_ids').filtered(
                    lambda p: p.state == 'done',
                )
                if confirmed:
                    agreement.sor_compound_status = _('Active | Consigned out')
                    continue
            agreement.sor_compound_status = False

    def _get_partner_location(self, partner, direction):
        """Return the external location to use for a consignment counterparty.

        Default: Partners/External pool provisioned by sor_tracking.
        Override in sor_consignment_agreements_locations_external to check
        for a contact-linked external location first.

        Args:
            partner: res.partner recordset (consignor or consignee)
            direction: 'in' (artwork arriving) or 'out' (artwork leaving)
        Returns:
            stock.location recordset (single record)
        Raises:
            UserError if the Partners/External pool is not found for this company
        """
        self.ensure_one()
        location = self.env['stock.location'].search([
            ('name', '=', 'Partners/External'),
            ('company_id', '=', self.company_id.id),
            ('usage', '=', 'internal'),
        ], limit=1)
        if not location:
            raise UserError(_(
                'Partners/External pool location not found for company %(company)s. '
                'Ensure sor_tracking is installed and has been initialised.',
                company=self.company_id.name,
            ))
        return location

    def action_view_movements(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Movements'),
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('agreement_id', '=', self.id)],
            'context': {'default_agreement_id': self.id},
        }

    def write(self, vals):
        """Replace (2) delete commands on picking_ids with (3) disconnect commands.

        When OWL removes a picking from the Linked Movements list (trash icon),
        it issues (2, id, 0) commands which call picking.unlink() — blocked by the
        guard that prevents deletion of agreement-linked pickings. The correct
        semantic for removing from this list is unlink (set agreement_id = False),
        not delete. Command (3) achieves this without calling unlink().
        """
        if 'picking_ids' in vals:
            new_cmds = []
            for cmd in vals['picking_ids']:
                if cmd[0] == 2:
                    new_cmds.append((3, cmd[1], 0))
                else:
                    new_cmds.append(cmd)
            vals = dict(vals, picking_ids=new_cmds)
        return super().write(vals)

    def action_send_for_signature(self):
        """Override: gate consignment agreements on having at least one linked movement.

        A consignment sent for signature with no linked movements covers no items —
        this is operationally inconsistent. Base agreements are unaffected.
        """
        for agreement in self:
            if agreement.agreement_type in ('consignment_in', 'consignment_out'):
                if not agreement.picking_ids:
                    raise UserError(_(
                        'Cannot send "%s" for signature: no movements are linked. '
                        'Link at least one intake or release movement before sending '
                        'this consignment agreement for signature.',
                        agreement.name,
                    ))
        return super().action_send_for_signature()

    def action_create_intake(self):
        """Create a Receipt (MVI) intake picking for a Consignment In agreement.

        Guard: only valid in Draft state — the picking is pre-created before the
        agreement is signed so the movement scope is fixed at countersigning time.
        """
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_(
                'An intake can only be created against a Consignment In agreement '
                'that is in Draft state. '
                'The agreement "%s" is currently %s.',
                self.name,
                dict(self._fields['state'].selection)[self.state],
            ))

        # Explicit MVI picking type lookup — Partners/External pool has usage='internal';
        # _sor_infer_picking_type_id would produce MVT (Internal Transfer), not MVI.
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'incoming'),
            ('warehouse_id.company_id', '=', self.company_id.id),
            ('warehouse_id.active', '=', True),
        ], limit=1)
        if not picking_type:
            raise UserError(_(
                'No Receipt operation type found for company "%s". '
                'Please check your warehouse configuration.',
                self.company_id.name,
            ))

        source_location = self._get_partner_location(self.primary_partner_id, 'in')
        dest_location = picking_type.default_location_dest_id

        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': source_location.id,
            'location_dest_id': dest_location.id,
            'partner_id': self.primary_partner_id.id,
            'agreement_id': self.id,
            'company_id': self.company_id.id,
            'move_ids': [
                (0, 0, {
                    'product_id': line.product_id.product_variant_id.id,
                    'product_uom_qty': 1,
                    'product_uom': line.product_id.uom_id.id,
                    'location_id': source_location.id,
                    'location_dest_id': dest_location.id,
                    'company_id': self.company_id.id,
                })
                for line in self.line_ids
            ],
        })

        self.invalidate_recordset(['picking_ids', 'move_ids', 'picking_count'])

        return {
            'type': 'ir.actions.act_window',
            'name': _('Intake Movement'),
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_link_existing_intake(self):
        """Open a filtered list of receipt pickings for retrospective agreement linking.

        Allows staff to link an existing picking to a Consignment In agreement
        when artwork was received before the paperwork was completed.
        """
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_(
                'Existing intakes can only be linked to a Consignment In agreement '
                'in Draft state.',
            ))
        link_list_view = self.env.ref(
            'sor_consignment_agreements.view_picking_link_dialog_list',
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Link Existing Intake'),
            'res_model': 'stock.picking',
            'view_mode': 'list',
            'views': [(link_list_view.id, 'list')],
            'domain': [
                ('picking_type_id.code', '=', 'incoming'),
                ('company_id', '=', self.company_id.id),
                ('agreement_id', '=', False),
            ],
            'context': {
                'default_agreement_id': self.id,
                'create': False,
            },
            'target': 'new',
        }

    def action_create_release(self):
        """Create a Dispatch (MVO) release picking for a Consignment Out agreement.

        Guard: only valid in Draft state — the picking is pre-created before the
        agreement is signed.
        """
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_(
                'A release can only be created against a Consignment Out agreement '
                'that is in Draft state. '
                'The agreement "%s" is currently %s.',
                self.name,
                dict(self._fields['state'].selection)[self.state],
            ))

        # Explicit MVO picking type lookup — Partners/External has usage='internal';
        # _sor_infer_picking_type_id would produce MVT, not MVO.
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'outgoing'),
            ('warehouse_id.company_id', '=', self.company_id.id),
            ('warehouse_id.active', '=', True),
        ], limit=1)
        if not picking_type:
            raise UserError(_(
                'No Delivery Orders operation type found for company "%s". '
                'Please check your warehouse configuration.',
                self.company_id.name,
            ))

        dest_location = self._get_partner_location(self.primary_partner_id, 'out')
        src_location = picking_type.default_location_src_id

        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': src_location.id,
            'location_dest_id': dest_location.id,
            'partner_id': self.primary_partner_id.id,
            'agreement_id': self.id,
            'company_id': self.company_id.id,
            'move_ids': [
                (0, 0, {
                    'product_id': line.product_id.product_variant_id.id,
                    'product_uom_qty': 1,
                    'product_uom': line.product_id.uom_id.id,
                    'location_id': src_location.id,
                    'location_dest_id': dest_location.id,
                    'company_id': self.company_id.id,
                })
                for line in self.line_ids
            ],
        })

        self.invalidate_recordset(['picking_ids', 'move_ids', 'picking_count'])

        return {
            'type': 'ir.actions.act_window',
            'name': _('Release Movement'),
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_link_existing_release(self):
        """Open a filtered list of dispatch pickings for retrospective agreement linking.

        Allows staff to link an existing picking to a Consignment Out agreement
        when artwork was dispatched before the paperwork was completed.
        """
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_(
                'Existing releases can only be linked to a Consignment Out agreement '
                'in Draft state.',
            ))
        link_list_view = self.env.ref(
            'sor_consignment_agreements.view_picking_link_dialog_list',
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Link Existing Release'),
            'res_model': 'stock.picking',
            'view_mode': 'list',
            'views': [(link_list_view.id, 'list')],
            'domain': [
                ('picking_type_id.code', '=', 'outgoing'),
                ('company_id', '=', self.company_id.id),
                ('agreement_id', '=', False),
            ],
            'context': {
                'default_agreement_id': self.id,
                'create': False,
            },
            'target': 'new',
        }
