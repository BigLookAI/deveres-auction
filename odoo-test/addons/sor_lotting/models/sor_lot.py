from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SorLot(models.Model):
    _name = 'sor.lot'
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
    lot_suffix = fields.Char(
        string='Suffix',
        size=3,
    )
    product_id = fields.Many2one(
        comodel_name='product.template',
        string='Product',
        required=True,
        domain=[('type', 'not in', ('service',))],
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

    @api.depends('reserve_price')
    def _compute_break_even_value(self):
        for lot in self:
            lot.break_even_value = lot.reserve_price or 0.0

    def action_catalogue(self):
        for lot in self:
            if lot.state != 'draft':
                raise UserError(_('Only a Draft lot can be catalogued.'))
        self.write({'state': 'catalogued'})

    def action_mark_sold(self):
        for lot in self:
            if lot.state not in ('catalogued', 'live'):
                raise UserError(_('Only a Catalogued or Live lot can be marked Sold.'))
        self.write({'state': 'sold'})

    def action_mark_passed(self):
        for lot in self:
            if lot.state not in ('catalogued', 'live'):
                raise UserError(_('Only a Catalogued or Live lot can be marked Passed.'))
        self.write({'state': 'passed'})

    def action_withdraw(self):
        for lot in self:
            if lot.state not in ('draft', 'catalogued'):
                raise UserError(_('Only a Draft or Catalogued lot can be withdrawn.'))
        self.write({'state': 'withdrawn'})

    def action_open_product(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.template',
            'res_id': self.product_id.id,
            'view_mode': 'form',
            'target': 'new',
        }
