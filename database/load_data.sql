-- Run from the dataset bundle root with psql, e.g.:
-- psql -d your_database -f load_data.sql
\set ON_ERROR_STOP on
BEGIN;

TRUNCATE TABLE date_dimension, order_item_promotions, inventory_snapshots, inventory_transactions, purchase_order_items, purchase_orders, order_protection_plans, return_items, returns, payments, order_items, orders, promotions, suppliers, warehouses, protection_plans, return_reasons, product_prices, products, categories, brands, customers, employee_shifts, employee_compensation_history, employees, employee_roles, stores RESTART IDENTITY CASCADE;

\copy stores (store_id, store_code, store_name, city, province, postal_code, store_type, region, opening_date, square_feet, active) FROM 'csv/stores.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy employee_roles (role_id, role_name, department) FROM 'csv/employee_roles.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy employees (employee_id, store_id, role_id, first_name, last_name, hire_date, termination_date, employment_type, manager_id, active) FROM 'csv/employees.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy employee_compensation_history (compensation_id, employee_id, effective_from, effective_to, hourly_rate, annual_salary) FROM 'csv/employee_compensation_history.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy employee_shifts (shift_id, employee_id, store_id, shift_date, clock_in, clock_out, regular_hours, overtime_hours, shift_type) FROM 'csv/employee_shifts.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy customers (customer_id, customer_type, first_name, last_name, city, province, postal_code, created_date, email_opt_in) FROM 'csv/customers.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy brands (brand_id, brand_name, brand_tier, active) FROM 'csv/brands.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy categories (category_id, category_name, parent_category_id) FROM 'csv/categories.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy products (product_id, sku, model_number, brand_id, category_id, product_name, color, width_inches, height_inches, depth_inches, energy_star, launch_date, discontinued_date, active) FROM 'csv/products.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy product_prices (product_price_id, product_id, effective_from, effective_to, regular_price, standard_cost) FROM 'csv/product_prices.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy return_reasons (return_reason_id, reason_name, reason_category) FROM 'csv/return_reasons.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy protection_plans (protection_plan_id, plan_name, duration_years, minimum_item_price, maximum_item_price, regular_price, active) FROM 'csv/protection_plans.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy warehouses (warehouse_id, warehouse_name, city, province, active) FROM 'csv/warehouses.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy suppliers (supplier_id, supplier_name, lead_time_days, active) FROM 'csv/suppliers.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy promotions (promotion_id, promotion_name, promotion_type, start_date, end_date, brand_id, category_id, discount_type, discount_value, active) FROM 'csv/promotions.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy orders (order_id, customer_id, store_id, salesperson_id, order_datetime, sales_channel, order_status, subtotal, discount_total, tax_total, total_amount) FROM 'csv/orders.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy order_items (order_item_id, order_id, product_id, quantity, regular_unit_price, sold_unit_price, unit_cost, discount_amount) FROM 'csv/order_items.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy payments (payment_id, order_id, payment_datetime, payment_type, payment_status, transaction_type, amount) FROM 'csv/payments.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy returns (return_id, order_id, customer_id, store_id, processed_by_employee_id, return_datetime, return_status, refund_total) FROM 'csv/returns.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy return_items (return_item_id, return_id, order_item_id, return_reason_id, quantity, item_condition, refund_amount, restockable) FROM 'csv/return_items.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy order_protection_plans (order_protection_plan_id, order_item_id, protection_plan_id, sold_by_employee_id, sold_price, purchase_date) FROM 'csv/order_protection_plans.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy purchase_orders (purchase_order_id, supplier_id, warehouse_id, order_date, expected_date, received_date, status) FROM 'csv/purchase_orders.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy purchase_order_items (purchase_order_item_id, purchase_order_id, product_id, quantity_ordered, quantity_received, unit_cost) FROM 'csv/purchase_order_items.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy inventory_transactions (inventory_transaction_id, product_id, location_type, location_id, transaction_datetime, transaction_type, quantity_change, reference_type, reference_id) FROM 'csv/inventory_transactions.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy inventory_snapshots (snapshot_date, product_id, location_type, location_id, quantity_on_hand, quantity_reserved) FROM 'csv/inventory_snapshots.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy order_item_promotions (order_item_id, promotion_id, discount_amount) FROM 'csv/order_item_promotions.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');
\copy date_dimension (date_key, calendar_year, calendar_quarter, month_number, month_name, week_of_year, day_of_month, day_of_week, day_name, is_weekend, fiscal_year, fiscal_quarter, is_holiday, holiday_name) FROM 'csv/date_dimension.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');

-- Reset BIGSERIAL sequences because IDs were explicitly loaded.
SELECT setval(pg_get_serial_sequence('stores','store_id'), COALESCE((SELECT MAX(store_id) FROM stores), 1), true);
SELECT setval(pg_get_serial_sequence('employee_roles','role_id'), COALESCE((SELECT MAX(role_id) FROM employee_roles), 1), true);
SELECT setval(pg_get_serial_sequence('employees','employee_id'), COALESCE((SELECT MAX(employee_id) FROM employees), 1), true);
SELECT setval(pg_get_serial_sequence('employee_compensation_history','compensation_id'), COALESCE((SELECT MAX(compensation_id) FROM employee_compensation_history), 1), true);
SELECT setval(pg_get_serial_sequence('employee_shifts','shift_id'), COALESCE((SELECT MAX(shift_id) FROM employee_shifts), 1), true);
SELECT setval(pg_get_serial_sequence('customers','customer_id'), COALESCE((SELECT MAX(customer_id) FROM customers), 1), true);
SELECT setval(pg_get_serial_sequence('brands','brand_id'), COALESCE((SELECT MAX(brand_id) FROM brands), 1), true);
SELECT setval(pg_get_serial_sequence('categories','category_id'), COALESCE((SELECT MAX(category_id) FROM categories), 1), true);
SELECT setval(pg_get_serial_sequence('products','product_id'), COALESCE((SELECT MAX(product_id) FROM products), 1), true);
SELECT setval(pg_get_serial_sequence('product_prices','product_price_id'), COALESCE((SELECT MAX(product_price_id) FROM product_prices), 1), true);
SELECT setval(pg_get_serial_sequence('orders','order_id'), COALESCE((SELECT MAX(order_id) FROM orders), 1), true);
SELECT setval(pg_get_serial_sequence('order_items','order_item_id'), COALESCE((SELECT MAX(order_item_id) FROM order_items), 1), true);
SELECT setval(pg_get_serial_sequence('payments','payment_id'), COALESCE((SELECT MAX(payment_id) FROM payments), 1), true);
SELECT setval(pg_get_serial_sequence('return_reasons','return_reason_id'), COALESCE((SELECT MAX(return_reason_id) FROM return_reasons), 1), true);
SELECT setval(pg_get_serial_sequence('returns','return_id'), COALESCE((SELECT MAX(return_id) FROM returns), 1), true);
SELECT setval(pg_get_serial_sequence('return_items','return_item_id'), COALESCE((SELECT MAX(return_item_id) FROM return_items), 1), true);
SELECT setval(pg_get_serial_sequence('protection_plans','protection_plan_id'), COALESCE((SELECT MAX(protection_plan_id) FROM protection_plans), 1), true);
SELECT setval(pg_get_serial_sequence('order_protection_plans','order_protection_plan_id'), COALESCE((SELECT MAX(order_protection_plan_id) FROM order_protection_plans), 1), true);
SELECT setval(pg_get_serial_sequence('warehouses','warehouse_id'), COALESCE((SELECT MAX(warehouse_id) FROM warehouses), 1), true);
SELECT setval(pg_get_serial_sequence('suppliers','supplier_id'), COALESCE((SELECT MAX(supplier_id) FROM suppliers), 1), true);
SELECT setval(pg_get_serial_sequence('purchase_orders','purchase_order_id'), COALESCE((SELECT MAX(purchase_order_id) FROM purchase_orders), 1), true);
SELECT setval(pg_get_serial_sequence('purchase_order_items','purchase_order_item_id'), COALESCE((SELECT MAX(purchase_order_item_id) FROM purchase_order_items), 1), true);
SELECT setval(pg_get_serial_sequence('inventory_transactions','inventory_transaction_id'), COALESCE((SELECT MAX(inventory_transaction_id) FROM inventory_transactions), 1), true);
SELECT setval(pg_get_serial_sequence('promotions','promotion_id'), COALESCE((SELECT MAX(promotion_id) FROM promotions), 1), true);

COMMIT;
