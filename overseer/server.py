import http.server
import socketserver
import json
import mysql.connector
from mysql.connector import Error, pooling
import time
import os
import sys

PORT = 8080

# Database Configuration with Environment Variable Fallbacks
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'telemetry_db'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'Tsdg2@vxh'), # Use env var or default
    'pool_name': 'telemetry_pool',
    'pool_size': 5
}

# Global Connection Pool
try:
    db_pool = mysql.connector.pooling.MySQLConnectionPool(**DB_CONFIG)
except Error as e:
    print(f"Error creating connection pool: {e}")
    db_pool = None

class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    pass

class TelemetryHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/ingest':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data)
                self.process_telemetry(data)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Data Received")
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid JSON")
        else:
            self.send_response(404)
            self.end_headers()

    def process_telemetry(self, data):
        # TODO: Validate schema and insert into DB
        print(f"Received data: {data}")
        # Placeholder for DB insertion logic
        # self.save_to_vault(data)

    def save_to_vault(self, data):
        conn = None
        try:
            if not db_pool:
                 print("Database pool not initialized.")
                 return

            conn = db_pool.get_connection()
            if conn.is_connected():
                cursor = conn.cursor()
                # TODO: Parse 'data' and execute INSERT statements here
                # Example:
                # cursor.execute("INSERT INTO events (...) VALUES (...)", (...))
                conn.commit()
                cursor.close()
                print("Data saved to MySQL vault")
        except Error as e:
            print(f"Error connecting to MySQL: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")
        finally:
            if conn and conn.is_connected():
                conn.close() # Returns connection to pool

if __name__ == "__main__":
    # Ensure database exists (optional, usually done separately)
    # create_database_if_not_exists()
    
    # Use ThreadingTCPServer for better stability with concurrent requests
    with ThreadingTCPServer(("", PORT), TelemetryHandler) as httpd:
        print(f"The Overseer is listening on port {PORT}")
        print(f"Connected to MySQL at {DB_CONFIG['host']}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            httpd.shutdown()
