"""Run once a day from cron or a scheduler: python -m app.alerts"""
from app.main import run_alerts
print(run_alerts(), "alerts created")
