"""部署资产守卫（PRD 9.19/9.20/故事 8）：Caddy/生产 compose/备份脚本/协议页存在性。

职责：防止部署关键文件被误删或退化（terms/HTTPS/backup 无行为测试，靠存在性守卫）。
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # 项目根目录


def test_caddyfile_has_reverse_proxy_and_ws():
    caddy = ROOT / "deploy" / "Caddyfile"
    assert caddy.is_file(), "Caddyfile 缺失（PRD 9.19 HTTPS）"
    text = caddy.read_text(encoding="utf-8")
    assert "reverse_proxy" in text
    assert "/api/negotiation/" in text, "Caddyfile 应反代 WebSocket 端点（Caddy 自动处理 Upgrade）"


def test_prod_compose_has_full_stack():
    compose = ROOT / "docker-compose.prod.yml"
    assert compose.is_file(), "docker-compose.prod.yml 缺失"
    text = compose.read_text(encoding="utf-8")
    for service in ("caddy:", "fastapi:", "celery_worker:", "milvus-standalone:"):
        assert f"  {service}" in text, f"生产 compose 应含 {service} 服务"


def test_backup_script_exists_and_uses_pg_dump():
    script = ROOT / "scripts" / "backup.sh"
    assert script.is_file(), "backup.sh 缺失（PRD 9.20）"
    text = script.read_text(encoding="utf-8")
    assert "pg_dump" in text, "备份脚本应基于 pg_dump"


def test_prod_env_example_has_required_keys():
    example = ROOT / ".env.prod.example"
    assert example.is_file(), ".env.prod.example 缺失"
    text = example.read_text(encoding="utf-8")
    for key in ("POSTGRES_USER", "LLM_API_KEY", "ALIPAY_APP_ID", "LANGFUSE_SECRET_KEY"):
        assert key in text, f".env.prod.example 应含 {key} 配置"


def test_terms_views_exist():
    terms = ROOT / "frontend" / "src" / "views" / "TermsView.vue"
    assert terms.is_file(), "TermsView.vue 缺失（故事 8 协议/隐私）"
