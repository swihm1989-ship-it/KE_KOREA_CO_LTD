# ECLADO catalog SQL package

Target project: `jusozufdsnpdxezxptfp`  
Project URL: https://jusozufdsnpdxezxptfp.supabase.co  
Status: SQL prepared locally. No remote connection, table creation or data upload has occurred.

## Local API credentials

The ignored local [`.env` file](../.env) has placeholders for the OpenAI API and this Supabase project. The Git-safe [`.env.example` template](../.env.example) has the same variable names. Keep real keys in `.env` only.

1. Create an OpenAI project API key in the [OpenAI API platform](https://platform.openai.com/api-keys). Paste it into `OPENAI_API_KEY`. Set `OPENAI_MODEL` to a model enabled for that API project.
2. In the Supabase dashboard for project `jusozufdsnpdxezxptfp`, open **Settings → API Keys**. Copy the publishable key to `SUPABASE_PUBLISHABLE_KEY` if public/client access is later needed. Copy the secret key to `SUPABASE_SECRET_KEY` only for server-side code with its own access checks.
3. `SUPABASE_URL` is already set to the project URL supplied by the user.

The Supabase secret key has elevated access and bypasses RLS, so never put it in browser code or source control. The current database grants in the prepared migration are also separate from these API credentials; the migration and seed still need to be run in the dashboard SQL Editor. An API key by itself does not apply SQL migrations.

No API keys were created, retrieved, or saved here. Once you paste your keys into `.env`, the Python application can load them as environment variables after its API client configuration is implemented.

## Files and application order

1. Review and run [the schema migration](migrations/202610300001_eclado_catalog.sql) in the intended project's SQL Editor as the database owner. It creates four new tables inside one transaction. It does not drop or replace existing tables. If the names already exist, inspect them before applying an adapted migration.
2. Review and run [the private data seed](../private/eclado/002_eclado_catalog_seed.sql). It contains the real product names, purchase prices and buyer prices and is excluded from Git. Do not put it in a public repository or send it to a different project.
3. Run [verification queries](verify_catalog.sql). Match the exact import ID against [the private import report](../private/eclado/import_report.json). For this source import, expect 157 products, 157 purchase prices and 157 buyer prices.

`seed_template.sql` is a generator template, not an executable data seed. Do not run it directly.

## Tables

| Table | Purpose |
| --- | --- |
| `public.kekorea_catalog_imports` | Source file names and SHA-256 hashes, source label, import time and validation issues |
| `public.kekorea_products` | Distinct catalog products, original codes, English item names and source capacities |
| `public.kekorea_purchase_prices` | ECLADO-to-KE KOREA costs, currency, source cell references and packing reference data |
| `public.kekorea_buyer_prices` | KE KOREA-to-Dear Glow base sales prices, currency, source cell references and reference discounts |

Price records belong to a source import. A new price-list file creates a new import rather than overwriting previous prices. The same ordered source manifest (roles, filenames and file hashes) generates the same import and price IDs. Reapplying an identical seed does not create duplicate rows. A changed payload for an existing import, or differing existing product/price fields, causes a transaction error instead of silently skipping the conflict. Review such conflicts as an explicit catalog or extraction revision. Effective dates remain null because a filename does not establish contractual price validity. The future quotation engine must select a confirmed price snapshot explicitly.

## Confirmed source mapping

| Source | Sheet / column | Meaning |
| --- | --- | --- |
| KRW workbook | `ECLADO_Products_List!N` | Purchase price, KRW per catalog unit |
| Buyer workbook | `ECLADO_Products_List!N` | Dear Glow base sale price, USD per catalog unit |
| KRW workbook | `ECLADO_Products_List!P` | Independent cross-check of the same Dear Glow base sale price |
| KRW / buyer workbooks | main-sheet `Q` / `O` | Reference price at 10% discount; checked against the base price with Decimal |
| KRW workbook | `Sample!C` | Sample purchase price, KRW |
| Buyer workbook | `Sample!C` | Sample sale price, KRW; not USD |

The original data contains 131 standard catalog products and 26 samples. Standard catalog entries include the equipment/accessories listed in the workbooks. All 131 base sales prices match across both files; both reference discount columns reconcile. Retail/wholesale prices, workbook profit formulas and FX-derived USD purchase values are not imported as costs or buyer sale prices.

`CATALOG_UNIT` means one complete sale unit as described by Capacity. For example, a capacity describing a multi-piece pack does not multiply the order quantity automatically. Samples have no supplied capacity and remain null. They are separate products even when their names match full-size items.

## Source exceptions

- Standard code `73568` is assigned to both Exo Clinica Toner / 500ml and Exo Clinica Cream / 50g. Separate deterministic product IDs preserve both. Product code alone is not a key.
- `MK-2`, main-sheet row 112, has a numeric carton-size result and an implausible gross-weight formula. The source values remain reference metadata marked `needs_review`; do not use them as verified shipping data.
- The 26 sample capacities are not supplied. Confirm actual capacity and packing information before issuing documents that require them.
- Source terms differ: the KRW workbook mentions FOB / EX VAT, while the buyer workbook mentions CIF PORT (Sea Freight ONLY). These are source context, not permanently active Incoterms for future documents.

## Discounts and promotions

The imported 10% discount is a source reference, not an active global campaign. Store and select the order's actual discount separately; 0%, 10%, 15% or another confirmed rate can be used without replacing the base price.

```text
final_unit_price = base_sale_price * (1 - discount_percent / 100)
payable_amount = final_unit_price * paid_quantity
free_quantity = floor(paid_quantity / buy_quantity) * free_per_bundle
shipped_quantity = paid_quantity + free_quantity
```

The same-product initial interpretation is Buy 2 Get 1 Free and Buy 3 Get 1 Free. The user must specify whether a requested quantity is paid quantity or total shipped quantity if ambiguous. Different-product gifts, mixed-SKU eligibility, caps, campaign dates and discount/gift stacking require explicit rules. Do not activate a discount and gift campaign together without choosing that combination.

Future invoices should show paid and `Free of Charge (FOC)` quantities distinctly, with no additional charge for the gift line. Packing lists and stock movements include all shipped units. For commercial invoices, keep the amount charged and the confirmed customs-declaration value separate; do not infer the latter from a zero-charge gift line. CI finalization requires the applicable declared values to be confirmed.

[Pricing examples](pricing_examples.sql) demonstrate the arithmetic using synthetic prices. They are read-only examples, not an implemented promotion engine or invoice generator. Unit-price precision, currency-specific rounding and final document layouts still need implementation and validation.

## English document requirement

All generated PO, PI, CI, PL and inventory annexes must use English headings, product descriptions, dates, terms, remarks and amount-in-words text. Retain verified registered company names and source technical symbols. Translate Korean free text into a reviewable English draft; do not invent legal company names. Korean input remains supported. Internal developer notes may remain Korean.

## Access and verification limits

The schema enables RLS and revokes public, anonymous and general authenticated access. No public access policies are created. The backend service role receives SELECT/INSERT, while database-owner access is used for administration. Do not expose a secret key to the browser. Employee access policies can be added after authentication and role requirements are defined.

Source extraction and synthetic import tests have run locally. PostgreSQL syntax, database constraints, actual grants and RLS have not been executed against Supabase in this phase. Run the migration, seed and verification queries before treating the database as populated or the access policy as tested.

Official references: [OpenAI project API keys](https://help.openai.com/en/articles/9186755-managing-projects-in-the-api-platform), [Supabase API keys](https://supabase.com/docs/guides/getting-started/api-keys), [Supabase migrations](https://supabase.com/docs/guides/deployment/database-migrations), [RLS and grants](https://supabase.com/docs/guides/database/postgres/row-level-security).

## Regenerating the private seed

Requires Python 3.12+ and `openpyxl` for read-only extraction. Run from the repository root with the supplied files' actual paths:

```powershell
python Quotation_KEKOREA/scripts/build_eclado_seed.py --purchase "<KRW workbook path>" --buyer "<buyer workbook path>"
python -m unittest discover -s Quotation_KEKOREA/tests -v
```

No source workbook is edited. The generator performs no network requests and never applies SQL. It writes `002_eclado_catalog_seed.sql` and `import_report.json` under the ignored `Quotation_KEKOREA/private/eclado/` directory.

The CLI requires 131 standard products and 26 samples for this source snapshot, so matching truncated copies cannot silently pass. For a reviewed future catalog with different counts, pass explicit `--expected-standard-count` and `--expected-sample-count` values.
