# The Overseer: Telemetry System

The Grand Vision: To build a standalone, engine-agnostic telemetry software that runs silently in the background, archiving game data for analysis.

## Repository Structure

The project is organized into following components:

- **`backend/`**: The Python server (FastAPI-style behavior using `http.server`).
  - Port: `8090` (Default)
  - Config: Controlled via `.env` file.
  
- **`clients/`**: Client-side integrations.
  - **`java/`**: A Maven project for Java applications (LibGDX, LWJGL, etc.).
  
- **`database/`**: SQL storage.
  - Contains `schema.sql` for MySQL database setup.
  
- **`visualizer/`**: Data analysis and heatmap generation.
  - Generates heatmaps (PNG images) from event data.

## Getting Started

### 1. Database Setup
Ensure MySQL is running and execute:
```bash
mysql -u root -p < database/schema.sql
```

### 2. Backend (Overseer)
Navigate to `backend/`, configure the `.env` file and install dependencies:
```bash
pip install -r ../requirements.txt
python server.py
```

### 3. Visualizer
Navigate to `visualizer/` and generate a heatmap:
```bash
python generator.py --event PLAYER_DEATH
```

### 4. Java Client
Build the telemetry library:
```bash
cd clients/java
mvn clean install
```
