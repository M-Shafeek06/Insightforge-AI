# InsightForge AI

### AI-Powered Business Analytics & Decision Intelligence Platform

<p align="center">
  <strong>Transform Raw Data into Meaningful Business Insights.</strong>
</p>

<p align="center">
  <a href="https://insightforge-ai-chi.vercel.app/">Live Application</a> •
  <a href="https://insightforge-ai-gskd.onrender.com/docs">API Documentation</a> •
  <a href="https://github.com/M-Shafeek06/Insightforge-AI">GitHub Repository</a>
</p>

---

## Overview

**InsightForge AI** is a web-based Business Analytics and Decision Intelligence platform designed to help users explore datasets, assess data quality, perform analytical operations, and interpret results in a business context.

The platform combines dataset profiling, data-quality assessment, business analysis planning, data cleaning, analytical execution, interactive visualizations, and AI-assisted interpretation within a unified application.

It provides a structured workflow that connects data understanding with business-oriented analysis.

### Core Workflow

**Understand → Clean → Analyze → Visualize → Explain → Decide**

**Project Status:** Publicly deployed MVP.

---

## Live Application

| Component | Link |
|---|---|
| Web Application | [InsightForge AI](https://insightforge-ai-chi.vercel.app/) |
| Backend API | [Render API](https://insightforge-ai-gskd.onrender.com) |
| API Documentation | [Swagger UI](https://insightforge-ai-gskd.onrender.com/docs) |
| Source Code | [GitHub Repository](https://github.com/M-Shafeek06/Insightforge-AI) |

---

## Project Workflow

The following diagram illustrates the end-to-end workflow of InsightForge AI, from dataset ingestion to analytical results and business decision support.

<p align="center">
  <img src="docs/architecture/InsightForge%20AI%20Project%20Workflow%202.png" alt="InsightForge AI - Complete Project Workflow" width="100%">
</p>

## System Architecture

InsightForge AI follows a separated frontend and backend architecture. The frontend communicates with backend services through API requests, while data processing, analytical operations, persistence, and AI-assisted interpretation are handled by their respective application components.

<p align="center">
  <img src="docs/architecture/InsightForge%20AI%20Workflow%20Architecture.png" alt="InsightForge AI - System Architecture" width="100%">
</p>

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
- Additional business clarification questions.

Planner recommendations are suggestions. They are separate from the analytical operations users subsequently execute.

### 6. Analytical Execution

Supports multiple analytical operations through the backend.

| Analysis Type | Description |
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

### 8. Business Insights & Decision Support

Provides deterministic observations based on executed analytical results.

Depending on the analysis, this can include:

- Findings supported by calculated results.
- Interpretations within the limits of the analysis.
- Data limitations.
- Questions for further investigation.

These observations support analysis; they do not establish causation or independently explain underlying business drivers.

### 9. AI-Assisted Business Interpretation

Provides AI-assisted explanations based on analytical results and dataset context.

The interpretation workflow can produce:

- Executive summaries.
- Key findings.
- Business implications.
- Risks and limitations.
- Actionable recommendations.

AI-generated interpretations should be reviewed against the underlying data and business context. They are not guaranteed to be factually correct or to predict business outcomes.

### 10. Analytics History & PDF Reports

Supports saving analytical results and generating downloadable reports.

- Save executed analytical results.
- Retrieve saved analytics.
- Maintain saved analytical records.
- Generate downloadable PDF reports.

**Report inclusion rule:** Only analyses explicitly saved by the user are included in the generated report. Executed but unsaved analyses are excluded.

#### Sample Analytics Report

A sample PDF report generated by the application is available below.

[View Sample Analytics Report](InsightForge_Analytics_Report_Sample.pdf)

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

### Deployment & Infrastructure

| Platform | Responsibility |
|---|---|
| Vercel | Frontend deployment |
| Render | Backend API hosting |
| Neon | Managed PostgreSQL database |
| GitHub | Source-code repository and version control |

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
│       ├── InsightForge AI Project Workflow 2.png
│       └── InsightForge AI Workflow Architecture.png
│
├── scripts/
│
├── .env.example
├── .gitignore
├── docker-compose.yml
├── InsightForge_Analytics_Report_Sample.pdf
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

Configure the required backend environment variables using `.env.example` as a reference.

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

Open another terminal and navigate to the frontend directory:

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
python -m pytest -q
```

**Latest recorded backend test result — November 20, 2026:**

```text
243 passed, 1 warning
```

The warning was a dependency deprecation warning.

### Frontend Production Build

From the frontend directory:

```powershell
npm run build
```

The frontend production build was successfully validated during the MVP deployment process.

---

## Deployment Architecture

The publicly accessible application uses three primary hosting services.

### Frontend — Vercel

- Hosts the Next.js application.
- Provides public web access.
- Forwards API requests to the backend.

### Backend — Render

- Hosts the FastAPI application.
- Handles dataset processing and analytical requests.
- Connects to the PostgreSQL database.

### Database — Neon

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
- The platform is an MVP and should not be represented as enterprise-scale analytics infrastructure.

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
