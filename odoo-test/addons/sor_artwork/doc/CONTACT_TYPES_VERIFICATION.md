# Contact Types Verification Guide

This document explains how to verify all contact types in the test database.

## All Contact Types Created

### 1. Creator Type with Artist Subtype
- **Type**: Creator (parent)
- **Subtype**: Artist
- **Count**: 200 (default)
- **Name Pattern**: "Artist 1", "Artist 2", etc.
- **Verification**: 
  - Filter Contacts by "Is Creator" = Yes
  - Check "Contact Sub-types" field shows "Artist"
  - Verify `is_creator` = True and `is_artist` = True

### 2. Customer Type with Subtypes

#### Private Collector
- **Type**: Customer (parent)
- **Subtype**: Private Collector
- **Count**: 150 (default)
- **Name Pattern**: "Private Collector 1", "Private Collector 2", etc.

#### Corporate Collector
- **Type**: Customer (parent)
- **Subtype**: Corporate Collector
- **Count**: 100 (default)
- **Name Pattern**: "Corporate Collector 1", "Corporate Collector 2", etc.

#### Institutions Collection
- **Type**: Customer (parent)
- **Subtype**: Institutions Collection
- **Count**: 50 (default)
- **Name Pattern**: "Institutions Collection 1", "Institutions Collection 2", etc.

#### Dealer
- **Type**: Customer (parent)
- **Subtype**: Dealer
- **Count**: 100 (default)
- **Name Pattern**: "Dealer 1", "Dealer 2", etc.

#### Buyer
- **Type**: Customer (parent)
- **Subtype**: Buyer
- **Count**: 100 (default)
- **Name Pattern**: "Buyer 1", "Buyer 2", etc.

**Verification for Customer Types**:
- Filter Contacts by "Is Customer" = Yes
- Check "Contact Sub-types" field shows the appropriate subtype
- Verify `is_customer` = True

### 3. Standalone Types

#### Consignor
- **Type**: Consignor (standalone, no parent)
- **Count**: 50 (default)
- **Name Pattern**: "Consignor 1", "Consignor 2", etc.
- **Description**: Auction seller

#### Bidder
- **Type**: Bidder (standalone, no parent)
- **Count**: 50 (default)
- **Name Pattern**: "Bidder 1", "Bidder 2", etc.
- **Description**: Auction participant

#### Donor
- **Type**: Donor (standalone, no parent)
- **Count**: 30 (default)
- **Name Pattern**: "Donor 1", "Donor 2", etc.
- **Description**: Museum contributor

#### Advisor
- **Type**: Advisor (standalone, no parent)
- **Count**: 30 (default)
- **Name Pattern**: "Advisor 1", "Advisor 2", etc.
- **Description**: Art consultant

**Verification for Standalone Types**:
- Filter Contacts by the specific type
- Check "Contact Types" field shows the type
- No subtypes should be assigned

## Usage

### Delete Existing Data
```bash
./addons/sor_artwork/tests/delete_test_data.sh test_perf_manual
```

### Populate with All Contact Types
```bash
# Default counts
./addons/sor_artwork/tests/populate_test_data.sh test_perf_manual

# Custom counts (in order):
# Artists, Private Collectors, Corporate Collectors, Institutions, 
# Dealers, Buyers, Consignors, Bidders, Donors, Advisors,
# Artworks, Furniture, Jewelry, Collectibles
./addons/sor_artwork/tests/populate_test_data.sh test_perf_manual \
  200 150 100 50 100 100 50 50 30 30 1000 200 100 100
```

### Verify All Contact Types
```bash
./addons/sor_artwork/tests/verify_test_data.sh test_perf_manual
```

## Verification Checklist

### In Odoo UI

1. **Go to Contacts** menu
2. **Filter by Contact Type**:
   - ✅ Creator → Should show 200 Artists
   - ✅ Customer → Should show 500 contacts (all customer subtypes)
   - ✅ Consignor → Should show 50 Consignors
   - ✅ Bidder → Should show 50 Bidders
   - ✅ Donor → Should show 30 Donors
   - ✅ Advisor → Should show 30 Advisors

3. **Filter by Contact Subtype**:
   - ✅ Artist → Should show 200 Artists
   - ✅ Private Collector → Should show 150 Private Collectors
   - ✅ Corporate Collector → Should show 100 Corporate Collectors
   - ✅ Institutions Collection → Should show 50 Institutions
   - ✅ Dealer → Should show 100 Dealers
   - ✅ Buyer → Should show 100 Buyers

4. **Open Individual Contacts**:
   - ✅ Artists: Check "Contact Types" = Creator, "Contact Sub-types" = Artist
   - ✅ Private Collectors: Check "Contact Types" = Customer, "Contact Sub-types" = Private Collector
   - ✅ Corporate Collectors: Check "Contact Types" = Customer, "Contact Sub-types" = Corporate Collector
   - ✅ Institutions: Check "Contact Types" = Customer, "Contact Sub-types" = Institutions Collection
   - ✅ Dealers: Check "Contact Types" = Customer, "Contact Sub-types" = Dealer
   - ✅ Buyers: Check "Contact Types" = Customer, "Contact Sub-types" = Buyer
   - ✅ Consignors: Check "Contact Types" = Consignor, "Contact Sub-types" = (empty)
   - ✅ Bidders: Check "Contact Types" = Bidder, "Contact Sub-types" = (empty)
   - ✅ Donors: Check "Contact Types" = Donor, "Contact Sub-types" = (empty)
   - ✅ Advisors: Check "Contact Types" = Advisor, "Contact Sub-types" = (empty)

5. **Check Computed Fields**:
   - ✅ Artists: `is_creator` = True, `is_artist` = True
   - ✅ All Customer subtypes: `is_customer` = True
   - ✅ Private Collectors: `is_private_collector` = True
   - ✅ Corporate Collectors: `is_corporate_collector` = True
   - ✅ Dealers: `is_dealer` = True
   - ✅ Buyers: `is_buyer` = True

## Expected Counts (Default)

| Contact Type | Count | Type Assignment | Subtype Assignment |
|--------------|-------|-----------------|-------------------|
| Artist | 200 | Creator | Artist |
| Private Collector | 150 | Customer | Private Collector |
| Corporate Collector | 100 | Customer | Corporate Collector |
| Institutions Collection | 50 | Customer | Institutions Collection |
| Dealer | 100 | Customer | Dealer |
| Buyer | 100 | Customer | Buyer |
| Consignor | 50 | Consignor | (none) |
| Bidder | 50 | Bidder | (none) |
| Donor | 30 | Donor | (none) |
| Advisor | 30 | Advisor | (none) |
| **TOTAL** | **860** | | |

## Database Verification

The verification script checks:
- ✅ Product counts by type and subtype
- ✅ Contact counts by category
- ✅ Contacts with Creator type
- ✅ Contacts with Artist subtype
- ✅ Contacts with Customer type
- ✅ Contacts with Customer subtypes (all 5 subtypes)
- ✅ Contacts with standalone types (Consignor, Bidder, Donor, Advisor)
- ✅ Contact type assignment combinations
- ✅ Artworks linked to creators

## Related Files

- `populate_test_data.sh` - Creates all contact types and products
- `delete_test_data.sh` - Deletes all test data
- `verify_test_data.sh` - Verifies all contact types and products

---

**Last Updated**: January 14, 2026

