-- Read-only verification after applying the schema and private seed.
-- Identify the exact import_id from private/eclado/import_report.json.
-- The original two workbooks should yield 157 products and 157 prices per side.
SELECT i.id AS import_id, i.source_label,
       (SELECT count(*) FROM public.kekorea_purchase_prices c WHERE c.import_id = i.id) AS purchase_prices,
       (SELECT count(*) FROM public.kekorea_buyer_prices b WHERE b.import_id = i.id) AS buyer_prices,
       (SELECT count(DISTINCT b.product_id) FROM public.kekorea_buyer_prices b WHERE b.import_id = i.id) AS products
FROM public.kekorea_catalog_imports i
ORDER BY i.imported_at DESC;

-- Original import: standard/KRW purchase = 131; standard/USD sale = 131;
-- sample/KRW purchase = 26; sample/KRW sale = 26.
SELECT c.import_id, 'purchase' AS price_side, p.kind, c.currency, count(*) AS price_count
FROM public.kekorea_purchase_prices c JOIN public.kekorea_products p ON p.id = c.product_id
GROUP BY c.import_id, p.kind, c.currency
UNION ALL
SELECT b.import_id, 'sale', p.kind, b.currency, count(*)
FROM public.kekorea_buyer_prices b JOIN public.kekorea_products p ON p.id = b.product_id
GROUP BY b.import_id, p.kind, b.currency
ORDER BY 1, 2, 3, 4;

-- Should return no rows: every imported sale price must have a matching cost.
SELECT b.import_id, b.product_id AS missing_purchase_product_id
FROM public.kekorea_buyer_prices b
LEFT JOIN public.kekorea_purchase_prices c ON c.import_id = b.import_id AND c.product_id = b.product_id
WHERE c.id IS NULL;

-- Should return no rows: reference discount must agree with the base price.
SELECT id AS inconsistent_reference_discount_id
FROM public.kekorea_buyer_prices
WHERE reference_discount_percent IS NOT NULL
  AND reference_discounted_price IS DISTINCT FROM round(unit_price * (1 - reference_discount_percent / 100), 6);

-- Expected source exception: code 73568 belongs to two different standard items.
SELECT brand, kind, source_code, count(*) AS distinct_products,
       jsonb_agg(jsonb_build_object('product_id', id, 'item', item_name, 'capacity', capacity)) AS choices
FROM public.kekorea_products
GROUP BY brand, kind, source_code HAVING count(*) > 1;

-- All four rows should show rls_enabled=true, anon_can_select=false,
-- authenticated_can_select=false, backend_can_select=true, backend_can_update=false.
SELECT c.relname AS table_name, c.relrowsecurity AS rls_enabled,
       has_table_privilege('anon', c.oid, 'SELECT') AS anon_can_select,
       has_table_privilege('authenticated', c.oid, 'SELECT') AS authenticated_can_select,
       has_table_privilege('service_role', c.oid, 'SELECT') AS backend_can_select,
       has_table_privilege('service_role', c.oid, 'UPDATE') AS backend_can_update
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relname IN
    ('kekorea_catalog_imports', 'kekorea_products', 'kekorea_purchase_prices', 'kekorea_buyer_prices');
