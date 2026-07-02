"""
deVeres Auction — Reconciliation · Field mapping
=================================================

Single source of truth for how the two data sources map onto the engine's
canonical contact schema. Keeping this in one place means new export formats
(different Blue Cubes versions, other auction houses) only need a new map here,
not changes across the engine.

Canonical fields the engine reasons about:
    client_ref, title, first_name, last_name, company,
    email, phone, mobile, address1, address2, address3,
    town, county, country, postcode
"""
from __future__ import annotations

# All Clients.csv  (canonical master) column → canonical field
MASTER_MAP = {
    "client_ref": "clientRef",
    "title":      "title",
    "first_name": "firstName",
    "last_name":  "lastName",
    "company":    "companyName",
    "email":      "email",
    "phone":      "telNo",
    "mobile":     "mobile",
    "address1":   "address1",
    "address2":   "address2",
    "address3":   "address3",
    "town":       "townCity",
    "county":     "countyState",
    "country":    "country",
    "postcode":   "postalCode",
}

# Design-April 2026.csv  (Blue Cubes buyer export / upload) column → canonical field
INCOMING_MAP = {
    "buyer_number": "Buyer Number",
    "first_name":   "First Name",
    "last_name":    "Last Name",
    "email":        "Email",
    "address1":     "Address 1",
    "address2":     "Address 2",
    "town":         "Town",
    "county":       "County",
    "postcode":     "Postcode",
    "country":      "Country",
    "phone":        "Phone",
    # per-row extras (aggregated per buyer, not used for matching)
    "lot_number":   "Lot Number",
    "lot_title":    "Lot Title",
    "winning_bid":  "Winning Bid",
}

# Seller List Export column → canonical field (vendors/consignors from Blue Cubes)
SELLER_MAP = {
    "buyer_number": "Seller Ref",     # reused as the source reference key
    "first_name":   "First Name",
    "last_name":    "Last Name",
    "company":      "Company",
    "phone":        "Telephone",
    "mobile":       "Mobile",
    "email":        "Email",
}

# Lot List Export column → canonical lot field
LOT_MAP = {
    "lot_number":   "Lot Number",
    "seller_ref":   "Seller ref",
    "seller_name":  "Seller Name",
    "title":        "Title",
    "description":  "Lot Description",
    "condition":    "Condition",
    "estimate_low": "Estimate From",
    "estimate_high":"Estimate To",
    "starting_bid": "Starting Bid",
    "reserve":      "Reserve",
    "hammer":       "Hammer",          # ← forced to 0 on import (meeting rule)
    "internal_notes":"Internal Notes",
}

# Fields shown in the field-by-field difference viewer, in display order.
DIFF_FIELDS = [
    ("name",     "Name"),
    ("email",    "Email"),
    ("phone",    "Phone"),
    ("company",  "Company"),
    ("address1", "Address 1"),
    ("address2", "Address 2"),
    ("town",     "Town"),
    ("county",   "County"),
    ("postcode", "Postcode"),
    ("country",  "Country"),
]
