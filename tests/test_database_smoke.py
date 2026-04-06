import hashlib

import database


def test_init_and_default_admin_login(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "APP_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "devops.db")
    monkeypatch.setattr(database, "SECRET_KEY_PATH", tmp_path / "secret.key")

    database.init_db()
    user, err = database.authenticate_user("admin", "admin123")

    assert err is None
    assert user is not None
    assert user["username"] == "admin"


def test_legacy_sha256_migrates_to_bcrypt(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "APP_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "devops.db")
    monkeypatch.setattr(database, "SECRET_KEY_PATH", tmp_path / "secret.key")

    database.init_db()
    legacy_hash = hashlib.sha256("legacy-pass".encode("utf-8")).hexdigest()

    conn = database._get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password, role, created) VALUES (?, ?, ?, ?)",
        ("legacy", legacy_hash, "viewer", "2026-01-01T00:00:00"),
    )
    conn.commit()
    cur.close()
    conn.close()

    user, err = database.authenticate_user("legacy", "legacy-pass")
    assert err is None
    assert user is not None

    conn = database._get_conn()
    cur = conn.cursor()
    cur.execute("SELECT password FROM users WHERE username=?", ("legacy",))
    row = cur.fetchone()
    cur.close()
    conn.close()

    assert row is not None
    assert not database._is_legacy_sha256(row["password"])


def test_lockout_after_failed_attempts(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "APP_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "devops.db")
    monkeypatch.setattr(database, "SECRET_KEY_PATH", tmp_path / "secret.key")

    database.init_db()

    for _ in range(database.LOCKOUT_THRESHOLD):
        user, err = database.authenticate_user("admin", "wrong-password")
        assert user is None
        assert err is not None

    user, err = database.authenticate_user("admin", "admin123")
    assert user is None
    assert err is not None
    assert "locked" in err.lower()


def test_server_secrets_are_encrypted_at_rest(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "APP_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "devops.db")
    monkeypatch.setattr(database, "SECRET_KEY_PATH", tmp_path / "secret.key")

    database.init_db()
    database.add_server(
        name="srv-1",
        host="127.0.0.1",
        port=22,
        username="tester",
        password="super-secret",
        key_path="/tmp/id_rsa",
        tags="test",
    )

    conn = database._get_conn()
    cur = conn.cursor()
    cur.execute("SELECT password, key_path FROM servers WHERE name='srv-1'")
    row = cur.fetchone()
    cur.close()
    conn.close()

    assert row is not None
    assert row["password"].startswith("enc:")
    assert row["key_path"].startswith("enc:")

    server = database.get_servers()[0]
    assert server["password"] == "super-secret"
    assert server["key_path"] == "/tmp/id_rsa"
