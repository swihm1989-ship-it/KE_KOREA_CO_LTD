-- Confidential commercial data. Generated seed must remain outside Git.
-- Run only after the schema migration, in the intended project's SQL Editor.
BEGIN;
DO $kekorea_import$
DECLARE
    payload jsonb := $kekorea_seed$__CATALOG_JSON__$kekorea_seed$::jsonb;
    batch_id uuid := (payload->'import'->>'id')::uuid;
    expected_count integer := jsonb_array_length(payload->'products');
    actual_count integer;
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.kekorea_catalog_imports i WHERE i.id = batch_id
        AND (i.payload_sha256 IS DISTINCT FROM payload->'import'->>'payload_sha256'
             OR i.source_files IS DISTINCT FROM payload->'import'->'source_files'
             OR i.source_label IS DISTINCT FROM payload->'import'->>'source_label'
             OR i.validation_issues IS DISTINCT FROM payload->'import'->'validation_issues')
    ) THEN
        RAISE EXCEPTION 'Existing import differs from the prepared payload; review the extraction revision before applying.';
    END IF;

    INSERT INTO public.kekorea_catalog_imports(id, source_label, source_files, validation_issues, payload_sha256)
    VALUES (batch_id, payload->'import'->>'source_label', payload->'import'->'source_files',
            payload->'import'->'validation_issues', payload->'import'->>'payload_sha256') ON CONFLICT (id) DO NOTHING;

    INSERT INTO public.kekorea_products(id, identity_key, brand, kind, source_code,
                                       item_name, capacity, group_name, metadata)
    SELECT id, identity_key, brand, kind, source_code, item_name, capacity, group_name, metadata
    FROM jsonb_to_recordset(payload->'products') AS x(
        id uuid, identity_key text, brand text, kind text, source_code text,
        item_name text, capacity text, group_name text, metadata jsonb)
    ON CONFLICT (id) DO NOTHING;

    IF EXISTS (
        SELECT 1 FROM jsonb_to_recordset(payload->'products') AS x(
            id uuid, identity_key text, brand text, kind text, source_code text,
            item_name text, capacity text, group_name text, metadata jsonb)
        JOIN public.kekorea_products p ON p.id = x.id
        WHERE (to_jsonb(p) - 'created_at') IS DISTINCT FROM to_jsonb(x)
    ) THEN
        RAISE EXCEPTION 'Existing product differs from the source product; resolve the catalog conflict explicitly.';
    END IF;

    INSERT INTO public.kekorea_purchase_prices(id, import_id, product_id, supplier_key,
        currency, unit_price, source_sheet, source_row, source_column, source_reference)
    SELECT id, import_id, product_id, supplier_key, currency, unit_price,
           source_sheet, source_row, source_column, source_reference
    FROM jsonb_to_recordset(payload->'purchase_prices') AS x(
        id uuid, import_id uuid, product_id uuid, supplier_key text, currency text,
        unit_price numeric, source_sheet text, source_row integer, source_column text, source_reference jsonb)
    ON CONFLICT (id) DO NOTHING;

    IF EXISTS (
        SELECT 1 FROM jsonb_to_recordset(payload->'purchase_prices') AS x(
            id uuid, import_id uuid, product_id uuid, supplier_key text, currency text,
            unit_price numeric, source_sheet text, source_row integer, source_column text, source_reference jsonb)
        JOIN public.kekorea_purchase_prices p ON p.id = x.id
        WHERE (to_jsonb(p) - ARRAY['price_basis', 'effective_from', 'effective_to']) IS DISTINCT FROM to_jsonb(x)
    ) THEN
        RAISE EXCEPTION 'Existing purchase prices differ from the prepared payload.';
    END IF;

    INSERT INTO public.kekorea_buyer_prices(id, import_id, product_id, buyer_key, currency,
        unit_price, reference_discount_percent, reference_discounted_price,
        source_sheet, source_row, source_column, source_reference)
    SELECT id, import_id, product_id, buyer_key, currency, unit_price,
           reference_discount_percent, reference_discounted_price,
           source_sheet, source_row, source_column, source_reference
    FROM jsonb_to_recordset(payload->'buyer_prices') AS x(
        id uuid, import_id uuid, product_id uuid, buyer_key text, currency text, unit_price numeric,
        reference_discount_percent numeric, reference_discounted_price numeric,
        source_sheet text, source_row integer, source_column text, source_reference jsonb)
    ON CONFLICT (id) DO NOTHING;

    IF EXISTS (
        SELECT 1 FROM jsonb_to_recordset(payload->'buyer_prices') AS x(
            id uuid, import_id uuid, product_id uuid, buyer_key text, currency text, unit_price numeric,
            reference_discount_percent numeric, reference_discounted_price numeric,
            source_sheet text, source_row integer, source_column text, source_reference jsonb)
        JOIN public.kekorea_buyer_prices p ON p.id = x.id
        WHERE (to_jsonb(p) - ARRAY['price_basis', 'effective_from', 'effective_to']) IS DISTINCT FROM to_jsonb(x)
    ) THEN
        RAISE EXCEPTION 'Existing buyer prices differ from the prepared payload.';
    END IF;

    SELECT count(*) INTO actual_count FROM public.kekorea_purchase_prices WHERE import_id = batch_id;
    IF actual_count <> expected_count THEN
        RAISE EXCEPTION 'Purchase count mismatch: expected %, got %', expected_count, actual_count;
    END IF;
    SELECT count(*) INTO actual_count FROM public.kekorea_buyer_prices WHERE import_id = batch_id;
    IF actual_count <> expected_count THEN
        RAISE EXCEPTION 'Buyer price count mismatch: expected %, got %', expected_count, actual_count;
    END IF;
END;
$kekorea_import$;
COMMIT;
