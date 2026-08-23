CREATE SCHEMA IF NOT EXISTS analytics;

DROP VIEW IF EXISTS analytics.store_category_performance;

CREATE VIEW analytics.store_category_performance AS

WITH

/* ============================================================
   1. CATEGORY HIERARCHY

   A product can belong either to:
     - a parent category directly, or
     - a subcategory whose parent is the main category.

   Example:

   Appliances
      -> Refrigerators

   OR, depending on your generated hierarchy:

   Refrigerators
      -> French Door
      -> Side-by-Side

   The COALESCE logic ensures we always expose a parent category.
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
   2. PRODUCT SALES BY CATEGORY

   Use transaction-time sold price and cost from order_items.

   DO NOT join product_prices because historical sale price and
   cost are already frozen on order_items.
   ============================================================ */
    sales_daily AS (
        SELECT
            o.order_datetime::date AS date_key,
            o.store_id,

            ch.parent_category_id,
            ch.parent_category_name,
            ch.subcategory_id,
            ch.subcategory_name,

            COUNT(DISTINCT o.order_id)
                                   AS order_count,

            COUNT(oi.order_item_id)
                                   AS item_line_count,

            SUM(oi.quantity)
                                   AS units_sold,

            /* Revenue at normal price before discount */
            SUM(
                    oi.regular_unit_price * oi.quantity
            ) AS regular_product_value,

            /* Explicit discount */
            SUM(
                    oi.discount_amount
            ) AS discount_amount,

            /* Actual product revenue */
            SUM(
                    oi.sold_unit_price * oi.quantity
            ) AS product_revenue,

            /* Transaction-time product cost */
            SUM(
                    oi.unit_cost * oi.quantity
            ) AS product_cost

        FROM public.orders o

                 INNER JOIN public.order_items oi
                            ON oi.order_id = o.order_id

                 INNER JOIN public.products p
                            ON p.product_id = oi.product_id

                 INNER JOIN category_hierarchy ch
                            ON ch.product_category_id = p.category_id

        WHERE o.order_status IN (
                                 'COMPLETED',
                                 'PARTIALLY_RETURNED',
                                 'RETURNED'
            )

        GROUP BY
            o.order_datetime::date,
            o.store_id,
            ch.parent_category_id,
            ch.parent_category_name,
            ch.subcategory_id,
            ch.subcategory_name
    ),


/* ============================================================
   3. PROTECTION PLAN REVENUE BY CATEGORY

   Protection plans are tied to individual order items, so we
   can attribute the plan to the category of the appliance it
   was purchased for.
   ============================================================ */
    protection_daily AS (
        SELECT
            opp.purchase_date AS date_key,
            o.store_id,

            ch.parent_category_id,
            ch.parent_category_name,
            ch.subcategory_id,
            ch.subcategory_name,

            COUNT(opp.order_protection_plan_id)
                              AS protection_plan_count,

            COUNT(DISTINCT opp.order_item_id)
                              AS protected_item_line_count,

            SUM(opp.sold_price)
                              AS protection_plan_revenue

        FROM public.order_protection_plans opp

                 INNER JOIN public.order_items oi
                            ON oi.order_item_id = opp.order_item_id

                 INNER JOIN public.orders o
                            ON o.order_id = oi.order_id

                 INNER JOIN public.products p
                            ON p.product_id = oi.product_id

                 INNER JOIN category_hierarchy ch
                            ON ch.product_category_id = p.category_id

        WHERE o.order_status IN (
                                 'COMPLETED',
                                 'PARTIALLY_RETURNED',
                                 'RETURNED'
            )

        GROUP BY
            opp.purchase_date,
            o.store_id,
            ch.parent_category_id,
            ch.parent_category_name,
            ch.subcategory_id,
            ch.subcategory_name
    ),


/* ============================================================
   4. RETURNS BY CATEGORY

   Return revenue is recorded on the RETURN DATE rather than
   changing the historical date of the original sale.

   refund_amount is the pre-tax refund.

   Restockable merchandise gives us back its inventory cost.
   ============================================================ */
    returns_daily AS (
        SELECT
            r.return_datetime::date AS date_key,
            r.store_id,

            ch.parent_category_id,
            ch.parent_category_name,
            ch.subcategory_id,
            ch.subcategory_name,

            COUNT(DISTINCT r.return_id)
                                    AS return_count,

            COUNT(ri.return_item_id)
                                    AS returned_item_line_count,

            SUM(ri.quantity)
                                    AS returned_units,

            SUM(ri.refund_amount)
                                    AS refund_amount,

            SUM(
                    oi.unit_cost * ri.quantity
            ) AS returned_product_cost,

            SUM(
                    CASE
                        WHEN ri.restockable
                            THEN ri.quantity
                        ELSE 0
                        END
            ) AS restocked_units,

            SUM(
                    CASE
                        WHEN ri.restockable
                            THEN oi.unit_cost * ri.quantity
                        ELSE 0
                        END
            ) AS recovered_product_cost,

            SUM(
                    CASE
                        WHEN NOT ri.restockable
                            THEN oi.unit_cost * ri.quantity
                        ELSE 0
                        END
            ) AS non_restockable_return_cost

        FROM public.returns r

                 INNER JOIN public.return_items ri
                            ON ri.return_id = r.return_id

                 INNER JOIN public.order_items oi
                            ON oi.order_item_id = ri.order_item_id

                 INNER JOIN public.products p
                            ON p.product_id = oi.product_id

                 INNER JOIN category_hierarchy ch
                            ON ch.product_category_id = p.category_id

        WHERE r.return_status = 'COMPLETED'

        GROUP BY
            r.return_datetime::date,
            r.store_id,
            ch.parent_category_id,
            ch.parent_category_name,
            ch.subcategory_id,
            ch.subcategory_name
    ),


/* ============================================================
   5. ALL STORE / DATE / CATEGORY COMBINATIONS THAT ACTUALLY
      HAD ACTIVITY

   Unlike store_daily_performance, I would NOT create every
   possible store x date x category combination.

   That would create a lot of unnecessary zero rows.
   ============================================================ */
    activity_keys AS (

        SELECT
            date_key,
            store_id,
            parent_category_id,
            parent_category_name,
            subcategory_id,
            subcategory_name
        FROM sales_daily

        UNION

        SELECT
            date_key,
            store_id,
            parent_category_id,
            parent_category_name,
            subcategory_id,
            subcategory_name
        FROM protection_daily

        UNION

        SELECT
            date_key,
            store_id,
            parent_category_id,
            parent_category_name,
            subcategory_id,
            subcategory_name
        FROM returns_daily
    )


/* ============================================================
   6. FINAL CATEGORY PERFORMANCE VIEW
   ============================================================ */

SELECT
    ak.date_key,
    ak.store_id,

    ak.parent_category_id,
    ak.parent_category_name,

    ak.subcategory_id,
    ak.subcategory_name,


    /* -------------------------
       SALES ACTIVITY
       ------------------------- */

    COALESCE(sd.order_count, 0)
          AS order_count,

    COALESCE(sd.item_line_count, 0)
          AS item_line_count,

    COALESCE(sd.units_sold, 0)
          AS units_sold,


    /* -------------------------
       PRODUCT REVENUE
       ------------------------- */

    COALESCE(sd.regular_product_value, 0)
          AS regular_product_value,

    COALESCE(sd.discount_amount, 0)
          AS discount_amount,

    COALESCE(sd.product_revenue, 0)
          AS product_revenue,


    /* -------------------------
       PROTECTION PLANS
       ------------------------- */

    COALESCE(pd.protection_plan_count, 0)
          AS protection_plan_count,

    COALESCE(pd.protected_item_line_count, 0)
          AS protected_item_line_count,

    COALESCE(pd.protection_plan_revenue, 0)
          AS protection_plan_revenue,


    /* -------------------------
       REVENUE BEFORE RETURNS
       ------------------------- */

    (
        COALESCE(sd.product_revenue, 0)
            +
        COALESCE(pd.protection_plan_revenue, 0)
        ) AS gross_revenue,


    /* -------------------------
       PRODUCT COST
       ------------------------- */

    COALESCE(sd.product_cost, 0)
          AS product_cost,


    /* -------------------------
       RETURNS
       ------------------------- */

    COALESCE(rd.return_count, 0)
          AS return_count,

    COALESCE(rd.returned_item_line_count, 0)
          AS returned_item_line_count,

    COALESCE(rd.returned_units, 0)
          AS returned_units,

    COALESCE(rd.refund_amount, 0)
          AS refund_amount,

    COALESCE(rd.returned_product_cost, 0)
          AS returned_product_cost,

    COALESCE(rd.restocked_units, 0)
          AS restocked_units,

    COALESCE(rd.recovered_product_cost, 0)
          AS recovered_product_cost,

    COALESCE(rd.non_restockable_return_cost, 0)
          AS non_restockable_return_cost,


    /* -------------------------
       NET REVENUE
       ------------------------- */

    (
        COALESCE(sd.product_revenue, 0)
            +
        COALESCE(pd.protection_plan_revenue, 0)
            -
        COALESCE(rd.refund_amount, 0)
        ) AS net_revenue,


    /* -------------------------
       NET PRODUCT COST

       Cost recovered from restockable returns is removed from
       COGS.
       ------------------------- */

    (
        COALESCE(sd.product_cost, 0)
            -
        COALESCE(rd.recovered_product_cost, 0)
        ) AS net_product_cost,


    /* -------------------------
       GROSS PROFIT
       ------------------------- */

    (
        COALESCE(sd.product_revenue, 0)
            +
        COALESCE(pd.protection_plan_revenue, 0)
            -
        COALESCE(rd.refund_amount, 0)
            -
        COALESCE(sd.product_cost, 0)
            +
        COALESCE(rd.recovered_product_cost, 0)
        ) AS gross_profit


FROM activity_keys ak

         LEFT JOIN sales_daily sd
                   ON sd.date_key = ak.date_key
                       AND sd.store_id = ak.store_id
                       AND sd.parent_category_id = ak.parent_category_id
                       AND sd.subcategory_id IS NOT DISTINCT FROM ak.subcategory_id

         LEFT JOIN protection_daily pd
                   ON pd.date_key = ak.date_key
                       AND pd.store_id = ak.store_id
                       AND pd.parent_category_id = ak.parent_category_id
                       AND pd.subcategory_id IS NOT DISTINCT FROM ak.subcategory_id

         LEFT JOIN returns_daily rd
                   ON rd.date_key = ak.date_key
                       AND rd.store_id = ak.store_id
                       AND rd.parent_category_id = ak.parent_category_id
                       AND rd.subcategory_id IS NOT DISTINCT FROM ak.subcategory_id;