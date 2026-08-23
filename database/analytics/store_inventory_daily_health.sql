CREATE SCHEMA IF NOT EXISTS analytics;

DROP MATERIALIZED VIEW IF EXISTS analytics.store_inventory_daily_health;


/* ============================================================
   STORE INVENTORY DAILY HEALTH

   GRAIN:
       one date + one store + one product

   PURPOSE:
       - historical inventory position
       - inventory value
       - daily product demand
       - stockout analysis
       - slow-moving / overstock analysis
       - transfer / damage analysis

   IMPORTANT:
       Inventory snapshots in the source dataset are MONTH-END,
       not daily.

       Daily quantity-on-hand is therefore reconstructed from
       signed inventory transactions.
   ============================================================ */

CREATE MATERIALIZED VIEW analytics.store_inventory_daily_health AS

WITH


/* ============================================================
   1. CATEGORY HIERARCHY

   Resolves products into:

       Parent Category
           -> Subcategory

   Same hierarchy logic as store_category_performance.
   ============================================================ */
    category_hierarchy AS (

        SELECT
            c.category_id AS product_category_id,

            COALESCE(
                    parent.category_id,
                    c.category_id
            ) AS parent_category_id,

            COALESCE(
                    parent.category_name,
                    c.category_name
            ) AS parent_category_name,

            CASE
                WHEN c.parent_category_id IS NOT NULL
                    THEN c.category_id
                ELSE NULL
                END AS subcategory_id,

            CASE
                WHEN c.parent_category_id IS NOT NULL
                    THEN c.category_name
                ELSE NULL
                END AS subcategory_name

        FROM public.categories c

                 LEFT JOIN public.categories parent
                           ON parent.category_id = c.parent_category_id
    ),


/* ============================================================
   2. STORE / PRODUCT LIFECYCLE

   We do NOT cross join every product to every store from the
   beginning of the dataset.

   A store/product combination begins when that product first
   appears in a store inventory transaction.

   This greatly reduces unnecessary rows.
   ============================================================ */
    store_products AS (

        SELECT
            it.location_id AS store_id,
            it.product_id,

            MIN(
                    it.transaction_datetime::date
            ) AS first_inventory_date

        FROM public.inventory_transactions it

        WHERE it.location_type = 'STORE'

        GROUP BY
            it.location_id,
            it.product_id
    ),


/* ============================================================
   3. STORE / PRODUCT / DATE SPINE

   Once a product appears at a store, create one row for every
   subsequent day in the dataset.

   This is required so inventory carries forward through days
   where there were no inventory movements.
   ============================================================ */
    inventory_spine AS (

        SELECT
            d.date_key,
            sp.store_id,
            sp.product_id

        FROM store_products sp

                 INNER JOIN public.date_dimension d
                            ON d.date_key >= sp.first_inventory_date
    ),


/* ============================================================
   4. DAILY INVENTORY MOVEMENTS

   Inventory transactions already use signed quantities:

       SALE             negative
       TRANSFER_OUT     negative
       DAMAGE           negative

       CUSTOMER_RETURN  positive
       TRANSFER_IN      positive
       PURCHASE_RECEIPT positive

       ADJUSTMENT       either direction

   Aggregate those movements to one product/store/day.
   ============================================================ */
    daily_inventory_movement AS (

        SELECT
            it.transaction_datetime::date AS date_key,
            it.location_id AS store_id,
            it.product_id,


            /* Net movement during the day */
            SUM(
                    it.quantity_change
            ) AS net_inventory_change,


            /* -------------------------
               PRODUCT SALES
               ------------------------- */

            SUM(
                    CASE
                        WHEN it.transaction_type = 'SALE'
                            THEN -it.quantity_change
                        ELSE 0
                        END
            ) AS sale_units,


            /* -------------------------
               CUSTOMER RETURNS
               ------------------------- */

            SUM(
                    CASE
                        WHEN it.transaction_type = 'CUSTOMER_RETURN'
                            THEN it.quantity_change
                        ELSE 0
                        END
            ) AS customer_return_units,


            /* -------------------------
               STORE TRANSFERS
               ------------------------- */

            SUM(
                    CASE
                        WHEN it.transaction_type = 'TRANSFER_IN'
                            THEN it.quantity_change
                        ELSE 0
                        END
            ) AS transfer_in_units,


            SUM(
                    CASE
                        WHEN it.transaction_type = 'TRANSFER_OUT'
                            THEN -it.quantity_change
                        ELSE 0
                        END
            ) AS transfer_out_units,


            /* -------------------------
               DAMAGE
               ------------------------- */

            SUM(
                    CASE
                        WHEN it.transaction_type = 'DAMAGE'
                            THEN -it.quantity_change
                        ELSE 0
                        END
            ) AS damaged_units,


            /* -------------------------
               POSITIVE ADJUSTMENTS
               ------------------------- */

            SUM(
                    CASE
                        WHEN it.transaction_type = 'ADJUSTMENT'
                            AND it.quantity_change > 0
                            THEN it.quantity_change
                        ELSE 0
                        END
            ) AS adjustment_in_units,


            /* -------------------------
               NEGATIVE ADJUSTMENTS
               ------------------------- */

            SUM(
                    CASE
                        WHEN it.transaction_type = 'ADJUSTMENT'
                            AND it.quantity_change < 0
                            THEN -it.quantity_change
                        ELSE 0
                        END
            ) AS adjustment_out_units,


            /* -------------------------
               DIRECT PURCHASE RECEIPTS

               Normally purchasing occurs at warehouses, but keeping
               this allows the table to remain correct if a store
               receipt ever exists.
               ------------------------- */

            SUM(
                    CASE
                        WHEN it.transaction_type = 'PURCHASE_RECEIPT'
                            THEN it.quantity_change
                        ELSE 0
                        END
            ) AS purchase_receipt_units


        FROM public.inventory_transactions it

        WHERE it.location_type = 'STORE'

        GROUP BY
            it.transaction_datetime::date,
            it.location_id,
            it.product_id
    ),


/* ============================================================
   5. DAILY INVENTORY POSITION

   Joining the movement table to the daily spine allows the
   running total to carry inventory through days with no
   transaction.

   quantity_on_hand =
       cumulative sum of all signed inventory movements
   ============================================================ */
    inventory_position AS (

        SELECT
            sp.date_key,
            sp.store_id,
            sp.product_id,

            COALESCE(
                    dm.net_inventory_change,
                    0
            ) AS net_inventory_change,

            COALESCE(
                    dm.sale_units,
                    0
            ) AS inventory_sale_units,

            COALESCE(
                    dm.customer_return_units,
                    0
            ) AS customer_return_units,

            COALESCE(
                    dm.transfer_in_units,
                    0
            ) AS transfer_in_units,

            COALESCE(
                    dm.transfer_out_units,
                    0
            ) AS transfer_out_units,

            COALESCE(
                    dm.damaged_units,
                    0
            ) AS damaged_units,

            COALESCE(
                    dm.adjustment_in_units,
                    0
            ) AS adjustment_in_units,

            COALESCE(
                    dm.adjustment_out_units,
                    0
            ) AS adjustment_out_units,

            COALESCE(
                    dm.purchase_receipt_units,
                    0
            ) AS purchase_receipt_units,


            /* -------------------------
               END-OF-DAY INVENTORY
               ------------------------- */

            SUM(
            COALESCE(
                    dm.net_inventory_change,
                    0
            )
               )
            OVER (
                PARTITION BY
                    sp.store_id,
                    sp.product_id

                ORDER BY
                    sp.date_key

                ROWS BETWEEN
                    UNBOUNDED PRECEDING
                    AND CURRENT ROW
                ) AS quantity_on_hand


        FROM inventory_spine sp

                 LEFT JOIN daily_inventory_movement dm
                           ON dm.date_key = sp.date_key
                               AND dm.store_id = sp.store_id
                               AND dm.product_id = sp.product_id
    ),


/* ============================================================
   6. DAILY PRODUCT SALES

   Inventory movements tell us how many units physically left
   inventory.

   order_items gives us the financial side:

       revenue
       discount
       product cost
       gross profit

   Historical prices/costs are frozen on order_items.
   ============================================================ */
    daily_sales AS (

        SELECT
            o.order_datetime::date AS date_key,
            o.store_id,
            oi.product_id,

            COUNT(DISTINCT o.order_id)
                                   AS product_order_count,

            COUNT(oi.order_item_id)
                                   AS item_line_count,

            SUM(oi.quantity)
                                   AS units_sold,

            SUM(
                    oi.regular_unit_price
                        *
                    oi.quantity
            ) AS regular_product_value,

            SUM(
                    oi.discount_amount
            ) AS discount_amount,

            SUM(
                    oi.sold_unit_price
                        *
                    oi.quantity
            ) AS product_revenue,

            SUM(
                    oi.unit_cost
                        *
                    oi.quantity
            ) AS product_cost,

            SUM(
                    (
                        oi.sold_unit_price
                            -
                        oi.unit_cost
                        )
                        *
                    oi.quantity
            ) AS sales_gross_profit


        FROM public.orders o

                 INNER JOIN public.order_items oi
                            ON oi.order_id = o.order_id

        WHERE o.order_status IN (
                                 'COMPLETED',
                                 'PARTIALLY_RETURNED',
                                 'RETURNED'
            )

        GROUP BY
            o.order_datetime::date,
            o.store_id,
            oi.product_id
    )


/* ============================================================
   7. FINAL DAILY INVENTORY FACT
   ============================================================ */

SELECT

    /* ========================================================
       KEYS
       ======================================================== */

    ip.date_key,
    ip.store_id,
    ip.product_id,


    /* ========================================================
       PRODUCT DETAILS
       ======================================================== */

    p.sku,
    p.model_number,
    p.product_name,

    p.brand_id,
    b.brand_name,
    b.brand_tier,

    ch.parent_category_id,
    ch.parent_category_name,

    ch.subcategory_id,
    ch.subcategory_name,

    p.launch_date,
    p.discontinued_date,
    p.active AS product_active,


    /* ========================================================
       INVENTORY POSITION

       quantity_on_hand is END-OF-DAY stock.
       ======================================================== */

    ip.quantity_on_hand,


    /* ========================================================
       INVENTORY MOVEMENTS DURING THIS DAY
       ======================================================== */

    ip.net_inventory_change,

    ip.inventory_sale_units,

    ip.customer_return_units,

    ip.transfer_in_units,

    ip.transfer_out_units,

    ip.damaged_units,

    ip.adjustment_in_units,

    ip.adjustment_out_units,

    ip.purchase_receipt_units,


    /* ========================================================
       DAILY SELLING ACTIVITY

       These are SALES facts rather than inventory movement facts.
       They should normally reconcile closely with SALE movement
       units.
       ======================================================== */

    COALESCE(
            ds.product_order_count,
            0
    ) AS product_order_count,

    COALESCE(
            ds.item_line_count,
            0
    ) AS item_line_count,

    COALESCE(
            ds.units_sold,
            0
    ) AS units_sold,

    COALESCE(
            ds.regular_product_value,
            0
    ) AS regular_product_value,

    COALESCE(
            ds.discount_amount,
            0
    ) AS discount_amount,

    COALESCE(
            ds.product_revenue,
            0
    ) AS product_revenue,

    COALESCE(
            ds.product_cost,
            0
    ) AS product_cost,

    COALESCE(
            ds.sales_gross_profit,
            0
    ) AS sales_gross_profit,


    /* ========================================================
       HISTORICAL STANDARD COST

       Uses the product cost record that was effective on the
       inventory date.

       This is used to estimate inventory value.
       ======================================================== */

    price.standard_cost,

    price.regular_price,


    /* ========================================================
       INVENTORY VALUE

       Inventory is valued at historical standard cost.

       This is an additive value across products/stores ON THE
       SAME DATE, but must NOT be summed through time.
       ======================================================== */

    (
        ip.quantity_on_hand
            *
        price.standard_cost
        ) AS inventory_value,


    /* ========================================================
       POTENTIAL RETAIL VALUE

       Not accounting value; simply on-hand quantity multiplied
       by the regular selling price effective on that date.
       ======================================================== */

    (
        ip.quantity_on_hand
            *
        price.regular_price
        ) AS inventory_retail_value


FROM inventory_position ip


         INNER JOIN public.products p
                    ON p.product_id = ip.product_id


         INNER JOIN public.brands b
                    ON b.brand_id = p.brand_id


         INNER JOIN category_hierarchy ch
                    ON ch.product_category_id = p.category_id


         LEFT JOIN daily_sales ds
                   ON ds.date_key = ip.date_key
                       AND ds.store_id = ip.store_id
                       AND ds.product_id = ip.product_id


/* ============================================================
   HISTORICAL PRODUCT PRICE / COST

   Use the price record effective on this particular inventory
   date rather than today's price.
   ============================================================ */
         LEFT JOIN LATERAL (

    SELECT
        pp.standard_cost,
        pp.regular_price

    FROM public.product_prices pp

    WHERE pp.product_id = ip.product_id

      AND pp.effective_from <= ip.date_key

      AND (
        pp.effective_to IS NULL
            OR pp.effective_to >= ip.date_key
        )

    ORDER BY
        pp.effective_from DESC

    LIMIT 1

    ) price ON TRUE;