# Commands to Run SOR Gallery Module

## Prerequisites
- Activate the virtual environment: `source env312/bin/activate`
- Ensure PostgreSQL is running
- Have a database ready (or create one)

## Installation Commands

### 1. Install Module on Fresh Database
```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
python3 odoo-bin --addons-path=addons,odoo/addons -d your_database_name -i sor_contact_roles
```

### 2. Upgrade Module on Existing Database
```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
python3 odoo-bin --addons-path=addons,odoo/addons -d your_database_name -u sor_contact_roles
```

### 3. Start Odoo Server (Normal Mode)
```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
python3 odoo-bin --addons-path=addons,odoo/addons --http-port=8069 -d your_database_name
```

### 4. Start Odoo Server (Development Mode with Auto-Reload)
```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
python3 odoo-bin --addons-path=addons,odoo/addons --http-port=8069 -d your_database_name --dev=reload,qweb,werkzeug,xml
```

### 5. Update Module List (if module not showing in Apps)
```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
python3 odoo-bin --addons-path=addons,odoo/addons -d your_database_name --update-module-list
```

## Testing the Module

### Running Unit Tests (121+ Test Cases)

#### Run All Tests in Module
```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
python3 odoo-bin --addons-path=addons,odoo/addons -d your_database_name \
  --test-enable --stop-after-init --test-tags=sor_contact_roles
```

#### Run Specific Test File
```bash
# Contact type model tests
python3 odoo-bin --addons-path=addons,odoo/addons -d your_database_name \
  --test-enable --stop-after-init --test-tags=sor_contact_roles/test_sor_contact_type

# Partner tests
python3 odoo-bin --addons-path=addons,odoo/addons -d your_database_name \
  --test-enable --stop-after-init --test-tags=sor_contact_roles/test_res_partner

# Social media tests
python3 odoo-bin --addons-path=addons,odoo/addons -d your_database_name \
  --test-enable --stop-after-init --test-tags=sor_contact_roles/test_sor_contact_social_media

# Integration tests
python3 odoo-bin --addons-path=addons,odoo/addons -d your_database_name \
  --test-enable --stop-after-init --test-tags=sor_contact_roles/test_res_partner_integration
```

#### Run Single Test Method
```bash
python3 odoo-bin --addons-path=addons,odoo/addons -d your_database_name \
  --test-enable --stop-after-init \
  --test-tags=sor_contact_roles/test_res_partner.TestResPartnerContactTypes.test_multiple_contact_types_assignment
```

#### Run Tests with Verbose Output
```bash
python3 odoo-bin --addons-path=addons,odoo/addons -d your_database_name \
  --test-enable --stop-after-init --test-tags=sor_contact_roles \
  --log-level=test
```

### Via Odoo Web Interface:
1. Go to: http://localhost:8069
2. Login to your database
3. Go to **Apps** menu
4. Remove "Apps" filter
5. Search for "SOR Contact Roles" or "Contact Types"
6. Click **Install** (if not already installed)

### Via Odoo Shell (Python):
```bash
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
python3 odoo-bin shell -d your_database_name
```

Then in the shell:
```python
# Verify model exists
env['sor.contact.type'].search([])

# Check contact types loaded
env['sor.contact.type'].search_count([])  # Should return 12+

# Test partner assignment
partner = env['res.partner'].create({'name': 'Test Artist'})
artist = env['sor.contact.type'].search([('code', '=', 'artist')])
partner.contact_types = [(6, 0, [artist.id])]
partner.is_artist  # Should be True
partner.is_creator  # Should be True (because Artist is sub-type of Creator)
```

### Quick Test Example
```bash
# 1. Create test database (if needed)
createdb test_db

# 2. Install module with tests
cd /Users/deepkharadi/Documents/BL
source env312/bin/activate
python3 odoo-bin --addons-path=addons,odoo/addons -d test_db \
  -i base,sor_contact_roles --stop-after-init

# 3. Run all tests
python3 odoo-bin --addons-path=addons,odoo/addons -d test_db \
  --test-enable --stop-after-init --test-tags=sor_contact_roles \
  --log-level=test

# Expected output: "Tests run: 121, Failures: 0, Errors: 0"
```

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
ls -la addons/sor_contact_roles/

# Validate Python syntax
python3 -m py_compile addons/sor_contact_roles/models/*.py

# Validate XML files
python3 -c "import xml.etree.ElementTree as ET; ET.parse('addons/sor_contact_roles/data/sor_contact_type_data.xml'); print('XML valid')"
```

