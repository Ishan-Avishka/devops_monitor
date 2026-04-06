import database


def test_alert_engine_generates_alert_and_notifies(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "APP_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "devops.db")
    monkeypatch.setattr(database, "SECRET_KEY_PATH", tmp_path / "secret.key")

    database.init_db()

    import alerts

    alerts.AlertEngine._instance = None
    engine = alerts.AlertEngine()

    seen = []
    engine.register_observer(lambda alert: seen.append(alert))

    engine.check("localhost", "cpu_percent", 96.0)

    persisted = database.get_alerts(limit=20, acknowledged=False)
    assert len(seen) >= 1
    assert len(persisted) >= 1
    assert any(a["metric"] == "cpu_percent" for a in persisted)
