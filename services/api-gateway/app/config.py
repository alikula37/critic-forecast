import os

STORAGE_URL = os.getenv("STORAGE_URL", "http://storage:9000")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DEEP_LEARNING_URL = os.getenv("DEEP_LEARNING_URL", "http://deep-learning-engine:9001")
QUANT_URL = os.getenv("QUANT_URL", "http://quant-engine:9002")

CRITIC_TEMPERATURE = float(os.getenv("CRITIC_TEMPERATURE", "1.0"))
DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "BTC")
DEFAULT_INTERVAL = os.getenv("DEFAULT_INTERVAL", "1d")
DEFAULT_HORIZON = int(os.getenv("DEFAULT_HORIZON", "30"))

MAX_BARS = 3000
TRAIN_BARS = 1500
MIN_BARS = 260
BACKFILL_DAYS = 60
LIVE_DECAY = 0.85
LIVE_WEIGHT = 0.6
BACKTEST_WEIGHT = 0.4
