

def post_init_hook(env):
    """Set asset_paradigm = 'unique_object' and is_storable = True on all existing
    artwork products.  Runs once on first install of this bridge module.
    """
    artworks = env['product.template'].search([('product_type', '=', 'artwork')])
    if artworks:
        artworks.write({'asset_paradigm': 'unique_object', 'is_storable': True})
