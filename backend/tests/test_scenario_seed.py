from sqlalchemy import select

from app.models import Scenario
from app.services.scenario_seed import seed_scenarios


def test_seed_scenarios_creates_all(session):
    created = seed_scenarios(session)

    ids = {s.id for s in created}
    assert ids == {"it_procurement", "salary", "supplier"}


def test_seed_scenarios_is_idempotent(session):
    seed_scenarios(session)
    session.commit()

    second = seed_scenarios(session)
    session.commit()

    assert second == []
    rows = session.scalars(select(Scenario)).all()
    assert len(rows) == 3


def test_seed_scenarios_config_matches_json(session):
    seed_scenarios(session)
    session.commit()

    row = session.scalar(
        select(Scenario).where(Scenario.id == "it_procurement")
    )
    assert row.title == "IT 采购谈判"
    assert row.domain.value == "it_procurement"
    assert row.config_json["opening_line"]  # 完整 JSON 配置入库
    assert row.price is None
    assert row.is_free is True
