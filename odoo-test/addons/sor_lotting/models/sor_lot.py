from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SorLot(models.Model):
    _name = 'sor.lot'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'SOR Lot'
    _rec_name = 'lot_reference'
    _order = 'lot_reference asc'
    _check_company_auto = True

    # Identification
    lot_reference = fields.Char(
        string='Lot Reference',
        required=True,
        copy=False,
        readonly=True,
        default='New Lot',
        index=True,
    )
    lot_number = fields.Char(
        string='Lot Number',
        size=10,
    )
    product_id = fields.Many2one(
        comodel_name='product.template',
        string='Product',
        domain=[('type', 'not in', ('service',))],
    )
    lot_title = fields.Char(string='Lot Title')
    lot_description = fields.Html(string='Lot Description')
    lot_item_name = fields.Char(
        string='Item',
        compute='_compute_lot_item_name',
        store=False,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )

    # Currency (required for Monetary fields)
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        related='company_id.currency_id',
        store=True,
    )

    # Financial
    estimate_low = fields.Monetary(
        string='Low Estimate',
        currency_field='currency_id',
    )
    estimate_high = fields.Monetary(
        string='High Estimate',
        currency_field='currency_id',
    )
    reserve_price = fields.Monetary(
        string='Reserve Price',
        currency_field='currency_id',
    )
    no_reserve = fields.Boolean(
        string='No Reserve',
        default=False,
    )
    starting_bid = fields.Monetary(
        string='Starting Bid',
        currency_field='currency_id',
    )
    hammer_price = fields.Monetary(
        string='Hammer Price',
        currency_field='currency_id',
    )
    break_even_value = fields.Monetary(
        string='Break-Even Value',
        currency_field='currency_id',
        compute='_compute_break_even_value',
        store=False,
        help=(
            'Minimum hammer price for house profitability. Currently reflects reserve price; '
            'fee data is added by sor_commercial_auction_house.'
        ),
    )

    # Parties
    consignor_id = fields.Many2one(
        comodel_name='res.partner',
        string='Consignor',
        check_company=True,
    )
    buyer_id = fields.Many2one(
        comodel_name='res.partner',
        string='Buyer',
        check_company=True,
    )

    # Status
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('catalogued', 'Catalogued'),
            ('sold', 'Sold'),
            ('passed', 'Passed'),
            ('withdrawn', 'Withdrawn'),
        ],
        string='State',
        default='draft',
        required=True,
        copy=False,
        tracking=True,
    )
    auction_result = fields.Selection(
        selection=[('sold', 'Sold'), ('passed', 'Passed')],
        string='Auction Result',
        copy=False,
    )
    is_collected = fields.Boolean(
        string='Collected',
        default=False,
        copy=False,
        tracking=True,
    )
    collected_display = fields.Char(
        compute='_compute_collected_display',
        store=False,
    )

    # Internal notes

    internal_notes = fields.Html(
        string='Internal Notes',
    )

    _estimate_check = models.Constraint(
        'CHECK(estimate_low IS NULL OR estimate_high IS NULL OR estimate_low <= estimate_high)',
        'Low estimate must not exceed high estimate.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('lot_reference', 'New Lot') == 'New Lot':
                company = self.env['res.company'].browse(
                    vals.get('company_id', self.env.company.id),
                )
                vals['lot_reference'] = (
                    self.env['ir.sequence'].with_company(company).next_by_code('sor.lot')
                    or 'New Lot'
                )
        return super().create(vals_list)

    def unlink(self):
        for lot in self:
            if lot.state != 'draft':
                raise UserError(
                    _('Lot "%s" cannot be deleted because it is %s. '
                      'Only Draft lots may be deleted.')
                    % (lot.lot_reference, dict(self._fields['state'].selection)[lot.state]),
                )
        return super().unlink()

    @api.model
    def _name_search(self, name='', domain=None, operator='ilike', limit=100, order=None):
        if name:
            domain = ['|', ('lot_reference', operator, name), ('lot_title', operator, name)] + (domain or [])
            return self._search(domain, limit=limit, order=order)
        return super()._name_search(name=name, domain=domain, operator=operator, limit=limit, order=order)

    @api.depends('product_id', 'product_id.name', 'lot_title')
    def _compute_lot_item_name(self):
        for lot in self:
            lot.lot_item_name = lot.product_id.name or lot.lot_title or ''

    @api.depends('reserve_price')
    def _compute_break_even_value(self):
        for lot in self:
            lot.break_even_value = lot.reserve_price or 0.0

    @api.depends('is_collected')
    def _compute_collected_display(self):
        for lot in self:
            lot.collected_display = 'Collected' if lot.is_collected else ''

    def action_catalogue(self):
        for lot in self:
            if lot.state != 'draft':
                raise UserError(_('Only a Draft lot can be catalogued.'))
        missing = self.filtered(lambda lot: not lot.lot_number)
        if missing:
            raise UserError(_(
                '%(count)d lot(s) cannot be catalogued — Please provide a Lot Number for: %(refs)s',
                count=len(missing),
                refs=', '.join(missing.mapped('lot_reference')),
            ))
        self.write({'state': 'catalogued'})

    def action_mark_sold(self):
        for lot in self:
            if lot.state not in ('catalogued', 'live'):
                raise UserError(_('Only a Catalogued or Live lot can be marked Sold.'))
        self.write({'state': 'sold', 'auction_result': 'sold'})

    def action_mark_passed(self):
        for lot in self:
            if lot.state not in ('catalogued', 'live'):
                raise UserError(_('Only a Catalogued or Live lot can be marked Passed.'))
        self.write({'state': 'passed', 'auction_result': 'passed'})

    def action_withdraw(self):
        for lot in self:
            if lot.state not in ('draft', 'catalogued'):
                raise UserError(_('Only a Draft or Catalogued lot can be withdrawn.'))
        self.write({'state': 'withdrawn'})

    def action_mark_collected(self):
        for lot in self:
            if lot.state not in ('sold', 'passed'):
                raise UserError(_('Only a Sold or Passed lot can be marked as Collected.'))
        self.write({'is_collected': True})

    def action_open_product(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.template',
            'res_id': self.product_id.id,
            'view_mode': 'form',
            'target': 'new',
        }
