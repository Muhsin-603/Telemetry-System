import http.server
import socketserver
import json
import mysql.connector
from mysql.connector import Error, pooling
import time
import os
import sys

PORT = 8090

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

# Database Configuration with Environment Variable Fallbacks
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'telemetry_db'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'Tsdg2@vxh'),
    'pool_name': 'telemetry_pool',
    'pool_size': 5
}

# Config without database for initial setup
DB_CONFIG_NO_DB = {
    'host': DB_CONFIG['host'],
    'user': DB_CONFIG['user'],
    'password': DB_CONFIG['password']
}

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
                os_info TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)
        
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
            
            # Create session
            cursor.execute("""
                INSERT INTO sessions (session_id, user_id, start_time, os_info)
                VALUES (%s, %s, %s, %s)
            """, (session_id, user_id, int(time.time() * 1000), os_info))
            
            conn.commit()
            cursor.close()
            
            print(f"[OVERSEER] Session started: {session_id}")
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
        
        if not session_id:
            self.send_json_response(400, {"error": "session_id required"})
            return
        
        conn = None
        try:
            conn = db_pool.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE sessions SET end_time = %s WHERE session_id = %s
            """, (int(time.time() * 1000), session_id))
            
            conn.commit()
            cursor.close()
            
            print(f"[OVERSEER] Session ended: {session_id}")
            self.send_json_response(200, {"status": "session_ended"})
            
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
