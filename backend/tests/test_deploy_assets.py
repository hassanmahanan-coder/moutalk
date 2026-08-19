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
    assert "--restore" in text, "备份脚本应支持恢复演练模式"
    assert "psql" in text, "恢复模式应使用 psql"


def test_backup_readme_has_recovery_drill():
    readme = ROOT / "deploy" / "backup-README.md"
    assert readme.is_file(), "backup-README.md 缺失"
    text = readme.read_text(encoding="utf-8")
    assert "恢复演练" in text, "README 应含恢复演练流程（PRD 9.20 流程项）"
    assert "--restore" in text


def test_prod_env_example_has_required_keys():
    example = ROOT / ".env.prod.example"
    assert example.is_file(), ".env.prod.example 缺失"
    text = example.read_text(encoding="utf-8")
    for key in ("POSTGRES_USER", "LLM_API_KEY", "ALIPAY_APP_ID", "LANGFUSE_SECRET_KEY"):
        assert key in text, f".env.prod.example 应含 {key} 配置"


def test_terms_views_exist():
    terms = ROOT / "frontend" / "src" / "views" / "TermsView.vue"
    assert terms.is_file(), "TermsView.vue 缺失（故事 8 协议/隐私）"


def test_llm_smoke_script_exists():
    script = ROOT / "backend" / "scripts" / "llm_smoke.py"
    assert script.is_file(), "llm_smoke.py 缺失（CI 真实网关验证）"
    text = script.read_text(encoding="utf-8")
    assert "OpenAIClient" in text
    assert "astream" in text, "smoke 应覆盖真流式链路"


def test_ci_has_llm_smoke_step():
    ci = ROOT / ".github" / "workflows" / "ci.yml"
    assert ci.is_file()
    text = ci.read_text(encoding="utf-8")
    assert "llm_smoke.py" in text, "CI 应含 LLM smoke 步骤（有密钥时）"
