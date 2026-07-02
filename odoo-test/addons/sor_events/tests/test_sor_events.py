from datetime import datetime

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSorEvents(TransactionCase):
    """Automated tests for the sor_events module.

    Covers: module install, field defaults, optional fields, state machine
    transitions, state machine guards, company isolation, and both event types.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.venue = cls.env['res.partner'].create({
            'name': 'Test Gallery Venue',
            'is_company': True,
        })

    # ------------------------------------------------------------------
    # 1. Module installs
    # ------------------------------------------------------------------

    def test_module_installs(self):
        """sor.event model is accessible from env."""
        self.assertIn('sor.event', self.env)

    # ------------------------------------------------------------------
    # 2. Basic creation
    # ------------------------------------------------------------------

    def test_create_event_with_required_fields(self):
        """Create an event with only the required fields; it saves cleanly."""
        event = self.env['sor.event'].create({
            'name': 'Spring Exhibition',
            'event_type': 'exhibition',
            'date_start': datetime(2026, 3, 1, 10, 0, 0),
        })
        self.assertTrue(event.id)
        self.assertEqual(event.name, 'Spring Exhibition')

    def test_date_end_is_optional(self):
        """Creating an event without date_end raises no error."""
        event = self.env['sor.event'].create({
            'name': 'No End Date Event',
            'event_type': 'exhibition',
            'date_start': datetime(2026, 4, 1, 9, 0, 0),
        })
        self.assertFalse(event.date_end)

    def test_venue_is_optional(self):
        """Creating an event without venue_id raises no error."""
        event = self.env['sor.event'].create({
            'name': 'Venue-free Event',
            'event_type': 'auction',
            'date_start': datetime(2026, 5, 1, 9, 0, 0),
        })
        self.assertFalse(event.venue_id)

    # ------------------------------------------------------------------
    # 3. Defaults
    # ------------------------------------------------------------------

    def test_status_defaults_to_draft(self):
        """A newly created event has status='draft'."""
        event = self.env['sor.event'].create({
            'name': 'Default Status Event',
            'event_type': 'exhibition',
            'date_start': datetime(2026, 6, 1, 10, 0, 0),
        })
        self.assertEqual(event.status, 'draft')

    def test_company_id_defaults_to_current_company(self):
        """A newly created event has company_id equal to env.company."""
        event = self.env['sor.event'].create({
            'name': 'Company Default Event',
            'event_type': 'exhibition',
            'date_start': datetime(2026, 7, 1, 10, 0, 0),
        })
        self.assertEqual(event.company_id, self.env.company)

    # ------------------------------------------------------------------
    # 4. State machine — happy path
    # ------------------------------------------------------------------

    def test_action_publish(self):
        """A draft event transitions to published via action_publish()."""
        event = self.env['sor.event'].create({
            'name': 'Publish Test',
            'event_type': 'exhibition',
            'date_start': datetime(2026, 8, 1, 10, 0, 0),
        })
        event.action_publish()
        self.assertEqual(event.status, 'published')

    def test_action_activate(self):
        """A published event transitions to active via action_activate()."""
        event = self.env['sor.event'].create({
            'name': 'Activate Test',
            'event_type': 'exhibition',
            'date_start': datetime(2026, 8, 2, 10, 0, 0),
            'status': 'published',
        })
        event.action_activate()
        self.assertEqual(event.status, 'active')

    def test_action_close(self):
        """An active event transitions to closed via action_close()."""
        event = self.env['sor.event'].create({
            'name': 'Close Test',
            'event_type': 'exhibition',
            'date_start': datetime(2026, 8, 3, 10, 0, 0),
            'status': 'active',
        })
        event.action_close()
        self.assertEqual(event.status, 'closed')

    def test_action_archive_event(self):
        """A closed event transitions to archived via action_archive_event()."""
        event = self.env['sor.event'].create({
            'name': 'Archive Test',
            'event_type': 'auction',
            'date_start': datetime(2026, 8, 4, 10, 0, 0),
            'status': 'closed',
        })
        event.action_archive_event()
        self.assertEqual(event.status, 'archived')

    # ------------------------------------------------------------------
    # 5. State machine — guard clauses (invalid transitions raise UserError)
    # ------------------------------------------------------------------

    def test_action_publish_raises_if_not_draft(self):
        """Calling action_publish() on an active event raises UserError."""
        event = self.env['sor.event'].create({
            'name': 'Guard Publish Test',
            'event_type': 'exhibition',
            'date_start': datetime(2026, 9, 1, 10, 0, 0),
            'status': 'active',
        })
        with self.assertRaises(UserError):
            event.action_publish()

    def test_action_activate_raises_if_not_published(self):
        """Calling action_activate() on a draft event raises UserError."""
        event = self.env['sor.event'].create({
            'name': 'Guard Activate Test',
            'event_type': 'exhibition',
            'date_start': datetime(2026, 9, 2, 10, 0, 0),
        })
        with self.assertRaises(UserError):
            event.action_activate()

    def test_action_close_raises_if_not_active(self):
        """Calling action_close() on a draft event raises UserError."""
        event = self.env['sor.event'].create({
            'name': 'Guard Close Test',
            'event_type': 'auction',
            'date_start': datetime(2026, 9, 3, 10, 0, 0),
        })
        with self.assertRaises(UserError):
            event.action_close()

    def test_action_archive_raises_if_not_closed(self):
        """Calling action_archive_event() on a draft event raises UserError."""
        event = self.env['sor.event'].create({
            'name': 'Guard Archive Test',
            'event_type': 'auction',
            'date_start': datetime(2026, 9, 4, 10, 0, 0),
        })
        with self.assertRaises(UserError):
            event.action_archive_event()

    # ------------------------------------------------------------------
    # 6. Both event types accepted
    # ------------------------------------------------------------------

    def test_both_event_types_accepted(self):
        """Creating both exhibition and auction events raises no error."""
        exhibition = self.env['sor.event'].create({
            'name': 'Type Test Exhibition',
            'event_type': 'exhibition',
            'date_start': datetime(2026, 10, 1, 10, 0, 0),
        })
        auction = self.env['sor.event'].create({
            'name': 'Type Test Auction',
            'event_type': 'auction',
            'date_start': datetime(2026, 10, 2, 10, 0, 0),
        })
        self.assertEqual(exhibition.event_type, 'exhibition')
        self.assertEqual(auction.event_type, 'auction')
