"""
Deviours Auction — Personalised Outreach Email Drafter
Uses Gemma4 on DGX (vLLM at :8000) to draft personalised emails for APPROVED bidders.
Email tone and template are controlled by Shelly-editable Markdown skill files —
no Python changes needed to adjust voice, greeting style, or CTA.
"""
from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Optional

from .models import EvaluationResult, Recommendation


# ── Skill template location (Shelly-editable) ────────────────────────────────
SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills" / "outreach-email"

# ── DGX vLLM endpoint ────────────────────────────────────────────────────────
VLLM_URL = "http://100.101.39.73:8000/generate"


def load_skill_template() -> dict:
    """
    Load tone guidance and email template from skills/outreach-email/.
    Returns dict with keys: tone, template, subject_template, sign_off.
    Falls back to built-in defaults if files not found.
    """
    tone_path     = SKILLS_DIR / "email_tone.md"
    template_path = SKILLS_DIR / "outreach_template.md"

    tone = tone_path.read_text(encoding="utf-8") if tone_path.exists() else _DEFAULT_TONE
    template = template_path.read_text(encoding="utf-8") if template_path.exists() else _DEFAULT_TEMPLATE

    return {"tone": tone, "template": template}


def draft_email(
    result: EvaluationResult,
    vllm_url: str = VLLM_URL,
    dry_run: bool = False,
) -> dict:
    """
    Draft a personalised outreach email for one approved bidder.

    Args:
        result:   EvaluationResult (should be APPROVE recommendation)
        vllm_url: Gemma4 vLLM endpoint
        dry_run:  If True, return filled template without calling Gemma4

    Returns:
        dict with keys: subject, body, bidder_id, bidder_email, status
    """
    if result.recommendation != Recommendation.APPROVE:
        return {
            "bidder_id":    result.bidder_id,
            "bidder_email": result.bidder_email,
            "status":       "skipped",
            "reason":       f"Recommendation is {result.recommendation.value}, not approve",
        }

    skill = load_skill_template()
    lot_lines = _format_lot_list(result)
    subject   = f"Preview Invitation — Upcoming Auction Lots Selected for You"

    if dry_run:
        body = _fill_template(skill["template"], result, lot_lines)
        return {
            "bidder_id":    result.bidder_id,
            "bidder_email": result.bidder_email,
            "subject":      subject,
            "body":         body,
            "status":       "dry_run",
        }

    prompt = _build_prompt(skill, result, lot_lines)
    body   = _call_gemma4(prompt, vllm_url)

    return {
        "bidder_id":    result.bidder_id,
        "bidder_email": result.bidder_email,
        "subject":      subject,
        "body":         body,
        "status":       "drafted",
    }


def draft_all_emails(
    results: list[EvaluationResult],
    vllm_url: str = VLLM_URL,
    dry_run: bool = False,
) -> list[dict]:
    """Draft emails for all APPROVED bidders. REVIEW/REJECT bidders are skipped."""
    return [draft_email(r, vllm_url=vllm_url, dry_run=dry_run) for r in results]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _format_lot_list(result: EvaluationResult) -> str:
    if not result.matched_lots:
        return "We have a wonderful selection of works coming up that we think you will enjoy."
    parts = []
    for lot in result.matched_lots[:3]:
        parts.append(
            f"- **{lot.title}** ({lot.category.title()}) — "
            f"Estimate €{lot.estimate_low:,.0f}–€{lot.estimate_high:,.0f}, "
            f"auction {lot.auction_date[:10]}"
        )
    return "\n".join(parts)


def _fill_template(template: str, result: EvaluationResult, lot_lines: str) -> str:
    """Simple placeholder substitution for dry_run / fallback.
    Strips metadata header (everything before the first --- separator)."""
    # Strip YAML-like header / instruction block before the email body
    if "---" in template:
        parts = template.split("---")
        # Take the last non-empty section as the actual email body
        body = next((p.strip() for p in reversed(parts) if p.strip()), template)
    else:
        body = template.strip()

    first_name = result.bidder_name.split()[0]
    return (
        body
        .replace("{first_name}", first_name)
        .replace("{full_name}", result.bidder_name)
        .replace("{matched_lots}", lot_lines)
        .replace("{score}", f"{result.score:.2f}")
    )


def _build_prompt(skill: dict, result: EvaluationResult, lot_lines: str) -> str:
    first_name = result.bidder_name.split()[0]
    b = result.breakdown
    return f"""You are drafting a personalised auction preview invitation email.

TONE GUIDANCE:
{skill['tone']}

TEMPLATE STRUCTURE:
{skill['template']}

BIDDER CONTEXT:
- Name: {result.bidder_name} (first name: {first_name})
- Total bids placed: {b.total_bids}
- Lots won: {b.total_wins}
- Price band trajectory: {b.trajectory.value}
- Collector score: {result.score:.2f}/1.00

UPCOMING LOTS MATCHED TO THIS BIDDER:
{lot_lines}

Write a warm, professional email. Use the bidder's first name. Mention 1–2 specific upcoming lots.
Include a clear call-to-action to register for the preview day.
Do NOT mention their score or that they were algorithmically evaluated.
Maximum 200 words. Return only the email body text, no subject line."""


def _call_gemma4(prompt: str, url: str) -> str:
    try:
        import requests
        r = requests.post(
            url,
            json={
                "system_prompt": "You are a professional auction house correspondent. Write warm, concise emails.",
                "user_prompt":   prompt,
                "max_new_tokens": 400,
                "temperature":    0.7,
            },
            timeout=60,
        )
        raw = r.json().get("response", "")
        # Strip any system/prompt echo
        raw = re.sub(r"^(You are|Draft|Write|Email:|Subject:).*\n?", "", raw, flags=re.MULTILINE).strip()
        return raw if raw else _FALLBACK_BODY
    except Exception as e:
        return f"[EMAIL DRAFT FAILED — {e}]\n\n{_FALLBACK_BODY}"


# ─────────────────────────────────────────────────────────────────────────────
# Built-in defaults (used when skill files are missing)
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_TONE = """
- Warm and personal, not corporate
- Reference the bidder's history where natural (e.g. "as a returning collector")
- Enthusiastic about the works, not pushy about selling
- Professional sign-off from the gallery team
"""

_DEFAULT_TEMPLATE = """
Dear {first_name},

We hope this message finds you well. As a valued participant in our previous auctions,
we wanted to personally invite you to our upcoming preview event.

We have selected a number of works we think will interest you:

{matched_lots}

We would love to welcome you to our preview day, where you can view these works in person
before the auction. Please register your attendance by replying to this email or
visiting our website.

We look forward to seeing you.

Warm regards,
The Gallery Team
"""

_FALLBACK_BODY = """Dear Collector,

We hope this finds you well. We are delighted to invite you as a valued returning bidder
to our upcoming auction preview. We have a carefully curated selection of works that we
believe will be of interest to you.

Please contact us to register for our preview day and secure your place.

Warm regards,
The Gallery Team"""
