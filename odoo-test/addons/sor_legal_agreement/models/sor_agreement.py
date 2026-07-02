import base64
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SorAgreement(models.Model):
    _name = 'sor.agreement'
    _description = 'SOR Agreement'
    _order = 'name desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        default='New Agreement',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    agreement_type = fields.Selection(
        selection=[('base', 'Base Agreement')],
        string='Agreement Type',
    )
    primary_partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Counterparty',
        check_company=True,
    )
    date_start = fields.Date(string='Effective Date')
    date_end = fields.Date(string='End Date')
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('pending_signature', 'Pending Signature'),
            ('active', 'Active'),
            ('closed', 'Closed'),
            ('revoked', 'Revoked'),
        ],
        string='State',
        default='draft',
        required=True,
        copy=False,
        tracking=True,
    )
    terms = fields.Html(string='Terms and Conditions')
    notes = fields.Text(string='Internal Notes')
    line_ids = fields.One2many(
        comodel_name='sor.agreement.line',
        inverse_name='agreement_id',
        string='Lines',
        copy=True,
    )
    picking_ids = fields.One2many(
        comodel_name='stock.picking',
        inverse_name='agreement_id',
        string='Stock Movements',
    )
    supersedes_id = fields.Many2one(
        comodel_name='sor.agreement',
        string='Supersedes',
        copy=False,
        readonly=True,
        help='The agreement this record replaces after a Rescind action.',
    )
    superseded_by_id = fields.Many2one(
        comodel_name='sor.agreement',
        string='Superseded By',
        compute='_compute_superseded_by_id',
        store=False,
    )
    date_sent_for_signature = fields.Date(
        string='Sent for Signature',
        copy=False,
        readonly=True,
    )
    is_stale = fields.Boolean(
        string='Overdue',
        compute='_compute_is_stale',
        search='_search_is_stale',
        store=False,
    )
    stale_indicator = fields.Html(
        string='',
        compute='_compute_stale_indicator',
        sanitize=False,
        store=False,
    )
    last_stale_notified = fields.Date(
        string='Stale Notification Sent',
        copy=False,
        readonly=True,
    )

    def _search_is_stale(self, operator, value):
        today = fields.Date.today()
        threshold_sent = today - timedelta(days=14)
        threshold_end = today + timedelta(days=7)
        stale_domain = [
            ('state', '=', 'pending_signature'),
            '|',
            '&', ('date_sent_for_signature', '!=', False), ('date_sent_for_signature', '<', threshold_sent),
            '&', ('date_end', '!=', False), ('date_end', '<=', threshold_end),
        ]
        # Odoo 19 normalizes '='/'!=' to 'in'/'not in' with an OrderedSet before invoking
        # search methods. Unwrap to canonical form so the condition check below works.
        if operator == 'in':
            operator, value = '=', (True in value)
        elif operator == 'not in':
            operator, value = '!=', (True in value)
        if (operator == '=' and value) or (operator == '!=' and not value):
            return stale_domain
        return ['!'] + stale_domain

    @api.depends('state', 'date_sent_for_signature', 'date_end')
    def _compute_is_stale(self):
        today = fields.Date.today()
        threshold_sent = today - timedelta(days=14)
        threshold_end = today + timedelta(days=7)
        for rec in self:
            if rec.state != 'pending_signature':
                rec.is_stale = False
                continue
            stale_by_age = bool(rec.date_sent_for_signature) and rec.date_sent_for_signature < threshold_sent
            stale_by_date = bool(rec.date_end) and rec.date_end <= threshold_end
            rec.is_stale = stale_by_age or stale_by_date

    @api.depends('state', 'date_sent_for_signature', 'date_end')
    def _compute_stale_indicator(self):
        icon = '<i class="fa fa-exclamation-triangle text-warning" title="Overdue for signature"/>'
        for rec in self:
            rec.stale_indicator = icon if rec.is_stale else ''

    def _compute_superseded_by_id(self):
        for rec in self:
            rec.superseded_by_id = self.search([('supersedes_id', '=', rec.id)], limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New Agreement') == 'New Agreement':
                company = self.env['res.company'].browse(
                    vals.get('company_id', self.env.company.id),
                )
                vals['name'] = (
                    self.env['ir.sequence'].with_company(company).next_by_code('sor.agreement')
                    or 'New Agreement'
                )
        records = super().create(vals_list)
        records.filtered(lambda a: a.state == 'draft')._generate_draft_pdf()
        return records

    def _check_can_trigger_movement(self):
        """Bridge contract: call this before creating any stock.picking for this agreement.

        Raises UserError if any record in self is not in 'active' state.
        Bridges must call this method before creating pickings to enforce the
        agreement-first principle: no physical movement before a signed agreement.
        """
        for record in self:
            if record.state != 'active':
                raise UserError(
                    _('Movement cannot be triggered: the agreement "%s" must be Active.')
                    % record.name,
                )

    def write(self, vals):
        result = super().write(vals)
        self.filtered(lambda a: a.state == 'draft')._generate_draft_pdf()
        return result

    def _generate_draft_pdf(self):
        report = self.env.ref('sor_legal_agreement.action_report_sor_agreement')
        for agreement in self:
            pdf_content, _mime = report._render_qweb_pdf(
                'sor_legal_agreement.action_report_sor_agreement',
                res_ids=[agreement.id],
            )
            draft_name = f'{agreement.name} (Draft).pdf'
            self.env['ir.attachment'].search([
                ('res_model', '=', agreement._name),
                ('res_id', '=', agreement.id),
                ('name', '=', draft_name),
            ]).unlink()
            self.env['ir.attachment'].create({
                'name': draft_name,
                'type': 'binary',
                'datas': base64.b64encode(pdf_content),
                'res_model': agreement._name,
                'res_id': agreement.id,
                'mimetype': 'application/pdf',
            })

    def unlink(self):
        """Only Draft agreements may be deleted.

        Once an agreement has been sent for signature, it has legal significance
        and must not be deleted. Non-draft agreements should be closed or archived
        instead.
        """
        for record in self:
            if record.state != 'draft':
                raise UserError(
                    _('Agreement "%s" cannot be deleted because it is %s. '
                      'Only Draft agreements may be deleted.')
                    % (record.name, dict(self._fields['state'].selection)[record.state]),
                )
        return super().unlink()

    def action_send_for_signature(self):
        """Transition the agreement from Draft to Pending Signature.

        Generates a final PDF, removes the draft preview attachment, attaches
        the final PDF, transitions to Pending Signature, and sets date_sent_for_signature.
        """
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(
                _('Only a Draft agreement can be sent for signature.'),
            )
        report = self.env.ref('sor_legal_agreement.action_report_sor_agreement')
        pdf_content, _mime = report._render_qweb_pdf(
            'sor_legal_agreement.action_report_sor_agreement', res_ids=self.ids,
        )
        self.env['ir.attachment'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('name', '=', f'{self.name} (Draft).pdf'),
        ]).unlink()
        self.env['ir.attachment'].create({
            'name': f'{self.name}.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })
        self.write({
            'state': 'pending_signature',
            'date_sent_for_signature': fields.Date.today(),
        })
        self.message_post(body=_('Sent for signature. PDF attached.'))

    def action_confirm_signed(self):
        """Transition the agreement from Pending Signature to Active.

        Once Active, bridge modules may trigger physical movements against this
        agreement by calling _check_can_trigger_movement() before creating pickings.
        """
        self.ensure_one()
        if self.state != 'pending_signature':
            raise UserError(
                _('Only an agreement in Pending Signature state can be confirmed as signed.'),
            )
        self.write({'state': 'active'})
        self.message_post(
            body=_('Agreement confirmed as signed. Movements may now be triggered.'),
        )

    def action_close(self):
        """Transition the agreement from Active to Closed.

        Closed is a terminal state. No further state transitions are possible
        from this base module. Bridge modules must not add a re-open transition
        without explicit PO approval.
        """
        self.ensure_one()
        if self.state != 'active':
            raise UserError(
                _('Only an Active agreement can be closed.'),
            )
        self.write({'state': 'closed'})
        self.message_post(body=_('Agreement closed.'))

    def action_rescind(self):
        """Void this agreement and create a new Draft replacement.

        The original moves to Revoked. The replacement is a copy with a new
        system-generated reference and a supersedes_id link back to this record.
        """
        self.ensure_one()
        if self.state not in ('pending_signature', 'active'):
            raise UserError(
                _('Only a Pending Signature or Active agreement can be rescinded.'),
            )
        self.write({'state': 'revoked'})
        self.message_post(body=_('Agreement rescinded. A replacement draft has been created.'))
        replacement = self.copy({
            'state': 'draft',
            'supersedes_id': self.id,
            'name': 'New Agreement',
        })
        replacement.message_post(
            body=_('This agreement replaces %(original)s, which was rescinded.', original=self.name),
        )
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': replacement.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _action_notify_stale_agreements(self):
        today = fields.Date.today()
        stale = self.search([
            ('state', '=', 'pending_signature'),
            ('last_stale_notified', '=', False),
            '|',
            ('date_sent_for_signature', '<', today - timedelta(days=14)),
            ('date_end', '<=', today + timedelta(days=7)),
        ])
        for agreement in stale:
            follower_partner_ids = agreement.message_follower_ids.mapped('partner_id').ids
            agreement.message_post(
                body=_(
                    'This agreement is overdue for signature. '
                    'Please follow up with the counterparty.',
                ),
                message_type='comment',
                subtype_xmlid='mail.mt_note',
                partner_ids=follower_partner_ids,
            )
            agreement.last_stale_notified = today
