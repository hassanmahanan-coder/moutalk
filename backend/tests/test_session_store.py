import uuid

import pytest
from sqlalchemy import select

from app.models import NegotiationSession, SessionStatus
from app.services.session_store import (
    SessionNotFoundError,
    create_session,
    end_session,
    get_session_state,
    save_round,
)


def test_create_session(session, user, scenario):
    ns = create_session(session, user.id, scenario.id)
    session.commit()

    assert ns.id is not None
    assert isinstance(ns.id, uuid.UUID)
    assert ns.user_id == user.id
    assert ns.scenario_id == scenario.id
    assert ns.status == SessionStatus.ACTIVE
    assert ns.messages_json == []
    assert ns.offers_json == []


def test_create_session_requires_existing_user(session, scenario):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        create_session(session, uuid.uuid4(), scenario.id)
        session.commit()


def test_save_round_appends_messages_and_offers(session, user, scenario):
    ns = create_session(session, user.id, scenario.id)

    state = {
        "history": [{"role": "user", "content": "太贵了"}, {"role": "assistant", "content": "可以谈"}],
        "offers_json": [{"round": 1, "price": 200}],
        "last_offer": {"round": 1, "price": 200},
        "simple_result": None,
    }
    save_round(session, ns.id, state)
    session.commit()

    fetched = session.scalar(
        select(NegotiationSession).where(NegotiationSession.id == ns.id)
    )
    assert len(fetched.messages_json) == 2
    assert fetched.messages_json[0]["content"] == "太贵了"
    assert fetched.offers_json[0]["price"] == 200


def test_save_round_overwrites_previous_round(session, user, scenario):
    ns = create_session(session, user.id, scenario.id)
    save_round(session, ns.id, {"history": [{"role": "user", "content": "第一轮"}]})
    session.commit()

    save_round(session, ns.id, {"history": [{"role": "user", "content": "第二轮"}]})
    session.commit()

    fetched = session.scalar(
        select(NegotiationSession).where(NegotiationSession.id == ns.id)
    )
    assert [m["content"] for m in fetched.messages_json] == ["第二轮"]


def test_save_round_unknown_session_raises(session, user, scenario):
    with pytest.raises(SessionNotFoundError):
        save_round(session, uuid.uuid4(), {"history": []})


def test_end_session_sets_status_and_ended_at(session, user, scenario):
    ns = create_session(session, user.id, scenario.id)
    session.commit()

    end_session(session, ns.id, simple_result={"score": 80, "won": True})
    session.commit()

    fetched = session.scalar(
        select(NegotiationSession).where(NegotiationSession.id == ns.id)
    )
    assert fetched.status == SessionStatus.ENDED
    assert fetched.ended_at is not None
    assert fetched.simple_result == {"score": 80, "won": True}


def test_end_session_unknown_raises(session, user, scenario):
    with pytest.raises(SessionNotFoundError):
        end_session(session, uuid.uuid4())


def test_get_session_state_restores_engine_input(session, user, scenario):
    ns = create_session(session, user.id, scenario.id)
    save_round(
        session,
        ns.id,
        {
            "history": [{"role": "user", "content": "hi"}],
            "offers_json": [{"round": 1, "price": 100}],
            "last_offer": {"round": 1, "price": 100},
        },
    )
    session.commit()

    state = get_session_state(session, ns.id)
    assert state["session_id"] == str(ns.id)
    assert state["scenario_id"] == scenario.id
    assert state["scenario"] is not None
    assert state["history"] == [{"role": "user", "content": "hi"}]
    assert state["offers_json"] == [{"round": 1, "price": 100}]
    assert state["last_offer"] == {"round": 1, "price": 100}


def test_get_session_state_unknown_raises(session, user, scenario):
    with pytest.raises(SessionNotFoundError):
        get_session_state(session, uuid.uuid4())


def test_list_sessions_by_user(session, user, scenario):
    s1 = create_session(session, user.id, scenario.id)
    s2 = create_session(session, user.id, scenario.id)
    session.commit()

    from app.services.session_store import list_sessions

    rows = list_sessions(session, user.id)
    ids = {str(r["id"]) for r in rows}
    assert ids == {str(s1.id), str(s2.id)}
    assert rows[0]["scenario_id"] == scenario.id
