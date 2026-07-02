# Commands to Run SOR Artwork Module

## Module Name
**`sor_artwork`**

## Prerequisites
- Activate the virtual environment: `source env312/bin/activate`
- Ensure PostgreSQL is running
- Have a database ready (or create one)

## Installation Commands

### 1. Update Module List (if module not showing in Apps)
```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
python3 odoo-bin --addons-path=addons,odoo/addons -d your_database_name --update-module-list
```

### 2. Install Module on Fresh Database
```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
python3 odoo-bin --addons-path=addons,odoo/addons -d your_database_name -i sor_artwork
```

### 3. Upgrade Module on Existing Database
```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
python3 odoo-bin --addons-path=addons,odoo/addons -d your_database_name -u sor_artwork
```

### 4. Start Odoo Server (Normal Mode)
```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
python3 odoo-bin --addons-path=addons,odoo/addons --http-port=8069 -d your_database_name
```

### 5. Start Odoo Server (Development Mode with Auto-Reload)
```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
python3 odoo-bin --addons-path=addons,odoo/addons --http-port=8069 -d your_database_name --dev=reload,qweb,werkzeug,xml
```

## Via Odoo Web Interface:
1. Go to: http://localhost:8069
2. Login to your database
3. Go to **Apps** menu
4. Remove "Apps" filter (if needed)
5. Search for "SOR Artwork Management" or "sor_artwork"
6. Click **Install**

## Troubleshooting

### If you get "Module not found":
- Check addons path includes both `addons` and `odoo/addons`
- Run: `python3 odoo-bin --addons-path=addons,odoo/addons -d your_db --update-module-list`

### If you get import errors:
- Make sure virtual environment is activated: `source env312/bin/activate`
- Check Python version matches: `python3 --version` (should be 3.12)

### If server won't start:
- Check PostgreSQL is running
- Check database exists
- Check port 8069 is not in use: `lsof -i :8069`

## Quick Test Commands

```bash
# Check module files exist
ls -la addons/sor_artwork/

# Validate Python syntax
python3 -m py_compile addons/sor_artwork/models/*.py

# Validate XML files
python3 -c "import xml.etree.ElementTree as ET; ET.parse('addons/sor_artwork/views/sor_art_product_views.xml'); print('XML valid')"
```

