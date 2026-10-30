-- Read-only arithmetic examples with SYNTHETIC prices, not company price data.
-- Quantities mean PAID catalog sales units. Gifts are additional shipped units.
-- A stacked discount/gift example is explicit, never a default campaign rule.
WITH examples(case_name, base_unit_price, paid_quantity, discount_percent, buy_quantity, free_per_bundle) AS (
    VALUES
      ('No discount', 10.00::numeric, 10, 0::numeric, NULL::integer, 0),
      ('10 percent discount', 10.00, 10, 10, NULL, 0),
      ('15 percent discount', 10.00, 10, 15, NULL, 0),
      ('Buy 2 get 1 free', 10.00, 5, 0, 2, 1),
      ('Buy 3 get 1 free', 10.00, 10, 0, 3, 1),
      ('Explicit discount and gift combination', 10.00, 10, 10, 2, 1)
), calculated AS (
    SELECT *, round(base_unit_price * (1 - discount_percent / 100), 6) AS final_unit_price,
        CASE WHEN buy_quantity IS NULL THEN 0
             ELSE (paid_quantity / buy_quantity) * free_per_bundle END AS free_quantity
    FROM examples
)
SELECT case_name, final_unit_price, paid_quantity, free_quantity,
       paid_quantity + free_quantity AS shipped_quantity,
       round(final_unit_price * paid_quantity, 2) AS payable_amount
FROM calculated;
