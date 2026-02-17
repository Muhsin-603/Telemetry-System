import java.net.HttpURLConnection;
import java.net.URL;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class TelemetryClient {
    private static final String OVERSEER_URL = "http://localhost:8080/ingest";

    public static void sendEvent(String jsonPayload) {
        new Thread(() -> {
            try {
                URL url = new URL(OVERSEER_URL);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setDoOutput(true);
                conn.setConnectTimeout(1000); // Fail fast
                conn.setReadTimeout(1000);

                try (OutputStream os = conn.getOutputStream()) {
                    byte[] input = jsonPayload.getBytes(StandardCharsets.UTF_8);
                    os.write(input, 0, input.length);
                }

                int responseCode = conn.getResponseCode();
                // We don't really care about the response, fire and forget.
            } catch (Exception e) {
                // Silently fail, don't crash the game
                System.err.println("Telemetry failed to send: " + e.getMessage());
            }
        }).start();
    }
}
