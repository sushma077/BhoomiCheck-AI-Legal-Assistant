"""Due-diligence checklists. An item is marked only from what was uploaded, never as 'verified'."""
from __future__ import annotations

from core.models import ProcessedDocument

SEEN, NOT_SEEN, MANUAL = "Document seen in uploads", "Not seen in uploads", "Check in person or with an office"

# (task, why it matters, where to check, doc types that show the document was seen)
COMMON = [
    ("Compare the seller's ID with the name on the deed", "The person selling should be the person the records name.", "Original ID, deed", ()),
    ("Search for court cases about this property or the seller", "BhoomiCheck does not search court records.", "eCourts services, with a lawyer", ()),
    ("Visit the site and check who is in possession", "Papers do not show who occupies the property today.", "Site visit, neighbours", ()),
]
PURCHASE = [
    ("Collect the registered sale deed and earlier title deeds", "These show how ownership reached the seller. A search commonly goes back 30 years.", "Seller, Sub-Registrar certified copies", ("sale_deed", "gift_deed", "partition_deed")),
    ("Get an Encumbrance Certificate up to the current date", "It shows registered transactions. It may not reveal every claim, such as unregistered ones.", "Sub-Registrar office or state registration portal", ("encumbrance_certificate",)),
    ("Check the mutation record and current land record", "Shows the name in revenue records. It is not conclusive proof of title.", "Tehsil, municipal office, state land-records portal", ("mutation_record", "land_record")),
    ("Check property tax is paid up to date", "Dues can follow the property. A receipt does not prove title.", "Municipal body", ("property_tax_receipt",)),
    ("If there was a loan, get the bank's no-dues letter and release deed", "An unreleased mortgage may affect the property.", "Bank, Sub-Registrar", ()),
    ("Have a property lawyer give a written title opinion", "Only a qualified lawyer can give a legal opinion on title.", "Independent advocate", ()),
    ("Confirm stamp duty and registration charges for your state", "Rates and rules differ by state.", "State registration department", ()),
]
SALE = [
    ("Keep original title deeds and the full chain ready", "A buyer's lawyer will ask for them.", "Your records", ("sale_deed", "gift_deed", "partition_deed")),
    ("Clear any loan and get the release deed", "A buyer will need proof the charge has ended.", "Bank, Sub-Registrar", ()),
    ("Clear property tax, society and utility dues", "These are commonly checked before sale.", "Municipal body, society", ("property_tax_receipt",)),
    ("Check capital gains tax with a tax adviser", "Tax may be due on the sale.", "Chartered accountant", ()),
    ("If co-owned or inherited, get all owners' written consent", "One owner usually cannot sell another's share.", "All co-owners, with a lawyer", ()),
]
RENTAL = [
    ("Confirm the landlord has the right to let the property", "The person signing should own or be authorised.", "Title deed or tax receipt, ID", ("sale_deed", "property_tax_receipt")),
    ("Write down rent, deposit, period, notice and repairs", "Clear terms prevent disputes.", "Agreement", ("rent_agreement", "lease_deed")),
    ("Register the agreement if required", "Leases over one year generally must be registered. Some states have stricter rules.", "Sub-Registrar", ()),
    ("Check local tenant verification and rent law", "Rules differ by state. Check if your state has adopted Model Tenancy Act provisions.", "Local police, Rent Authority", ()),
    ("Record the property's condition at handover", "Helps with deposit disputes.", "Dated photos, inventory", ()),
]
AGRICULTURAL = [
    ("Get the current Khasra, Khatauni, Jamabandi or 7/12", "Shows recorded holders and survey numbers. It is not conclusive title.", "State land-records portal, Tehsil", ("land_record",)),
    ("Check who can legally buy agricultural land in this state", "Many states restrict non-agriculturist buyers.", "Revenue office, lawyer", ()),
    ("Check ceiling, tenancy and government-grant restrictions", "Some land cannot be freely transferred.", "Revenue office", ()),
    ("If you plan to build, check conversion requirements", "Using land for non-farm purposes may need permission.", "Revenue or planning authority", ()),
    ("Have the land measured against the revenue map", "Field boundaries can differ from papers.", "Licensed surveyor", ()),
]
RESIDENTIAL = [
    ("Get the sanctioned building plan", "Unauthorised construction can cause problems later.", "Development authority", ()),
    ("Get the Occupancy or Completion Certificate, where applicable", "Shows authorities cleared the building for use.", "Municipal body", ()),
    ("For a builder project, search the state RERA website", "Registered projects must disclose key details.", "State RERA portal", ("rera_document",)),
    ("Get a society or apartment NOC, if applicable", "Societies often require it for transfer.", "Society or association", ("noc",)),
]
COMMERCIAL = [
    ("Check that commercial use is permitted at this location", "Zoning decides how a property can be used.", "Development authority", ()),
    ("Check fire, trade and other operating approvals", "These depend on the business and location.", "Local authorities", ("noc",)),
    ("Check existing tenants and their lease terms", "A buyer may take the property subject to leases.", "Lease deeds, site visit", ("lease_deed", "rent_agreement")),
    ("Check property tax category and dues", "Commercial rates differ from residential rates.", "Municipal body", ("property_tax_receipt",)),
]
INHERITED = [
    ("Collect the death certificate", "Needed to establish succession.", "Local registrar", ()),
    ("Identify every legal heir, under the personal law that applies", "Heirs may have shares. This needs a lawyer.", "Lawyer, legal heir certificate", ()),
    ("If there is a will, check it, and whether probate is needed", "Rules vary by place and religion.", "Lawyer, court", ("will",)),
    ("Get all heirs' written consent or a registered relinquishment", "A buyer needs every owner's rights.", "Heirs, Sub-Registrar", ("partition_deed",)),
    ("Update mutation in the heirs' names", "Revenue records should reflect succession. Mutation is not title.", "Tehsil or municipal office", ("mutation_record",)),
]

CHECKLISTS = {
    "Property purchase": PURCHASE, "Property sale": SALE, "Rental agreement": RENTAL, "Agricultural land": AGRICULTURAL,
    "Residential property": RESIDENTIAL, "Commercial property": COMMERCIAL, "Inherited property": INHERITED,
}


def generate(context: str, docs: list[ProcessedDocument] | None = None) -> list[dict]:
    docs = docs or []
    present = {d.doc_type for d in docs if d.status in ("ok", "partial")}
    items = []
    for task, why, where, doc_types in CHECKLISTS[context] + (COMMON if context != "Rental agreement" else COMMON[:1]):
        seen = sorted(present & set(doc_types))
        if seen:
            status = SEEN
        elif doc_types:
            status = NOT_SEEN
        else:
            status = MANUAL
        items.append({"task": task, "why": why, "where": where, "status": status})
    return items


def suggest_contexts(docs: list[ProcessedDocument]) -> list[str]:
    """Which checklists fit the uploaded documents. The user can still pick others."""
    usable = [d for d in docs if d.status in ("ok", "partial")]
    types = {d.doc_type for d in usable}
    text = " ".join(d.full_text for d in usable).lower()
    out = []
    if types & {"rent_agreement", "lease_deed"}:
        out.append("Rental agreement")
    if types & {"sale_deed", "agreement_to_sell", "encumbrance_certificate", "mutation_record", "power_of_attorney"} or not out:
        out.append("Property purchase")
    if ("agricultural" in text and "non-agricultural" not in text) or "कृषि" in text:
        out.append("Agricultural land")
    if any(d.fields.get("inheritance_refs") for d in usable):
        out.append("Inherited property")
    if any(w in text for w in ("residential", "flat", "apartment", "house")):
        out.append("Residential property")
    if any(w in text for w in ("commercial", "shop", "office space")):
        out.append("Commercial property")
    return out
