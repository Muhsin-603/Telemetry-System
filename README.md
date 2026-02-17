# The Overseer: Telemetry System

The Grand Vision: To build a standalone, engine-agnostic telemetry software that runs silently in the background, archiving game data for analysis.

## Project Structure

This project is organized into three main components (phases):

1. **`overseer/`** (Phase 2): The Python server application.
   - Listens for telemetry data via HTTP.
   - Validates incoming JSON payloads.
   - Writes valid data to the Vault.

2. **`vault/`** (Phase 3): The Database storage.
   - Contains the MySQL schema.
   - Stores Users, Sessions, Events, and Save Files.

3. **`visualizer/`** (Phase 4): The Data Visualization tool.
   - Reads from the Vault.
   - Generates heatmaps (PNG images) of death locations/events.

4. **`client_integrations/`** (Phase 1): Example implementations for game clients.
   - Java (LibGDX/LWJGL)
   - Godot (GDScript)
   - Unity (C#)

## Getting Started

### 1. The Overseer (Server)
Navigate to the `overseer` directory and install dependencies:
```bash
cd overseer
pip install -r requirements.txt
# Check server.py to update MySQL credentials
python server.py
```
The server will start listening on `localhost:8080`.

### 2. The Visualizer
Navigate to the `visualizer` directory to generate heatmaps:
```bash
cd visualizer
pip install -r requirements.txt
python generator.py
```

### 3. The Client
Check `client_integrations/` for example code to drop into your game project.
