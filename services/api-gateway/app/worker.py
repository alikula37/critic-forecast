import redis
from rq import Queue, Worker

from app import config
from app import jobs

if __name__ == "__main__":
    conn = redis.Redis.from_url(config.REDIS_URL)
    q = Queue("forecast-jobs", connection=conn)
    worker = Worker([q], connection=conn)
    worker.work()
