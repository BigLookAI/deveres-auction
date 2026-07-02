# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'SOR Locations — Artist Studios × Artwork',
    'summary': 'Bridge: AS disable guard uses current_location_id for artworks (sor_locations_artist_studios + sor_locations_artwork)',
    'category': 'Hidden/Technical',
    'version': '19.0.1.0.0',
    'author': 'BL',
    'license': 'LGPL-3',
    'depends': [
        'sor_locations_artist_studios',
        'sor_locations_artwork',
    ],
    'auto_install': True,
    'application': False,
    'installable': True,
    'data': [
        'security/ir.model.access.csv',
    ],
}
