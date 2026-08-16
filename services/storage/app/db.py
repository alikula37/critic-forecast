import os
import threading

import duckdb

DATA_DIR = os.getenv("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "critic.duckdb")

_lock = threading.Lock()
_conn = None


def get_conn() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                os.makedirs(DATA_DIR, exist_ok=True)
                _conn = duckdb.connect(DB_PATH)
                _conn.execute("INSTALL json; LOAD json;")
                _init_schema(_conn)
    return _conn


def _init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ohlcv (
            symbol VARCHAR NOT NULL, ts TIMESTAMP NOT NULL,
            interval VARCHAR NOT NULL,
            open DOUBLE NOT NULL, high DOUBLE NOT NULL,
            low DOUBLE NOT NULL, close DOUBLE NOT NULL,
            volume DOUBLE NOT NULL,
            PRIMARY KEY (symbol, ts, interval)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ensemble_forecasts (
            job_id VARCHAR NOT NULL, symbol VARCHAR NOT NULL,
            interval VARCHAR NOT NULL, horizon INTEGER NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            up_probability DOUBLE, points JSON, critic JSON,
            PRIMARY KEY (job_id)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS forecast_points (
            job_id VARCHAR NOT NULL, model_id VARCHAR NOT NULL,
            ts TIMESTAMP NOT NULL,
            p10 DOUBLE, p50 DOUBLE, p90 DOUBLE
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS model_scores (
            symbol VARCHAR NOT NULL, model_id VARCHAR NOT NULL,
            as_of TIMESTAMP NOT NULL DEFAULT current_timestamp,
            score DOUBLE, weight DOUBLE, metrics JSON
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS backtests (
            job_id VARCHAR NOT NULL, symbol VARCHAR NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            summary JSON
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS results (
            job_id VARCHAR NOT NULL,
            symbol VARCHAR NOT NULL,
            interval VARCHAR NOT NULL,
            horizon INTEGER NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            payload JSON,
            PRIMARY KEY (job_id)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS strategy_backtests (
            job_id VARCHAR NOT NULL,
            symbol VARCHAR NOT NULL,
            interval VARCHAR NOT NULL,
            strategy_id VARCHAR NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            params JSON,
            metrics JSON,
            equity JSON,
            trades JSON,
            benchmark JSON,
            PRIMARY KEY (job_id)
        );
        """
    )
    try:
        conn.execute("ALTER TABLE strategy_backtests ADD COLUMN IF NOT EXISTS benchmark JSON")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE ensemble_forecasts ADD COLUMN IF NOT EXISTS last_close DOUBLE")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE ensemble_forecasts ADD COLUMN IF NOT EXISTS backfilled BOOLEAN DEFAULT FALSE")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE results ADD COLUMN IF NOT EXISTS backfilled BOOLEAN DEFAULT FALSE")
    except Exception:
        pass
