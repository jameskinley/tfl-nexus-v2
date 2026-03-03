import pytest
import importlib
from unittest.mock import patch, MagicMock


class TestDatabaseUrlDefault:
    def test_sqlite_used_when_no_db_env_vars_set(self):
        import data.database as db_module

        assert "sqlite" in db_module.DATABASE_URL.lower()


class TestDatabaseUrlConstruction:
    def test_database_url_env_var_used_verbatim(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host/db")
        monkeypatch.delenv("DB_HOST", raising=False)
        monkeypatch.delenv("DB_USER", raising=False)
        monkeypatch.delenv("DB_NAME", raising=False)

        with patch("sqlalchemy.create_engine", return_value=MagicMock()) as mock_ce, \
             patch("sqlalchemy.orm.sessionmaker", return_value=MagicMock()):
            import data.database as db_module
            importlib.reload(db_module)
            url_used = mock_ce.call_args[0][0]

        assert url_used == "postgresql+psycopg://u:p@host/db"

    def test_individual_vars_build_postgres_url(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("DB_USER", "pguser")
        monkeypatch.setenv("DB_PASSWORD", "pgpass")
        monkeypatch.setenv("DB_HOST", "db.example.com")
        monkeypatch.setenv("DB_PORT", "5432")
        monkeypatch.setenv("DB_NAME", "mydb")

        with patch("sqlalchemy.create_engine", return_value=MagicMock()) as mock_ce, \
             patch("sqlalchemy.orm.sessionmaker", return_value=MagicMock()):
            import data.database as db_module
            importlib.reload(db_module)
            url_used = mock_ce.call_args[0][0]

        assert "pguser" in url_used
        assert "db.example.com" in url_used
        assert "mydb" in url_used
        assert "postgresql" in url_used

    def test_no_env_vars_falls_back_to_sqlite(self, monkeypatch):
        for var in ["DATABASE_URL", "DB_USER", "DB_HOST", "DB_NAME", "DB_PASSWORD", "DB_PORT"]:
            monkeypatch.delenv(var, raising=False)

        with patch("sqlalchemy.create_engine", return_value=MagicMock()) as mock_ce, \
             patch("sqlalchemy.orm.sessionmaker", return_value=MagicMock()):
            import data.database as db_module
            importlib.reload(db_module)
            url_used = mock_ce.call_args[0][0]

        assert "sqlite" in url_used.lower()

    def test_cleanup_restores_sqlite_module(self, monkeypatch):
        import data.database as db_module
        importlib.reload(db_module)

        assert "sqlite" in db_module.DATABASE_URL.lower()


class TestGetDbSession:
    def test_session_closed_after_normal_use(self):
        mock_session = MagicMock()

        with patch("data.database.SessionLocal", return_value=mock_session):
            from data.database import get_db_session
            with get_db_session():
                pass

        mock_session.close.assert_called_once()

    def test_rollback_called_when_exception_raised(self):
        mock_session = MagicMock()

        with patch("data.database.SessionLocal", return_value=mock_session):
            from data.database import get_db_session
            with pytest.raises(ValueError):
                with get_db_session():
                    raise ValueError("test error")

        mock_session.rollback.assert_called_once()

    def test_exception_re_raised_after_rollback(self):
        mock_session = MagicMock()

        with patch("data.database.SessionLocal", return_value=mock_session):
            from data.database import get_db_session
            with pytest.raises(ValueError, match="propagated"):
                with get_db_session():
                    raise ValueError("propagated")

    def test_session_closed_even_after_exception(self):
        mock_session = MagicMock()

        with patch("data.database.SessionLocal", return_value=mock_session):
            from data.database import get_db_session
            with pytest.raises(RuntimeError):
                with get_db_session():
                    raise RuntimeError("error")

        mock_session.close.assert_called_once()
