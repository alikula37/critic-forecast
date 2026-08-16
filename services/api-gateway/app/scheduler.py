import datetime as dt
import time

from app import jobs

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "LINK", "GLD", "SLV"]


def run():
    last_day = None
    last_week = None
    last_quality = None
    while True:
        now = dt.datetime.now(dt.timezone.utc)
        try:
            if last_day != now.date() and now.hour == 2 and now.minute < 15:
                last_day = now.date()
                print("[scheduler] günlük canlı tahmin kuyruğa alınıyor", flush=True)
                for sym in SYMBOLS:
                    jobs.enqueue(jobs.run_forecast, {"symbol": sym, "interval": "1d", "horizon": 30, "force": True}, timeout=7200)
            if last_week != now.date() and now.weekday() == 6 and now.hour == 3 and now.minute < 15:
                last_week = now.date()
                print("[scheduler] haftalık backfill uzatması kuyruğa alınıyor", flush=True)
                for sym in SYMBOLS:
                    jobs.enqueue(jobs.run_backfill, {"symbol": sym, "interval": "1d", "horizon": 30, "days": 30, "end_offset": 0, "skip_wf": True}, timeout=21600)
            if last_quality != now.date() and now.weekday() == 6 and now.hour == 4 and now.minute < 15:
                last_quality = now.date()
                print("[scheduler] haftalık tam kalite geçiş kuyruğa alınıyor", flush=True)
                for sym in SYMBOLS:
                    jobs.enqueue(jobs.run_backfill, {"symbol": sym, "interval": "1d", "horizon": 30, "days": 15, "end_offset": 0, "skip_wf": False}, timeout=21600)
        except Exception as e:
            print(f"[scheduler] hata: {e}", flush=True)
        time.sleep(60)


if __name__ == "__main__":
    run()
