from odoo import _, fields, models
from odoo.exceptions import UserError


class SorEvent(models.Model):
    _name = 'sor.event'
    _description = 'SOR Event'
    _order = 'date_start desc'
    _check_company_auto = True
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Event Name',
        required=True,
        tracking=True,
    )
    event_type = fields.Selection(
        selection=[
            ('exhibition', 'Exhibition'),
            ('auction', 'Auction'),
        ],
        string='Type',
        required=True,
        tracking=True,
    )
    status = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('published', 'Published'),
            ('active', 'Active'),
            ('closed', 'Closed'),
            ('archived', 'Archived'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
    )
    date_start = fields.Datetime(
        string='Start Date',
        required=True,
        tracking=True,
    )
    date_end = fields.Datetime(
        string='End Date',
        tracking=True,
    )
    venue_id = fields.Many2one(
        comodel_name='res.partner',
        string='Venue',
        domain=[('is_company', '=', True)],
        ondelete='restrict',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    notes = fields.Html(
        string='Internal Notes',
    )

    def action_publish(self):
        for event in self:
            if event.status != 'draft':
                raise UserError(_('Only Draft events can be published.'))
            event.status = 'published'
            event.message_post(body=_('Event published.'))

    def action_activate(self):
        for event in self:
            if event.status != 'published':
                raise UserError(_('Only Published events can be activated.'))
            event.status = 'active'
            event.message_post(body=_('Event activated.'))

    def action_close(self):
        for event in self:
            if event.status != 'active':
                raise UserError(_('Only Active events can be closed.'))
            event.status = 'closed'
            event.message_post(body=_('Event closed.'))

    def action_archive_event(self):
        for event in self:
            if event.status != 'closed':
                raise UserError(_('Only Closed events can be archived.'))
            event.status = 'archived'
            event.message_post(body=_('Event archived.'))
