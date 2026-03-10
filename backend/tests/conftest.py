"""
conftest.py - Fixtures Condivise per Test

Fixtures disponibili:
- client: TestClient FastAPI
- mock_meeting_data: Dati meeting di esempio
- sample_texts: Testi per test sentiment/toxicity
"""

import pytest
from fastapi.testclient import TestClient
from typing import Dict, List, Any


@pytest.fixture(scope="session")
def client():
    """
    Fixture session-scoped per TestClient FastAPI.
    
    Creata UNA VOLTA per tutta la sessione test.
    Risparmia tempo evitando di ricreare il client ogni volta.
    
    Yields:
        TestClient: Client per fare richieste HTTP
    """
    from main import app
    
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def mock_meeting_data() -> Dict[str, Any]:
    """
    Dati meeting di esempio per test.
    
    Returns:
        Dict con struttura meeting completa
    """
    return {
        "metadata": {
            "participants": [
                {"id": "fj93829", "name": "Alice"},
                {"id": "dkd9320", "name": "Bob"},
                {"id": "abc1234", "name": "Charlie"}
            ],
            "date": "2024-06-01T10:00:00Z"
        },
        "transcript": [
            {
                "uid": "12345",
                "nickname": "Alice",
                "text": "This meeting was very productive!",
                "from": "00:00:00.000",
                "to": "00:00:05.000"
            },
            {
                "uid": "12346",
                "nickname": "Bob",
                "text": "I disagree with this approach.",
                "from": "00:00:05.000",
                "to": "00:00:10.000"
            },
            {
                "uid": "12347",
                "nickname": "Charlie",
                "text": "Let me share my screen.",
                "from": "00:00:10.000",
                "to": "00:00:15.000"
            }
        ]
    }


@pytest.fixture
def sample_texts() -> Dict[str, List[str]]:
    """
    Testi di esempio categorizzati per tipo.
    
    Utile per testare sentiment/toxicity con diversi scenari.
    
    Returns:
        Dict con categorie di testi
    """
    return {
        "positive": [
            "This is amazing work!",
            "Great job everyone!",
            "I'm really impressed with the progress.",
            "Thank you for your help.",
            "Excellent presentation!"
        ],
        "neutral": [
            "Let me share my screen.",
            "Can everyone see the slides?",
            "We should schedule a follow-up.",
            "I'll send the document via email.",
            "The deadline is next week."
        ],
        "negative": [
            "I don't agree with this approach.",
            "This is not what I expected.",
            "I'm concerned about the timeline.",
            "The data doesn't support this.",
            "This proposal has some drawbacks."
        ],
        "toxic": [
            "This is completely stupid.",
            "You're wasting everyone's time.",
            "You have no idea what you're doing.",
            "This is terrible work.",
            "Stop being so incompetent."
        ],
        "safe": [
            "Thank you for your time.",
            "Looking forward to the next meeting.",
            "Have a great day!",
            "Let's collaborate on this.",
            "I appreciate your input."
        ]
    }


@pytest.fixture
def valid_meeting_ids() -> List[str]:
    """
    IDs meeting validi per test.
    
    Returns:
        Lista di meeting IDs esistenti
    """
    return ["mtg001", "mtg002", "mtg003"]


@pytest.fixture
def invalid_meeting_ids() -> List[str]:
    """
    IDs meeting invalidi per test errori.
    
    Returns:
        Lista di meeting IDs NON esistenti
    """
    return ["mtg999", "FAKE123", "invalid", ""]


@pytest.fixture
def participant_ids() -> Dict[str, str]:
    """
    Mapping participant IDs per filtri.
    
    Returns:
        Dict con id -> name mapping
    """
    return {
        "fj93829": "Alice",
        "dkd9320": "Bob",
        "abc1234": "Charlie"
    }


@pytest.fixture(autouse=True)
def reset_state():
    """
    Fixture auto-use che resetta lo stato prima di ogni test.
    
    Garantisce che ogni test parta da stato pulito.
    """
    # Setup (eseguito PRIMA del test)
    yield
    # Teardown (eseguito DOPO il test)
    pass


# Hook per personalizzare output test
def pytest_configure(config):
    """Configurazione pytest personalizzata"""
    config.addinivalue_line(
        "markers",
        "smoke: Test smoke veloci per verifica base"
    )


def pytest_collection_modifyitems(config, items):
    """
    Modifica ordine esecuzione test.
    
    Esegue prima i test marcati come 'smoke' (veloci).
    """
    smoke_tests = []
    other_tests = []
    
    for item in items:
        if "smoke" in item.keywords:
            smoke_tests.append(item)
        else:
            other_tests.append(item)
    
    items[:] = smoke_tests + other_tests