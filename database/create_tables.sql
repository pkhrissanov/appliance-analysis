-- PostgreSQL DDL for the synthetic appliance-retail operational dataset.
-- Generated for PostgreSQL 14+.

CREATE TABLE stores (
  store_id BIGSERIAL PRIMARY KEY,
  store_code VARCHAR(10) UNIQUE NOT NULL,
  store_name VARCHAR(100) NOT NULL,
  city VARCHAR(100) NOT NULL,
  province CHAR(2) NOT NULL,
  postal_code VARCHAR(7),
  store_type VARCHAR(20) NOT NULL CHECK (store_type IN ('SHOWROOM','OUTLET')),
  region VARCHAR(50) NOT NULL,
  opening_date DATE NOT NULL,
  square_feet INTEGER CHECK (square_feet IS NULL OR square_feet > 0),
  active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE employee_roles (
  role_id BIGSERIAL PRIMARY KEY,
  role_name VARCHAR(100) UNIQUE NOT NULL,
  department VARCHAR(50) NOT NULL
);

CREATE TABLE employees (
  employee_id BIGSERIAL PRIMARY KEY,
  store_id BIGINT NOT NULL REFERENCES stores(store_id),
  role_id BIGINT NOT NULL REFERENCES employee_roles(role_id),
  first_name VARCHAR(50) NOT NULL,
  last_name VARCHAR(50) NOT NULL,
  hire_date DATE NOT NULL,
  termination_date DATE,
  employment_type VARCHAR(20) NOT NULL CHECK (employment_type IN ('FULL_TIME','PART_TIME')),
  manager_id BIGINT REFERENCES employees(employee_id),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  CHECK (termination_date IS NULL OR termination_date >= hire_date)
);

CREATE TABLE employee_compensation_history (
  compensation_id BIGSERIAL PRIMARY KEY,
  employee_id BIGINT NOT NULL REFERENCES employees(employee_id),
  effective_from DATE NOT NULL,
  effective_to DATE,
  hourly_rate NUMERIC(8,2),
  annual_salary NUMERIC(10,2),
  CHECK (hourly_rate IS NOT NULL OR annual_salary IS NOT NULL),
  CHECK (hourly_rate IS NULL OR hourly_rate >= 0),
  CHECK (annual_salary IS NULL OR annual_salary >= 0),
  CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

CREATE TABLE employee_shifts (
  shift_id BIGSERIAL PRIMARY KEY,
  employee_id BIGINT NOT NULL REFERENCES employees(employee_id),
  store_id BIGINT NOT NULL REFERENCES stores(store_id),
  shift_date DATE NOT NULL,
  clock_in TIMESTAMP NOT NULL,
  clock_out TIMESTAMP NOT NULL,
  regular_hours NUMERIC(5,2) NOT NULL CHECK (regular_hours >= 0),
  overtime_hours NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (overtime_hours >= 0),
  shift_type VARCHAR(20) NOT NULL DEFAULT 'REGULAR' CHECK (shift_type IN ('REGULAR','TRAINING','HOLIDAY','SICK')),
  CHECK (clock_out > clock_in)
);

CREATE TABLE customers (
  customer_id BIGSERIAL PRIMARY KEY,
  customer_type VARCHAR(30) NOT NULL CHECK (customer_type IN ('INDIVIDUAL','BUILDER','CONTRACTOR','PROPERTY_MANAGER')),
  first_name VARCHAR(50),
  last_name VARCHAR(50),
  city VARCHAR(100),
  province CHAR(2),
  postal_code VARCHAR(7),
  created_date DATE NOT NULL,
  email_opt_in BOOLEAN DEFAULT FALSE
);

CREATE TABLE brands (
  brand_id BIGSERIAL PRIMARY KEY,
  brand_name VARCHAR(100) UNIQUE NOT NULL,
  brand_tier VARCHAR(20) NOT NULL CHECK (brand_tier IN ('VALUE','MAINSTREAM','PREMIUM','LUXURY')),
  active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE categories (
  category_id BIGSERIAL PRIMARY KEY,
  category_name VARCHAR(100) NOT NULL,
  parent_category_id BIGINT REFERENCES categories(category_id)
);

CREATE TABLE products (
  product_id BIGSERIAL PRIMARY KEY,
  sku VARCHAR(30) UNIQUE NOT NULL,
  model_number VARCHAR(50) NOT NULL,
  brand_id BIGINT NOT NULL REFERENCES brands(brand_id),
  category_id BIGINT NOT NULL REFERENCES categories(category_id),
  product_name VARCHAR(200) NOT NULL,
  color VARCHAR(50),
  width_inches NUMERIC(5,2),
  height_inches NUMERIC(5,2),
  depth_inches NUMERIC(5,2),
  energy_star BOOLEAN,
  launch_date DATE,
  discontinued_date DATE,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  CHECK (discontinued_date IS NULL OR launch_date IS NULL OR discontinued_date >= launch_date)
);

CREATE TABLE product_prices (
  product_price_id BIGSERIAL PRIMARY KEY,
  product_id BIGINT NOT NULL REFERENCES products(product_id),
  effective_from DATE NOT NULL,
  effective_to DATE,
  regular_price NUMERIC(10,2) NOT NULL CHECK (regular_price >= 0),
  standard_cost NUMERIC(10,2) NOT NULL CHECK (standard_cost >= 0),
  CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

CREATE TABLE orders (
  order_id BIGSERIAL PRIMARY KEY,
  customer_id BIGINT REFERENCES customers(customer_id),
  store_id BIGINT NOT NULL REFERENCES stores(store_id),
  salesperson_id BIGINT REFERENCES employees(employee_id),
  order_datetime TIMESTAMP NOT NULL,
  sales_channel VARCHAR(20) NOT NULL CHECK (sales_channel IN ('IN_STORE','PHONE','ONLINE')),
  order_status VARCHAR(20) NOT NULL CHECK (order_status IN ('PLACED','COMPLETED','CANCELLED','PARTIALLY_RETURNED','RETURNED')),
  subtotal NUMERIC(12,2) NOT NULL CHECK (subtotal >= 0),
  discount_total NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (discount_total >= 0),
  tax_total NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (tax_total >= 0),
  total_amount NUMERIC(12,2) NOT NULL CHECK (total_amount >= 0)
);

CREATE TABLE order_items (
  order_item_id BIGSERIAL PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(order_id),
  product_id BIGINT NOT NULL REFERENCES products(product_id),
  quantity INTEGER NOT NULL CHECK (quantity > 0),
  regular_unit_price NUMERIC(10,2) NOT NULL CHECK (regular_unit_price >= 0),
  sold_unit_price NUMERIC(10,2) NOT NULL CHECK (sold_unit_price >= 0),
  unit_cost NUMERIC(10,2) NOT NULL CHECK (unit_cost >= 0),
  discount_amount NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (discount_amount >= 0)
);

CREATE TABLE payments (
  payment_id BIGSERIAL PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(order_id),
  payment_datetime TIMESTAMP NOT NULL,
  payment_type VARCHAR(30) NOT NULL CHECK (payment_type IN ('CREDIT_CARD','DEBIT_CARD','CASH','FINANCING','GIFT_CARD')),
  payment_status VARCHAR(20) NOT NULL CHECK (payment_status IN ('PENDING','COMPLETED','FAILED','CANCELLED')),
  transaction_type VARCHAR(20) NOT NULL CHECK (transaction_type IN ('PAYMENT','REFUND')),
  amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0)
);

CREATE TABLE return_reasons (
  return_reason_id BIGSERIAL PRIMARY KEY,
  reason_name VARCHAR(100) UNIQUE NOT NULL,
  reason_category VARCHAR(50)
);

CREATE TABLE returns (
  return_id BIGSERIAL PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(order_id),
  customer_id BIGINT REFERENCES customers(customer_id),
  store_id BIGINT NOT NULL REFERENCES stores(store_id),
  processed_by_employee_id BIGINT REFERENCES employees(employee_id),
  return_datetime TIMESTAMP NOT NULL,
  return_status VARCHAR(20) NOT NULL CHECK (return_status IN ('REQUESTED','APPROVED','COMPLETED','REJECTED')),
  refund_total NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (refund_total >= 0)
);

CREATE TABLE return_items (
  return_item_id BIGSERIAL PRIMARY KEY,
  return_id BIGINT NOT NULL REFERENCES returns(return_id),
  order_item_id BIGINT NOT NULL REFERENCES order_items(order_item_id),
  return_reason_id BIGINT NOT NULL REFERENCES return_reasons(return_reason_id),
  quantity INTEGER NOT NULL CHECK (quantity > 0),
  item_condition VARCHAR(30) NOT NULL CHECK (item_condition IN ('UNOPENED','OPEN_BOX','DAMAGED','DEFECTIVE')),
  refund_amount NUMERIC(10,2) NOT NULL CHECK (refund_amount >= 0),
  restockable BOOLEAN NOT NULL
);

CREATE TABLE protection_plans (
  protection_plan_id BIGSERIAL PRIMARY KEY,
  plan_name VARCHAR(100) NOT NULL,
  duration_years INTEGER NOT NULL CHECK (duration_years > 0),
  minimum_item_price NUMERIC(10,2),
  maximum_item_price NUMERIC(10,2),
  regular_price NUMERIC(10,2) NOT NULL CHECK (regular_price >= 0),
  active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE order_protection_plans (
  order_protection_plan_id BIGSERIAL PRIMARY KEY,
  order_item_id BIGINT NOT NULL REFERENCES order_items(order_item_id),
  protection_plan_id BIGINT NOT NULL REFERENCES protection_plans(protection_plan_id),
  sold_by_employee_id BIGINT REFERENCES employees(employee_id),
  sold_price NUMERIC(10,2) NOT NULL CHECK (sold_price >= 0),
  purchase_date DATE NOT NULL
);

CREATE TABLE warehouses (
  warehouse_id BIGSERIAL PRIMARY KEY,
  warehouse_name VARCHAR(100) NOT NULL,
  city VARCHAR(100),
  province CHAR(2),
  active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE suppliers (
  supplier_id BIGSERIAL PRIMARY KEY,
  supplier_name VARCHAR(100) NOT NULL,
  lead_time_days INTEGER CHECK (lead_time_days IS NULL OR lead_time_days >= 0),
  active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE purchase_orders (
  purchase_order_id BIGSERIAL PRIMARY KEY,
  supplier_id BIGINT NOT NULL REFERENCES suppliers(supplier_id),
  warehouse_id BIGINT NOT NULL REFERENCES warehouses(warehouse_id),
  order_date DATE NOT NULL,
  expected_date DATE,
  received_date DATE,
  status VARCHAR(20) NOT NULL CHECK (status IN ('CREATED','ORDERED','PARTIALLY_RECEIVED','RECEIVED','CANCELLED')),
  CHECK (expected_date IS NULL OR expected_date >= order_date),
  CHECK (received_date IS NULL OR received_date >= order_date)
);

CREATE TABLE purchase_order_items (
  purchase_order_item_id BIGSERIAL PRIMARY KEY,
  purchase_order_id BIGINT NOT NULL REFERENCES purchase_orders(purchase_order_id),
  product_id BIGINT NOT NULL REFERENCES products(product_id),
  quantity_ordered INTEGER NOT NULL CHECK (quantity_ordered > 0),
  quantity_received INTEGER NOT NULL DEFAULT 0 CHECK (quantity_received >= 0),
  unit_cost NUMERIC(10,2) NOT NULL CHECK (unit_cost >= 0),
  CHECK (quantity_received <= quantity_ordered)
);

CREATE TABLE inventory_transactions (
  inventory_transaction_id BIGSERIAL PRIMARY KEY,
  product_id BIGINT NOT NULL REFERENCES products(product_id),
  location_type VARCHAR(20) NOT NULL CHECK (location_type IN ('STORE','WAREHOUSE')),
  location_id BIGINT NOT NULL,
  transaction_datetime TIMESTAMP NOT NULL,
  transaction_type VARCHAR(30) NOT NULL CHECK (transaction_type IN ('PURCHASE_RECEIPT','SALE','CUSTOMER_RETURN','TRANSFER_IN','TRANSFER_OUT','DAMAGE','ADJUSTMENT')),
  quantity_change INTEGER NOT NULL,
  reference_type VARCHAR(30) CHECK (reference_type IS NULL OR reference_type IN ('ORDER_ITEM','RETURN_ITEM','PURCHASE_ORDER_ITEM','TRANSFER','ADJUSTMENT')),
  reference_id BIGINT
);

CREATE TABLE inventory_snapshots (
  snapshot_date DATE NOT NULL,
  product_id BIGINT NOT NULL REFERENCES products(product_id),
  location_type VARCHAR(20) NOT NULL CHECK (location_type IN ('STORE','WAREHOUSE')),
  location_id BIGINT NOT NULL,
  quantity_on_hand INTEGER NOT NULL CHECK (quantity_on_hand >= 0),
  quantity_reserved INTEGER NOT NULL DEFAULT 0 CHECK (quantity_reserved >= 0),
  PRIMARY KEY (snapshot_date, product_id, location_type, location_id),
  CHECK (quantity_reserved <= quantity_on_hand)
);

CREATE TABLE promotions (
  promotion_id BIGSERIAL PRIMARY KEY,
  promotion_name VARCHAR(100) NOT NULL,
  promotion_type VARCHAR(30) NOT NULL CHECK (promotion_type IN ('BRAND','CATEGORY','PRODUCT','STOREWIDE')),
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  brand_id BIGINT REFERENCES brands(brand_id),
  category_id BIGINT REFERENCES categories(category_id),
  discount_type VARCHAR(20) NOT NULL CHECK (discount_type IN ('PERCENT','FIXED_AMOUNT')),
  discount_value NUMERIC(10,2) NOT NULL CHECK (discount_value >= 0),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  CHECK (end_date >= start_date)
);

CREATE TABLE order_item_promotions (
  order_item_id BIGINT NOT NULL REFERENCES order_items(order_item_id),
  promotion_id BIGINT NOT NULL REFERENCES promotions(promotion_id),
  discount_amount NUMERIC(10,2) NOT NULL CHECK (discount_amount >= 0),
  PRIMARY KEY (order_item_id, promotion_id)
);

CREATE TABLE date_dimension (
  date_key DATE PRIMARY KEY,
  calendar_year INTEGER,
  calendar_quarter INTEGER,
  month_number INTEGER,
  month_name VARCHAR(20),
  week_of_year INTEGER,
  day_of_month INTEGER,
  day_of_week INTEGER,
  day_name VARCHAR(20),
  is_weekend BOOLEAN,
  fiscal_year INTEGER,
  fiscal_quarter INTEGER,
  is_holiday BOOLEAN,
  holiday_name VARCHAR(100)
);

-- Useful operational/BI access-path indexes; no analytical metrics are materialized.
CREATE INDEX idx_orders_store_datetime ON orders(store_id, order_datetime);
CREATE INDEX idx_orders_salesperson_datetime ON orders(salesperson_id, order_datetime);
CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_order_items_product ON order_items(product_id);
CREATE INDEX idx_payments_order ON payments(order_id);
CREATE INDEX idx_returns_order_datetime ON returns(order_id, return_datetime);
CREATE INDEX idx_return_items_order_item ON return_items(order_item_id);
CREATE INDEX idx_shifts_employee_date ON employee_shifts(employee_id, shift_date);
CREATE INDEX idx_shifts_store_date ON employee_shifts(store_id, shift_date);
CREATE INDEX idx_prices_product_dates ON product_prices(product_id, effective_from, effective_to);
CREATE INDEX idx_inventory_tx_product_datetime ON inventory_transactions(product_id, transaction_datetime);
CREATE INDEX idx_inventory_tx_location_datetime ON inventory_transactions(location_type, location_id, transaction_datetime);
CREATE INDEX idx_inventory_snap_location_date ON inventory_snapshots(location_type, location_id, snapshot_date);
CREATE INDEX idx_po_supplier_date ON purchase_orders(supplier_id, order_date);
CREATE INDEX idx_po_warehouse_date ON purchase_orders(warehouse_id, order_date);
