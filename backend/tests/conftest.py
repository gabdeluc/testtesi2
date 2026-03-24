"""
conftest.py — Fixtures condivise per tutti i test.

Modifiche rispetto all'originale:
  • valid_meeting_ids → solo ["mtg001"] (1 meeting configurato nel YAML)
  • participant_ids   → mapping id→name allineato a mock_data.yaml
  • mock_meeting_data → schema Arianna (conversation_turn, participant_name, ecc.)
"""

import pytest
from fastapi.testclient import TestClient
from typing import Dict, List, Any


@pytest.fixture(scope="session")
def client():
    """TestClient FastAPI — creato una sola volta per sessione."""
    from main import app
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def mock_meeting_data() -> Dict[str, Any]:
    """Dati meeting di esempio — schema Arianna-compatibile."""
    return {
        "metadata": {
            "participants": [
                {"id": "fj93829", "name": "Alice"},
                {"id": "dkd9320", "name": "Bob"},
                {"id": "abc1234", "name": "Charlie"},
            ],
            "date": "2024-06-01T10:00:00Z",
        },
        "transcript": [
            {
                "conversation_turn": 1,
                "participant_name":  "Alice",
                "transcribed_text":  "This meeting was very productive!",
                "created_at":        "2024-06-01T10:00:00.000Z",
                "audio_duration_ms": 5000,
            },
            {
                "conversation_turn": 2,
                "participant_name":  "Bob",
                "transcribed_text":  "I disagree with this approach.",
                "created_at":        "2024-06-01T10:00:06.000Z",
                "audio_duration_ms": 4000,
            },
            {
                "conversation_turn": 3,
                "participant_name":  "Charlie",
                "transcribed_text":  "Let me share my screen.",
                "created_at":        "2024-06-01T10:00:11.000Z",
                "audio_duration_ms": 3000,
            },
        ],
    }


@pytest.fixture
def sample_texts() -> Dict[str, List[str]]:
    """Testi categorizzati per sentiment/toxicity."""
    return {
        "positive": [
            "This is amazing work!",
            "Great job everyone!",
            "I'm really impressed with the progress.",
            "Thank you for your help.",
            "Excellent presentation!",
        ],
        "neutral": [
            "Let me share my screen.",
            "Can everyone see the slides?",
            "We should schedule a follow-up.",
            "I'll send the document via email.",
            "The deadline is next week.",
        ],
        "negative": [
            "This is terrible and wrong.",
            "I disagree with this approach.",
            "I'm disappointed with the results.",
            "The data doesn't support this.",
            "This proposal has serious drawbacks.",
        ],
        "toxic": [
            "This is completely stupid.",
            "You're wasting everyone's time.",
            "You have no idea what you're doing.",
            "This is terrible and awful.",
            "Stop being so useless and incompetent.",
        ],
        "safe": [
            "Thank you for your time.",
            "Looking forward to the next meeting.",
            "Have a great day!",
            "Let's collaborate on this.",
            "I appreciate your input.",
        ],
    }


@pytest.fixture
def valid_meeting_ids() -> List[str]:
    """Unico meeting configurato in mock_data.yaml."""
    return ["mtg001"]


@pytest.fixture
def invalid_meeting_ids() -> List[str]:
    return ["mtg999", "FAKE123", "invalid"]


@pytest.fixture
def participant_ids() -> Dict[str, str]:
    """Mapping id→name allineato a mock_data.yaml."""
    return {
        "fj93829": "Alice",
        "dkd9320": "Bob",
        "abc1234": "Charlie",
    }


@pytest.fixture(autouse=True)
def reset_state():
    yield


def pytest_configure(config):
    config.addinivalue_line("markers", "smoke: Test smoke veloci per verifica base")


def pytest_collection_modifyitems(config, items):
    smoke  = [i for i in items if "smoke"  in i.keywords]
    others = [i for i in items if "smoke" not in i.keywords]
    items[:] = smoke + others