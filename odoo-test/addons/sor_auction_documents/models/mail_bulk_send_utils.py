from odoo import _


def bulk_send_via_template(records, template, no_email_reason):
    """Send `records` via mail.compose.message mass-mail mode using `template`.

    `records` must have a `consignor_id` field. Returns (sent, skipped) recordsets.
    Does not write any state — the caller decides what state transition, if any,
    applies to `sent`. Posts a chatter note on each `skipped` record explaining why.
    """
    sent = records.filtered(lambda r: r.consignor_id.email)
    skipped = records - sent
    for record in skipped:
        record.message_post(body=no_email_reason % (record.consignor_id.name or _('Unknown')))
    if sent:
        composer = records.env['mail.compose.message'].create({
            'model': sent._name,
            'res_ids': str(sent.ids),
            'composition_mode': 'mass_mail',
            'template_id': template.id,
            'auto_delete': False,
            'force_send': True,
        })
        composer.action_send_mail()
    return sent, skipped


def bulk_send_notification(sent_count, skipped_count, plural_noun, not_eligible_count=0):
    """Build a transient display_notification action summarising a bulk send.

    `not_eligible_count` covers records excluded before the sent/skipped split
    even ran (e.g. wrong starting state) — distinct from `skipped_count`,
    which is records that reached the split but had no email on file.
    """
    if not skipped_count and not not_eligible_count:
        message = _('%(count)d %(noun)s sent.') % {'count': sent_count, 'noun': plural_noun}
        notif_type = 'success'
    else:
        segments = [_('%(sent)d %(noun)s sent') % {'sent': sent_count, 'noun': plural_noun}]
        if skipped_count:
            segments.append(_('%(count)d skipped — no email on file') % {'count': skipped_count})
        if not_eligible_count:
            segments.append(_('%(count)d not eligible (wrong state)') % {'count': not_eligible_count})
        message = ', '.join(segments) + '.'
        if skipped_count:
            message += ' ' + _('See the chatter on each skipped record for details.')
        notif_type = 'warning'
    return {
        'type': 'ir.actions.client',
        'tag': 'display_notification',
        'params': {
            'title': _('Bulk Send'),
            'message': message,
            'type': notif_type,
            'sticky': bool(skipped_count or not_eligible_count),
            'next': {'type': 'ir.actions.act_window_close'},
        },
    }
