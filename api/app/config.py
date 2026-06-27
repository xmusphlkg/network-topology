from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Switch Topology"
    environment: Literal["dev", "prod", "test"] = "prod"
    public_base_url: str = "http://192.168.3.222"

    database_url: str | None = None
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "dashboard"
    mysql_password: str | None = None
    mysql_database: str = "dashboard"
    mysql_connect_timeout_sec: int = 10
    db_echo: bool = False
    auto_create_tables: bool = True
    read_only_mode: bool = False
    admin_token: str | None = None

    zabbix_url: str = "http://127.0.0.1:8080"
    zabbix_token: str | None = None
    zabbix_user: str | None = None
    zabbix_password: str | None = None
    zabbix_auth_mode: Literal["bearer", "auth", "auto"] = "bearer"
    zabbix_logout_on_shutdown: bool = True
    zabbix_timeout_sec: float = 10.0
    zabbix_concurrency: int = 4

    sync_interval_sec: int = 60
    auto_sync_enabled: bool = True
    switch_group_terms: str = "exchange,switch,交换机"
    server_group_terms: str = "Negev"
    zabbix_host_limit: int = 0

    @field_validator("public_base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("zabbix_url")
    @classmethod
    def normalize_zabbix_url(cls, value: str) -> str:
        stripped = value.rstrip("/")
        if not stripped or stripped.endswith("/api_jsonrpc.php"):
            return stripped
        return f"{stripped}/api_jsonrpc.php"

    @field_validator("zabbix_auth_mode", mode="before")
    @classmethod
    def normalize_zabbix_auth_mode(cls, value: str | None) -> str:
        return str(value or "bearer").strip().lower()

    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        password = self.mysql_password or ""
        return (
            f"mysql+aiomysql://{self.mysql_user}:{password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )

    def switch_terms(self) -> list[str]:
        return split_terms(self.switch_group_terms)

    def server_terms(self) -> list[str]:
        return split_terms(self.server_group_terms)

    def zabbix_configured(self) -> bool:
        return bool(self.zabbix_token or (self.zabbix_user and self.zabbix_password))


def split_terms(value: str) -> list[str]:
    return [item.strip().lower() for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
