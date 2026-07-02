# Knowledge Base: External Locations

## What are External Locations?

External Locations represent places outside the gallery or institution where artworks are physically held — for example, a collector's home, a client's corporate premises, a storage facility, or an auction house. When an artwork moves to an External Location, it is no longer counted as part of internal stock.

Each External Location can be linked to a specific customer contact, and a single customer can have multiple External Locations with different addresses (e.g. a home and a storage facility).

**Use cases:**
- Commercial gallery: artwork delivered post-sale, or held at a client's premises on approval
- Auction house: artwork released to a buyer after sale
- Permanent collection: artwork on long-term loan, donated, or sold at auction

> **Note:** External Locations represent *where* an artwork is. The specific reason (sold, on loan, donated) is managed by separate Consignments and Loans workflows.

---

## Prerequisites

External Locations require the following to be available:

- **Inventory module** must be installed
- **SOR Contact Roles** must be installed (provides customer contact types)
- **External Locations** must be enabled in Settings (see Guide 1 below)

> **Multi-company install note:** When `sor_locations_external` is installed, the "External Locations" parent location is automatically created for **every existing company** in the database. The Settings toggle described in Guide 1 controls **menu visibility** only — the underlying location structure is already in place for all companies from the moment of install.

---

## Guide 1 — Enable External Locations

**When to use:** The first time you set up External Locations for your organisation. This is required before External Locations can be created or managed.

### Steps

1. Go to **Inventory** in the main menu.
2. Click **Configuration** → **Settings**.
3. Scroll to the **Locations** section.
4. Tick the checkbox labelled **"Track artworks at specific external locations"**.
5. Click **Save**.

### Expected outcome

- The Settings page saves without error.
- A new menu item — **External Locations** — appears under **Inventory → Configuration**.
- An "External Locations" container is created in the location tree (visible in Inventory → Configuration → External Locations as the parent grouping).

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R1 | External Locations menu visible after save | Yes — under Inventory → Configuration |
| R2 | External Locations menu absent before enabling | Yes — menu hidden until toggled on |
| R3 | Saving again with setting still ticked | No duplicate parent created |

---

## Guide 2 — Create an External Location from the Inventory Menu

**When to use:** When setting up a new off-premises location before any artwork is moved there, or when you want to register a location independently of a specific contact.

### Steps

1. Go to **Inventory → Configuration → External Locations**.
2. Click **New**.
3. Enter a descriptive **Name** for the location (e.g. "Collector A — Home", "Buyer B — Corporate HQ").
4. In the **Customer Contact** field, search for and select the customer this location belongs to.
   - Only contacts with the Customer role are shown in the search list.
   - Leave blank if the location is not linked to a specific contact.
5. The **External Address** fields (Street, City, ZIP / Postcode, Country) will populate automatically from the contact's address. Edit them if the location address differs from the contact's main address.
6. Click **Save**.

### Expected outcome

- The new External Location record is saved and appears in the External Locations list.
- The Customer Contact field shows the linked contact (if set).
- The address fields hold the values entered (independently of the contact's address).
- The location does **not** appear in the Rooms list under Inventory.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R4 | New location appears in External Locations list | Yes |
| R5 | Location absent from Rooms list | Yes — Rooms shows internal locations only |
| R6 | Address fields editable independently | Yes — editing address does not change contact record |
| R7 | Non-customer contact not selectable in Customer Contact field | Yes — field restricted to customer contacts |

---

## Guide 3 — Create an External Location from a Customer Contact

**When to use:** When working with a specific customer and you want to register one of their locations directly from their contact record — keeping context on the customer throughout.

### Steps

1. Go to **Contacts** and open the customer's record.
   - The **Create External Location** button is only visible on contacts with the **Customer** role. If you do not see the button, check that the contact has a Customer contact type assigned.
2. Click **Create External Location**.
3. A new External Location form opens as an overlay.
   - The **Customer Contact** field is pre-filled with this customer.
   - The **External Address** fields are pre-filled from the customer's address. Edit them if the location has a different address.
4. Enter a descriptive **Name** for the location.
5. Click **Save**.

### Expected outcome

- The new External Location is created and linked to this customer.
- The overlay closes and you are returned to the customer's contact record.
- The **External Locations** smart button (top of the contact form) shows an updated count.
- Clicking the smart button opens a filtered list showing only this customer's external locations.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R8 | "Create External Location" button visible on Customer contact | Yes |
| R9 | "Create External Location" button absent on non-Customer contact | Yes — hidden for non-customer contacts |
| R10 | Address pre-populated in the new location form | Yes — defaults from customer's address |
| R11 | Smart button count increments after save | Yes |
| R12 | Smart button click shows only this customer's locations | Yes — filtered list |
| R13 | Clicking button when External Locations not enabled shows an error message | Yes — UserError explaining feature must be enabled in Settings |

---

## Guide 4 — View All External Locations for a Customer

**When to use:** When you want to see all off-premises locations registered for a specific customer.

### Steps

1. Open the customer's contact record.
2. Click the **External Locations** smart button at the top of the form (shows the count of linked locations).

### Expected outcome

- A filtered list opens showing only External Locations linked to this customer.
- Each row shows the location name, customer contact, city, and country.
- The **New** button on this list pre-fills the Customer Contact with the current customer.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R14 | List shows only this customer's locations | Yes — no other customers' locations shown |
| R15 | Count on smart button matches number of rows in list | Yes |

---

## Guide 5 — View All External Locations

**When to use:** When you need a full overview of all off-premises locations across all customers, or to search and filter across locations.

### Steps

1. Go to **Inventory → Configuration → External Locations**.

### Expected outcome

- A list of all External Locations is shown, with columns for name, customer contact, city, and country.
- You can search by location name or customer contact name using the search bar.
- You can filter to show only contact-linked locations, or group by customer.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R16 | All external locations visible in list | Yes |
| R17 | Search by customer name filters list correctly | Yes |
| R18 | Group by Customer groups locations correctly | Yes |

---

## Guide 6 — Update an External Location's Address

**When to use:** When a customer's location address changes after the location was first created (e.g. they move to a new premises). The location's address is stored independently — updating it here does not affect the customer contact record.

### Steps

1. Go to **Inventory → Configuration → External Locations**.
2. Open the External Location you want to update.
3. Edit the fields in the **External Address** section (Street, City, ZIP / Postcode, Country).
4. Click **Save**.

### Expected outcome

- The location record is saved with the new address.
- The customer contact record is unchanged — their address is not updated.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R19 | Location saves with new address | Yes |
| R20 | Customer contact address unchanged after location address edit | Yes |

---

## Guide 7 — Register Multiple Locations for the Same Customer

**When to use:** When a customer has more than one off-premises location (e.g. a home and a separate storage facility).

### Steps

1. Follow **Guide 3** to create the first External Location for the customer.
2. Return to the customer contact record.
3. Click **Create External Location** again.
4. Enter the name and address for the second location.
5. Click **Save**.

### Expected outcome

- Both External Locations exist independently with their own addresses.
- The **External Locations** smart button on the contact shows a count of 2 (or more).
- Each location appears as a separate row in the External Locations list.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R21 | Two locations with different addresses coexist for same customer | Yes |
| R22 | Smart button count reflects total (e.g. 2) | Yes |
| R23 | First location unaffected after creating second | Yes |

---

## Quick Reference: Regression Test Checklist

The following table consolidates all regression checks from the guides above for use in manual regression testing.

| Ref | Area | Check | Expected |
|-----|------|-------|----------|
| R1 | Enable | External Locations menu visible after enabling in Settings | Yes |
| R2 | Enable | Menu absent before enabling | Yes |
| R3 | Enable | No duplicate parent on re-save | Yes |
| R4 | Create (Menu) | New location appears in list | Yes |
| R5 | Create (Menu) | Location absent from Rooms list | Yes |
| R6 | Create (Menu) | Address editable independently of contact | Yes |
| R7 | Create (Menu) | Non-customer contact not selectable | Yes |
| R8 | Create (Contact) | Button visible on Customer contact | Yes |
| R9 | Create (Contact) | Button absent on non-Customer contact | Yes |
| R10 | Create (Contact) | Address pre-populated from contact | Yes |
| R11 | Create (Contact) | Smart button count increments | Yes |
| R12 | Create (Contact) | Smart button shows only this customer's locations | Yes |
| R13 | Create (Contact) | Error shown when feature not enabled | Yes |
| R14 | View (Contact) | List filtered to this customer only | Yes |
| R15 | View (Contact) | Smart button count matches list rows | Yes |
| R16 | View (Menu) | All locations visible | Yes |
| R17 | View (Menu) | Search by customer name works | Yes |
| R18 | View (Menu) | Group by Customer works | Yes |
| R19 | Edit | Location saves with new address | Yes |
| R20 | Edit | Contact address unchanged after edit | Yes |
| R21 | Multiple | Two locations with distinct addresses coexist | Yes |
| R22 | Multiple | Smart button count reflects total | Yes |
| R23 | Multiple | First location unaffected by second | Yes |
