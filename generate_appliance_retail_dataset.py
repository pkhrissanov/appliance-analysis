#!/usr/bin/env python3
"""Reproducible synthetic appliance-retail PostgreSQL dataset generator.

The generated data models correlated operational behavior for a multi-store
Canadian appliance retailer. It intentionally stores operational facts only;
analytical metrics such as gross margin, return rate, inventory turnover, or
salesperson rankings are left for downstream SQL/BI.

Default history: 2023-08-01 through 2026-07-31 (36 months)
Default seed:    42

Dependencies: Python 3.10+ and numpy.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import gzip
import json
import math
import os
import shutil
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

SEED = 42
DEFAULT_START = date(2023, 8, 1)
DEFAULT_END = date(2026, 7, 31)

TIER_ORDER = ["VALUE", "MAINSTREAM", "PREMIUM", "LUXURY"]
TIER_INDEX = {x: i for i, x in enumerate(TIER_ORDER)}

FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Avery", "Cameron",
    "Jamie", "Parker", "Drew", "Quinn", "Rowan", "Reese", "Sydney", "Logan",
    "Noah", "Liam", "Ethan", "Lucas", "Mason", "Oliver", "Emma", "Olivia",
    "Sophia", "Mia", "Amelia", "Charlotte", "Isla", "Ava", "Aria", "Leo",
    "Maya", "Ella", "Chloe", "Grace", "Nathan", "Evan", "Owen", "Ryan",
    "Daniel", "Sophie", "Hannah", "Emily", "Zoe", "Nora", "Caleb", "Isaac",
]
LAST_NAMES = [
    "Smith", "Brown", "Wilson", "Lee", "Martin", "Anderson", "Clark", "Young",
    "Lewis", "Walker", "Hall", "Allen", "King", "Wright", "Scott", "Green",
    "Baker", "Adams", "Nelson", "Carter", "Mitchell", "Roberts", "Turner",
    "Phillips", "Campbell", "Parker", "Evans", "Edwards", "Collins", "Stewart",
    "Morris", "Rogers", "Reed", "Cook", "Morgan", "Bell", "Murphy", "Bailey",
    "Cooper", "Richardson", "Cox", "Howard", "Ward", "Brooks", "Gray", "James",
]

BC_CITIES = ["Vancouver", "Burnaby", "Coquitlam", "Richmond", "Surrey", "Langley", "Victoria", "Kelowna", "Nanaimo", "Abbotsford"]
AB_CITIES = ["Calgary", "Edmonton", "Red Deer", "Airdrie", "St. Albert", "Lethbridge", "Sherwood Park"]

STORE_DEFS = [
    ("BC01", "Harbour Home Appliances - Vancouver", "Vancouver", "BC", "SHOWROOM", "Lower Mainland", 47000, 1.22, 0.76, 0.98, 1.01),
    ("BC02", "Harbour Home Appliances - Burnaby", "Burnaby", "BC", "SHOWROOM", "Lower Mainland", 42000, 1.16, 0.65, 1.00, 0.98),
    ("BC03", "Harbour Home Appliances - Coquitlam", "Coquitlam", "BC", "SHOWROOM", "Lower Mainland", 38000, 1.06, 0.57, 1.01, 1.00),
    ("BC04", "Harbour Home Appliances - Richmond Outlet", "Richmond", "BC", "OUTLET", "Lower Mainland", 32000, 1.02, 0.32, 1.13, 1.10),
    ("BC05", "Harbour Home Appliances - Langley", "Langley", "BC", "SHOWROOM", "Lower Mainland", 45000, 1.12, 0.51, 1.00, 0.97),
    ("BC06", "Harbour Home Appliances - Surrey", "Surrey", "BC", "SHOWROOM", "Lower Mainland", 40000, 1.10, 0.43, 1.03, 1.04),
    ("BC07", "Harbour Home Appliances - Victoria", "Victoria", "BC", "SHOWROOM", "Vancouver Island", 35000, 0.91, 0.61, 0.99, 0.96),
    ("BC08", "Harbour Home Appliances - Kelowna", "Kelowna", "BC", "SHOWROOM", "Interior BC", 33000, 0.88, 0.55, 1.01, 0.98),
    ("AB01", "Harbour Home Appliances - Calgary South", "Calgary", "AB", "SHOWROOM", "Calgary", 48000, 1.20, 0.64, 0.97, 0.97),
    ("AB02", "Harbour Home Appliances - Calgary North Outlet", "Calgary", "AB", "OUTLET", "Calgary", 34000, 0.97, 0.29, 1.15, 1.08),
    ("AB03", "Harbour Home Appliances - Edmonton South", "Edmonton", "AB", "SHOWROOM", "Edmonton", 43000, 1.11, 0.54, 1.00, 1.02),
    ("AB04", "Harbour Home Appliances - Edmonton North", "Edmonton", "AB", "SHOWROOM", "Edmonton", 37000, 0.96, 0.47, 1.02, 1.03),
]

BRANDS = [
    ("Frigidaire", "VALUE"), ("Whirlpool", "VALUE"),
    ("GE", "MAINSTREAM"), ("LG", "MAINSTREAM"), ("Samsung", "MAINSTREAM"),
    ("Bosch", "PREMIUM"), ("KitchenAid", "PREMIUM"), ("Cafe", "PREMIUM"),
    ("Miele", "LUXURY"), ("Thermador", "LUXURY"), ("Wolf", "LUXURY"),
]

CATEGORY_TREE = [
    ("Refrigeration", None),
    ("French Door Refrigerator", "Refrigeration"),
    ("Side-by-Side Refrigerator", "Refrigeration"),
    ("Bottom Freezer Refrigerator", "Refrigeration"),
    ("Column Refrigerator", "Refrigeration"),
    ("Cooking", None),
    ("Electric Range", "Cooking"),
    ("Gas Range", "Cooking"),
    ("Induction Range", "Cooking"),
    ("Cooktop", "Cooking"),
    ("Wall Oven", "Cooking"),
    ("Laundry", None),
    ("Front Load Washer", "Laundry"),
    ("Top Load Washer", "Laundry"),
    ("Electric Dryer", "Laundry"),
    ("Gas Dryer", "Laundry"),
    ("Dishwashers", None),
    ("Built-In Dishwasher", "Dishwashers"),
    ("Microwaves", None),
    ("Over-the-Range Microwave", "Microwaves"),
    ("Countertop Microwave", "Microwaves"),
    ("Ventilation", None),
    ("Range Hood", "Ventilation"),
    ("Freezers", None),
    ("Upright Freezer", "Freezers"),
    ("Chest Freezer", "Freezers"),
]

# Leaf-category demand share used as a starting point. Normalized by generator.
CATEGORY_SHARES = {
    "French Door Refrigerator": 0.115,
    "Side-by-Side Refrigerator": 0.040,
    "Bottom Freezer Refrigerator": 0.055,
    "Column Refrigerator": 0.018,
    "Electric Range": 0.080,
    "Gas Range": 0.050,
    "Induction Range": 0.060,
    "Cooktop": 0.040,
    "Wall Oven": 0.038,
    "Front Load Washer": 0.105,
    "Top Load Washer": 0.050,
    "Electric Dryer": 0.090,
    "Gas Dryer": 0.035,
    "Built-In Dishwasher": 0.095,
    "Over-the-Range Microwave": 0.045,
    "Countertop Microwave": 0.035,
    "Range Hood": 0.025,
    "Upright Freezer": 0.040,
    "Chest Freezer": 0.034,
}

PRICE_RANGES = {
    "French Door Refrigerator": (1600, 4200), "Side-by-Side Refrigerator": (1300, 3000),
    "Bottom Freezer Refrigerator": (1100, 2800), "Column Refrigerator": (4200, 9000),
    "Electric Range": (850, 2200), "Gas Range": (1100, 3200), "Induction Range": (1600, 4200),
    "Cooktop": (850, 2800), "Wall Oven": (1500, 4200),
    "Front Load Washer": (850, 1800), "Top Load Washer": (650, 1400),
    "Electric Dryer": (700, 1600), "Gas Dryer": (850, 1800),
    "Built-In Dishwasher": (650, 2200), "Over-the-Range Microwave": (350, 950),
    "Countertop Microwave": (150, 600), "Range Hood": (350, 1800),
    "Upright Freezer": (700, 1800), "Chest Freezer": (500, 1400),
}

RETURN_RISK = {
    "French Door Refrigerator": 0.050, "Side-by-Side Refrigerator": 0.045,
    "Bottom Freezer Refrigerator": 0.043, "Column Refrigerator": 0.040,
    "Electric Range": 0.035, "Gas Range": 0.040, "Induction Range": 0.038,
    "Cooktop": 0.030, "Wall Oven": 0.032,
    "Front Load Washer": 0.050, "Top Load Washer": 0.045,
    "Electric Dryer": 0.040, "Gas Dryer": 0.040,
    "Built-In Dishwasher": 0.048, "Over-the-Range Microwave": 0.042,
    "Countertop Microwave": 0.060, "Range Hood": 0.030,
    "Upright Freezer": 0.035, "Chest Freezer": 0.030,
}

CATEGORY_DIMENSIONS = {
    "French Door Refrigerator": (30, 36, 70), "Side-by-Side Refrigerator": (33, 36, 70),
    "Bottom Freezer Refrigerator": (30, 33, 69), "Column Refrigerator": (24, 30, 84),
    "Electric Range": (30, 28, 47), "Gas Range": (30, 29, 47), "Induction Range": (30, 28, 47),
    "Cooktop": (30, 22, 4), "Wall Oven": (30, 25, 29),
    "Front Load Washer": (27, 31, 39), "Top Load Washer": (27, 28, 44),
    "Electric Dryer": (27, 31, 39), "Gas Dryer": (27, 31, 39),
    "Built-In Dishwasher": (24, 25, 34), "Over-the-Range Microwave": (30, 16, 17),
    "Countertop Microwave": (22, 18, 13), "Range Hood": (30, 20, 12),
    "Upright Freezer": (28, 30, 67), "Chest Freezer": (45, 28, 34),
}

COLORS = ["Stainless Steel", "Black Stainless", "White", "Black", "Panel Ready"]

RETURN_REASONS = [
    ("Defective", "Product"),
    ("Damaged on arrival", "Product"),
    ("Cosmetic damage", "Product"),
    ("Wrong item", "Fulfillment"),
    ("Does not fit", "Customer"),
    ("Changed mind", "Customer"),
    ("Missing parts", "Product"),
    ("Installation compatibility issue", "Service"),
]

ROLE_DEFS = [
    ("Sales Consultant", "Sales"),
    ("Sales Manager", "Management"),
    ("Store Manager", "Management"),
    ("Customer Service Representative", "Customer Service"),
    ("Warehouse Associate", "Warehouse"),
]

HOLIDAYS = {
    (1, 1): "New Year's Day",
    (7, 1): "Canada Day",
    (12, 25): "Christmas Day",
    (12, 26): "Boxing Day",
}

BUNDLE_COMPANIONS = {
    "Front Load Washer": ["Electric Dryer", "Gas Dryer"],
    "Top Load Washer": ["Electric Dryer", "Gas Dryer"],
    "Electric Dryer": ["Front Load Washer", "Top Load Washer"],
    "Gas Dryer": ["Front Load Washer", "Top Load Washer"],
    "Electric Range": ["Range Hood", "Over-the-Range Microwave"],
    "Gas Range": ["Range Hood", "Over-the-Range Microwave"],
    "Induction Range": ["Range Hood", "Over-the-Range Microwave"],
    "Cooktop": ["Wall Oven", "Range Hood"],
    "Wall Oven": ["Cooktop", "Range Hood"],
    "French Door Refrigerator": ["Built-In Dishwasher"],
    "Side-by-Side Refrigerator": ["Built-In Dishwasher"],
}


def daterange(start: date, end: date) -> Iterable[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def iso_bool(v: bool) -> str:
    return "true" if v else "false"


def dtstr(v: datetime) -> str:
    return v.strftime("%Y-%m-%d %H:%M:%S")


def datestr(v: Optional[date]) -> str:
    return "" if v is None else v.isoformat()


def money(x: float) -> float:
    return round(float(x) + 1e-9, 2)


def canadian_postal(rng: np.random.Generator, province: str) -> str:
    # Synthetic but Canadian-looking. First letters roughly province-coded.
    first = rng.choice(list("V" if province == "BC" else "T"))
    letters = list("ABCEGHJKLMNPRSTVWXYZ")
    return f"{first}{int(rng.integers(0,10))}{rng.choice(letters)} {int(rng.integers(0,10))}{rng.choice(letters)}{int(rng.integers(0,10))}"


def weighted_choice(rng: np.random.Generator, values: Sequence, weights: Sequence[float]):
    arr = np.asarray(weights, dtype=float)
    total = arr.sum()
    if total <= 0:
        return values[int(rng.integers(0, len(values)))]
    p = arr / total
    return values[int(rng.choice(len(values), p=p))]


def month_end(d: date) -> bool:
    return d.day == calendar.monthrange(d.year, d.month)[1]


def season_multiplier(d: date) -> float:
    m = d.month
    return {
        1: 0.78, 2: 0.88, 3: 0.96, 4: 1.00, 5: 1.08, 6: 1.10,
        7: 1.07, 8: 1.02, 9: 1.00, 10: 1.05, 11: 1.28, 12: 1.38,
    }[m]


def category_season(cat: str, d: date) -> float:
    m = d.month
    if "Refrigerator" in cat or "Freezer" in cat:
        return 1.16 if m in (5, 6, 7, 8) else (0.92 if m in (1, 2) else 1.0)
    if cat in ("Electric Range", "Gas Range", "Induction Range", "Cooktop", "Wall Oven", "Range Hood"):
        return 1.20 if m in (10, 11, 12) else (0.94 if m in (1, 2) else 1.0)
    if "Washer" in cat or "Dryer" in cat:
        return 1.10 if m in (3, 4, 8, 9) else 1.0
    if "Dishwasher" in cat:
        return 1.16 if m in (11, 12) else 1.0
    if "Microwave" in cat:
        return 1.12 if m in (8, 9, 11, 12) else 1.0
    return 1.0


def weekday_multiplier(d: date) -> float:
    # Monday=0 ... Sunday=6
    return [0.86, 0.92, 0.98, 1.02, 1.12, 1.25, 1.18][d.weekday()]


def tenure_factor(hire_date: date, d: date) -> float:
    days = max(0, (d - hire_date).days)
    if days < 90:
        return 0.72 + 0.0015 * days
    if days < 365:
        return 0.86 + 0.00035 * (days - 90)
    return min(1.10, 0.96 + 0.00008 * (days - 365))


def tax_rate(province: str) -> float:
    return 0.12 if province == "BC" else 0.05


@dataclass
class EmployeeHidden:
    employee_id: int
    store_idx: int
    role_name: str
    hire_date: date
    termination_date: Optional[date]
    employment_type: str
    productivity: float
    discount_tendency: float
    premium_tendency: float
    attach_ability: float


@dataclass
class ProductHidden:
    product_id: int
    brand_id: int
    brand_name: str
    tier: str
    category_id: int
    category_name: str
    launch_date: date
    discontinued_date: Optional[date]
    base_demand: float
    price_sensitivity: float
    seasonality: float
    supplier_id: int


class Generator:
    def __init__(self, out_dir: Path, seed: int, start: date, end: date,
                 n_customers: int, n_products: int, order_rate: float):
        self.out_dir = out_dir
        self.csv_dir = out_dir / "csv"  # logical path used inside the final archive
        self.work_csv_gz = out_dir / ".work_csv_gz"
        if self.work_csv_gz.exists():
            shutil.rmtree(self.work_csv_gz)
        self.work_csv_gz.mkdir(parents=True, exist_ok=True)
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.start = start
        self.end = end
        self.days = list(daterange(start, end))
        self.day_index = {d: i for i, d in enumerate(self.days)}
        self.n_customers = n_customers
        self.n_products = n_products
        self.order_rate = order_rate
        self.rows: Dict[str, List[list]] = defaultdict(list)
        self.headers: Dict[str, List[str]] = {}
        self.validation_notes: List[str] = []
        self.counts: Dict[str, int] = defaultdict(int)
        # Large append-only fact tables are streamed to CSV to keep memory bounded across 36 months.
        self.stream_tables = {
            "employee_shifts", "customers", "order_items", "payments", "return_items",
            "order_protection_plans", "purchase_order_items", "inventory_transactions",
            "inventory_snapshots", "order_item_promotions"
        }
        self._stream_files = {}
        self._stream_writers = {}

    def add(self, table: str, row: list):
        self.counts[table] += 1
        if table in self.stream_tables:
            if table == "inventory_snapshots":
                assert int(row[4]) >= 0 and int(row[5]) >= 0 and int(row[5]) <= int(row[4])
            self._stream_writers[table].writerow(row)
        else:
            self.rows[table].append(row)

    def setup_headers(self):
        self.headers = {
            "stores": ["store_id","store_code","store_name","city","province","postal_code","store_type","region","opening_date","square_feet","active"],
            "employee_roles": ["role_id","role_name","department"],
            "employees": ["employee_id","store_id","role_id","first_name","last_name","hire_date","termination_date","employment_type","manager_id","active"],
            "employee_compensation_history": ["compensation_id","employee_id","effective_from","effective_to","hourly_rate","annual_salary"],
            "employee_shifts": ["shift_id","employee_id","store_id","shift_date","clock_in","clock_out","regular_hours","overtime_hours","shift_type"],
            "customers": ["customer_id","customer_type","first_name","last_name","city","province","postal_code","created_date","email_opt_in"],
            "brands": ["brand_id","brand_name","brand_tier","active"],
            "categories": ["category_id","category_name","parent_category_id"],
            "products": ["product_id","sku","model_number","brand_id","category_id","product_name","color","width_inches","height_inches","depth_inches","energy_star","launch_date","discontinued_date","active"],
            "product_prices": ["product_price_id","product_id","effective_from","effective_to","regular_price","standard_cost"],
            "orders": ["order_id","customer_id","store_id","salesperson_id","order_datetime","sales_channel","order_status","subtotal","discount_total","tax_total","total_amount"],
            "order_items": ["order_item_id","order_id","product_id","quantity","regular_unit_price","sold_unit_price","unit_cost","discount_amount"],
            "payments": ["payment_id","order_id","payment_datetime","payment_type","payment_status","transaction_type","amount"],
            "return_reasons": ["return_reason_id","reason_name","reason_category"],
            "returns": ["return_id","order_id","customer_id","store_id","processed_by_employee_id","return_datetime","return_status","refund_total"],
            "return_items": ["return_item_id","return_id","order_item_id","return_reason_id","quantity","item_condition","refund_amount","restockable"],
            "protection_plans": ["protection_plan_id","plan_name","duration_years","minimum_item_price","maximum_item_price","regular_price","active"],
            "order_protection_plans": ["order_protection_plan_id","order_item_id","protection_plan_id","sold_by_employee_id","sold_price","purchase_date"],
            "warehouses": ["warehouse_id","warehouse_name","city","province","active"],
            "suppliers": ["supplier_id","supplier_name","lead_time_days","active"],
            "purchase_orders": ["purchase_order_id","supplier_id","warehouse_id","order_date","expected_date","received_date","status"],
            "purchase_order_items": ["purchase_order_item_id","purchase_order_id","product_id","quantity_ordered","quantity_received","unit_cost"],
            "inventory_transactions": ["inventory_transaction_id","product_id","location_type","location_id","transaction_datetime","transaction_type","quantity_change","reference_type","reference_id"],
            "inventory_snapshots": ["snapshot_date","product_id","location_type","location_id","quantity_on_hand","quantity_reserved"],
            "promotions": ["promotion_id","promotion_name","promotion_type","start_date","end_date","brand_id","category_id","discount_type","discount_value","active"],
            "order_item_promotions": ["order_item_id","promotion_id","discount_amount"],
            "date_dimension": ["date_key","calendar_year","calendar_quarter","month_number","month_name","week_of_year","day_of_month","day_of_week","day_name","is_weekend","fiscal_year","fiscal_quarter","is_holiday","holiday_name"],
        }
        for table in self.stream_tables:
            path = self.work_csv_gz / f"{table}.csv.gz"
            fh = gzip.open(path, "wt", newline="", encoding="utf-8", compresslevel=4)
            wr = csv.writer(fh)
            wr.writerow(self.headers[table])
            self._stream_files[table] = fh
            self._stream_writers[table] = wr

    def generate_dimensions(self):
        # Stores and hidden store parameters.
        self.store_hidden = []
        opening_years = [1998, 2001, 2004, 2008, 2010, 2012, 2014, 2016, 2018, 2019, 2020, 2021]
        for i, sd in enumerate(STORE_DEFS, 1):
            code, name, city, prov, stype, region, sqft, traffic, premium, disc, ret = sd
            opening = date(opening_years[i-1], int(self.rng.integers(1,13)), int(self.rng.integers(1,25)))
            self.add("stores", [i, code, name, city, prov, canadian_postal(self.rng, prov), stype, region, opening.isoformat(), sqft, "true"])
            self.store_hidden.append({
                "store_id": i, "city": city, "province": prov, "type": stype, "region": region,
                "sqft": sqft, "traffic": traffic, "premium": premium, "discount": disc,
                "return": ret, "base_orders": self.order_rate * traffic * (0.90 + sqft / 180000.0),
            })

        # Roles.
        self.role_id = {}
        for i, (role, dept) in enumerate(ROLE_DEFS, 1):
            self.role_id[role] = i
            self.add("employee_roles", [i, role, dept])

        # Brands / suppliers.
        self.brand_id = {}
        self.supplier_by_brand = {}
        for i, (brand, tier) in enumerate(BRANDS, 1):
            self.brand_id[brand] = i
            self.add("brands", [i, brand, tier, "true"])
            self.supplier_by_brand[brand] = i
            lead = int(self.rng.integers(8, 20))
            self.add("suppliers", [i, f"{brand} Canada Distribution", lead, "true"])
        self.supplier_lead = {int(r[0]): int(r[2]) for r in self.rows["suppliers"]}

        # Categories: parents are created before children by CATEGORY_TREE order.
        self.category_id = {}
        for i, (cat, parent) in enumerate(CATEGORY_TREE, 1):
            self.category_id[cat] = i
            self.add("categories", [i, cat, "" if parent is None else self.category_id[parent]])
        self.leaf_categories = list(CATEGORY_SHARES.keys())
        shares = np.array([CATEGORY_SHARES[c] for c in self.leaf_categories], dtype=float)
        shares /= shares.sum()
        self.base_category_probs = shares

        # Warehouses.
        self.add("warehouses", [1, "Pacific Distribution Centre", "Surrey", "BC", "true"])
        self.add("warehouses", [2, "Prairie Distribution Centre", "Calgary", "AB", "true"])
        self.store_warehouse_idx = np.array([0 if x[3] == "BC" else 1 for x in STORE_DEFS], dtype=int)

        # Return reasons.
        for i, (reason, cat) in enumerate(RETURN_REASONS, 1):
            self.add("return_reasons", [i, reason, cat])
        self.return_reason_id = {name: i+1 for i, (name, _) in enumerate(RETURN_REASONS)}

        # Protection plans: price bands × term.
        plan_id = 1
        self.plan_bands = []
        for duration, mult in [(3, 1.0), (5, 1.55)]:
            for low, high, price in [(0,999.99,99),(1000,1999.99,149),(2000,3999.99,229),(4000,999999,349)]:
                p = money(price * mult)
                name = f"{duration}-Year Protection Plan - ${int(low)}+" if high > 900000 else f"{duration}-Year Protection Plan - ${int(low)}-${int(high)}"
                self.add("protection_plans", [plan_id, name, duration, low, high, p, "true"])
                self.plan_bands.append((plan_id, duration, low, high, p))
                plan_id += 1

        # Date dimension. Fiscal year starts Feb 1 for a non-calendar example.
        for d in self.days:
            fiscal_year = d.year + (1 if d.month >= 2 else 0)
            fiscal_month = ((d.month - 2) % 12) + 1
            fiscal_q = (fiscal_month - 1)//3 + 1
            holiday_name = HOLIDAYS.get((d.month, d.day), "")
            self.add("date_dimension", [
                d.isoformat(), d.year, (d.month-1)//3+1, d.month, calendar.month_name[d.month],
                int(d.isocalendar().week), d.day, d.isoweekday(), calendar.day_name[d.weekday()],
                iso_bool(d.weekday() >= 5), fiscal_year, fiscal_q, iso_bool(bool(holiday_name)), holiday_name,
            ])

    def generate_employees_and_shifts(self):
        self.employees_hidden: Dict[int, EmployeeHidden] = {}
        self.employee_by_store_role: Dict[Tuple[int, str], List[int]] = defaultdict(list)
        employee_id = 1
        compensation_id = 1
        # Store managers and sales managers first so forward manager refs are avoided.
        store_employee_blocks = []
        for s_idx, sh in enumerate(self.store_hidden):
            sqft = sh["sqft"]
            sales_slots = int(round(8 + sqft / 10500))
            csr_slots = 2 if sqft >= 38000 else 1
            wh_slots = 2 if sqft >= 36000 else 1
            role_sequence = ["Store Manager", "Sales Manager"] + ["Sales Consultant"] * sales_slots + ["Customer Service Representative"] * csr_slots + ["Warehouse Associate"] * wh_slots
            # Add a small number of replacement records to create natural turnover.
            if self.rng.random() < 0.80:
                role_sequence += ["Sales Consultant"]
            if self.rng.random() < 0.35:
                role_sequence += ["Customer Service Representative"]
            store_employee_blocks.append((s_idx, role_sequence))

        for s_idx, role_sequence in store_employee_blocks:
            sh = self.store_hidden[s_idx]
            manager_ids = {}
            for rpos, role in enumerate(role_sequence):
                # Managers are stable and pre-date the history; other roles have some in-period hires/terminations.
                if role in ("Store Manager", "Sales Manager"):
                    hire = self.start - timedelta(days=int(self.rng.integers(600, 3000)))
                    termination = None
                else:
                    if self.rng.random() < 0.74:
                        hire = self.start - timedelta(days=int(self.rng.integers(60, 2200)))
                    else:
                        hire = self.start + timedelta(days=int(self.rng.integers(0, max(1,(self.end-self.start).days-120))))
                    termination = None
                    # Turnover is more common for non-management employees hired before/early in the dataset.
                    if hire < self.end - timedelta(days=240) and self.rng.random() < (0.16 if role == "Sales Consultant" else 0.11):
                        earliest = max(hire + timedelta(days=180), self.start + timedelta(days=90))
                        if earliest < self.end - timedelta(days=60):
                            termination = earliest + timedelta(days=int(self.rng.integers(0, (self.end-earliest).days-30)))
                employment_type = "PART_TIME" if (role in ("Sales Consultant", "Customer Service Representative", "Warehouse Associate") and self.rng.random() < 0.27) else "FULL_TIME"
                first = str(self.rng.choice(FIRST_NAMES)); last = str(self.rng.choice(LAST_NAMES))
                if role == "Store Manager":
                    manager_id = ""
                    manager_ids["store"] = employee_id
                elif role == "Sales Manager":
                    manager_id = manager_ids["store"]
                    manager_ids["sales"] = employee_id
                elif role == "Sales Consultant":
                    manager_id = manager_ids.get("sales", manager_ids["store"])
                else:
                    manager_id = manager_ids["store"]
                active = termination is None or termination > self.end
                self.add("employees", [employee_id, s_idx+1, self.role_id[role], first, last, hire.isoformat(), datestr(termination), employment_type, manager_id, iso_bool(active)])

                hidden = EmployeeHidden(
                    employee_id=employee_id, store_idx=s_idx, role_name=role, hire_date=hire,
                    termination_date=termination, employment_type=employment_type,
                    productivity=float(np.clip(self.rng.lognormal(mean=0.0, sigma=0.18), 0.65, 1.45)),
                    discount_tendency=float(np.clip(self.rng.normal(1.0, 0.17), 0.65, 1.45)),
                    premium_tendency=float(np.clip(self.rng.normal(1.0, 0.18), 0.60, 1.45)),
                    attach_ability=float(np.clip(self.rng.normal(1.0, 0.22), 0.50, 1.60)),
                )
                self.employees_hidden[employee_id] = hidden
                self.employee_by_store_role[(s_idx, role)].append(employee_id)

                # Compensation history with calendar-year raises.
                if role == "Store Manager":
                    salary = money(self.rng.normal(83000, 7000)); hourly = ""
                elif role == "Sales Manager":
                    salary = money(self.rng.normal(71000, 6000)); hourly = ""
                else:
                    base = {"Sales Consultant": 23.5, "Customer Service Representative": 21.5, "Warehouse Associate": 24.0}[role]
                    hourly = money(max(17.5, self.rng.normal(base, 2.0))); salary = ""
                starts = [hire]
                for yr in range(max(self.start.year, hire.year+1), self.end.year+1):
                    raise_date = date(yr, 1, 1)
                    if raise_date <= self.end and raise_date > hire and (termination is None or raise_date <= termination):
                        starts.append(raise_date)
                starts = sorted(set(starts))
                current_hourly = hourly
                current_salary = salary
                for j, eff in enumerate(starts):
                    eff_to = None
                    if j+1 < len(starts):
                        eff_to = starts[j+1] - timedelta(days=1)
                    elif termination is not None:
                        eff_to = termination
                    if j > 0:
                        if current_hourly != "": current_hourly = money(float(current_hourly) * float(self.rng.uniform(1.025, 1.055)))
                        if current_salary != "": current_salary = money(float(current_salary) * float(self.rng.uniform(1.025, 1.055)))
                    self.add("employee_compensation_history", [compensation_id, employee_id, eff.isoformat(), datestr(eff_to), current_hourly, current_salary])
                    compensation_id += 1
                employee_id += 1

        # Shift generation and mappings used by sales/returns.
        self.sales_shifts = [[[] for _ in self.days] for _ in self.store_hidden]
        self.processor_shifts = [[[] for _ in self.days] for _ in self.store_hidden]
        shift_id = 1
        for emp_id, e in self.employees_hidden.items():
            start_d = max(self.start, e.hire_date)
            end_d = min(self.end, e.termination_date or self.end)
            if start_d > end_d:
                continue
            for d in daterange(start_d, end_d):
                wd = d.weekday()
                high_season = season_multiplier(d) >= 1.18
                if e.employment_type == "FULL_TIME":
                    p = 0.71 if wd < 5 else 0.44
                else:
                    p = 0.34 if wd < 5 else 0.56
                if e.role_name in ("Sales Consultant", "Sales Manager"):
                    if wd >= 4: p += 0.14
                    if high_season: p += 0.08
                elif e.role_name == "Store Manager":
                    p = 0.86 if wd < 5 else 0.22
                elif e.role_name == "Warehouse Associate":
                    p = 0.76 if wd < 6 else 0.22
                if HOLIDAYS.get((d.month, d.day)) == "Christmas Day":
                    p = 0.0
                if self.rng.random() >= min(0.95, p):
                    continue
                if e.employment_type == "FULL_TIME":
                    hours = float(np.clip(self.rng.normal(8.0, 0.35), 7.0, 9.2))
                else:
                    hours = float(np.clip(self.rng.normal(6.0, 0.8), 4.0, 8.0))
                # Two common shift patterns; warehouse begins earlier.
                if e.role_name == "Warehouse Associate":
                    start_hour = float(np.clip(self.rng.normal(8.0, 0.35), 7.0, 9.0))
                elif e.role_name == "Store Manager":
                    start_hour = float(np.clip(self.rng.normal(8.75, 0.25), 8.0, 9.5))
                else:
                    start_hour = float(self.rng.choice([8.75, 9.0, 10.0, 11.0], p=[0.22,0.34,0.28,0.16]))
                overtime = 0.0
                if high_season and e.employment_type == "FULL_TIME" and self.rng.random() < 0.055:
                    overtime = money(float(self.rng.uniform(0.5, 2.0)))
                total = hours + overtime
                total_minutes = int(round(start_hour * 60))
                h, minute = divmod(total_minutes, 60)
                clock_in = datetime.combine(d, time(h, minute))
                clock_out = clock_in + timedelta(hours=total)
                regular = money(min(hours, 8.0)); overtime_h = money(max(0.0, total-regular))
                shift_type = "TRAINING" if self.rng.random() < 0.008 else "REGULAR"
                self.add("employee_shifts", [shift_id, emp_id, e.store_idx+1, d.isoformat(), dtstr(clock_in), dtstr(clock_out), regular, overtime_h, shift_type])
                info = (emp_id, clock_in, clock_out)
                di = self.day_index[d]
                if e.role_name in ("Sales Consultant", "Sales Manager"):
                    self.sales_shifts[e.store_idx][di].append(info)
                if e.role_name in ("Customer Service Representative", "Sales Manager", "Store Manager"):
                    self.processor_shifts[e.store_idx][di].append(info)
                shift_id += 1

        self.typical_sales_staff = []
        for s_idx in range(len(self.store_hidden)):
            counts = [len(x) for x in self.sales_shifts[s_idx]]
            positive = [x for x in counts if x > 0]
            self.typical_sales_staff.append(max(1.0, float(np.median(positive)) if positive else 1.0))

    def generate_customers(self):
        self.customer_by_type = {t: [] for t in ["INDIVIDUAL","BUILDER","CONTRACTOR","PROPERTY_MANAGER"]}
        probs = [0.895, 0.038, 0.037, 0.030]
        types = list(self.customer_by_type.keys())
        history_days = (self.end-self.start).days
        for cid in range(1, self.n_customers+1):
            ctype = str(self.rng.choice(types, p=probs))
            # 22% existed before the analysis window; remaining accounts appear across history.
            if self.rng.random() < 0.22:
                created = self.start - timedelta(days=int(self.rng.integers(30, 1800)))
            else:
                # Slightly more customer acquisition later as company grows.
                u = float(self.rng.random()) ** 0.90
                created = self.start + timedelta(days=int(u * history_days))
            prov = "BC" if self.rng.random() < 0.68 else "AB"
            city = str(self.rng.choice(BC_CITIES if prov == "BC" else AB_CITIES))
            first = str(self.rng.choice(FIRST_NAMES)); last = str(self.rng.choice(LAST_NAMES))
            optin = self.rng.random() < (0.36 if ctype == "INDIVIDUAL" else 0.54)
            self.add("customers", [cid, ctype, first, last, city, prov, canadian_postal(self.rng, prov), created.isoformat(), iso_bool(optin)])
            self.customer_by_type[ctype].append((created, cid, prov))
        for ctype in self.customer_by_type:
            self.customer_by_type[ctype].sort(key=lambda x: x[0])
            self.customer_by_type[ctype] = self.customer_by_type[ctype]

    def generate_products_and_prices(self):
        # Allocate product counts by category share, with a floor to preserve variety.
        raw = self.base_category_probs * self.n_products
        counts = np.maximum(24, np.floor(raw).astype(int))
        while counts.sum() > self.n_products:
            idx = int(np.argmax(counts - raw))
            if counts[idx] > 24: counts[idx] -= 1
            else: break
        while counts.sum() < self.n_products:
            idx = int(np.argmax(raw - counts))
            counts[idx] += 1

        self.products_hidden: List[ProductHidden] = []
        self.product_price_periods: Dict[int, List[Tuple[date,date,float,float]]] = {}
        self.products_by_cat_tier: Dict[Tuple[str,str], List[int]] = defaultdict(list)
        self.products_by_brand: Dict[int, List[int]] = defaultdict(list)
        self.product_id_to_index = {}
        product_price_id = 1
        pid = 1
        tier_price_mult = {"VALUE":0.82, "MAINSTREAM":1.0, "PREMIUM":1.38, "LUXURY":2.05}
        # Category-specific brand suitability.
        luxury_heavy = {"Column Refrigerator","Cooktop","Wall Oven","Range Hood"}
        for cat, count in zip(self.leaf_categories, counts):
            low, high = PRICE_RANGES[cat]
            for _ in range(int(count)):
                brand_weights = []
                for brand, tier in BRANDS:
                    w = {"VALUE":1.15,"MAINSTREAM":1.35,"PREMIUM":0.95,"LUXURY":0.48}[tier]
                    if cat in luxury_heavy:
                        w *= {"VALUE":0.35,"MAINSTREAM":0.70,"PREMIUM":1.25,"LUXURY":1.65}[tier]
                    if cat == "Countertop Microwave" and tier == "LUXURY": w *= 0.15
                    if cat in ("Gas Range","Cooktop","Wall Oven") and brand == "Wolf": w *= 1.8
                    if cat in ("Built-In Dishwasher",) and brand in ("Bosch","Miele"): w *= 1.8
                    brand_weights.append(w)
                brand = weighted_choice(self.rng, [x[0] for x in BRANDS], brand_weights)
                tier = dict(BRANDS)[brand]
                brand_id = self.brand_id[brand]
                # Product introduction and discontinuation create lifecycle effects.
                if self.rng.random() < 0.78:
                    launch = self.start - timedelta(days=int(self.rng.integers(90, 1600)))
                else:
                    launch = self.start + timedelta(days=int(self.rng.integers(0, max(1,(self.end-self.start).days-120))))
                discontinued = None
                if launch < self.end - timedelta(days=260) and self.rng.random() < 0.13:
                    earliest = max(launch + timedelta(days=300), self.start + timedelta(days=180))
                    if earliest < self.end - timedelta(days=45):
                        discontinued = earliest + timedelta(days=int(self.rng.integers(0, max(1,(self.end-earliest).days-30))))
                base = float(self.rng.lognormal(mean=0.0, sigma=0.62))
                price_sens = float(np.clip(self.rng.normal(1.0, 0.22), 0.55, 1.55))
                seasonality = float(np.clip(self.rng.normal(1.0, 0.10), 0.75, 1.30))
                # Price position within category combined with tier.
                base_price = float(self.rng.uniform(low, high)) * tier_price_mult[tier]
                # Round to common retail endings.
                base_price = max(129.0, round(base_price/10.0)*10.0 - 1.0)
                cost_ratio = {"VALUE":0.67,"MAINSTREAM":0.64,"PREMIUM":0.61,"LUXURY":0.58}[tier] + float(self.rng.normal(0,0.025))
                base_cost = max(60.0, base_price * cost_ratio)
                width, depth, height = CATEGORY_DIMENSIONS[cat]
                width_v = money(max(12, self.rng.normal(width, max(0.8,width*0.045))))
                depth_v = money(max(10, self.rng.normal(depth, max(0.8,depth*0.045))))
                height_v = money(max(3, self.rng.normal(height, max(0.8,height*0.04))))
                color = str(self.rng.choice(COLORS, p=[0.57,0.12,0.12,0.10,0.09]))
                energy = self.rng.random() < (0.82 if cat in ("French Door Refrigerator","Bottom Freezer Refrigerator","Built-In Dishwasher","Front Load Washer") else 0.54)
                model = f"{brand[:3].upper().replace(' ','')}{cat[:2].upper().replace(' ','')}{pid:05d}"
                name = f"{brand} {cat} {model}"
                active = discontinued is None or discontinued > self.end
                self.add("products", [pid, f"SKU{pid:06d}", model, brand_id, self.category_id[cat], name, color, width_v, height_v, depth_v, iso_bool(bool(energy)), launch.isoformat(), datestr(discontinued), iso_bool(active)])
                hidden = ProductHidden(pid, brand_id, brand, tier, self.category_id[cat], cat, launch, discontinued, base, price_sens, seasonality, self.supplier_by_brand[brand])
                self.product_id_to_index[pid] = len(self.products_hidden)
                self.products_hidden.append(hidden)
                self.products_by_cat_tier[(cat,tier)].append(len(self.products_hidden)-1)
                self.products_by_brand[brand_id].append(len(self.products_hidden)-1)

                # Historical price/cost periods, frozen later into order items.
                first_eff = launch
                if first_eff < self.start - timedelta(days=540):
                    first_eff = self.start - timedelta(days=540)
                starts = [first_eff]
                cur = first_eff
                while True:
                    cur = cur + timedelta(days=int(self.rng.integers(210, 390)))
                    if cur > self.end or (discontinued is not None and cur > discontinued): break
                    starts.append(cur)
                reg = base_price
                cost = base_cost
                periods = []
                for j, eff in enumerate(starts):
                    if j > 0:
                        reg *= float(self.rng.uniform(1.015, 1.065))
                        cost *= float(self.rng.uniform(1.018, 1.075))
                    eff_to = (starts[j+1]-timedelta(days=1)) if j+1 < len(starts) else (discontinued if discontinued else date(2099,12,31))
                    reg_r = money(round(reg/5.0)*5.0 - 1.0)
                    cost_r = money(cost)
                    periods.append((eff, eff_to, reg_r, cost_r))
                    self.add("product_prices", [product_price_id, pid, eff.isoformat(), "" if eff_to.year==2099 else eff_to.isoformat(), reg_r, cost_r])
                    product_price_id += 1
                self.product_price_periods[pid] = periods
                pid += 1

        # Static store assortments and hidden category mix.
        S, P = len(self.store_hidden), len(self.products_hidden)
        self.assortment = np.zeros((S,P), dtype=bool)
        self.category_mix_by_store = []
        self.static_product_weight = np.array([p.base_demand for p in self.products_hidden], dtype=float)
        for s_idx, sh in enumerate(self.store_hidden):
            # Category mix varies by market; normalized after perturbation.
            mix = self.base_category_probs * self.rng.lognormal(0, 0.12, len(self.base_category_probs))
            if sh["region"] in ("Calgary","Edmonton"):
                for i,c in enumerate(self.leaf_categories):
                    if c in ("Gas Range","Gas Dryer"): mix[i] *= 1.18
            if sh["region"] == "Lower Mainland":
                for i,c in enumerate(self.leaf_categories):
                    if c in ("Induction Range","Front Load Washer","Built-In Dishwasher"): mix[i] *= 1.10
            mix /= mix.sum()
            self.category_mix_by_store.append(mix)
            for p_idx,p in enumerate(self.products_hidden):
                tier_i = TIER_INDEX[p.tier]
                premium = sh["premium"]
                carry_prob = [0.76,0.82,0.70,0.44][tier_i]
                if p.tier == "LUXURY": carry_prob *= (0.45 + premium)
                if p.tier == "PREMIUM": carry_prob *= (0.75 + 0.50*premium)
                if sh["type"] == "OUTLET":
                    carry_prob *= 0.88 if p.tier in ("PREMIUM","LUXURY") else 1.06
                self.assortment[s_idx,p_idx] = self.rng.random() < min(0.95, carry_prob)
            # Ensure every category has a useful selection at each store.
            for cat in self.leaf_categories:
                cat_indices = [i for i,p in enumerate(self.products_hidden) if p.category_name==cat]
                carried = [i for i in cat_indices if self.assortment[s_idx,i]]
                if len(carried) < min(8, len(cat_indices)):
                    missing = [i for i in cat_indices if not self.assortment[s_idx,i]]
                    self.rng.shuffle(missing)
                    for i in missing[:min(8,len(cat_indices))-len(carried)]: self.assortment[s_idx,i] = True

        # Precompute store/category/tier candidate pools for fast stock-aware product selection.
        self.store_cat_tier_candidates = {}
        self.store_cat_candidates = {}
        self.store_brand_cat_candidates = {}
        for s_idx in range(S):
            for cat in self.leaf_categories:
                all_inds = [i for i,p in enumerate(self.products_hidden) if p.category_name == cat and self.assortment[s_idx,i]]
                self.store_cat_candidates[(s_idx,cat)] = all_inds
                for tier in TIER_ORDER:
                    inds = [i for i in all_inds if self.products_hidden[i].tier == tier]
                    self.store_cat_tier_candidates[(s_idx,cat,tier)] = inds
                brand_ids = {self.products_hidden[i].brand_id for i in all_inds}
                for b_id in brand_ids:
                    self.store_brand_cat_candidates[(s_idx,b_id,cat)] = [i for i in all_inds if self.products_hidden[i].brand_id == b_id]

        self.tier_prob_cache = {}
        for s_idx in range(S):
            for ctype in ("INDIVIDUAL","BUILDER","CONTRACTOR","PROPERTY_MANAGER"):
                self.tier_prob_cache[(s_idx,ctype)] = self.tier_probs(s_idx,ctype)

        # Expected store-product daily demand used only inside generator for replenishment.
        self.expected_store_daily = np.zeros((S,P), dtype=float)
        for s_idx, sh in enumerate(self.store_hidden):
            expected_items = sh["base_orders"] * 1.70
            for c_idx, cat in enumerate(self.leaf_categories):
                inds = [i for i,p in enumerate(self.products_hidden) if p.category_name==cat and self.assortment[s_idx,i]]
                if not inds: continue
                w = np.array([self.products_hidden[i].base_demand / (max(250.0, self.get_price(self.products_hidden[i].product_id, max(self.start,self.products_hidden[i].launch_date))[0]) ** (0.16*self.products_hidden[i].price_sensitivity)) for i in inds])
                if w.sum() <= 0: w = np.ones(len(inds))
                w /= w.sum()
                self.expected_store_daily[s_idx, inds] = expected_items * self.category_mix_by_store[s_idx][c_idx] * w

    def get_price(self, product_id: int, d: date) -> Tuple[float,float]:
        periods = self.product_price_periods[product_id]
        for eff, eff_to, reg, cost in reversed(periods):
            if eff <= d <= eff_to:
                return reg, cost
        # Pre-launch caller should avoid this; fall back to first period for forecast cost only.
        return periods[0][2], periods[0][3]

    def generate_promotions(self):
        promo_id = 1
        self.promos = []
        # Deterministic seasonal campaign windows, with brand/category offers.
        for yr in range(self.start.year, self.end.year+1):
            windows = [
                (date(yr,2,10), date(yr,2,20), "Family Day"),
                (date(yr,3,15), date(yr,3,31), "Spring Refresh"),
                (date(yr,5,15), date(yr,5,31), "May Long Weekend"),
                (date(yr,6,24), date(yr,7,7), "Canada Day"),
                (date(yr,8,20), date(yr,9,8), "Labour Day"),
                (date(yr,10,5), date(yr,10,20), "Fall Home Event"),
                (date(yr,11,18), date(yr,12,2), "Black Friday"),
                (date(yr,12,20), date(yr,12,31), "Boxing Week"),
            ]
            for st,en,label in windows:
                if en < self.start or st > self.end: continue
                st = max(st,self.start); en=min(en,self.end)
                # One category offer and one brand offer per campaign.
                cat = str(self.rng.choice(self.leaf_categories, p=self.base_category_probs))
                brand_id = int(self.rng.integers(1, len(BRANDS)+1))
                for kind in ("CATEGORY","BRAND"):
                    if kind == "CATEGORY":
                        c_id = self.category_id[cat]; b_id = ""
                    else:
                        c_id = ""; b_id = brand_id
                    if self.rng.random() < 0.82:
                        dtype="PERCENT"; value=float(self.rng.choice([5,7.5,10,12.5,15,20]))
                    else:
                        dtype="FIXED_AMOUNT"; value=float(self.rng.choice([50,75,100,150,200,250]))
                    name = f"{label} {yr} - {kind.title()} Offer {promo_id}"
                    self.add("promotions", [promo_id,name,kind,st.isoformat(),en.isoformat(),b_id,c_id,dtype,money(value),iso_bool(en>=self.end)])
                    self.promos.append({"id":promo_id,"type":kind,"start":st,"end":en,"brand_id":b_id or None,"category_id":c_id or None,"discount_type":dtype,"discount_value":value})
                    promo_id += 1
                # Companywide promotion for the two biggest periods.
                if label in ("Black Friday","Boxing Week"):
                    value=float(self.rng.choice([5,7.5,10]))
                    name=f"{label} {yr} - Storewide {promo_id}"
                    self.add("promotions", [promo_id,name,"STOREWIDE",st.isoformat(),en.isoformat(),"","","PERCENT",money(value),iso_bool(en>=self.end)])
                    self.promos.append({"id":promo_id,"type":"STOREWIDE","start":st,"end":en,"brand_id":None,"category_id":None,"discount_type":"PERCENT","discount_value":value})
                    promo_id += 1
        # Additional shorter brand/category events.
        total_days = (self.end-self.start).days
        for _ in range(34):
            st = self.start + timedelta(days=int(self.rng.integers(0,max(1,total_days-14))))
            en = min(self.end, st + timedelta(days=int(self.rng.integers(7,22))))
            kind = str(self.rng.choice(["BRAND","CATEGORY"], p=[0.58,0.42]))
            if kind=="BRAND":
                b_id=int(self.rng.integers(1,len(BRANDS)+1)); c_id=""
            else:
                b_id=""; c_id=self.category_id[str(self.rng.choice(self.leaf_categories,p=self.base_category_probs))]
            dtype = "PERCENT" if self.rng.random()<0.85 else "FIXED_AMOUNT"
            value = float(self.rng.choice([5,7.5,10,12.5,15]) if dtype=="PERCENT" else self.rng.choice([50,75,100,150]))
            name=f"Vendor Event {promo_id}"
            self.add("promotions", [promo_id,name,kind,st.isoformat(),en.isoformat(),b_id,c_id,dtype,money(value),iso_bool(en>=self.end)])
            self.promos.append({"id":promo_id,"type":kind,"start":st,"end":en,"brand_id":b_id or None,"category_id":c_id or None,"discount_type":dtype,"discount_value":value})
            promo_id+=1
        self.promos_by_day = [[] for _ in self.days]
        for pr in self.promos:
            for d in daterange(pr["start"], pr["end"]):
                if d in self.day_index:
                    self.promos_by_day[self.day_index[d]].append(pr)

    def eligible_customer(self, ctype: str, d: date, store_province: str) -> Optional[int]:
        pool = self.customer_by_type[ctype]
        # binary search manually via bisect on date projection would allocate; use numpy-like boundary with Python bisect and a cached list.
        # Create cached dates on first use.
        if not hasattr(self, "customer_dates"):
            import bisect
            self._bisect = bisect
            self.customer_dates = {k:[x[0] for x in v] for k,v in self.customer_by_type.items()}
        n = self._bisect.bisect_right(self.customer_dates[ctype], d)
        if n == 0: return None
        # Business accounts repeat more often because pool is smaller. Individuals have a mild recency skew.
        if ctype == "INDIVIDUAL":
            idx = min(n-1, int((float(self.rng.random())**0.88) * n))
        else:
            idx = int(self.rng.integers(0,n))
        # Try a few times to match store province; cross-province online/phone remains possible.
        for _ in range(3):
            created,cid,prov = pool[idx]
            if prov == store_province or self.rng.random()<0.12:
                return cid
            idx=int(self.rng.integers(0,n))
        return pool[idx][1]

    def pick_salesperson(self, s_idx: int, di: int, d: date) -> Optional[Tuple[int,datetime,datetime]]:
        shifts = self.sales_shifts[s_idx][di]
        if not shifts: return None
        weights=[]
        for emp_id,cin,cout in shifts:
            e=self.employees_hidden[emp_id]
            weights.append(e.productivity*tenure_factor(e.hire_date,d))
        return weighted_choice(self.rng, shifts, weights)

    def pick_processor(self, s_idx: int, di: int) -> Optional[Tuple[int,datetime,datetime]]:
        shifts=self.processor_shifts[s_idx][di]
        if not shifts: return None
        return shifts[int(self.rng.integers(0,len(shifts)))]

    def order_time_within_shift(self, d: date, shift: Optional[Tuple[int,datetime,datetime]]) -> datetime:
        if shift is None:
            # Online order distribution peaks in the evening.
            hr=float(np.clip(self.rng.normal(16.0,3.1),8.0,21.8))
            h=int(hr); m=int((hr-h)*60); return datetime.combine(d,time(h,m))
        _,cin,cout=shift
        span=max(30,int((cout-cin).total_seconds()//60)-5)
        # triangular within shift, peak slightly after midpoint.
        frac=float(self.rng.triangular(0.03,0.58,0.98))
        return cin+timedelta(minutes=int(frac*span))

    def customer_type_for_order(self, channel: str) -> str:
        if channel=="ONLINE": probs=[0.95,0.015,0.015,0.020]
        elif channel=="PHONE": probs=[0.68,0.10,0.11,0.11]
        else: probs=[0.87,0.045,0.045,0.040]
        return str(self.rng.choice(["INDIVIDUAL","BUILDER","CONTRACTOR","PROPERTY_MANAGER"],p=probs))

    def tier_probs(self, s_idx: int, ctype: str) -> np.ndarray:
        premium=self.store_hidden[s_idx]["premium"]
        if ctype=="INDIVIDUAL": base=np.array([0.20,0.43,0.27,0.10])
        elif ctype=="BUILDER": base=np.array([0.23,0.48,0.24,0.05])
        elif ctype=="CONTRACTOR": base=np.array([0.28,0.49,0.19,0.04])
        else: base=np.array([0.38,0.45,0.14,0.03])
        base *= np.array([1.10-0.25*premium,1.0,0.78+0.48*premium,0.45+0.75*premium])
        if self.store_hidden[s_idx]["type"]=="OUTLET": base*=np.array([1.25,1.12,0.82,0.55])
        return base/base.sum()

    def choose_category(self, s_idx: int, d: date, ctype: str, previous_cat: Optional[str], di: int) -> str:
        if previous_cat and previous_cat in BUNDLE_COMPANIONS and self.rng.random()<0.50:
            companions=BUNDLE_COMPANIONS[previous_cat]
            return str(self.rng.choice(companions))
        probs=np.array(self.category_mix_by_store[s_idx],copy=True)
        for i,cat in enumerate(self.leaf_categories):
            probs[i]*=category_season(cat,d)
            if ctype in ("BUILDER","CONTRACTOR","PROPERTY_MANAGER"):
                if cat in ("Column Refrigerator","Cooktop","Wall Oven"): probs[i]*=0.72
                if cat in ("Top Load Washer","Electric Range","Built-In Dishwasher"): probs[i]*=1.12
        # Active category promos lift category incidence.
        active_cat_ids={p["category_id"] for p in self.promos_by_day[di] if p["type"]=="CATEGORY"}
        for i,cat in enumerate(self.leaf_categories):
            if self.category_id[cat] in active_cat_ids: probs[i]*=1.24
        probs/=probs.sum()
        return str(self.rng.choice(self.leaf_categories,p=probs))

    def product_active(self, p: ProductHidden, d: date) -> bool:
        return p.launch_date<=d and (p.discontinued_date is None or d<=p.discontinued_date)

    def select_product(self, s_idx: int, cat: str, d: date, di: int, ctype: str,
                       store_inventory: np.ndarray, qty_needed: int=1,
                       daily_tier: Optional[Dict[Tuple[str,str], List[int]]]=None,
                       daily_cat: Optional[Dict[str, List[int]]]=None) -> Optional[int]:
        tierp=self.tier_prob_cache.get((s_idx,ctype))
        if tierp is None:
            tierp=self.tier_probs(s_idx,ctype)
        active_brand_promos=[pr["brand_id"] for pr in self.promos_by_day[di] if pr["type"]=="BRAND"]
        cat_pool = daily_cat.get(cat,[]) if daily_cat is not None else self.store_cat_candidates.get((s_idx,cat),[])
        if not cat_pool:
            return None
        # Brand promotions can steer product choice among today's actually stocked products.
        if active_brand_promos and self.rng.random()<0.26:
            b_id=int(self.rng.choice(active_brand_promos))
            branded=[i for i in cat_pool if self.products_hidden[i].brand_id==b_id and store_inventory[s_idx,i]>=qty_needed]
            if branded:
                a=int(branded[int(self.rng.integers(0,len(branded)))])
                if len(branded)==1: return a
                b=int(branded[int(self.rng.integers(0,len(branded)))])
                wa=self.products_hidden[a].base_demand; wb=self.products_hidden[b].base_demand
                return a if self.rng.random()<wa/(wa+wb) else b
        # Draw a desired tier, then choose among today's stocked candidates.
        for _ in range(4):
            u=float(self.rng.random()); cum=0.0; tier=TIER_ORDER[-1]
            for ti,pr in enumerate(tierp):
                cum+=float(pr)
                if u<=cum:
                    tier=TIER_ORDER[ti]; break
            candidates = daily_tier.get((cat,tier),[]) if daily_tier is not None else self.store_cat_tier_candidates.get((s_idx,cat,tier),[])
            if not candidates: continue
            for __ in range(3):
                a=int(candidates[int(self.rng.integers(0,len(candidates)))])
                if store_inventory[s_idx,a] < qty_needed: continue
                if len(candidates)==1: return a
                b=int(candidates[int(self.rng.integers(0,len(candidates)))])
                if store_inventory[s_idx,b] < qty_needed: return a
                wa=self.products_hidden[a].base_demand; wb=self.products_hidden[b].base_demand
                return a if self.rng.random()<wa/(wa+wb) else b
        # Fallback from today's active/in-stock category pool.
        for _ in range(min(8,len(cat_pool))):
            p_idx=int(cat_pool[int(self.rng.integers(0,len(cat_pool)))])
            if store_inventory[s_idx,p_idx]>=qty_needed:
                return p_idx
        return None

    def applicable_promotions(self, p: ProductHidden, di: int) -> List[dict]:
        out=[]
        for pr in self.promos_by_day[di]:
            if pr["type"]=="STOREWIDE" or (pr["type"]=="BRAND" and pr["brand_id"]==p.brand_id) or (pr["type"]=="CATEGORY" and pr["category_id"]==p.category_id):
                out.append(pr)
        # Limit stacking to two offers, strongest first.
        def strength(pr):
            return pr["discount_value"] if pr["discount_type"]=="PERCENT" else pr["discount_value"]/20.0
        out.sort(key=strength, reverse=True)
        return out[:2]

    def promo_discount_each(self, regular: float, promos: List[dict]) -> Tuple[float,List[Tuple[int,float]]]:
        remaining=regular
        parts=[]
        for pr in promos:
            if pr["discount_type"]=="PERCENT": disc=remaining*(pr["discount_value"]/100.0)
            else: disc=min(remaining*0.22, pr["discount_value"])
            disc=max(0.0,disc); remaining-=disc; parts.append((pr["id"],disc))
        return regular-remaining,parts

    def plan_for_price(self, price: float, employee_id: Optional[int], category: str, ctype: str) -> Optional[Tuple[int,float]]:
        base_prob=0.18
        if category in ("French Door Refrigerator","Column Refrigerator","Induction Range","Wall Oven","Front Load Washer","Built-In Dishwasher"): base_prob+=0.08
        if price>=2500: base_prob+=0.06
        if ctype!="INDIVIDUAL": base_prob-=0.05
        if employee_id:
            base_prob*=self.employees_hidden[employee_id].attach_ability
        else:
            base_prob*=0.72
        if self.rng.random()>=min(0.48,max(0.04,base_prob)): return None
        duration=5 if (price>=1800 and self.rng.random()<0.56) else 3
        candidates=[x for x in self.plan_bands if x[1]==duration and x[2]<=price<=x[3]]
        if not candidates: return None
        plan=candidates[0]
        sold=money(plan[4]*(0.95 if self.rng.random()<0.10 else 1.0))
        return plan[0],sold

    def payment_type(self, total: float, ctype: str) -> str:
        if ctype!="INDIVIDUAL": probs=[0.36,0.16,0.04,0.42,0.02]
        elif total>3500: probs=[0.42,0.13,0.03,0.39,0.03]
        elif total>1200: probs=[0.57,0.22,0.05,0.13,0.03]
        else: probs=[0.53,0.28,0.11,0.05,0.03]
        return str(self.rng.choice(["CREDIT_CARD","DEBIT_CARD","CASH","FINANCING","GIFT_CARD"],p=probs))

    def generate_transactions(self):
        S=len(self.store_hidden); P=len(self.products_hidden); W=2
        store_inv=np.zeros((S,P),dtype=np.int32)
        wh_inv=np.zeros((W,P),dtype=np.int32)
        transfer_id=1; inventory_tx_id=1; po_id=1; poi_id=1
        order_id=1; order_item_id=1; payment_id=1; opp_id=1
        return_id=1; return_item_id=1
        pending_receipts=defaultdict(list)
        pending_returns=defaultdict(list)
        self.order_row_index={}
        self.order_total_qty=defaultdict(int); self.order_returned_qty=defaultdict(int)
        self.order_primary_payment={}
        self.final_reserved=np.zeros((S,P),dtype=np.int32)

        # Initial inventory: purchase receipt into warehouses, then transfer to stores.
        initial_receipt_date=self.start-timedelta(days=3)
        initial_transfer_date=self.start-timedelta(days=2)
        # Expected demand by warehouse/product.
        expected_wh=np.zeros((W,P),dtype=float)
        for s in range(S): expected_wh[self.store_warehouse_idx[s]] += self.expected_store_daily[s]
        # Initial store stock targets; launch-active only.
        store_targets=np.ceil(self.expected_store_daily*20.0).astype(int)
        store_targets=np.where(self.assortment, np.maximum(store_targets,1),0)
        for p_idx,p in enumerate(self.products_hidden):
            if not self.product_active(p,initial_transfer_date): store_targets[:,p_idx]=0
        wh_safety=np.ceil(expected_wh*90.0).astype(int)+3
        initial_wh_needed=wh_safety.copy()
        for s in range(S): initial_wh_needed[self.store_warehouse_idx[s]] += store_targets[s]
        # Build initial PO per warehouse/supplier.
        for w in range(W):
            for supplier_id in range(1,len(BRANDS)+1):
                inds=[i for i,p in enumerate(self.products_hidden) if p.supplier_id==supplier_id and initial_wh_needed[w,i]>0]
                if not inds: continue
                order_d=initial_receipt_date-timedelta(days=self.supplier_lead[supplier_id]+2)
                self.add("purchase_orders",[po_id,supplier_id,w+1,order_d.isoformat(),initial_receipt_date.isoformat(),initial_receipt_date.isoformat(),"RECEIVED"])
                for p_idx in inds:
                    qty=int(initial_wh_needed[w,p_idx]); _,cost=self.get_price(self.products_hidden[p_idx].product_id,max(order_d,self.products_hidden[p_idx].launch_date))
                    self.add("purchase_order_items",[poi_id,po_id,self.products_hidden[p_idx].product_id,qty,qty,money(cost)])
                    wh_inv[w,p_idx]+=qty
                    self.add("inventory_transactions",[inventory_tx_id,self.products_hidden[p_idx].product_id,"WAREHOUSE",w+1,dtstr(datetime.combine(initial_receipt_date,time(6,0))),"PURCHASE_RECEIPT",qty,"PURCHASE_ORDER_ITEM",poi_id]); inventory_tx_id+=1
                    poi_id+=1
                po_id+=1
        # Initial transfers.
        for s in range(S):
            w=self.store_warehouse_idx[s]
            for p_idx in np.where(store_targets[s]>0)[0]:
                qty=int(min(store_targets[s,p_idx],wh_inv[w,p_idx]))
                if qty<=0: continue
                wh_inv[w,p_idx]-=qty; store_inv[s,p_idx]+=qty
                self.add("inventory_transactions",[inventory_tx_id,self.products_hidden[p_idx].product_id,"WAREHOUSE",w+1,dtstr(datetime.combine(initial_transfer_date,time(7,0))),"TRANSFER_OUT",-qty,"TRANSFER",transfer_id]); inventory_tx_id+=1
                self.add("inventory_transactions",[inventory_tx_id,self.products_hidden[p_idx].product_id,"STORE",s+1,dtstr(datetime.combine(initial_transfer_date,time(9,0))),"TRANSFER_IN",qty,"TRANSFER",transfer_id]); inventory_tx_id+=1
                transfer_id+=1

        # Internal helper to process returns on a day.
        def process_returns(d: date, di: int):
            nonlocal payment_id, return_id, return_item_id, inventory_tx_id
            events=pending_returns.pop(d,[])
            for ev in events:
                s_idx=ev["store_idx"]
                proc=self.pick_processor(s_idx,di)
                if proc:
                    proc_id=proc[0]; rdt=self.order_time_within_shift(d,proc)
                else:
                    proc_id=""; rdt=datetime.combine(d,time(13,0))
                # Near the end, some returns remain requested. A small fraction are rejected.
                if d>=self.end-timedelta(days=5) and self.rng.random()<0.16:
                    status="REQUESTED"
                elif self.rng.random()<0.025:
                    status="REJECTED"
                else:
                    status="COMPLETED"
                refund_pre_tax=0.0
                item_rows=[]
                for item in ev["items"]:
                    cat=item["category"]
                    reason_weights={
                        "Defective":0.22,"Damaged on arrival":0.11,"Cosmetic damage":0.12,"Wrong item":0.08,
                        "Does not fit":0.15,"Changed mind":0.18,"Missing parts":0.08,"Installation compatibility issue":0.06,
                    }
                    if cat in ("Countertop Microwave","Over-the-Range Microwave"): reason_weights["Changed mind"]*=1.35
                    if cat in ("French Door Refrigerator","Column Refrigerator","Wall Oven"): reason_weights["Does not fit"]*=1.30
                    reason=weighted_choice(self.rng,list(reason_weights),list(reason_weights.values()))
                    if reason=="Defective": condition="DEFECTIVE"; restock=False
                    elif reason in ("Damaged on arrival","Cosmetic damage"): condition="DAMAGED"; restock=False
                    elif reason=="Wrong item": condition="UNOPENED" if self.rng.random()<0.8 else "OPEN_BOX"; restock=True
                    elif reason=="Changed mind": condition="UNOPENED" if self.rng.random()<0.55 else "OPEN_BOX"; restock=(condition=="UNOPENED" or self.rng.random()<0.65)
                    elif reason=="Does not fit": condition="OPEN_BOX"; restock=self.rng.random()<0.62
                    else: condition="OPEN_BOX"; restock=self.rng.random()<0.35
                    refund=item["sold_price"]*item["return_qty"]
                    if reason=="Changed mind" and condition=="OPEN_BOX" and self.rng.random()<0.18:
                        refund*=0.90
                    if status!="COMPLETED": refund=0.0; restock=False
                    refund=money(refund)
                    refund_pre_tax+=refund
                    item_rows.append((item,reason,condition,restock,refund))
                refund_total=money(refund_pre_tax*(1.0+tax_rate(self.store_hidden[s_idx]["province"]))) if status=="COMPLETED" else 0.0
                self.add("returns",[return_id,ev["order_id"],ev["customer_id"],s_idx+1,proc_id,dtstr(rdt),status,refund_total])
                for item,reason,condition,restock,refund in item_rows:
                    self.add("return_items",[return_item_id,return_id,item["order_item_id"],self.return_reason_id[reason],item["return_qty"],condition,refund,iso_bool(restock)])
                    if status=="COMPLETED":
                        self.order_returned_qty[ev["order_id"]]+=item["return_qty"]
                        if restock:
                            p_idx=item["p_idx"]; store_inv[s_idx,p_idx]+=item["return_qty"]
                            self.add("inventory_transactions",[inventory_tx_id,item["product_id"],"STORE",s_idx+1,dtstr(rdt),"CUSTOMER_RETURN",item["return_qty"],"RETURN_ITEM",return_item_id]); inventory_tx_id+=1
                    return_item_id+=1
                if status=="COMPLETED":
                    ptype=self.order_primary_payment.get(ev["order_id"],"CREDIT_CARD")
                    self.add("payments",[payment_id,ev["order_id"],dtstr(rdt),ptype,"COMPLETED","REFUND",refund_total]); payment_id+=1
                    idx=self.order_row_index[ev["order_id"]]
                    if self.order_returned_qty[ev["order_id"]]>=self.order_total_qty[ev["order_id"]]: self.rows["orders"][idx][6]="RETURNED"
                    else: self.rows["orders"][idx][6]="PARTIALLY_RETURNED"
                return_id+=1

        # Daily simulation.
        import time as _simtime
        _sim_t0=_simtime.time()
        for di,d in enumerate(self.days):
            if di % 180 == 0:
                print(f"  sim {d.isoformat()} elapsed={_simtime.time()-_sim_t0:.1f}s orders={len(self.rows['orders'])} invtx={self.counts['inventory_transactions']}", flush=True)
            # Process scheduled purchase receipts first.
            for rec in pending_receipts.pop(d,[]):
                w,p_idx,qty,poi_ref=rec
                wh_inv[w,p_idx]+=qty
                self.add("inventory_transactions",[inventory_tx_id,self.products_hidden[p_idx].product_id,"WAREHOUSE",w+1,dtstr(datetime.combine(d,time(6,0))),"PURCHASE_RECEIPT",qty,"PURCHASE_ORDER_ITEM",poi_ref]); inventory_tx_id+=1

            # Process customer returns before replenishment/sales.
            process_returns(d,di)

            # Weekly supplier ordering (Monday).
            if d.weekday()==0:
                seas=season_multiplier(d)
                for w in range(W):
                    for supplier_id in range(1,len(BRANDS)+1):
                        items=[]
                        for p_idx in self.products_by_brand[supplier_id]:
                            p=self.products_hidden[p_idx]
                            if not self.product_active(p,d): continue
                            exp=max(0.002,expected_wh[w,p_idx]*seas*category_season(p.category_name,d))
                            threshold=max(3,int(math.ceil(exp*50)))
                            target=max(6,int(math.ceil(exp*100)))
                            if wh_inv[w,p_idx]<threshold:
                                qty=target-int(wh_inv[w,p_idx])
                                if qty>0: items.append((p_idx,qty))
                        if not items: continue
                        lead=self.supplier_lead[supplier_id]
                        expected=d+timedelta(days=lead)
                        received=expected+timedelta(days=int(self.rng.integers(0,5)))
                        if received>self.end:
                            status="ORDERED"; received_field=""; fraction=0.0
                        else:
                            r=self.rng.random()
                            if r<0.012: status="CANCELLED"; received_field=""; fraction=0.0
                            elif r<0.048: status="PARTIALLY_RECEIVED"; received_field=received.isoformat(); fraction=float(self.rng.uniform(0.78,0.96))
                            else: status="RECEIVED"; received_field=received.isoformat(); fraction=1.0
                        self.add("purchase_orders",[po_id,supplier_id,w+1,d.isoformat(),expected.isoformat(),received_field,status])
                        for p_idx,qty_ordered in items:
                            qty_received=int(math.floor(qty_ordered*fraction))
                            _,cost=self.get_price(self.products_hidden[p_idx].product_id,d)
                            self.add("purchase_order_items",[poi_id,po_id,self.products_hidden[p_idx].product_id,qty_ordered,qty_received,money(cost)])
                            if qty_received>0:
                                pending_receipts[received].append((w,p_idx,qty_received,poi_id))
                            poi_id+=1
                        po_id+=1

            # Store replenishment twice weekly; availability can constrain later sales.
            if d.weekday() in (1,4):
                seas=season_multiplier(d)
                for s in range(S):
                    w=self.store_warehouse_idx[s]
                    exp=self.expected_store_daily[s]*seas
                    threshold=np.ceil(exp*11.0).astype(int)
                    target=np.ceil(exp*34.0).astype(int)
                    # Keep at least one display/sellable unit for carried active SKUs with meaningful demand.
                    for p_idx in np.where(self.assortment[s])[0]:
                        p=self.products_hidden[p_idx]
                        if not self.product_active(p,d): continue
                        if exp[p_idx]>=0.010:
                            threshold[p_idx]=max(threshold[p_idx],1); target[p_idx]=max(target[p_idx],2)
                        if store_inv[s,p_idx]>threshold[p_idx]: continue
                        need=max(0,target[p_idx]-int(store_inv[s,p_idx]))
                        qty=min(need,int(wh_inv[w,p_idx]))
                        if qty<=0: continue
                        wh_inv[w,p_idx]-=qty; store_inv[s,p_idx]+=qty
                        self.add("inventory_transactions",[inventory_tx_id,p.product_id,"WAREHOUSE",w+1,dtstr(datetime.combine(d,time(7,0))),"TRANSFER_OUT",-qty,"TRANSFER",transfer_id]); inventory_tx_id+=1
                        self.add("inventory_transactions",[inventory_tx_id,p.product_id,"STORE",s+1,dtstr(datetime.combine(d,time(8,30))),"TRANSFER_IN",qty,"TRANSFER",transfer_id]); inventory_tx_id+=1
                        transfer_id+=1

            # Occasional damage/shrinkage, correlated with store size and inventory.
            if d.day==15:
                for s in range(S):
                    n_events=max(1,int(self.store_hidden[s]["sqft"]/14000))
                    candidates=np.where(store_inv[s]>0)[0]
                    if len(candidates):
                        chosen=self.rng.choice(candidates,size=min(n_events,len(candidates)),replace=False)
                        for p_idx in np.atleast_1d(chosen):
                            store_inv[s,p_idx]-=1
                            self.add("inventory_transactions",[inventory_tx_id,self.products_hidden[int(p_idx)].product_id,"STORE",s+1,dtstr(datetime.combine(d,time(7,45))),"DAMAGE",-1,"ADJUSTMENT",inventory_tx_id]); inventory_tx_id+=1

            # Sales/orders per store.
            for s in range(S):
                sh=self.store_hidden[s]
                if HOLIDAYS.get((d.month,d.day))=="Christmas Day": continue
                staffing=len(self.sales_shifts[s][di])
                staffing_factor=float(np.clip(math.sqrt((staffing+0.6)/(self.typical_sales_staff[s]+0.6)),0.62,1.22))
                promo_mult=1.0+min(0.14,0.025*len(self.promos_by_day[di]))
                growth=1.0+0.024*((d-self.start).days/365.25)
                lam=sh["base_orders"]*weekday_multiplier(d)*season_multiplier(d)*staffing_factor*promo_mult*growth
                attempts=int(self.rng.poisson(max(0.2,lam)))
                # Daily active/in-stock assortment cache avoids repeatedly testing discontinued/zero-stock SKUs.
                daily_cat = {}
                daily_tier = {}
                for cat_name in self.leaf_categories:
                    pool=[i for i in self.store_cat_candidates.get((s,cat_name),[])
                          if self.product_active(self.products_hidden[i],d) and store_inv[s,i]>0]
                    daily_cat[cat_name]=pool
                    if pool:
                        by_tier={tier:[] for tier in TIER_ORDER}
                        for i in pool: by_tier[self.products_hidden[i].tier].append(i)
                        for tier in TIER_ORDER: daily_tier[(cat_name,tier)]=by_tier[tier]
                    else:
                        for tier in TIER_ORDER: daily_tier[(cat_name,tier)]=[]
                for _ in range(attempts):
                    channel=str(self.rng.choice(["IN_STORE","PHONE","ONLINE"],p=[0.76,0.09,0.15]))
                    shift=None; salesperson_id=None
                    if channel!="ONLINE":
                        shift=self.pick_salesperson(s,di,d)
                        if shift is None:
                            # Traffic without sales coverage is partly lost; a smaller share converts online.
                            if self.rng.random()<0.72: continue
                            channel="ONLINE"
                        else: salesperson_id=shift[0]
                    odt=self.order_time_within_shift(d,shift)
                    ctype=self.customer_type_for_order(channel)
                    cid=self.eligible_customer(ctype,d,sh["province"])
                    if cid is None: continue

                    # Correlated basket size / business quantities.
                    r=float(self.rng.random())
                    if ctype=="INDIVIDUAL":
                        n_lines=1 if r<0.57 else 2 if r<0.84 else 3 if r<0.96 else int(self.rng.integers(4,6))
                    else:
                        n_lines=1 if r<0.43 else 2 if r<0.72 else 3 if r<0.90 else int(self.rng.integers(4,7))
                    line_specs=[]; previous_cat=None
                    # The order is tentatively built without changing inventory until status is known.
                    temp_reserved=defaultdict(int)
                    for li in range(n_lines):
                        cat=self.choose_category(s,d,ctype,previous_cat,di)
                        qty=1
                        if ctype!="INDIVIDUAL" and self.rng.random()<0.17:
                            qty=int(self.rng.integers(2,5))
                        # select considering previously selected same-SKU quantity in this basket.
                        p_idx=self.select_product(s,cat,d,di,ctype,store_inv,qty_needed=qty,daily_tier=daily_tier,daily_cat=daily_cat)
                        if p_idx is None:
                            # Try another category once rather than force an unavailable sale.
                            cat=self.choose_category(s,d,ctype,None,di)
                            p_idx=self.select_product(s,cat,d,di,ctype,store_inv,qty_needed=qty,daily_tier=daily_tier,daily_cat=daily_cat)
                        if p_idx is None: continue
                        available=int(store_inv[s,p_idx])-temp_reserved[p_idx]
                        if available<=0: continue
                        qty=min(qty,available)
                        temp_reserved[p_idx]+=qty
                        previous_cat=cat
                        line_specs.append((p_idx,qty,cat))
                    if not line_specs: continue

                    # Cancellation/open-order behavior is determined after basket construction.
                    if d>=self.end-timedelta(days=3) and self.rng.random()<0.055:
                        status="PLACED"
                    elif self.rng.random()<0.014:
                        status="CANCELLED"
                    else:
                        status="COMPLETED"

                    order_regular_subtotal=0.0; discount_total=0.0; plan_total=0.0
                    item_details=[]; plan_rows=[]; promo_rows=[]
                    for p_idx,qty,cat in line_specs:
                        p=self.products_hidden[p_idx]
                        regular,cost=self.get_price(p.product_id,d)
                        promos=self.applicable_promotions(p,di)
                        promo_disc_each,promo_parts=self.promo_discount_each(regular,promos)
                        discretionary=0.0
                        if salesperson_id is not None:
                            emp=self.employees_hidden[salesperson_id]
                            # Discretionary discount rises for outlet stores, business buyers, and high-discount employees.
                            chance=0.20*sh["discount"]*emp.discount_tendency + (0.10 if ctype!="INDIVIDUAL" else 0)
                            if self.rng.random()<min(0.58,chance):
                                discretionary=regular*float(self.rng.uniform(0.01,0.045))*sh["discount"]*emp.discount_tendency
                        elif channel=="ONLINE" and self.rng.random()<0.06:
                            discretionary=regular*float(self.rng.uniform(0.01,0.025))
                        total_disc_each=min(regular*0.27,promo_disc_each+discretionary)
                        # Protect margin except for outlet clearance-like sales.
                        floor=cost*(0.98 if sh["type"]=="OUTLET" else 1.035)
                        sold=max(floor,regular-total_disc_each)
                        sold=money(sold); total_disc_each=max(0.0,regular-sold)
                        line_discount=money(total_disc_each*qty)
                        order_regular_subtotal+=regular*qty; discount_total+=line_discount
                        this_item_id=order_item_id+len(item_details)
                        item_details.append({"order_item_id":this_item_id,"p_idx":p_idx,"product_id":p.product_id,"qty":qty,"category":cat,"regular":regular,"sold":sold,"cost":cost,"discount":line_discount})
                        # Allocate represented promotion discounts proportionally, capped to actual line discount.
                        if promo_parts and line_discount>0:
                            promo_total=sum(x[1] for x in promo_parts)*qty
                            scale=min(1.0,line_discount/promo_total) if promo_total>0 else 0
                            for pr_id,amt_each in promo_parts:
                                amt=money(amt_each*qty*scale)
                                if amt>0: promo_rows.append((this_item_id,pr_id,amt))
                        if status!="CANCELLED":
                            plan=self.plan_for_price(sold,salesperson_id,cat,ctype)
                            if plan:
                                plan_id,sold_plan=plan; plan_total+=sold_plan
                                plan_rows.append((this_item_id,plan_id,salesperson_id or "",sold_plan,d.isoformat()))
                    if not item_details: continue
                    subtotal=money(order_regular_subtotal+plan_total)
                    discount_total=money(discount_total)
                    taxable=max(0.0,subtotal-discount_total)
                    taxes=money(taxable*tax_rate(sh["province"]))
                    total=money(taxable+taxes)
                    self.add("orders",[order_id,cid,s+1,salesperson_id or "",dtstr(odt),channel,status,subtotal,discount_total,taxes,total])
                    self.order_row_index[order_id]=len(self.rows["orders"])-1
                    self.order_total_qty[order_id]=sum(x["qty"] for x in item_details)

                    # Write item and plan/promotion rows.
                    for item in item_details:
                        self.add("order_items",[item["order_item_id"],order_id,item["product_id"],item["qty"],money(item["regular"]),money(item["sold"]),money(item["cost"]),item["discount"]])
                    for r in plan_rows:
                        self.add("order_protection_plans",[opp_id,r[0],r[1],r[2],r[3],r[4]]); opp_id+=1
                    for r in promo_rows:
                        self.add("order_item_promotions",[r[0],r[1],r[2]])

                    # Payment and inventory behavior by status.
                    ptype=self.payment_type(total,ctype); self.order_primary_payment[order_id]=ptype
                    if status=="COMPLETED":
                        # 8% split payment; avoid splitting cash-heavy low-value orders too much.
                        if self.rng.random()<0.082 and total>500:
                            ptype2=self.payment_type(total,ctype)
                            frac=float(self.rng.uniform(0.25,0.75)); a1=money(total*frac); a2=money(total-a1)
                            self.add("payments",[payment_id,order_id,dtstr(odt),ptype,"COMPLETED","PAYMENT",a1]); payment_id+=1
                            self.add("payments",[payment_id,order_id,dtstr(odt+timedelta(minutes=2)),ptype2,"COMPLETED","PAYMENT",a2]); payment_id+=1
                        else:
                            self.add("payments",[payment_id,order_id,dtstr(odt),ptype,"COMPLETED","PAYMENT",total]); payment_id+=1
                        # Finalize stock decrement and sales inventory transactions.
                        for item in item_details:
                            p_idx=item["p_idx"]; qty=item["qty"]
                            # Stock was checked earlier. If same product appeared twice, clamp gracefully.
                            qty=min(qty,int(store_inv[s,p_idx]))
                            if qty<=0: continue
                            store_inv[s,p_idx]-=qty
                            self.add("inventory_transactions",[inventory_tx_id,item["product_id"],"STORE",s+1,dtstr(odt),"SALE",-qty,"ORDER_ITEM",item["order_item_id"]]); inventory_tx_id+=1
                        # Schedule an order-level return event with correlated risk.
                        weighted_risk=np.average([RETURN_RISK[x["category"]] for x in item_details],weights=[x["qty"] for x in item_details])
                        disc_rate=discount_total/max(1.0,order_regular_subtotal)
                        risk=weighted_risk*sh["return"]*(1.0+0.9*disc_rate)
                        if salesperson_id:
                            # Very new salespeople create slightly more fit/expectation-related returns.
                            risk*=1.08 if tenure_factor(self.employees_hidden[salesperson_id].hire_date,d)<0.83 else 1.0
                        if self.rng.random()<min(0.12,risk):
                            offset=int(np.clip(self.rng.lognormal(mean=2.55,sigma=0.62),2,75))
                            rd=d+timedelta(days=offset)
                            if rd<=self.end:
                                nret=1 if len(item_details)==1 or self.rng.random()<0.88 else min(2,len(item_details))
                                risks=np.array([RETURN_RISK[x["category"]] for x in item_details]); risks/=risks.sum()
                                chosen_idx=self.rng.choice(len(item_details),size=nret,replace=False,p=risks)
                                ret_items=[]
                                for ci in np.atleast_1d(chosen_idx):
                                    item=item_details[int(ci)]
                                    rq=item["qty"] if item["qty"]==1 or self.rng.random()<0.72 else int(self.rng.integers(1,item["qty"]+1))
                                    ret_items.append({"order_item_id":item["order_item_id"],"p_idx":item["p_idx"],"product_id":item["product_id"],"return_qty":rq,"sold_price":item["sold"],"category":item["category"]})
                                pending_returns[rd].append({"order_id":order_id,"customer_id":cid,"store_idx":s,"items":ret_items})
                    elif status=="CANCELLED":
                        self.add("payments",[payment_id,order_id,dtstr(odt),ptype,"CANCELLED","PAYMENT",total]); payment_id+=1
                    else:  # PLACED
                        self.add("payments",[payment_id,order_id,dtstr(odt),ptype,"PENDING","PAYMENT",total]); payment_id+=1
                        for item in item_details:
                            self.final_reserved[s,item["p_idx"]]+=item["qty"]

                    order_item_id+=len(item_details); order_id+=1

            # Month-end snapshots after all activity for the day.
            if month_end(d):
                for s in range(S):
                    for p_idx in np.where(self.assortment[s])[0]:
                        q=int(store_inv[s,p_idx])
                        reserved=int(min(q,self.final_reserved[s,p_idx])) if d==self.end else 0
                        self.add("inventory_snapshots",[d.isoformat(),self.products_hidden[p_idx].product_id,"STORE",s+1,q,reserved])
                for w in range(W):
                    for p_idx,p in enumerate(self.products_hidden):
                        q=int(wh_inv[w,p_idx])
                        # Include all products that have launched by snapshot so warehouse zero-stock states remain visible.
                        if p.launch_date<=d:
                            self.add("inventory_snapshots",[d.isoformat(),p.product_id,"WAREHOUSE",w+1,q,0])

        # Any scheduled returns/receipts after end are intentionally absent; open POs remain ORDERED.
        self.final_store_inv=store_inv.copy(); self.final_wh_inv=wh_inv.copy()
        self.validation_notes.append(f"Simulation minimum final store inventory: {int(store_inv.min())}")
        self.validation_notes.append(f"Simulation minimum final warehouse inventory: {int(wh_inv.min())}")

    def close_streams(self):
        for fh in self._stream_files.values():
            if not fh.closed:
                fh.flush(); fh.close()

    def write_csvs(self):
        self.close_streams()
        for table, header in self.headers.items():
            if table in self.stream_tables:
                continue
            path=self.work_csv_gz/f"{table}.csv.gz"
            with gzip.open(path,"wt",newline="",encoding="utf-8",compresslevel=4) as f:
                w=csv.writer(f)
                w.writerow(header)
                w.writerows(self.rows.get(table,[]))

    def write_sql(self):
        create_sql = r'''-- PostgreSQL DDL for the synthetic appliance-retail operational dataset.
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
'''
        (self.out_dir/"create_tables.sql").write_text(create_sql,encoding="utf-8")

        serial_tables=[
            ("stores","store_id"),("employee_roles","role_id"),("employees","employee_id"),
            ("employee_compensation_history","compensation_id"),("employee_shifts","shift_id"),
            ("customers","customer_id"),("brands","brand_id"),("categories","category_id"),
            ("products","product_id"),("product_prices","product_price_id"),("orders","order_id"),
            ("order_items","order_item_id"),("payments","payment_id"),("return_reasons","return_reason_id"),
            ("returns","return_id"),("return_items","return_item_id"),("protection_plans","protection_plan_id"),
            ("order_protection_plans","order_protection_plan_id"),("warehouses","warehouse_id"),
            ("suppliers","supplier_id"),("purchase_orders","purchase_order_id"),("purchase_order_items","purchase_order_item_id"),
            ("inventory_transactions","inventory_transaction_id"),("promotions","promotion_id")]
        load_order=[
            "stores","employee_roles","employees","employee_compensation_history","employee_shifts","customers",
            "brands","categories","products","product_prices","return_reasons","protection_plans","warehouses","suppliers",
            "promotions","orders","order_items","payments","returns","return_items","order_protection_plans",
            "purchase_orders","purchase_order_items","inventory_transactions","inventory_snapshots","order_item_promotions","date_dimension"]
        lines=["-- Run from the dataset bundle root with psql, e.g.:", "-- psql -d your_database -f load_data.sql", "\\set ON_ERROR_STOP on", "BEGIN;", ""]
        # TRUNCATE is safe after all tables exist.
        lines.append("TRUNCATE TABLE " + ", ".join(reversed(load_order)) + " RESTART IDENTITY CASCADE;")
        lines.append("")
        for table in load_order:
            cols=", ".join(self.headers[table])
            lines.append(f"\\copy {table} ({cols}) FROM 'csv/{table}.csv' WITH (FORMAT csv, HEADER true, NULL '', ENCODING 'UTF8');")
        lines += ["", "-- Reset BIGSERIAL sequences because IDs were explicitly loaded."]
        for table,col in serial_tables:
            lines.append(f"SELECT setval(pg_get_serial_sequence('{table}','{col}'), COALESCE((SELECT MAX({col}) FROM {table}), 1), true);")
        lines += ["", "COMMIT;", ""]
        (self.out_dir/"load_data.sql").write_text("\n".join(lines),encoding="utf-8")

    def build_archive(self):
        archive_path = self.out_dir.with_suffix(".zip")
        if archive_path.exists():
            archive_path.unlink()
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as zf:
            for table in self.headers:
                src_path = self.work_csv_gz / f"{table}.csv.gz"
                with gzip.open(src_path, "rb") as src, zf.open(f"csv/{table}.csv", "w", force_zip64=True) as dst:
                    shutil.copyfileobj(src, dst, length=1024*1024)
            for name in ["create_tables.sql","load_data.sql","dataset_manifest.json","validation_report.txt","README.md","generate_appliance_retail_dataset.py"]:
                p=self.out_dir/name
                if p.exists():
                    zf.write(p, arcname=name)
        shutil.rmtree(self.work_csv_gz, ignore_errors=True)
        self.archive_path = archive_path

    def validate(self):
        # Targeted deterministic checks on generated in-memory facts.
        # 1. IDs unique where expected.
        pk_map={
            "stores":0,"employees":0,"products":0,"orders":0,"returns":0,"purchase_orders":0,
        }
        for table,idx in pk_map.items():
            vals=[r[idx] for r in self.rows[table]]
            assert len(vals)==len(set(vals)), f"Duplicate primary IDs in {table}"
        # Streamed primary-key tables use monotonic counters assigned exactly once by construction.
        # 2. Monetary order identity.
        bad=0
        for r in self.rows["orders"]:
            subtotal=float(r[7]); disc=float(r[8]); tax=float(r[9]); total=float(r[10])
            if abs((subtotal-disc+tax)-total)>0.011: bad+=1
        assert bad==0, f"{bad} orders fail total identity"
        # 3. Salespeople on in-store/phone orders must have a shift containing order time.
        bad_shift=0
        for r in self.rows["orders"]:
            if r[5] in ("IN_STORE","PHONE") and r[3] != "":
                odt=datetime.fromisoformat(r[4]); s_idx=int(r[2])-1; di=self.day_index[odt.date()]
                matching=[x for x in self.sales_shifts[s_idx][di] if int(x[0])==int(r[3])]
                if not any(a<=odt<=b for _,a,b in matching): bad_shift+=1
        assert bad_shift==0, f"{bad_shift} salesperson orders outside shifts"
        # 4. Snapshot nonnegativity/reservation checks are asserted at stream-write time.
        self.validation_notes += [
            "Order monetary identity subtotal - discount_total + tax_total = total_amount: PASS",
            "In-store/phone salesperson orders fall inside a recorded employee shift: PASS",
            "Inventory snapshots nonnegative and reserved <= on-hand: PASS",
            "Primary identifier uniqueness checks: PASS",
        ]

    def write_manifest_and_readme(self):
        src = Path(__file__).resolve()
        dst = (self.out_dir / "generate_appliance_retail_dataset.py").resolve()
        if src != dst:
            shutil.copy2(src, dst)
        counts={t:self.counts.get(t,0) for t in self.headers}
        manifest={
            "seed":self.seed,
            "history_start":self.start.isoformat(),
            "history_end":self.end.isoformat(),
            "history_days":len(self.days),
            "row_counts":counts,
            "notes":[
                "Operational values only; downstream analytical metrics are intentionally not materialized.",
                "Order-item regular price, sold price, and unit cost are frozen transaction-time facts.",
                "Inventory movements use signed quantity_change and reconcile through receipts, sales, returns, transfers, and damage.",
                "Inventory snapshots are month-end and include carried store SKUs plus launched warehouse SKUs.",
                "Promotions affect demand and discounting; employee/store hidden tendencies are generator-only and never written to the database.",
            ],
        }
        (self.out_dir/"dataset_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
        report=["Synthetic appliance-retail dataset validation report","="*52,"",f"Seed: {self.seed}",f"History: {self.start} through {self.end}",""]
        report += [f"{t:32s} {counts[t]:>10,d}" for t in self.headers]
        report += ["","Checks:"] + [f"- {x}" for x in self.validation_notes]
        (self.out_dir/"validation_report.txt").write_text("\n".join(report)+"\n",encoding="utf-8")
        readme=f'''# Synthetic Appliance Retail Dataset

This package contains a reproducible, correlated synthetic operational dataset for a multi-store Canadian appliance retailer.

- **Seed:** `{self.seed}`
- **History:** `{self.start.isoformat()}` through `{self.end.isoformat()}`
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

`load_data.sql` uses psql `\\copy`, so run it from the bundle root so paths such as `csv/orders.csv` resolve correctly.

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
'''
        (self.out_dir/"README.md").write_text(readme,encoding="utf-8")

    def run(self):
        import time as _time
        _t=_time.time()
        self.setup_headers(); print("phase headers", flush=True)
        self.generate_dimensions(); print(f"phase dimensions {_time.time()-_t:.1f}s", flush=True)
        self.generate_employees_and_shifts(); print(f"phase employees/shifts {_time.time()-_t:.1f}s", flush=True)
        self.generate_customers(); print(f"phase customers {_time.time()-_t:.1f}s", flush=True)
        self.generate_products_and_prices(); print(f"phase products/prices {_time.time()-_t:.1f}s", flush=True)
        self.generate_promotions(); print(f"phase promotions {_time.time()-_t:.1f}s", flush=True)
        self.generate_transactions(); print(f"phase transactions {_time.time()-_t:.1f}s", flush=True)
        self.close_streams()
        self.validate(); print(f"phase validation {_time.time()-_t:.1f}s", flush=True)
        self.write_csvs(); print(f"phase csv {_time.time()-_t:.1f}s", flush=True)
        self.write_sql()
        self.write_manifest_and_readme()
        if not getattr(self, "skip_archive", False):
            self.build_archive()
        print(f"phase done {_time.time()-_t:.1f}s", flush=True)


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",default="appliance_retail_dataset",help="Output directory")
    ap.add_argument("--seed",type=int,default=SEED)
    ap.add_argument("--start-date",type=parse_date,default=DEFAULT_START)
    ap.add_argument("--end-date",type=parse_date,default=DEFAULT_END)
    ap.add_argument("--customers",type=int,default=50000)
    ap.add_argument("--products",type=int,default=1000)
    ap.add_argument("--order-rate",type=float,default=4.0,help="Base daily order-rate scaler per store; use ~11 for a 200k-order stress-test scale")
    ap.add_argument("--skip-archive", action="store_true", help=argparse.SUPPRESS)
    args=ap.parse_args()
    if args.end_date < args.start_date: raise SystemExit("end-date must be >= start-date")
    out=Path(args.output).resolve(); out.mkdir(parents=True,exist_ok=True)
    g=Generator(out,args.seed,args.start_date,args.end_date,args.customers,args.products,args.order_rate)
    g.skip_archive=args.skip_archive
    g.run()
    archive_value=str(getattr(g,"archive_path",""))
    print(json.dumps({"output":str(out),"archive":archive_value,"seed":args.seed,"row_counts":{k:g.counts.get(k,0) for k in g.headers}},indent=2))

if __name__=="__main__":
    main()
