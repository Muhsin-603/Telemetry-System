import mysql.connector
import matplotlib.pyplot as plt
import numpy as np
from scipy import ndimage
from scipy.stats import gaussian_kde
import os
import argparse

OUTPUT_DIR = "output"

# Database Configuration - Update these with your MySQL credentials
DB_CONFIG = {
    'host': 'localhost',
    'database': 'telemetry_db',
    'user': 'root',
    'password': 'Tsdg2@vxh'  # Match your overseer config
}

# Event types matching the server
EVENT_TYPES = {
    'STEALTH_BROKEN': {'color': 'Oranges', 'name': 'Stealth Broken'},
    'PLAYER_DEATH': {'color': 'Reds', 'name': 'Player Deaths'},
    'ITEM_USED': {'color': 'Blues', 'name': 'Item Usage'},
    'LEVEL_COMPLETE': {'color': 'Greens', 'name': 'Level Completions'},
    'ENEMY_ALERT': {'color': 'YlOrRd', 'name': 'Enemy Alerts'},
    'CHECKPOINT': {'color': 'Purples', 'name': 'Checkpoints'},
    'DAMAGE_TAKEN': {'color': 'RdPu', 'name': 'Damage Taken'}
}


def connect_db():
    """Connect to the MySQL database."""
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as err:
        print(f"[ERROR] Connecting to MySQL: {err}")
        return None


def fetch_events_by_type(event_type, session_id=None):
    """Fetch coordinates for a specific event type."""
    conn = connect_db()
    if not conn or not conn.is_connected():
        return []
    
    try:
        cursor = conn.cursor()
        
        if session_id:
            cursor.execute(
                "SELECT x_coord, y_coord FROM events WHERE event_type=%s AND session_id=%s",
                (event_type, session_id)
            )
        else:
            cursor.execute(
                "SELECT x_coord, y_coord FROM events WHERE event_type=%s",
                (event_type,)
            )
        
        data = cursor.fetchall()
        cursor.close()
        conn.close()
        return data
    except mysql.connector.Error as err:
        print(f"[ERROR] Fetching events: {err}")
        return []


def generate_kde_heatmap(coords, event_type, map_size=(1000, 1000), output_name=None):
    """
    Generate a Kernel Density Estimation heatmap.
    
    Uses Gaussian KDE to create smooth density gradients from point data.
    Output is a transparent PNG that can be overlaid on level maps.
    """
    if not coords or len(coords) < 2:
        print(f"[WARNING] Not enough data points for {event_type} ({len(coords)} points)")
        return None
    
    x = np.array([c[0] for c in coords])
    y = np.array([c[1] for c in coords])
    
    # Get event config
    config = EVENT_TYPES.get(event_type, {'color': 'Reds', 'name': event_type})
    
    print(f"[INFO] Generating KDE heatmap for {config['name']} ({len(coords)} points)")
    
    # Create figure with transparent background
    fig, ax = plt.subplots(figsize=(12, 12))
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)
    
    try:
        # Kernel Density Estimation
        xy = np.vstack([x, y])
        kde = gaussian_kde(xy)
        
        # Create grid for evaluation
        xmin, xmax = 0, map_size[0]
        ymin, ymax = 0, map_size[1]
        
        # Auto-adjust if data is outside default bounds
        if x.max() > xmax or y.max() > ymax:
            xmax = max(xmax, x.max() * 1.1)
            ymax = max(ymax, y.max() * 1.1)
        
        xi, yi = np.mgrid[xmin:xmax:200j, ymin:ymax:200j]
        zi = kde(np.vstack([xi.flatten(), yi.flatten()]))
        zi = zi.reshape(xi.shape)
        
        # Apply Gaussian blur for smoother gradients
        zi = ndimage.gaussian_filter(zi, sigma=2)
        
        # Plot the KDE heatmap
        im = ax.pcolormesh(xi, yi, zi, shading='gouraud', cmap=config['color'], alpha=0.7)
        
        # Also scatter the actual points (semi-transparent)
        ax.scatter(x, y, c='white', s=20, alpha=0.3, edgecolors='none')
        
    except np.linalg.LinAlgError:
        # Fallback to histogram if KDE fails (e.g., colinear points)
        print(f"[WARNING] KDE failed, falling back to histogram")
        ax.hist2d(x, y, bins=30, cmap=config['color'], alpha=0.7)
    
    # Style the plot
    ax.set_xlim(0, map_size[0])
    ax.set_ylim(0, map_size[1])
    ax.set_aspect('equal')
    ax.axis('off')  # No axes for clean overlay
    
    # Save with transparency
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    if output_name:
        filename = f"{output_name}.png"
    else:
        filename = f"heatmap_{event_type.lower()}.png"
    
    output_path = os.path.join(OUTPUT_DIR, filename)
    plt.savefig(output_path, transparent=True, bbox_inches='tight', pad_inches=0, dpi=150)
    plt.close()
    
    print(f"[SUCCESS] Heatmap saved to {output_path}")
    return output_path


def generate_combined_heatmap(map_size=(1000, 1000)):
    """Generate a combined heatmap showing all death and danger zones."""
    
    # Fetch death and stealth broken events
    deaths = fetch_events_by_type('PLAYER_DEATH')
    stealth = fetch_events_by_type('STEALTH_BROKEN')
    
    all_danger = deaths + stealth
    
    if not all_danger:
        print("[WARNING] No danger zone data found")
        return None
    
    x = np.array([c[0] for c in all_danger])
    y = np.array([c[1] for c in all_danger])
    
    # Weight deaths higher than stealth breaks
    weights = np.array([2.0 if i < len(deaths) else 1.0 for i in range(len(all_danger))])
    
    fig, ax = plt.subplots(figsize=(12, 12))
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)
    
    try:
        xy = np.vstack([x, y])
        kde = gaussian_kde(xy, weights=weights)
        
        xi, yi = np.mgrid[0:map_size[0]:200j, 0:map_size[1]:200j]
        zi = kde(np.vstack([xi.flatten(), yi.flatten()]))
        zi = zi.reshape(xi.shape)
        zi = ndimage.gaussian_filter(zi, sigma=3)
        
        ax.pcolormesh(xi, yi, zi, shading='gouraud', cmap='hot', alpha=0.8)
        
        # Mark death locations with X
        if deaths:
            dx = [d[0] for d in deaths]
            dy = [d[1] for d in deaths]
            ax.scatter(dx, dy, marker='x', c='white', s=50, alpha=0.5)
        
    except Exception as e:
        print(f"[WARNING] Combined heatmap generation failed: {e}")
        ax.hist2d(x, y, bins=30, cmap='hot', alpha=0.8)
    
    ax.set_xlim(0, map_size[0])
    ax.set_ylim(0, map_size[1])
    ax.set_aspect('equal')
    ax.axis('off')
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, "heatmap_danger_zones.png")
    plt.savefig(output_path, transparent=True, bbox_inches='tight', pad_inches=0, dpi=150)
    plt.close()
    
    print(f"[SUCCESS] Combined danger zone heatmap saved to {output_path}")
    return output_path


def generate_player_flow(map_size=(1000, 1000)):
    """Generate a flow visualization showing player movement patterns."""
    
    # Use checkpoints and level completes to show intended paths
    checkpoints = fetch_events_by_type('CHECKPOINT')
    completes = fetch_events_by_type('LEVEL_COMPLETE')
    
    success_points = checkpoints + completes
    
    if not success_points or len(success_points) < 2:
        print("[WARNING] Not enough flow data")
        return None
    
    return generate_kde_heatmap(success_points, 'flow', map_size, 'heatmap_player_flow')


def get_stats():
    """Print statistics about collected events."""
    conn = connect_db()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        
        print("\n" + "=" * 50)
        print("  TELEMETRY STATISTICS")
        print("=" * 50)
        
        # Total events
        cursor.execute("SELECT COUNT(*) FROM events")
        total = cursor.fetchone()[0]
        print(f"Total Events: {total}")
        
        # Events by type
        cursor.execute("""
            SELECT event_type, COUNT(*) as count 
            FROM events 
            GROUP BY event_type 
            ORDER BY count DESC
        """)
        
        print("\nEvents by Type:")
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]}")
        
        # Sessions
        cursor.execute("SELECT COUNT(*) FROM sessions")
        sessions = cursor.fetchone()[0]
        print(f"\nTotal Sessions: {sessions}")
        
        cursor.close()
        conn.close()
        print("=" * 50 + "\n")
        
    except mysql.connector.Error as err:
        print(f"[ERROR] Getting stats: {err}")


def main():
    parser = argparse.ArgumentParser(description='Generate telemetry heatmaps')
    parser.add_argument('--event', '-e', type=str, help='Event type to visualize')
    parser.add_argument('--all', '-a', action='store_true', help='Generate all heatmaps')
    parser.add_argument('--combined', '-c', action='store_true', help='Generate combined danger zone map')
    parser.add_argument('--stats', '-s', action='store_true', help='Show statistics')
    parser.add_argument('--width', type=int, default=1000, help='Map width')
    parser.add_argument('--height', type=int, default=1000, help='Map height')
    
    args = parser.parse_args()
    map_size = (args.width, args.height)
    
    print("\n" + "=" * 50)
    print("  HEATMAP GENERATOR - Visualizing Suffering")
    print("=" * 50 + "\n")
    
    if args.stats:
        get_stats()
        return
    
    if args.combined:
        generate_combined_heatmap(map_size)
        return
    
    if args.event:
        if args.event.upper() in EVENT_TYPES:
            coords = fetch_events_by_type(args.event.upper())
            generate_kde_heatmap(coords, args.event.upper(), map_size)
        else:
            print(f"[ERROR] Unknown event type: {args.event}")
            print(f"Available: {', '.join(EVENT_TYPES.keys())}")
        return
    
    if args.all:
        for event_type in EVENT_TYPES.keys():
            coords = fetch_events_by_type(event_type)
            if coords:
                generate_kde_heatmap(coords, event_type, map_size)
        generate_combined_heatmap(map_size)
        return
    
    # Default: Generate death heatmap
    print("Generating death heatmap (use --help for more options)...")
    coords = fetch_events_by_type('PLAYER_DEATH')
    if coords:
        generate_kde_heatmap(coords, 'PLAYER_DEATH', map_size)
    else:
        print("[INFO] No death events found. Play the game first!")


if __name__ == "__main__":
    main()
