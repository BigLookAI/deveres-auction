# GDPR Draft Email — deVeres Auction Bidder Evaluation Pipeline

**To:** Data Collection Officer, Trinity College Dublin
**From:** [Shelly / Carl — add sender name]
**Subject:** Data Processing Notice — Bidder Evaluation System (deVeres Auction)
**Date:** 12 May 2026

---

Dear Data Collection Officer,

I am writing to notify you of a data processing activity that involves personal data held by Trinity College Dublin in connection with the **deVeres auction programme**.

---

## 1. Purpose of Processing

We are building an automated **bidder evaluation pipeline** to assist our auction house in assessing bidder engagement and readiness ahead of upcoming auction lots. The system analyses historical bidding behaviour to generate a qualification recommendation (Approve / Review / Reject) and, where appropriate, to draft personalised outreach emails inviting approved bidders to register for preview events.

---

## 2. Categories of Personal Data Processed

The following personal data is processed:

| Category | Source | Purpose |
|----------|--------|---------|
| Bidder name | Odoo CRM | Personalising outreach email |
| Email address | Odoo CRM | Email delivery only |
| Historical bidding records (lot IDs, bid amounts, outcomes, timestamps) | Odoo CRM | Scoring dimensions: win/loss rate, bid count, price band trajectory |
| Price band preferences | Derived from bidding history | Matching bidders to upcoming lots |

No special category data (Art. 9 GDPR) is processed. No biometric, health, or demographic data is collected.

---

## 3. Lawful Basis

We rely on **Legitimate Interest (Art. 6(1)(f) GDPR)** as the lawful basis for this processing. The legitimate interest is the direct commercial relationship between the auction house and registered bidders who have previously participated in auctions. A Legitimate Interest Assessment (LIA) has been completed and is available on request.

Outreach emails are sent only to individuals who have **previously participated as bidders** and where there is a reasonable expectation of further commercial engagement.

---

## 4. Automated Decision-Making

The pipeline produces a **recommendation score** (0.0–1.0) and a classification (Approve / Review / Reject). This is used as a **decision-support tool only** — no individual is automatically excluded or accepted based solely on this score. All Reject recommendations are subject to human review before any action is taken.

This system **does not constitute automated decision-making with legal or similarly significant effects** under Art. 22 GDPR.

---

## 5. Data Retention

| Data type | Retention period |
|-----------|-----------------|
| Bidder evaluation scores and recommendations | 90 days from date of evaluation |
| Source bidding history (read-only from Odoo) | Not copied — accessed via API, not stored separately |
| Draft outreach emails | Deleted after send or 30 days if unsent |

Evaluation results are automatically pruned after 90 days. No long-term profiling database is created.

---

## 6. Data Subject Rights

Registered bidders retain all rights under GDPR Chapter III:
- **Right of access** (Art. 15): Bidders may request a copy of their evaluation record
- **Right to erasure** (Art. 17): Evaluation records will be deleted on request within 72 hours
- **Right to object** (Art. 21): Bidders may object to Legitimate Interest processing at any time
- **Right not to be subject to automated decisions** (Art. 22): Human review is mandatory before any action

To exercise these rights, bidders should contact: **[Insert gallery/auction house data contact email]**

---

## 7. Data Transfers

All processing occurs within the **EU/EEA**. The pipeline runs on infrastructure located in Ireland and the EU. No personal data is transferred to third countries.

---

## 8. Data Processor

The pipeline is developed and operated by **Cimelium Ltd** acting as a data processor on behalf of the auction house (data controller). A Data Processing Agreement (DPA) between Cimelium and the auction house is in place / will be executed prior to go-live.

---

## 9. Contact for Queries

If you have any questions regarding this processing activity or require further documentation, please contact:

**[Lead contact name]**
[Email address]
Cimelium Ltd

We are happy to provide the full Legitimate Interest Assessment, data flow diagram, or any other documentation required.

Yours sincerely,
[Sender name]
[Title]
Cimelium Ltd / deVeres Auction

---

*Draft prepared: 12 May 2026. Review with Carl before sending.*
