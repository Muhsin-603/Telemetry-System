import mysql.connector
import matplotlib.pyplot as plt
import numpy as np
import os

OUTPUT_DIR = "output"
# Database Configuration - Update these with your MySQL credentials
DB_CONFIG = {
    'host': 'localhost',
    'database': 'telemetry_db',
    'user': 'root',
    'password': 'password' # CHANGE THIS
}

def connect_db():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as err:
        print(f"Error connecting to MySQL: {err}")
        return None

def fetch_death_coordinates():
    conn = connect_db()
    if conn and conn.is_connected():
        cursor = conn.cursor()
        cursor.execute("SELECT x_coord, y_coord FROM events WHERE event_type='DEATH'")
        data = cursor.fetchall()
        cursor.close()
        conn.close()
        return data
    return []

def generate_heatmap(coords):
    if not coords:
        print("No death events found to visualize.")
        return

    x = [c[0] for c in coords]
    y = [c[1] for c in coords]

    plt.figure(figsize=(10, 10))
    # Basic scatter plot for now - Gaussian Blur logic to be added
    plt.hist2d(x, y, bins=30, cmap='Reds')
    plt.title('Player Death Heatmap')
    plt.xlabel('X Coordinate')
    plt.ylabel('Y Coordinate')
    plt.colorbar(label='Death Count')
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, "heatmap_death.png")
    plt.savefig(output_path, transparent=True)
    print(f"Heatmap saved to {output_path}")

if __name__ == "__main__":
    print("Generating Visualizations...")
    death_coords = fetch_death_coordinates()
    generate_heatmap(death_coords)
