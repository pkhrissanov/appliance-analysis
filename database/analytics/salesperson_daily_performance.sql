CREATE SCHEMA IF NOT EXISTS analytics;

DROP VIEW IF EXISTS analytics.salesperson_daily_performance;

CREATE VIEW analytics.salesperson_daily_performance AS

WITH

/* ============================================================
   1. SALESPEOPLE

   Sales Consultants are the primary sellers, but Sales Managers
   may also have sales and shifts in the generated dataset.

   Keeping employee attributes here also makes Power BI visuals
   easier to build later.
   ============================================================ */
    salespeople AS (
        SELECT
            e.employee_id,
            e.store_id AS home_store_id,
            e.first_name,
            e.last_name,
            CONCAT(e.first_name, ' ', e.last_name) AS employee_name,
            e.employment_type,
            er.role_name

        FROM public.employees e

                 INNER JOIN public.employee_roles er
                            ON er.role_id = e.role_id

        WHERE er.role_name IN (
                               'Sales Consultant',
                               'Sales Manager'
            )
    ),


/* ============================================================
   2. ORDER-LEVEL SALES ACTIVITY

   Orders stay attributed to the salesperson who originally
   made the sale.

   Returned orders remain valid historical sales. Their refunds
   are handled separately on the return date.
   ============================================================ */
    order_daily AS (
        SELECT
            o.order_datetime::date AS date_key,
            o.store_id,
            o.salesperson_id AS employee_id,

            COUNT(DISTINCT o.order_id)
                                   AS order_count,

            COUNT(DISTINCT o.customer_id)
                                   AS customer_count,

            SUM(o.tax_total)
                                   AS sales_tax_amount,

            SUM(o.total_amount)
                                   AS gross_invoice_value

        FROM public.orders o

        WHERE o.salesperson_id IS NOT NULL

          AND o.order_status IN (
                                 'COMPLETED',
                                 'PARTIALLY_RETURNED',
                                 'RETURNED'
            )

        GROUP BY
            o.order_datetime::date,
            o.store_id,
            o.salesperson_id
    ),


/* ============================================================
   3. PRODUCT SALES

   Transaction-time prices and costs are already frozen on
   order_items.

   This is important because historical salesperson performance
   should not change when product_prices changes later.
   ============================================================ */
    item_daily AS (
        SELECT
            o.order_datetime::date AS date_key,
            o.store_id,
            o.salesperson_id AS employee_id,

            COUNT(oi.order_item_id)
                                   AS item_line_count,

            SUM(oi.quantity)
                                   AS units_sold,

            /* Revenue before discounts */
            SUM(
                    oi.regular_unit_price * oi.quantity
            ) AS regular_product_value,

            /* Discounts actually given */
            SUM(
                    oi.discount_amount
            ) AS discount_amount,

            /* Actual product revenue */
            SUM(
                    oi.sold_unit_price * oi.quantity
            ) AS product_revenue,

            /* Historical transaction-time product cost */
            SUM(
                    oi.unit_cost * oi.quantity
            ) AS product_cost

        FROM public.orders o

                 INNER JOIN public.order_items oi
                            ON oi.order_id = o.order_id

        WHERE o.salesperson_id IS NOT NULL

          AND o.order_status IN (
                                 'COMPLETED',
                                 'PARTIALLY_RETURNED',
                                 'RETURNED'
            )

        GROUP BY
            o.order_datetime::date,
            o.store_id,
            o.salesperson_id
    ),


/* ============================================================
   4. PROTECTION PLAN PERFORMANCE

   order_protection_plans explicitly records the employee who
   sold the protection plan.

   The generator assigns this employee from the salesperson on
   the original transaction.
   ============================================================ */
    protection_daily AS (
        SELECT
            opp.purchase_date AS date_key,
            o.store_id,
            opp.sold_by_employee_id AS employee_id,

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

        WHERE opp.sold_by_employee_id IS NOT NULL

          AND o.order_status IN (
                                 'COMPLETED',
                                 'PARTIALLY_RETURNED',
                                 'RETURNED'
            )

        GROUP BY
            opp.purchase_date,
            o.store_id,
            opp.sold_by_employee_id
    ),


/* ============================================================
   5. RETURNS

   IMPORTANT:

   The return is attributed to the ORIGINAL salesperson,
   NOT the employee who happened to process the return.

   Example:

       Sarah sells refrigerator
       Customer returns it later
       Mike processes return

   For salesperson-performance purposes, the return affects
   Sarah's sales performance, not Mike's.

   Returns are recorded on the return date.
   ============================================================ */
    return_daily AS (
        SELECT
            r.return_datetime::date AS date_key,
            r.store_id,
            o.salesperson_id AS employee_id,

            COUNT(DISTINCT r.return_id)
                                    AS return_count,

            COUNT(ri.return_item_id)
                                    AS returned_item_line_count,

            SUM(ri.quantity)
                                    AS returned_units,

            /* Pre-tax customer refund */
            SUM(ri.refund_amount)
                                    AS refund_amount,

            /* Cost originally associated with returned merchandise */
            SUM(
                    oi.unit_cost * ri.quantity
            ) AS returned_product_cost,

            /* Sellable merchandise returned to inventory */
            SUM(
                    CASE
                        WHEN ri.restockable
                            THEN ri.quantity
                        ELSE 0
                        END
            ) AS restocked_units,

            /* Product cost recovered when merchandise can be resold */
            SUM(
                    CASE
                        WHEN ri.restockable
                            THEN oi.unit_cost * ri.quantity
                        ELSE 0
                        END
            ) AS recovered_product_cost,

            /* Cost permanently lost on non-restockable merchandise */
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

                 INNER JOIN public.orders o
                            ON o.order_id = oi.order_id

        WHERE r.return_status = 'COMPLETED'

          AND o.salesperson_id IS NOT NULL

        GROUP BY
            r.return_datetime::date,
            r.store_id,
            o.salesperson_id
    ),


/* ============================================================
   6. LABOUR

   This uses the SAME compensation logic as the store-level
   performance table.

   Hourly:
       regular hours × hourly rate
       +
       overtime hours × hourly rate × 1.5

   Salaried:
       annual salary / 2080 × worked hours

   No overtime premium is applied to salaried employees.
   ============================================================ */
    labour_daily AS (
        SELECT
            es.shift_date AS date_key,
            es.store_id,
            es.employee_id,

            COUNT(es.shift_id)
                          AS shift_count,

            SUM(es.regular_hours)
                          AS regular_hours,

            SUM(es.overtime_hours)
                          AS overtime_hours,

            SUM(
                    es.regular_hours
                        +
                    es.overtime_hours
            ) AS total_hours,

            SUM(
                    CASE

                        /* --------------------
                           Hourly employee
                           -------------------- */
                        WHEN ech.hourly_rate IS NOT NULL THEN

                            (
                                es.regular_hours
                                    *
                                ech.hourly_rate
                                )

                                +

                            (
                                es.overtime_hours
                                    *
                                ech.hourly_rate
                                    *
                                1.5
                                )


                        /* --------------------
                           Salaried employee
                           -------------------- */
                        WHEN ech.annual_salary IS NOT NULL THEN

                            (
                                es.regular_hours
                                    +
                                es.overtime_hours
                                )

                                *
                            (
                                ech.annual_salary
                                    /
                                2080.0
                                )


                        ELSE 0

                        END
            ) AS labour_cost

        FROM public.employee_shifts es

                 INNER JOIN salespeople sp
                            ON sp.employee_id = es.employee_id

                 INNER JOIN public.employee_compensation_history ech
                            ON ech.employee_id = es.employee_id

                                AND es.shift_date >= ech.effective_from

                                AND (
                                   ech.effective_to IS NULL
                                       OR es.shift_date <= ech.effective_to
                                   )

        GROUP BY
            es.shift_date,
            es.store_id,
            es.employee_id
    ),


/* ============================================================
   7. ACTIVITY KEYS

   We want a salesperson/day row when ANYTHING happened:

       - they made sales
       - sold protection plans
       - received a return against previous sales
       - worked a shift

   This is particularly important for labour analysis.

   Example:

       employee works 8 hours
       makes zero sales

   We still NEED that row because it tells us something about
   their productivity.
   ============================================================ */
    activity_keys AS (

        SELECT
            date_key,
            store_id,
            employee_id
        FROM order_daily

        UNION

        SELECT
            date_key,
            store_id,
            employee_id
        FROM item_daily

        UNION

        SELECT
            date_key,
            store_id,
            employee_id
        FROM protection_daily

        UNION

        SELECT
            date_key,
            store_id,
            employee_id
        FROM return_daily

        UNION

        SELECT
            date_key,
            store_id,
            employee_id
        FROM labour_daily
    )


/* ============================================================
   8. FINAL SALESPERSON-DAY FACT VIEW
   ============================================================ */

SELECT
    ak.date_key,
    ak.store_id,
    ak.employee_id,

    sp.first_name,
    sp.last_name,
    sp.employee_name,
    sp.role_name,
    sp.employment_type,


    /* ========================================================
       SALES ACTIVITY
       ======================================================== */

    COALESCE(od.order_count, 0)
          AS order_count,

    COALESCE(od.customer_count, 0)
          AS customer_count,

    COALESCE(id.item_line_count, 0)
          AS item_line_count,

    COALESCE(id.units_sold, 0)
          AS units_sold,


    /* ========================================================
       PRODUCT SALES
       ======================================================== */

    COALESCE(id.regular_product_value, 0)
          AS regular_product_value,

    COALESCE(id.discount_amount, 0)
          AS discount_amount,

    COALESCE(id.product_revenue, 0)
          AS product_revenue,

    COALESCE(id.product_cost, 0)
          AS product_cost,


    /* ========================================================
       PROTECTION PLANS
       ======================================================== */

    COALESCE(pd.protection_plan_count, 0)
          AS protection_plan_count,

    COALESCE(pd.protected_item_line_count, 0)
          AS protected_item_line_count,

    COALESCE(pd.protection_plan_revenue, 0)
          AS protection_plan_revenue,


    /* ========================================================
       GROSS REVENUE BEFORE RETURNS
       ======================================================== */

    (
        COALESCE(id.product_revenue, 0)
            +
        COALESCE(pd.protection_plan_revenue, 0)
        ) AS gross_revenue,


    /* ========================================================
       RETURNS
       ======================================================== */

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


    /* ========================================================
       NET REVENUE
       ======================================================== */

    (
        COALESCE(id.product_revenue, 0)
            +
        COALESCE(pd.protection_plan_revenue, 0)
            -
        COALESCE(rd.refund_amount, 0)
        ) AS net_revenue,


    /* ========================================================
       NET PRODUCT COST

       Restockable returned inventory gives us its cost back.
       ======================================================== */

    (
        COALESCE(id.product_cost, 0)
            -
        COALESCE(rd.recovered_product_cost, 0)
        ) AS net_product_cost,


    /* ========================================================
       GROSS PROFIT

       Labour is deliberately NOT removed here.

       Keeping labour separate allows Power BI to calculate both:

           Gross Profit
           Gross Profit per Labour Hour
           Gross Profit - Labour Cost

       without mixing concepts.
       ======================================================== */

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


    /* ========================================================
       LABOUR
       ======================================================== */

    COALESCE(ld.shift_count, 0)
          AS shift_count,

    COALESCE(ld.regular_hours, 0)
          AS regular_hours,

    COALESCE(ld.overtime_hours, 0)
          AS overtime_hours,

    COALESCE(ld.total_hours, 0)
          AS total_hours,

    COALESCE(ld.labour_cost, 0)
          AS labour_cost,


    /* ========================================================
       OPTIONAL RECONCILIATION FIELDS
       ======================================================== */

    COALESCE(od.sales_tax_amount, 0)
          AS sales_tax_amount,

    COALESCE(od.gross_invoice_value, 0)
          AS gross_invoice_value


FROM activity_keys ak

         INNER JOIN salespeople sp
                    ON sp.employee_id = ak.employee_id


         LEFT JOIN order_daily od
                   ON od.date_key = ak.date_key
                       AND od.store_id = ak.store_id
                       AND od.employee_id = ak.employee_id


         LEFT JOIN item_daily id
                   ON id.date_key = ak.date_key
                       AND id.store_id = ak.store_id
                       AND id.employee_id = ak.employee_id


         LEFT JOIN protection_daily pd
                   ON pd.date_key = ak.date_key
                       AND pd.store_id = ak.store_id
                       AND pd.employee_id = ak.employee_id


         LEFT JOIN return_daily rd
                   ON rd.date_key = ak.date_key
                       AND rd.store_id = ak.store_id
                       AND rd.employee_id = ak.employee_id


         LEFT JOIN labour_daily ld
                   ON ld.date_key = ak.date_key
                       AND ld.store_id = ak.store_id
                       AND ld.employee_id = ak.employee_id;