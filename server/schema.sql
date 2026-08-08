CREATE TABLE IF NOT EXISTS readings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id TEXT NOT NULL,
  session_id TEXT,
  t INTEGER NOT NULL,          -- Unix epoch ms (送信側の時刻)
  sensor TEXT NOT NULL,        -- accel | gyro | orientation | gps | mic
  v1 REAL, v2 REAL, v3 REAL, v4 REAL, v5 REAL,
  received_at INTEGER NOT NULL DEFAULT (unixepoch() * 1000)
);
CREATE INDEX IF NOT EXISTS idx_readings_device_t ON readings (device_id, t);
CREATE INDEX IF NOT EXISTS idx_readings_session ON readings (session_id);
