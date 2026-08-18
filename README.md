# Synthetic Appliance Retail Dataset

This package contains a reproducible, correlated synthetic operational dataset for a multi-store Canadian appliance retailer.

- **Seed:** `20260816`
- **History:** `2023-08-01` through `2026-07-31`
- **Database target:** PostgreSQL 14+
- **CSV files:** one per table in `csv/` after extracting the generated ZIP archive

## Generate again

```bash
python -m pip install numpy
python generate_appliance_retail_dataset.py --output appliance_retail_dataset
```

The generator creates `appliance_retail_dataset.zip`; extract it to get the `csv/` directory and SQL scripts. The default seed and dates reproduce this delivered dataset. You can explicitly pass `--seed`, `--start-date`, `--end-date`, `--customers`, `--products`, and `--order-rate` for controlled variants.

## Load into PostgreSQL

Create an empty database, then from this directory run:

```bash
psql -d YOUR_DATABASE -f create_tables.sql
psql -d YOUR_DATABASE -f load_data.sql
```

`database/load_data.sql` uses psql `\copy`, so run it from the bundle root so paths such as `data/raw/orders.csv` resolve correctly.

## Modeling choices

- Raw tables contain operational facts, not precomputed BI metrics.
- Historical `regular_unit_price`, `sold_unit_price`, and `unit_cost` are frozen on `order_items`.
- Sales demand is affected by store traffic, staffing, weekday/weekend shape, seasonality, promotions, customer type, product tier, product lifecycle, and inventory availability.
- In-store/phone salesperson orders are generated only when that employee has a recorded shift containing the order timestamp.
- Purchasing is supplier/warehouse based, with lead times, occasional partial receipts/cancellations, and inventory receipt transactions.
- Stores replenish from their assigned warehouse; transfers create paired `TRANSFER_OUT`/`TRANSFER_IN` inventory transactions.
- Completed sales create negative inventory movements; completed restockable returns create positive inventory movements.
- Returns retain the original order item rather than mutating it; order status is updated to partial/full return when a return completes.
- Protection-plan attachment is influenced by item price/category and salesperson ability.
- Promotions are represented separately in `promotions` and `order_item_promotions`; discretionary discounts may also exist.
- Month-end inventory snapshots are stored for historical reporting.

See `dataset_manifest.json` for row counts and `validation_report.txt` for validation checks.
