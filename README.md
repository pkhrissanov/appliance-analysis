# Appliance Retail Analytics

An end-to-end retail analytics project built around a fictional multi-store Canadian appliance retailer.

The project combines **Python, PostgreSQL, Azure, SQL, DAX, and Power BI** to transform operational retail data into interactive business reporting focused on store performance, profitability, inventory, and sales operations.

> **Note:** All data used in this project is synthetic and was created specifically for portfolio and analytical purposes. It does not represent a real retailer or real customers.

---

## Current Project Status

The primary focus of the project is now the **Power BI reporting layer**.

The **Store Overview dashboard is the current showcase page**, providing a detailed view of an individual store's financial and operational performance.

The original **Executive Overview** is currently being redesigned to better complement the Store Overview. The final report will combine both perspectives:

- **Executive Overview** — company-wide performance and comparison across stores
- **Store Overview** — detailed investigation of an individual location

The Store Overview is currently the most complete representation of the intended final report design. Once the Executive Overview redesign is complete, the two pages will be presented together as the main showcase of the project.

---

# Store Overview

The Store Overview is designed around a simple management question:

**What is happening at this store, and where should management investigate further?**

It brings financial performance, operational metrics, inventory, product categories, and employee performance together on a single interactive page.

## Monthly Store View

![Store Overview - Calgary North Outlet - Monthly View](./Screenshot%202026-08-23%20230722.png)

The dashboard begins with five key store-level KPIs:

- **Revenue**
- **Gross Profit**
- **Average Order Value**
- **Gross Margin %**
- **Store Health Index**

Each KPI is accompanied by its change relative to the previous equivalent period, making it possible to quickly distinguish between current performance and performance direction.

---

## Dynamic Financial and Operational Trends

Two large trend visuals provide the main analytical area of the dashboard.

Rather than dedicating individual charts to every possible measure, the report uses **dynamic metric selectors** that allow users to change what each visual displays.

Financial metrics include measures such as:

- Revenue
- Gross Profit
- Margin %
- Average Order Value

Operational metrics include measures such as:

- Return Rate
- Protection Plan performance
- Store Health

Each trend compares the **selected store** against the **company average**, helping distinguish store-specific movements from broader company trends.

The dashboard can also change its time granularity, allowing the same report page to support both longer-term monthly analysis and more detailed daily investigation.

## Daily Store View

![Store Overview - Kelowna - Daily View](./Screenshot%202026-08-23%20230914.png)

This allows the Store Overview to move between high-level performance review and shorter-term operational investigation without requiring separate dashboards.

---

## Revenue by Category

Revenue is broken down by major appliance category to show the composition of the selected store's sales.

This makes it easy to identify:

- Leading revenue categories
- Categories contributing relatively little revenue
- Differences in product mix between stores
- Areas that may warrant further analysis

The reporting layer also supports more detailed category and subcategory analysis where required.

---

## Overstock Risk

The dashboard includes an **Overstock Risk** table intended to surface inventory requiring management attention.

Rather than showing inventory levels alone, the analysis combines current inventory with recent sales activity and inventory value.

The table includes:

- SKU
- Category
- Current inventory
- Recent units sold
- Days on hand
- Overstock value
- Risk level

This adds an operational decision-making component to the report and helps identify inventory that may be tying up capital without generating sufficient sales.

---

## Salesperson Performance

The final section ranks employees within the selected store.

The ranking metric can be changed, allowing managers to evaluate salesperson performance using measures such as revenue or margin rather than relying on a single definition of performance.

This connects store-level results back to the employees contributing to them and provides another level of investigation below the overall store KPIs.

---

# Store Health Index

A custom **Store Health Index** summarizes several dimensions of store performance into a single score.

| Component | Weight |
| --- | ---: |
| Profitability | 30% |
| Growth | 25% |
| Labour Efficiency | 20% |
| Return Performance | 15% |
| Protection Plan Performance | 10% |

The index is intended as a quick indicator of overall performance rather than a replacement for the underlying measures.

A manager can identify an unusual Store Health score at the top of the dashboard and then use the financial and operational visuals below it to investigate the underlying causes.

---

# Executive Overview

The project also includes a company-level **Executive Overview**.

An initial version of this dashboard was completed earlier in development. It is currently being redesigned so that it more closely matches the structure, visual language, and interactive approach established in the Store Overview.

The updated Executive Overview will focus on questions such as:

- How is the company performing overall?
- Which stores are outperforming or underperforming?
- Which stores require attention?
- How is company performance changing over time?
- What are the major drivers behind those movements?

The intended reporting workflow is:

```text
Executive Overview
        ↓
Identify Store
        ↓
Store Overview
        ↓
Financial / Operational Investigation
        ↓
Category / Inventory / Salesperson Drivers
```

Once the redesigned Executive Overview is complete, screenshots of both pages will be presented together as the primary showcase of the project.

---

# Project Architecture

The project follows a complete analytics workflow:

```text
Python Data Generation
        |
        v
PostgreSQL Operational Database
        |
        v
SQL Analytics Layer
        |
        v
Power BI Data Model
        |
        v
DAX Measures & Business Logic
        |
        v
Executive + Store Reporting
```

Operational transformations and reusable reporting logic are handled primarily in PostgreSQL, while Power BI and DAX handle interactive calculations that depend on filters, date ranges, stores, and user-selected metrics.

---

# Technology Stack

| Area | Technology |
| --- | --- |
| Data Generation | Python, NumPy |
| Database | PostgreSQL |
| Cloud Hosting | Azure Database for PostgreSQL |
| SQL Development | JetBrains DataGrip |
| Analytics | SQL, DAX |
| Visualization | Microsoft Power BI |
| Environment Management | Miniconda |
| Version Control | Git / GitHub |

---

# Data and Backend

The project uses a reproducible synthetic retail dataset covering multiple stores, employees, customers, products, orders, returns, inventory movements, promotions, and other operational activity.

The data was designed to create meaningful differences across stores, products, employees, and time periods so that the dashboards support realistic analytical comparisons.

The dataset is loaded into a normalized PostgreSQL database hosted on **Azure Database for PostgreSQL**.

SQL analytical views consolidate operational data into reporting-friendly datasets before it is consumed by Power BI.

This keeps the Power BI model focused on analytics and visualization rather than recreating complex operational joins inside the report.

---

# Analytics Layer

The reporting solution splits responsibilities between SQL and Power BI.

### PostgreSQL / SQL

Used primarily for:

- Joining normalized operational tables
- Creating reusable reporting datasets
- Aggregating store and daily performance
- Preparing sales, inventory, employee, and category analysis
- Centralizing reusable business logic

### Power BI / DAX

Used primarily for:

- Interactive KPI calculations
- Previous-period comparisons
- Dynamic metric selection
- Time-based analysis
- Store-versus-company comparisons
- Store Health calculations
- Ranking and conditional formatting
- User-controlled report interactions

This approach keeps reusable transformations close to the data while allowing Power BI to handle calculations that depend on the user's current report context.

---

# Development Process

The project evolved from the data layer upward.

### 1. Operational Data Model

A relational PostgreSQL model was created for the major areas of an appliance retail business, including sales, products, stores, employees, customers, inventory, returns, promotions, and purchasing.

### 2. Synthetic Data Generation

Python was used to create a multi-year dataset large enough to support store, employee, category, inventory, and time-based analysis.

### 3. Cloud Database

The generated dataset was loaded into an Azure-hosted PostgreSQL database to create a realistic separation between the reporting environment and the source data.

### 4. SQL Analytics

Reporting-oriented SQL views were created to transform the operational model into datasets better suited for analytical queries and Power BI.

### 5. Power BI Model and DAX

The analytical datasets were brought into Power BI and extended with DAX measures for KPIs, previous-period comparisons, dynamic trend metrics, rankings, store health, and other interactive calculations.

### 6. Dashboard Development

The first report page focused on company-wide executive reporting.

Development then moved to the Store Overview, which expanded the project into more detailed financial and operational analysis at the individual-store level.

The Store Overview is now the strongest representation of the intended final design, and the Executive Overview is being rebuilt to follow the same approach.

---

# Repository

Important project files include:

```text
appliance-analysis/
│
├── README.md
├── Appliance-analysis-exe-overview.pbix
├── Screenshot 2026-08-23 230722.png
├── Screenshot 2026-08-23 230914.png
├── generate_appliance_retail_dataset.py
├── dataset_manifest.json
├── validation_report.txt
├── environment.yml
│
└── database/
    ├── create_tables.sql
    ├── load_data.py
    ├── load_data.sql
    ├── test_connection.py
    │
    └── analytics/
        └── store_daily_performance.sql
```

Generated raw datasets and database credentials are intentionally excluded from the repository.

---

# Running the Project

## 1. Create the environment

```bash
conda env create -f environment.yml
conda activate appliance-retail
```

## 2. Configure PostgreSQL

Create a local `.env` file containing the PostgreSQL connection information.

```text
POSTGRES_HOST=<your-server>.postgres.database.azure.com
POSTGRES_PORT=5432
POSTGRES_DB=appliance_retail
POSTGRES_USER=<your-username>
POSTGRES_PASSWORD=<your-password>
POSTGRES_SSLMODE=require
```

The `.env` file is excluded from version control.

## 3. Generate the dataset

```bash
python generate_appliance_retail_dataset.py --output appliance_retail_dataset
```

## 4. Create and load the database

Create the PostgreSQL schema and load the generated data using the scripts in the `database/` directory.

## 5. Create the analytics layer

Run the analytical SQL definitions in:

```text
database/analytics/
```

## 6. Open Power BI

Open the `.pbix` report, configure the PostgreSQL connection if required, and refresh the model.

---

# Next Steps

The immediate next step is to **redesign the Executive Overview** so that it visually and analytically complements the Store Overview.

Once that is complete, the report will provide a two-level workflow:

```text
Company Performance
        ↓
Identify Store
        ↓
Store Performance
        ↓
Financial / Operational Investigation
        ↓
Inventory / Category / Salesperson Drivers
```

Potential later extensions include:

- Dedicated salesperson analysis
- Deeper inventory and purchasing reporting
- Supplier performance
- Stockout and slow-moving inventory analysis
- Additional drill-through between report pages
- Automated refresh
- Forecasting or anomaly detection

---

# Project Goal

The goal of this project is to demonstrate more than the ability to build individual Power BI charts.

It is intended to show the complete process of turning operational data into a structured analytics solution:

**data generation → database design → SQL analytics → business logic → interactive reporting**

The final report is being designed around a natural management workflow: begin with company-level performance, identify locations requiring attention, and then investigate the financial and operational factors affecting those stores.
