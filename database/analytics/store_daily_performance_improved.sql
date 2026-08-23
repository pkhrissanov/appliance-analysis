CREATE SCHEMA IF NOT EXISTS analytics;

DROP VIEW IF EXISTS analytics.store_daily_performance;

CREATE VIEW analytics.store_daily_performance AS

WITH

/* ============================================================
   1. STORE x DATE SPINE

   Guarantees one row per store per day, even when the store
   had no sales that day.

   This is useful for continuous Power BI time series and means
   labour-only / return-only days are not lost.
   ============================================================ */
    store_dates AS (
        SELECT
            d.date_key,
            s.store_id
        FROM public.date_dimension d
                 CROSS JOIN public.stores s
        WHERE d.date_key >= s.opening_date
    ),


/* ============================================================
   2. ORDER-LEVEL METRICS

   Include fulfilled sales, including orders that were later
   partially or fully returned.

   The original sale remains a valid transaction. Returns are
   accounted for separately on the date the return occurred.
   ============================================================ */
    order_daily AS (
        SELECT
            o.order_datetime::date AS date_key,
            o.store_id,

            COUNT(*) AS order_count,
            COUNT(DISTINCT o.customer_id) AS customer_count,

            SUM(o.tax_total) AS sales_tax_amount,
            SUM(o.total_amount) AS gross_invoice_value

        FROM public.orders o

        WHERE o.order_status IN (
                                 'COMPLETED',
                                 'PARTIALLY_RETURNED',
                                 'RETURNED'
            )

        GROUP BY
            o.order_datetime::date,
            o.store_id
    ),


/* ============================================================
   3. PRODUCT SALES

   Transaction-time sale price and cost are already frozen on
   order_items, so DO NOT join product_prices here.

   That is exactly why we stored those values on order_items.
   ============================================================ */
    item_daily AS (
        SELECT
            o.order_datetime::date AS date_key,
            o.store_id,

            COUNT(oi.order_item_id) AS item_line_count,
            SUM(oi.quantity) AS units_sold,

            /* Value before discount */
            SUM(
                    oi.regular_unit_price * oi.quantity
            ) AS regular_product_value,

            /* Explicit discount recorded on the line */
            SUM(
                    oi.discount_amount
            ) AS discount_amount,

            /* Actual product revenue after discount */
            SUM(
                    oi.sold_unit_price * oi.quantity
            ) AS product_revenue,

            /* Transaction-time cost of goods sold */
            SUM(
                    oi.unit_cost * oi.quantity
            ) AS product_cost

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
            o.store_id
    ),


/* ============================================================
   4. PROTECTION PLAN SALES

   Plans are stored separately from order_items, so aggregate
   them separately before joining to the store/day grain.

   This avoids multiplying product revenue when an order has
   multiple items / plans.
   ============================================================ */
    protection_daily AS (
        SELECT
            opp.purchase_date AS date_key,
            o.store_id,

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

        WHERE o.order_status IN (
                                 'COMPLETED',
                                 'PARTIALLY_RETURNED',
                                 'RETURNED'
            )

        GROUP BY
            opp.purchase_date,
            o.store_id
    ),


/* ============================================================
   5. RETURNS

   IMPORTANT:
   return_items.refund_amount is PRE-TAX.

   returns.refund_total includes tax, so return_items is the
   correct source for revenue / gross-profit calculations.

   We also distinguish restockable returns because their
   product cost can be recovered into inventory.
   ============================================================ */
    return_daily AS (
        SELECT
            r.return_datetime::date AS date_key,
            r.store_id,

            COUNT(DISTINCT r.return_id)
                                    AS return_count,

            COUNT(ri.return_item_id)
                                    AS returned_item_line_count,

            SUM(ri.quantity)
                                    AS returned_units,

            /* Pre-tax money refunded to customer */
            SUM(ri.refund_amount)
                                    AS refund_amount,

            /* Cost originally attached to returned merchandise */
            SUM(
                    oi.unit_cost * ri.quantity
            ) AS returned_product_cost,

            /* Inventory that can be placed back into sellable stock */
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

            /* Product cost we cannot recover */
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

        WHERE r.return_status = 'COMPLETED'

        GROUP BY
            r.return_datetime::date,
            r.store_id
    ),


/* ============================================================
   6. LABOUR

   Match each shift to the compensation rate effective on
   that shift date.

   Hourly employees:
      regular hours * hourly rate
      overtime hours * hourly rate * 1.5

   Salaried employees:
      annual salary / 2080 gives an approximate hourly cost.
      No overtime premium is applied to salaried employees.
   ============================================================ */
    labour_daily AS (
        SELECT
            es.shift_date AS date_key,
            es.store_id,

            COUNT(DISTINCT es.employee_id)
                          AS employees_worked,

            SUM(es.regular_hours)
                          AS regular_labour_hours,

            SUM(es.overtime_hours)
                          AS overtime_labour_hours,

            SUM(
                    es.regular_hours + es.overtime_hours
            ) AS total_labour_hours,

            SUM(
                    CASE

                        /* Hourly employee */
                        WHEN ech.hourly_rate IS NOT NULL THEN

                            (es.regular_hours * ech.hourly_rate)
                                +
                            (es.overtime_hours * ech.hourly_rate * 1.5)

                        /* Salaried employee */
                        WHEN ech.annual_salary IS NOT NULL THEN

                            (es.regular_hours + es.overtime_hours)
                                * (ech.annual_salary / 2080.0)

                        ELSE 0

                        END
            ) AS labour_cost

        FROM public.employee_shifts es

                 INNER JOIN public.employee_compensation_history ech
                            ON ech.employee_id = es.employee_id
                                AND es.shift_date >= ech.effective_from
                                AND (
                                   ech.effective_to IS NULL
                                       OR es.shift_date <= ech.effective_to
                                   )

        GROUP BY
            es.shift_date,
            es.store_id
    )


/* ============================================================
   7. FINAL STORE-DAY FACT TABLE
   ============================================================ */

SELECT
    sd.date_key,
    sd.store_id,


    /* -------------------------
       CUSTOMER / ORDER ACTIVITY
       ------------------------- */

    COALESCE(od.order_count, 0)
          AS order_count,

    COALESCE(od.customer_count, 0)
          AS customer_count,

    COALESCE(id.item_line_count, 0)
          AS item_line_count,

    COALESCE(id.units_sold, 0)
          AS units_sold,


    /* -------------------------
       SALES
       ------------------------- */

    COALESCE(id.regular_product_value, 0)
          AS regular_product_value,

    COALESCE(id.discount_amount, 0)
          AS discount_amount,

    COALESCE(id.product_revenue, 0)
          AS product_revenue,

    COALESCE(pd.protection_plan_revenue, 0)
          AS protection_plan_revenue,

    (
        COALESCE(id.product_revenue, 0)
            +
        COALESCE(pd.protection_plan_revenue, 0)
        ) AS gross_revenue,


    /* -------------------------
       PRODUCT COST
       ------------------------- */

    COALESCE(id.product_cost, 0)
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
       NET SALES

       Revenue after completed returns
       ------------------------- */

    (
        COALESCE(id.product_revenue, 0)
            +
        COALESCE(pd.protection_plan_revenue, 0)
            -
        COALESCE(rd.refund_amount, 0)
        ) AS net_revenue,


    /* -------------------------
       NET PRODUCT COST

       Restockable merchandise is recovered,
       non-restockable merchandise remains a cost.
       ------------------------- */

    (
        COALESCE(id.product_cost, 0)
            -
        COALESCE(rd.recovered_product_cost, 0)
        ) AS net_product_cost,


    /* -------------------------
       GROSS PROFIT

       Net revenue - net COGS

       Labour is NOT deducted here.
       ------------------------- */

    (
        COALESCE(id.product_revenue, 0)
            +
        COALESCE(pd.protection_plan_revenue, 0)
            -
        COALESCE(rd.refund_amount, 0)
            -
        COALESCE(id.product_cost, 0)
            +
        COALESCE(rd.recovered_product_cost, 0)
        ) AS gross_profit,


    /* -------------------------
       PROTECTION PLANS
       ------------------------- */

    COALESCE(pd.protection_plan_count, 0)
          AS protection_plan_count,

    COALESCE(pd.protected_item_line_count, 0)
          AS protected_item_line_count,


    /* -------------------------
       LABOUR
       ------------------------- */

    COALESCE(ld.employees_worked, 0)
          AS employees_worked,

    COALESCE(ld.regular_labour_hours, 0)
          AS regular_labour_hours,

    COALESCE(ld.overtime_labour_hours, 0)
          AS overtime_labour_hours,

    COALESCE(ld.total_labour_hours, 0)
          AS total_labour_hours,

    COALESCE(ld.labour_cost, 0)
          AS labour_cost,


    /* -------------------------
       OPTIONAL RECONCILIATION
       ------------------------- */

    COALESCE(od.sales_tax_amount, 0)
          AS sales_tax_amount,

    COALESCE(od.gross_invoice_value, 0)
          AS gross_invoice_value


FROM store_dates sd

         LEFT JOIN order_daily od
                   ON od.date_key = sd.date_key
                       AND od.store_id = sd.store_id

         LEFT JOIN item_daily id
                   ON id.date_key = sd.date_key
                       AND id.store_id = sd.store_id

         LEFT JOIN protection_daily pd
                   ON pd.date_key = sd.date_key
                       AND pd.store_id = sd.store_id

         LEFT JOIN return_daily rd
                   ON rd.date_key = sd.date_key
                       AND rd.store_id = sd.store_id

         LEFT JOIN labour_daily ld
                   ON ld.date_key = sd.date_key
                       AND ld.store_id = sd.store_id;