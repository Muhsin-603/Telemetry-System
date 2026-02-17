import http.server
import socketserver
import json
import mysql.connector
from mysql.connector import Error, pooling
import time
import os
import sys
from urllib.parse import urlparse, parse_qs

# Import shared configuration from the project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import var

PORT = var.SERVER_PORT

# ============================================================================
# EVENT TYPES - The Vocabulary of Suffering
# ============================================================================
class EventType:
    STEALTH_BROKEN = "STEALTH_BROKEN"    # Enemy spotted the player
    PLAYER_DEATH = "PLAYER_DEATH"        # Player died
    ITEM_USED = "ITEM_USED"              # Health/distraction item used
    LEVEL_COMPLETE = "LEVEL_COMPLETE"    # Player escaped the level
    ENEMY_ALERT = "ENEMY_ALERT"          # Enemy entered alert state
    CHECKPOINT = "CHECKPOINT"            # Player reached checkpoint
    DAMAGE_TAKEN = "DAMAGE_TAKEN"        # Player took damage

VALID_EVENT_TYPES = [
    EventType.STEALTH_BROKEN,
    EventType.PLAYER_DEATH,
    EventType.ITEM_USED,
    EventType.LEVEL_COMPLETE,
    EventType.ENEMY_ALERT,
    EventType.CHECKPOINT,
    EventType.DAMAGE_TAKEN
]

# Database Configuration from common var.py
DB_CONFIG = {
    'host': var.DB_HOST,
    'database': var.DB_NAME,
    'user': var.DB_USER,
    'password': var.DB_PASSWORD,
    'pool_name': 'telemetry_pool',
    'pool_size': 5
}

# Config without database for initial setup
DB_CONFIG_NO_DB = var.DB_CONFIG_NO_DB

db_pool = None

def initialize_database():
    """Forge the database and tables if they don't exist."""
    conn = None
    try:
        # Connect without specifying database first
        conn = mysql.connector.connect(**DB_CONFIG_NO_DB)
        cursor = conn.cursor()
        
        # Create database
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
        cursor.execute(f"USE {DB_CONFIG['database']}")
        
        # Create Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id VARCHAR(255) PRIMARY KEY,
                username VARCHAR(255),
                total_playtime INT DEFAULT 0,
                created_at BIGINT
            )
        """)
        
        # Create Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id VARCHAR(255) PRIMARY KEY,
                user_id VARCHAR(255),
                start_time BIGINT,
                end_time BIGINT,
                duration_seconds INT DEFAULT 0,
                os_info TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)

        # Migration: Add duration_seconds to sessions if it doesn't exist
        try:
            cursor.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS duration_seconds INT DEFAULT 0")
        except:
            pass # MySQL 8.0.19+ supports ADD COLUMN IF NOT EXISTS, older might not

        # Migration: Add total_playtime to users if it doesn't exist
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS total_playtime INT DEFAULT 0")
        except:
            pass

        # Create Events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id INT AUTO_INCREMENT PRIMARY KEY,
                session_id VARCHAR(255),
                event_type VARCHAR(50),
                x_coord FLOAT,
                y_coord FLOAT,
                timestamp BIGINT,
                meta_data JSON,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
        """)
        
        # Create Save Files table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS save_files (
                save_id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(255),
                level_data JSON,
                inventory_data JSON,
                updated_at BIGINT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)
        
        conn.commit()
        cursor.close()
        print("[OVERSEER] Database forged successfully.")
        return True
        
    except Error as e:
        print(f"[OVERSEER] Error initializing database: {e}")
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()

def create_connection_pool():
    """Create the connection pool after DB is initialized."""
    global db_pool
    try:
        db_pool = mysql.connector.pooling.MySQLConnectionPool(**DB_CONFIG)
        print("[OVERSEER] Connection pool created.")
        return True
    except Error as e:
        print(f"[OVERSEER] Error creating connection pool: {e}")
        return False


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True


class TelemetryHandler(http.server.BaseHTTPRequestHandler):
    
    def log_message(self, format, *args):
        """Custom logging format."""
        print(f"[{time.strftime('%H:%M:%S')}] {args[0]}")
    
    def send_json_response(self, status_code, data):
        """Helper to send JSON responses."""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
    
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data) if post_data else {}
        except json.JSONDecodeError:
            self.send_json_response(400, {"error": "Invalid JSON"})
            return
        
        # Route to appropriate handler
        if self.path == '/session/start':
            self.handle_session_start(data)
        elif self.path == '/session/end':
            self.handle_session_end(data)
        elif self.path == '/event':
            self.handle_event(data)
        elif self.path == '/save/upload':
            self.handle_save_upload(data)
        elif self.path == '/user/register':
            self.handle_user_register(data)
        elif self.path == '/ingest':
            # Legacy endpoint - process as generic event
            self.handle_event(data)
        else:
            self.send_json_response(404, {"error": "Endpoint not found"})
    
    def do_GET(self):
        if self.path == '/health':
            self.send_json_response(200, {"status": "alive", "pool": db_pool is not None})
        elif self.path == '/events':
            self.handle_get_events()
        elif self.path.startswith('/leaderboard'):
            self.handle_get_leaderboard()
        else:
            self.send_json_response(404, {"error": "Endpoint not found"})
    
    def handle_user_register(self, data):
        """Register a new user or return existing."""
        user_id = data.get('user_id')
        username = data.get('username', 'Anonymous')
        
        if not user_id:
            self.send_json_response(400, {"error": "user_id required"})
            return
        
        conn = None
        try:
            conn = db_pool.get_connection()
            cursor = conn.cursor()
            
            # Insert or ignore if exists
            cursor.execute("""
                INSERT IGNORE INTO users (user_id, username, created_at)
                VALUES (%s, %s, %s)
            """, (user_id, username, int(time.time() * 1000)))
            
            conn.commit()
            cursor.close()
            
            print(f"[OVERSEER] User registered: {user_id}")
            self.send_json_response(200, {"status": "registered", "user_id": user_id})
            
        except Error as e:
            print(f"[OVERSEER] DB Error: {e}")
            self.send_json_response(500, {"error": str(e)})
        finally:
            if conn and conn.is_connected():
                conn.close()
    
    def handle_session_start(self, data):
        """Initialize a new telemetry session."""
        session_id = data.get('session_id')
        user_id = data.get('user_id')
        os_info = data.get('os_info', 'Unknown')
        starting_total_playtime = data.get('starting_total_playtime')
        
        if not session_id or not user_id:
            self.send_json_response(400, {"error": "session_id and user_id required"})
            return
        
        conn = None
        try:
            conn = db_pool.get_connection()
            cursor = conn.cursor()
            
            # Ensure user exists first
            cursor.execute("""
                INSERT IGNORE INTO users (user_id, username, created_at)
                VALUES (%s, %s, %s)
            """, (user_id, 'Player', int(time.time() * 1000)))
            
            # Sync starting playtime if provided (cloud sync logic)
            if starting_total_playtime is not None:
                cursor.execute("""
                    UPDATE users SET total_playtime = GREATEST(total_playtime, %s)
                    WHERE user_id = %s
                """, (starting_total_playtime, user_id))
            
            # Create session
            cursor.execute("""
                INSERT INTO sessions (session_id, user_id, start_time, os_info)
                VALUES (%s, %s, %s, %s)
            """, (session_id, user_id, int(time.time() * 1000), os_info))
            
            conn.commit()
            cursor.close()
            
            print(f"[OVERSEER] Session started: {session_id} for user {user_id}")
            self.send_json_response(200, {"status": "session_started", "session_id": session_id})
            
        except Error as e:
            print(f"[OVERSEER] DB Error: {e}")
            self.send_json_response(500, {"error": str(e)})
        finally:
            if conn and conn.is_connected():
                conn.close()
    
    def handle_session_end(self, data):
        """End the current session."""
        session_id = data.get('session_id')
        playtime_seconds = data.get('playtime_seconds', 0)
        total_playtime_seconds = data.get('total_playtime_seconds')
        
        print(f"[OVERSEER] Session end request: {session_id}, {playtime_seconds}s, Total: {total_playtime_seconds}s")
        
        if not session_id:
            self.send_json_response(400, {"error": "session_id required"})
            return
        
        conn = None
        try:
            conn = db_pool.get_connection()
            cursor = conn.cursor()
            
            # Update session with end time and duration
            cursor.execute("""
                UPDATE sessions SET end_time = %s, duration_seconds = %s WHERE session_id = %s
            """, (int(time.time() * 1000), playtime_seconds, session_id))
            
            # Sync user's total playtime if provided
            if total_playtime_seconds is not None:
                # Find user_id from session_id
                cursor.execute("SELECT user_id FROM sessions WHERE session_id = %s", (session_id,))
                res = cursor.fetchone()
                if res:
                    user_id = res[0]
                    print(f"[OVERSEER] Updating playtime for user {user_id} to {total_playtime_seconds}")
                    cursor.execute("""
                        UPDATE users SET total_playtime = GREATEST(total_playtime, %s)
                        WHERE user_id = %s
                    """, (total_playtime_seconds, user_id))
                else:
                    print(f"[OVERSEER] Session {session_id} not found in database")
            
            conn.commit()
            cursor.close()
            
            print(f"[OVERSEER] Session ended: {session_id} with duration {playtime_seconds}s")
            self.send_json_response(200, {"status": "session_ended"})
            
        except Error as e:
            print(f"[OVERSEER] DB Error: {e}")
            self.send_json_response(500, {"error": str(e)})
        finally:
            if conn and conn.is_connected():
                conn.close()

    def handle_save_upload(self, data):
        """Process game save and sync playtime statistics."""
        user_id = data.get('user_id')
        save_data = data.get('save_data', {})
        
        if not user_id:
            self.send_json_response(400, {"error": "user_id required"})
            return
            
        total_playtime_seconds = save_data.get('totalPlaytimeSeconds')
        
        conn = None
        try:
            conn = db_pool.get_connection()
            cursor = conn.cursor()
            
            # Update save record
            cursor.execute("""
                INSERT INTO save_files (user_id, level_data, inventory_data, updated_at)
                VALUES (%s, %s, %s, %s)
            """, (
                user_id,
                json.dumps(save_data.get('level_data', {})),
                json.dumps(save_data.get('inventory_data', {})),
                int(time.time() * 1000)
            ))
            
            # Extract and sync playtime stats if present
            if total_playtime_seconds is not None:
                cursor.execute("""
                    UPDATE users SET total_playtime = GREATEST(total_playtime, %s)
                    WHERE user_id = %s
                """, (total_playtime_seconds, user_id))
            
            conn.commit()
            cursor.close()
            
            print(f"[OVERSEER] Save stats synced for {user_id}")
            self.send_json_response(200, {"status": "save_synced", "user_id": user_id})
            
        except Error as e:
            print(f"[OVERSEER] DB Error: {e}")
            self.send_json_response(500, {"error": str(e)})
        finally:
            if conn and conn.is_connected():
                conn.close()
    
    def handle_event(self, data):
        """Record a telemetry event."""
        session_id = data.get('session_id')
        event_type = data.get('event_type')
        x_coord = data.get('x', 0.0)
        y_coord = data.get('y', 0.0)
        meta_data = data.get('meta', {})
        
        if not session_id or not event_type:
            self.send_json_response(400, {"error": "session_id and event_type required"})
            return
        
        # Validate event type
        if event_type not in VALID_EVENT_TYPES:
            print(f"[OVERSEER] Warning: Unknown event type '{event_type}' - recording anyway")
        
        conn = None
        try:
            conn = db_pool.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO events (session_id, event_type, x_coord, y_coord, timestamp, meta_data)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                session_id, 
                event_type, 
                float(x_coord), 
                float(y_coord), 
                int(time.time() * 1000),
                json.dumps(meta_data)
            ))
            
            conn.commit()
            cursor.close()
            
            print(f"[OVERSEER] Event recorded: {event_type} at ({x_coord}, {y_coord})")
            self.send_json_response(200, {"status": "event_recorded"})
            
        except Error as e:
            print(f"[OVERSEER] DB Error: {e}")
            self.send_json_response(500, {"error": str(e)})
        finally:
            if conn and conn.is_connected():
                conn.close()
    
    def handle_get_events(self):
        """Fetch all events (for debugging/visualization)."""
        conn = None
        try:
            conn = db_pool.get_connection()
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("SELECT * FROM events ORDER BY timestamp DESC LIMIT 100")
            events = cursor.fetchall()
            cursor.close()
            
            self.send_json_response(200, {"events": events})
            
        except Error as e:
            self.send_json_response(500, {"error": str(e)})
        finally:
            if conn and conn.is_connected():
                conn.close()

    def handle_get_leaderboard(self):
        """Fetch game leaderboards."""
        parsed_url = urlparse(self.path)
        params = parse_qs(parsed_url.query)
        category = params.get('category', ['playtime'])[0]
        
        conn = None
        try:
            conn = db_pool.get_connection()
            cursor = conn.cursor(dictionary=True)
            
            if category == 'playtime':
                # Rank by total_playtime (DESC)
                cursor.execute("""
                    SELECT user_id, username, total_playtime 
                    FROM users 
                    ORDER BY total_playtime DESC 
                    LIMIT 20
                """)
                leaderboard = cursor.fetchall()
                cursor.close()
                self.send_json_response(200, {"category": category, "leaderboard": leaderboard})
            else:
                cursor.close()
                self.send_json_response(400, {"error": f"Unknown category: {category}"})
            
        except Error as e:
            print(f"[OVERSEER] DB Error: {e}")
            self.send_json_response(500, {"error": str(e)})
        finally:
            if conn and conn.is_connected():
                conn.close()


if __name__ == "__main__":
    print("=" * 50)
    print("  THE OVERSEER - Telemetry Collection Server")
    print("=" * 50)
    
    # Phase 1: Forge the database
    if not initialize_database():
        print("[OVERSEER] Failed to initialize database. Exiting.")
        sys.exit(1)
    
    # Create connection pool
    if not create_connection_pool():
        print("[OVERSEER] Failed to create connection pool. Exiting.")
        sys.exit(1)
    
    # Start the server
    with ThreadingTCPServer(("", PORT), TelemetryHandler) as httpd:
        print(f"[OVERSEER] Listening on port {PORT}")
        print(f"[OVERSEER] Connected to MySQL at {DB_CONFIG['host']}")
        print("-" * 50)
        print("Endpoints:")
        print("  POST /session/start  - Start a new session")
        print("  POST /session/end    - End a session")
        print("  POST /event          - Record an event")
        print("  POST /user/register  - Register a user")
        print("  GET  /health         - Health check")
        print("  GET  /events         - Fetch recent events")
        print("-" * 50)
        print("Waiting for victims...")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[OVERSEER] Shutting down...")
            httpd.shutdown()
