CREATE SCHEMA IF NOT EXISTS analytics;


CREATE OR REPLACE VIEW analytics.store_daily_performance AS

WITH

    sales AS (
        SELECT
            o.store_id,
            o.order_datetime::date AS performance_date,

            COUNT(DISTINCT o.order_id) AS orders,
            SUM(oi.quantity) AS units_sold,

            /* Actual product revenue at transaction-time selling price */
            SUM(
                    oi.quantity * oi.sold_unit_price
            ) AS product_revenue,

            /* Historical COGS frozen on order_items */
            SUM(
                    oi.quantity * oi.unit_cost
            ) AS cogs,

            SUM(
                    oi.quantity * (oi.sold_unit_price - oi.unit_cost)
            ) AS gross_profit_before_returns,

            SUM(oi.discount_amount) AS discount_amount,

            SUM(
                    oi.quantity * oi.regular_unit_price
            ) AS regular_price_value

        FROM orders o
                 JOIN order_items oi
                      ON oi.order_id = o.order_id

        WHERE o.order_status IN (
                                 'COMPLETED',
                                 'PARTIALLY_RETURNED',
                                 'RETURNED'
            )

        GROUP BY
            o.store_id,
            o.order_datetime::date
    ),


    return_activity AS (
        SELECT
            r.store_id,
            r.return_datetime::date AS performance_date,

            SUM(ri.quantity) AS returned_units,

            SUM(ri.refund_amount) AS refund_amount,

            SUM(
                    CASE
                        WHEN ri.restockable
                            THEN ri.quantity * oi.unit_cost
                        ELSE 0
                        END
            ) AS recovered_cogs

        FROM returns r
                 JOIN return_items ri
                      ON ri.return_id = r.return_id
                 JOIN order_items oi
                      ON oi.order_item_id = ri.order_item_id

        WHERE r.return_status = 'COMPLETED'

        GROUP BY
            r.store_id,
            r.return_datetime::date
    ),

    plan_sales AS (
        SELECT
            o.store_id,
            o.order_datetime::date AS performance_date,

            COUNT(DISTINCT opp.order_item_id)
                                   AS protected_item_lines,

            SUM(opp.sold_price)
                                   AS protection_plan_revenue

        FROM order_protection_plans opp
                 JOIN order_items oi
                      ON oi.order_item_id = opp.order_item_id
                 JOIN orders o
                      ON o.order_id = oi.order_id

        WHERE o.order_status IN (
                                 'COMPLETED',
                                 'PARTIALLY_RETURNED',
                                 'RETURNED'
            )

        GROUP BY
            o.store_id,
            o.order_datetime::date
    ),

    plan_eligible AS (
        SELECT
            o.store_id,
            o.order_datetime::date AS performance_date,

            COUNT(DISTINCT oi.order_item_id)
                                   AS eligible_item_lines

        FROM orders o
                 JOIN order_items oi
                      ON oi.order_id = o.order_id

        WHERE o.order_status IN (
                                 'COMPLETED',
                                 'PARTIALLY_RETURNED',
                                 'RETURNED'
            )

          AND EXISTS (
            SELECT 1
            FROM protection_plans pp
            WHERE
                (pp.minimum_item_price IS NULL
                    OR oi.sold_unit_price >= pp.minimum_item_price)

              AND

                (pp.maximum_item_price IS NULL
                    OR oi.sold_unit_price <= pp.maximum_item_price)
        )

        GROUP BY
            o.store_id,
            o.order_datetime::date
    ),


    labour AS (
        SELECT
            es.store_id,
            es.shift_date AS performance_date,

            SUM(
                    es.regular_hours + es.overtime_hours
            ) AS labour_hours,

            SUM(
                    CASE
                        WHEN ech.hourly_rate IS NOT NULL THEN
                            (es.regular_hours * ech.hourly_rate)
                                +
                            (es.overtime_hours * ech.hourly_rate * 1.5)

                        WHEN ech.annual_salary IS NOT NULL THEN
                            (es.regular_hours + es.overtime_hours)
                                * (ech.annual_salary / 2080.0)

                        ELSE 0
                        END
            ) AS labour_cost

        FROM employee_shifts es
                 JOIN employee_compensation_history ech
                      ON ech.employee_id = es.employee_id
                          AND es.shift_date >= ech.effective_from
                          AND (
                             ech.effective_to IS NULL
                                 OR es.shift_date <= ech.effective_to
                             )

        GROUP BY
            es.store_id,
            es.shift_date
    ),


/* ============================================================
   DATE × STORE SPINE

   Guarantees that a store/day exists even when there were
   no sales that day.
   ============================================================ */
    store_dates AS (
        SELECT
            d.date_key AS performance_date,
            s.store_id

        FROM date_dimension d
                 CROSS JOIN stores s

        WHERE d.date_key >= s.opening_date
    )

SELECT
    sd.performance_date,
    sd.store_id,

    /* ---------------- SALES ---------------- */

    COALESCE(sa.orders, 0)
        AS orders,

    COALESCE(sa.units_sold, 0)
        AS units_sold,

    COALESCE(sa.product_revenue, 0)
        AS gross_product_revenue,

    COALESCE(sa.cogs, 0)
        AS gross_cogs,

    COALESCE(sa.gross_profit_before_returns, 0)
        AS gross_profit_before_returns,

    COALESCE(sa.discount_amount, 0)
        AS discount_amount,

    COALESCE(sa.regular_price_value, 0)
        AS regular_price_value,


    /* ---------------- RETURNS ---------------- */

    COALESCE(ra.returned_units, 0)
        AS returned_units,

    COALESCE(ra.refund_amount, 0)
        AS refund_amount,

    COALESCE(ra.recovered_cogs, 0)
        AS recovered_cogs,


    /* Net product revenue after return events */

    COALESCE(sa.product_revenue, 0)
        - COALESCE(ra.refund_amount, 0)
        AS net_product_revenue,


    /* Net COGS after returned sellable inventory is recovered */

    COALESCE(sa.cogs, 0)
        - COALESCE(ra.recovered_cogs, 0)
        AS net_cogs,


    /* Net Gross Profit */

    (
        COALESCE(sa.product_revenue, 0)
            - COALESCE(ra.refund_amount, 0)
        )
        -
    (
        COALESCE(sa.cogs, 0)
            - COALESCE(ra.recovered_cogs, 0)
        )
        AS net_gross_profit,


    /* ---------------- LABOUR ---------------- */

    COALESCE(l.labour_hours, 0)
        AS labour_hours,

    COALESCE(l.labour_cost, 0)
        AS labour_cost,


    /* ---------------- PROTECTION ---------------- */

    COALESCE(pe.eligible_item_lines, 0)
        AS eligible_plan_item_lines,

    COALESCE(ps.protected_item_lines, 0)
        AS protected_item_lines,

    COALESCE(ps.protection_plan_revenue, 0)
        AS protection_plan_revenue


FROM store_dates sd

         LEFT JOIN sales sa
                   ON sa.store_id = sd.store_id
                       AND sa.performance_date = sd.performance_date

         LEFT JOIN return_activity ra
                   ON ra.store_id = sd.store_id
                       AND ra.performance_date = sd.performance_date

         LEFT JOIN labour l
                   ON l.store_id = sd.store_id
                       AND l.performance_date = sd.performance_date

         LEFT JOIN plan_eligible pe
                   ON pe.store_id = sd.store_id
                       AND pe.performance_date = sd.performance_date

         LEFT JOIN plan_sales ps
                   ON ps.store_id = sd.store_id
                       AND ps.performance_date = sd.performance_date;