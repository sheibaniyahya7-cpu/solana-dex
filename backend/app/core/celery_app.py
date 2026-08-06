"""
Celery application factory.
Defines task queues, beat schedule, and routing for all background workers.
"""

from celery import Celery
from celery.schedules import crontab
from kombu import Queue, Exchange

from app.core.config import settings


def create_celery_app() -> Celery:
    app = Celery("dex_trader")

    # ─── Configuration ────────────────────────────────────────────────────────
    app.conf.update(
        broker_url=settings.CELERY_BROKER_URL,
        result_backend=settings.CELERY_RESULT_BACKEND,
        task_serializer=settings.CELERY_TASK_SERIALIZER,
        result_serializer=settings.CELERY_RESULT_SERIALIZER,
        accept_content=settings.CELERY_ACCEPT_CONTENT,
        timezone=settings.CELERY_TIMEZONE,
        enable_utc=True,
        task_track_started=settings.CELERY_TASK_TRACK_STARTED,
        task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
        task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
        worker_prefetch_multiplier=1,   # Fair distribution
        task_acks_late=True,            # Only ack after successful completion
        task_reject_on_worker_lost=True,
        result_expires=3600,
        broker_connection_retry_on_startup=True,
    )

    # ─── Task Queues ──────────────────────────────────────────────────────────
    default_exchange = Exchange("default", type="direct")

    app.conf.task_queues = (
        Queue("collectors", default_exchange, routing_key="collectors"),
        Queue("monitors", default_exchange, routing_key="monitors"),
        Queue("analyzers", default_exchange, routing_key="analyzers"),
        Queue("alerts", default_exchange, routing_key="alerts"),
        Queue("default", default_exchange, routing_key="default"),
    )
    app.conf.task_default_queue = "default"
    app.conf.task_default_exchange = "default"
    app.conf.task_default_routing_key = "default"

    # ─── Task Routing ─────────────────────────────────────────────────────────
    app.conf.task_routes = {
        "app.collectors.*": {"queue": "collectors"},
        "app.monitors.*": {"queue": "monitors"},
        "app.analyzers.*": {"queue": "analyzers"},
        "app.alerts.*": {"queue": "alerts"},
    }

    # ─── Beat Schedule (periodic tasks) ───────────────────────────────────────
    app.conf.beat_schedule = {
        # Data Collection
        "collect-new-tokens": {
            "task": "app.collectors.token_collector.collect_new_tokens",
            "schedule": settings.COLLECT_NEW_TOKENS_INTERVAL,
            "options": {"queue": "collectors"},
        },
        "collect-prices": {
            "task": "app.collectors.price_collector.collect_prices",
            "schedule": settings.COLLECT_PRICES_INTERVAL,
            "options": {"queue": "collectors"},
        },
        "collect-volumes": {
            "task": "app.collectors.volume_collector.collect_volumes",
            "schedule": settings.COLLECT_VOLUMES_INTERVAL,
            "options": {"queue": "collectors"},
        },
        "collect-transactions": {
            "task": "app.collectors.transaction_collector.collect_transactions",
            "schedule": settings.COLLECT_TRANSACTIONS_INTERVAL,
            "options": {"queue": "collectors"},
        },
        # Market Monitoring
        "monitor-market-events": {
            "task": "app.monitors.market_monitor.detect_market_events",
            "schedule": settings.MONITOR_EVENTS_INTERVAL,
            "options": {"queue": "monitors"},
        },
        "monitor-whale-activity": {
            "task": "app.monitors.whale_monitor.detect_whale_activity",
            "schedule": 60,
            "options": {"queue": "monitors"},
        },
        # Analysis
        "analyze-wallets": {
            "task": "app.analyzers.wallet_analyzer.analyze_active_wallets",
            "schedule": settings.COLLECT_WALLETS_INTERVAL,
            "options": {"queue": "analyzers"},
        },
        "run-ai-analysis": {
            "task": "app.ai_agents.orchestrator.run_analysis_cycle",
            "schedule": 300,   # Every 5 minutes
            "options": {"queue": "analyzers"},
        },
        # Alerts
        "process-alerts": {
            "task": "app.alerts.alert_processor.process_alerts",
            "schedule": 30,  # Every 30 seconds
            "options": {"queue": "alerts"},
        },
        # Cleanup
        "cleanup-old-data": {
            "task": "app.database.cleanup.cleanup_old_records",
            "schedule": crontab(hour=3, minute=0),  # Daily at 3 AM UTC
            "options": {"queue": "default"},
        },
    }

    # Auto-discover tasks from all app modules
    app.autodiscover_tasks(
        packages=[
            "app.collectors",
            "app.monitors",
            "app.analyzers",
            "app.ai_agents",
            "app.alerts",
            "app.database",
        ],
        related_name="tasks",
    )

    return app


# Module-level singleton
celery_app = create_celery_app()
