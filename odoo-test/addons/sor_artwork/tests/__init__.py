# Part of Odoo. See LICENSE file for full copyright and licensing details.

# Note: test_contact_type_system, test_creator_artwork_relationship, and
# test_workflow_integration are sor_artwork_contact_roles bridge tests and have
# been excluded from this module's test suite. They will be replaced by proper
# bridge tests in sor_artwork_contact_roles at Show & Tell.

from . import (
    test_artwork_fields_validations,
    test_artwork_hooks,
    test_data_integrity,
    test_module_installation,
    test_performance,
    test_performance_data,
)
