from __future__ import annotations

from app.config import Settings


def test_zabbix_url_accepts_site_root():
    settings = Settings(zabbix_url="http://192.168.3.222:8080")

    assert settings.zabbix_url == "http://192.168.3.222:8080/api_jsonrpc.php"


def test_zabbix_url_keeps_jsonrpc_endpoint():
    settings = Settings(zabbix_url="http://192.168.3.222:8080/api_jsonrpc.php")

    assert settings.zabbix_url == "http://192.168.3.222:8080/api_jsonrpc.php"
