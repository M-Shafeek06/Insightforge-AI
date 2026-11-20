# InsightForge AI
### AI-Powered Business Analytics & Decision Intelligence Platform

<p align="center">
  <strong>Transform Raw Data into Meaningful Business Insights.</strong>
</p>

<p align="center">
  <a href="https://insightforge-ai-chi.vercel.app/">Live Application</a> •
  <a href="https://insightforge-ai-gskd.onrender.com/docs">API Documentation</a> •
  <a href="https://github.com/M-Shafeek06/Insightforge-AI">Source Code</a>
</p>

---

## Overview

**InsightForge AI** is a web-based Business Analytics and Decision Intelligence platform designed to help users explore datasets, evaluate data quality, perform analytical operations, and interpret results in a business context.

The platform brings together dataset profiling, data-quality assessment, business analysis planning, data cleaning, analytical execution, interactive visualizations, and AI-assisted interpretation within a unified application.

Rather than treating data analysis as an isolated technical task, InsightForge AI provides a structured workflow that connects data understanding with business-oriented analysis.

**Core Workflow:**

`Understand → Clean → Analyze → Visualize → Explain → Decide`

**Project Status:** Publicly deployed MVP.

---

## Live Application

| Component | URL |
|---|---|
| Web Application | [InsightForge AI](https://insightforge-ai-chi.vercel.app/) |
| Backend API | [Render API](https://insightforge-ai-gskd.onrender.com) |
| API Documentation | [Swagger UI](https://insightforge-ai-gskd.onrender.com/docs) |
| Source Code | [GitHub Repository](https://github.com/M-Shafeek06/Insightforge-AI) |

---

## Core Features

### 1. Dataset Upload & Profiling

Upload tabular datasets and obtain an overview of their structure.

- CSV and Excel file support.
- Excel workbook worksheet selection.
- Dataset dimensions and column information.
- Column data-type identification.
- Semantic column classification.
- Missing-value analysis.
- Dataset profiling and preview.

### 2. Data Quality Assessment

Evaluates datasets through deterministic data-quality checks.

Implemented checks include:

- Missing values.
- Duplicate rows.
- Empty columns.
- Constant columns.
- Date-like values stored as text.
- Invalid date values.
- High-cardinality columns.

Quality findings are categorized by severity to help users identify potential issues before performing analysis.

### 3. Column Intelligence

Provides additional information about individual dataset columns.

- Column data types.
- Semantic classification.
- Column-level statistics.
- Missing-value information.
- Analytical relevance.

### 4. Data Cleaning

Provides data-cleaning recommendations and supported cleaning operations.

- Review potential data-quality issues.
- Apply supported cleaning transformations.
- Execute cleaning operations.
- Generate cleaned dataset versions.
- Review dataset version information.

Cleaning operations depend on the selected transformation and the structure of the uploaded dataset.

### 5. Business Analysis Planner

Helps translate business objectives into structured analytical approaches.

- Business objective interpretation.
- Relevant column identification.
- Suggested KPIs.
- Recommended analytical operations.
- Data-quality considerations.

**Important:** Planner recommendations are suggestions. They are distinct from the analytical operations that users subsequently execute.

### 6. Analytical Execution

Supports multiple analytical operations through the backend.

| Operation | Description |
|---|---|
| KPI & Aggregation Analysis | Calculate measures with optional grouping. |
| Descriptive Statistics | Summarize numerical variables. |
| Trend Analysis | Examine measures across time periods. |
| Segment Comparison | Compare aggregated results across categories. |
| Correlation Analysis | Evaluate relationships between supported numerical variables. |

Available operations depend on the dataset structure, selected columns, and validation requirements.

### 7. Interactive Visualizations

Presents analytical outputs through charts and tables.

Supported visualization categories include:

- KPI results.
- Trend charts.
- Segment comparisons.
- Correlation visualizations.
- Analytical result summaries.

### 8. AI-Assisted Business Interpretation

Provides AI-assisted explanations based on analytical results and dataset context.

The objective is to make analytical outputs easier to understand and connect them with potential business implications.

AI-generated interpretations should be reviewed against the underlying data and business context. They are not guaranteed to be factually correct or to predict business outcomes.

### 9. Analytics History & Reports

Supports saving analytical results and generating downloadable reports.

- Save executed analytical results.
- Retrieve saved analytics.
- Maintain saved analytical records.
- Generate downloadable PDF reports.

**Report inclusion rule:** Only analyses explicitly saved by the user are included in the generated report. Executed but unsaved analyses are excluded.

---

## Technology Stack

### Frontend

| Technology | Purpose |
|---|---|
| Next.js | Frontend framework |
| React | User interface |
| TypeScript | Type-safe development |
| Tailwind CSS | Interface styling |
| Plotly | Data visualization |

### Backend

| Technology | Purpose |
|---|---|
| Python | Backend application and analytical logic |
| FastAPI | REST API framework |
| Pydantic | Data validation and settings |
| Pandas | Data processing and analysis |
| NumPy | Numerical operations |
| Uvicorn | ASGI application server |

### Database & Persistence

| Technology | Purpose |
|---|---|
| PostgreSQL | Relational database |
| SQLAlchemy | ORM and database operations |
| Psycopg | PostgreSQL connectivity |

### AI Integration

- Gemini API
- Groq API

These integrations support AI-assisted application functionality. AI-generated outputs are separate from deterministic analytical calculations.

### Deployment

| Platform | Responsibility |
|---|---|
| Vercel | Frontend deployment |
| Render | Backend API hosting |
| Neon | Managed PostgreSQL database |
| GitHub | Source-code repository and version control |

---

## Application Architecture

InsightForge AI follows a separated frontend and backend architecture.

```text
                 USER
                   |
                   v
             NEXT.JS FRONTEND
                   |
                   v
         NEXT.JS API ROUTE HANDLER
                   |
                   v
             FASTAPI BACKEND
                   |
          +--------+---------+
          |                  |
          v                  v
    DATASET SERVICES    DATABASE SERVICES
          |                  |
          v                  v
    DATA PROFILING       POSTGRESQL
          |
          v
    DATA QUALITY
          |
          v
    DATA CLEANING
          |
          v
    BUSINESS PLANNER
          |
          v
   ANALYTICAL EXECUTION
          |
          v
    VISUALIZATIONS
          |
          v
   AI INTERPRETATION
          |
          v
   SAVED ANALYTICS
          |
          v
      PDF REPORTS
```

The architecture separates dataset processing, analytical execution, database operations, and AI-assisted interpretation into distinct application responsibilities.

---

## Repository Structure

```text
Insightforge-AI/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── db.py
│   │   └── main.py
│   │
│   ├── tests/
│   ├── requirements.txt
│   └── pytest.ini
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── public/
│   ├── package.json
│   └── package-lock.json
│
├── data/
│   └── samples/
│
├── docs/
│   └── architecture/
│
├── scripts/
│
├── .env.example
├── .gitignore
├── docker-compose.yml
└── README.md
```

---

## Running Locally

### Prerequisites

- Python 3.12
- Node.js
- npm
- Git
- PostgreSQL (when using a local PostgreSQL database)

### 1. Clone the Repository

```bash
git clone https://github.com/M-Shafeek06/Insightforge-AI.git

cd Insightforge-AI
```

### 2. Backend Setup

Navigate to the backend directory:

```powershell
cd backend
```

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Configure the required backend environment variables using the provided `.env.example` as a reference.

Start the backend:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend:

```text
http://127.0.0.1:8000
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

### 3. Frontend Setup

Open another terminal:

```powershell
cd frontend
```

Install dependencies:

```powershell
npm install
```

Configure the frontend environment variable:

```env
BACKEND_URL=http://127.0.0.1:8000
```

Start the frontend:

```powershell
npm run dev
```

Open the local address displayed by Next.js.

---

## Testing

### Backend Tests

From the backend directory:

```powershell
pytest -q
```

**Latest recorded backend test result (November 20, 2026):**

```text
241 passed, 1 warning
```

The warning was a dependency deprecation warning.

### Frontend Production Build

From the frontend directory:

```powershell
npm run build
```

The frontend production build was also successfully validated during the MVP deployment process.

---

## Deployment Architecture

The publicly accessible application uses three primary hosting services:

**Frontend — Vercel**
- Hosts the Next.js application.
- Provides public web access.
- Forwards API requests to the backend.

**Backend — Render**
- Hosts the FastAPI application.
- Handles dataset processing and analytical requests.
- Connects to the PostgreSQL database.

**Database — Neon**
- Provides managed PostgreSQL hosting.
- Stores application records and saved analytical information.

### Deployment Considerations

The current deployment uses Render's free hosting tier.

Its filesystem is ephemeral. Consequently, uploaded files stored on the backend filesystem are not guaranteed to persist across service restarts or redeployments.

Database records stored in Neon are separate from files stored on Render's filesystem.

---

## Data & Analytical Limitations

- Analytical results depend on the quality and suitability of uploaded datasets.
- Data-quality findings are based on implemented deterministic checks.
- Business Planner recommendations are suggestions, not completed calculations.
- AI-generated interpretations may require manual verification.
- Correlation does not establish causation.
- Statistical results require appropriate business and domain context.
- File persistence on the current Render free deployment is limited by ephemeral storage.
- The platform is an MVP and should not be represented as an enterprise-scale analytics infrastructure.

---

## Future Enhancements

Potential areas for further development include:

- Expanded analytical capabilities.
- Additional data-cleaning transformations.
- Improved data persistence and file storage.
- Enhanced AI-assisted business analysis.
- Additional reporting and visualization capabilities.

These are potential improvements and are not represented as completed functionality.

---

## Author

**M. Shafeek**

B.Tech – Artificial Intelligence & Data Science  
Dhaanish Ahmed Institute of Technology

**Areas of Interest:**  
Data Analytics | Business Intelligence | Decision Intelligence | AI-Powered Analytics

- Portfolio: https://m-shafeek06.github.io/
- GitHub: https://github.com/M-Shafeek06
- LinkedIn: https://www.linkedin.com/in/m-shafeek
- Email: shafeekm529@gmail.com

---

<p align="center">
  <strong>InsightForge AI</strong>
  <br>
  Explore Data. Understand Results. Support Better Decisions.
</p>
