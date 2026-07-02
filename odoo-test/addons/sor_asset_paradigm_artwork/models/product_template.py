from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    asset_paradigm = fields.Selection(
        selection_add=[('unique_object', 'Unique Object')],
        ondelete={'unique_object': 'set default'},
    )

    # --- Per-element suppression booleans ---
    # store=False: recomputes on each form load, reflecting any runtime rule toggle.
    # @api.depends('asset_paradigm') ensures recompute when paradigm changes in-session.

    is_forecast_btn_suppressed = fields.Boolean(
        compute='_compute_artwork_suppression', store=False)
    is_reorder_btn_suppressed = fields.Boolean(
        compute='_compute_artwork_suppression', store=False)
    is_moves_btn_suppressed = fields.Boolean(
        compute='_compute_artwork_suppression', store=False)
    is_putaway_btn_suppressed = fields.Boolean(
        compute='_compute_artwork_suppression', store=False)
    is_storage_cap_btn_suppressed = fields.Boolean(
        compute='_compute_artwork_suppression', store=False)
    is_qty_available_suppressed = fields.Boolean(
        compute='_compute_artwork_suppression', store=False)
    is_qty_column_suppressed = fields.Boolean(
        compute='_compute_artwork_suppression', store=False)
    is_operations_group_suppressed = fields.Boolean(
        compute='_compute_artwork_suppression', store=False)
    is_replenish_suppressed = fields.Boolean(
        compute='_compute_artwork_suppression', store=False)
    is_odoo_product_type_field_suppressed = fields.Boolean(
        compute='_compute_artwork_suppression', store=False)
    is_product_type_field_suppressed = fields.Boolean(
        compute='_compute_artwork_suppression', store=False)
    is_track_inventory_field_suppressed = fields.Boolean(
        compute='_compute_artwork_suppression', store=False)
    is_inventory_tab_suppressed = fields.Boolean(
        compute='_compute_artwork_suppression', store=False)

    @api.depends('asset_paradigm')
    def _compute_artwork_suppression(self):
        for rec in self:
            rec.is_forecast_btn_suppressed = rec.is_element_suppressed('forecast_button')
            rec.is_reorder_btn_suppressed = rec.is_element_suppressed('reorder_button')
            rec.is_moves_btn_suppressed = rec.is_element_suppressed('moves_button')
            rec.is_putaway_btn_suppressed = rec.is_element_suppressed('putaway_button')
            rec.is_storage_cap_btn_suppressed = rec.is_element_suppressed('storage_capacity_button')
            rec.is_qty_available_suppressed = rec.is_element_suppressed('qty_available_field')
            rec.is_qty_column_suppressed = rec.is_element_suppressed('qty_column')
            rec.is_operations_group_suppressed = rec.is_element_suppressed('operations_group')
            rec.is_replenish_suppressed = rec.is_element_suppressed('replenish_action')
            rec.is_odoo_product_type_field_suppressed = rec.is_element_suppressed('odoo_product_type_field')
            rec.is_product_type_field_suppressed = rec.is_element_suppressed('product_type_field')
            rec.is_track_inventory_field_suppressed = rec.is_element_suppressed('track_inventory_field')
            rec.is_inventory_tab_suppressed = rec.is_element_suppressed('inventory_tab')

    # --- ORM-level override ---

    def _compute_show_qty_status_button(self):
        super()._compute_show_qty_status_button()
        for rec in self:
            if rec.is_element_suppressed('forecast_button'):
                rec.show_on_hand_qty_status_button = False
                rec.show_forecasted_qty_status_button = False

    # --- ORM-level defaults for new artwork records ---

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if 'type' in fields_list:
            defaults['type'] = 'consu'
        if 'is_storable' in fields_list:
            defaults['is_storable'] = True
        # Set asset_paradigm only for artwork products so suppression is active
        # from the moment the artwork form opens. Guards against setting
        # unique_object on non-artwork products created via generic product menus.
        if defaults.get('product_type') == 'artwork':
            defaults['asset_paradigm'] = 'unique_object'
        return defaults

    # --- Auto-assign paradigm on create/write ---

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('product_type') == 'artwork' and not vals.get('asset_paradigm'):
                vals['asset_paradigm'] = 'unique_object'
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('product_type') == 'artwork' and 'asset_paradigm' not in vals:
            vals['asset_paradigm'] = 'unique_object'
        return super().write(vals)
