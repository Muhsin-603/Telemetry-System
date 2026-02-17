-- The Vault Schema (MySQL Compatible)
CREATE DATABASE IF NOT EXISTS telemetry_db;
USE telemetry_db;

-- Stores Sessions, Users, and Events

CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(255) PRIMARY KEY,
    username VARCHAR(255),
    total_playtime INT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255),
    start_time BIGINT,
    end_time BIGINT,
    duration_seconds INT DEFAULT 0,
    os_info TEXT,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS events (
    event_id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(255),
    event_type VARCHAR(50), -- 'DEATH', 'JUMP', 'LEVEL_COMPLETE'
    x_coord FLOAT,
    y_coord FLOAT,
    timestamp BIGINT,
    meta_data JSON, -- JSON string for extra data
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS save_files (
    save_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(255),
    level_data JSON,
    inventory_data JSON,
    updated_at BIGINT,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);
