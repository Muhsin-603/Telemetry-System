import java.net.HttpURLConnection;
import java.net.URL;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * TelemetryClient - The Silent Observer
 * 
 * Tracks player behavior and sends data to the Overseer server.
 * All operations are asynchronous and fire-and-forget.
 * 
 * Usage:
 *   1. Call TelemetryClient.initialize() when game starts
 *   2. Call event methods (onPlayerDeath, onStealthBroken, etc.) in your game code
 *   3. Call TelemetryClient.shutdown() when game closes
 */
public class TelemetryClient {
    
    // ========================================================================
    // CONFIG
    // ========================================================================
    private static final String OVERSEER_HOST = "http://localhost:8080";
    private static final int TIMEOUT_MS = 2000;
    
    // ========================================================================
    // EVENT TYPES - Must match server's EventType class
    // ========================================================================
    public static final String EVENT_STEALTH_BROKEN = "STEALTH_BROKEN";
    public static final String EVENT_PLAYER_DEATH = "PLAYER_DEATH";
    public static final String EVENT_ITEM_USED = "ITEM_USED";
    public static final String EVENT_LEVEL_COMPLETE = "LEVEL_COMPLETE";
    public static final String EVENT_ENEMY_ALERT = "ENEMY_ALERT";
    public static final String EVENT_CHECKPOINT = "CHECKPOINT";
    public static final String EVENT_DAMAGE_TAKEN = "DAMAGE_TAKEN";
    
    // ========================================================================
    // STATE
    // ========================================================================
    private static String sessionId = null;
    private static String userId = null;
    private static ExecutorService executor = null;
    private static boolean initialized = false;
    
    // ========================================================================
    // INITIALIZATION
    // ========================================================================
    
    /**
     * Initialize the telemetry system. Call this when the game boots up.
     * Generates a unique session ID and registers with the Overseer.
     * 
     * @param playerId Unique identifier for the player (can be machine ID, save slot, etc.)
     */
    public static void initialize(String playerId) {
        if (initialized) {
            System.out.println("[Telemetry] Already initialized");
            return;
        }
        
        userId = playerId;
        sessionId = UUID.randomUUID().toString();
        executor = Executors.newSingleThreadExecutor();
        initialized = true;
        
        // Register session with Overseer
        String osInfo = System.getProperty("os.name") + " " + System.getProperty("os.version");
        String payload = String.format(
            "{\"session_id\":\"%s\",\"user_id\":\"%s\",\"os_info\":\"%s\"}",
            sessionId, userId, osInfo
        );
        
        sendAsync("/session/start", payload);
        System.out.println("[Telemetry] Session started: " + sessionId);
    }
    
    /**
     * Shutdown the telemetry system. Call this when the game closes.
     */
    public static void shutdown() {
        if (!initialized) return;
        
        // End session
        String payload = String.format("{\"session_id\":\"%s\"}", sessionId);
        sendSync("/session/end", payload); // Sync to ensure it completes before exit
        
        if (executor != null) {
            executor.shutdown();
        }
        
        initialized = false;
        System.out.println("[Telemetry] Session ended");
    }
    
    // ========================================================================
    // EVENT TRACKING METHODS - Insert these into your game code
    // ========================================================================
    
    /**
     * Track when an enemy spots the player (stealth broken).
     * 
     * @param x Player X coordinate
     * @param y Player Y coordinate
     * @param enemyType Type of enemy that spotted the player
     */
    public static void onStealthBroken(float x, float y, String enemyType) {
        sendEvent(EVENT_STEALTH_BROKEN, x, y, 
            String.format("{\"enemy_type\":\"%s\"}", enemyType));
    }
    
    /**
     * Track player death.
     * 
     * @param x Death X coordinate
     * @param y Death Y coordinate
     * @param causeOfDeath What killed the player
     */
    public static void onPlayerDeath(float x, float y, String causeOfDeath) {
        sendEvent(EVENT_PLAYER_DEATH, x, y,
            String.format("{\"cause\":\"%s\"}", causeOfDeath));
    }
    
    /**
     * Track item usage (health, distractions, etc.)
     * 
     * @param x Usage X coordinate
     * @param y Usage Y coordinate
     * @param itemType Type of item used
     */
    public static void onItemUsed(float x, float y, String itemType) {
        sendEvent(EVENT_ITEM_USED, x, y,
            String.format("{\"item_type\":\"%s\"}", itemType));
    }
    
    /**
     * Track level completion.
     * 
     * @param x Exit X coordinate
     * @param y Exit Y coordinate
     * @param levelName Name of completed level
     * @param timeSeconds Time taken to complete
     */
    public static void onLevelComplete(float x, float y, String levelName, int timeSeconds) {
        sendEvent(EVENT_LEVEL_COMPLETE, x, y,
            String.format("{\"level\":\"%s\",\"time_seconds\":%d}", levelName, timeSeconds));
    }
    
    /**
     * Track enemy alert state trigger.
     * 
     * @param x Player X coordinate when alert triggered
     * @param y Player Y coordinate when alert triggered
     * @param enemyType Type of enemy that entered alert
     */
    public static void onEnemyAlert(float x, float y, String enemyType) {
        sendEvent(EVENT_ENEMY_ALERT, x, y,
            String.format("{\"enemy_type\":\"%s\"}", enemyType));
    }
    
    /**
     * Track checkpoint reached.
     * 
     * @param x Checkpoint X coordinate
     * @param y Checkpoint Y coordinate
     * @param checkpointId Checkpoint identifier
     */
    public static void onCheckpoint(float x, float y, String checkpointId) {
        sendEvent(EVENT_CHECKPOINT, x, y,
            String.format("{\"checkpoint_id\":\"%s\"}", checkpointId));
    }
    
    /**
     * Track damage taken.
     * 
     * @param x Player X coordinate
     * @param y Player Y coordinate
     * @param damageAmount Amount of damage taken
     * @param source What caused the damage
     */
    public static void onDamageTaken(float x, float y, int damageAmount, String source) {
        sendEvent(EVENT_DAMAGE_TAKEN, x, y,
            String.format("{\"damage\":%d,\"source\":\"%s\"}", damageAmount, source));
    }
    
    // ========================================================================
    // CORE SENDING LOGIC
    // ========================================================================
    
    /**
     * Send a telemetry event to the Overseer.
     */
    private static void sendEvent(String eventType, float x, float y, String metaJson) {
        if (!initialized) {
            System.err.println("[Telemetry] Not initialized! Call initialize() first.");
            return;
        }
        
        String payload = String.format(
            "{\"session_id\":\"%s\",\"event_type\":\"%s\",\"x\":%.2f,\"y\":%.2f,\"meta\":%s}",
            sessionId, eventType, x, y, metaJson
        );
        
        sendAsync("/event", payload);
    }
    
    /**
     * Send data asynchronously (fire and forget).
     */
    private static void sendAsync(String endpoint, String jsonPayload) {
        if (executor == null || executor.isShutdown()) return;
        
        executor.submit(() -> sendSync(endpoint, jsonPayload));
    }
    
    /**
     * Send data synchronously (blocks until complete).
     */
    private static void sendSync(String endpoint, String jsonPayload) {
        HttpURLConnection conn = null;
        try {
            URL url = new URL(OVERSEER_HOST + endpoint);
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setDoOutput(true);
            conn.setConnectTimeout(TIMEOUT_MS);
            conn.setReadTimeout(TIMEOUT_MS);

            try (OutputStream os = conn.getOutputStream()) {
                byte[] input = jsonPayload.getBytes(StandardCharsets.UTF_8);
                os.write(input, 0, input.length);
            }

            int responseCode = conn.getResponseCode();
            if (responseCode != 200) {
                System.err.println("[Telemetry] Server returned: " + responseCode);
            }
        } catch (Exception e) {
            // Silently fail - don't crash the game over telemetry
            System.err.println("[Telemetry] Send failed: " + e.getMessage());
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }
    
    /**
     * Get the current session ID (for debugging).
     */
    public static String getSessionId() {
        return sessionId;
    }
    
    /**
     * Check if telemetry is active.
     */
    public static boolean isActive() {
        return initialized;
    }
}
