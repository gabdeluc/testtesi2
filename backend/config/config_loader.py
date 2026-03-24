import yaml
import json
from pathlib import Path
from typing import List, Dict, Any


class ConfigLoader:
    """Carica configurazioni da file YAML/JSON."""

    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(__file__).parent
        self._config = None

    def load_yaml(self, filename: str = "mock_data.yaml") -> Dict[str, Any]:
        filepath = self.config_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Config file not found: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def load_json(self, filename: str) -> Dict[str, Any]:
        filepath = self.config_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Config file not found: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_config(self) -> Dict[str, Any]:
        if self._config is None:
            self._config = self.load_yaml()
        return self._config

    def get_sample_phrases(self) -> List[str]:
        return self.get_config().get("sample_phrases", [])

    def get_participants(self) -> List[Dict[str, str]]:
        return self.get_config().get("participants", [])

    def get_meetings(self) -> List[Dict[str, Any]]:
        return self.get_config().get("meetings", [])

    def get_generation_config(self) -> Dict[str, int]:
        return self.get_config().get("generation", {
            "min_duration_seconds": 3,
            "max_pause_seconds":    3,
            "chars_per_second":     15,
        })

    def get_generation_overrides(self) -> Dict[str, Dict[str, int]]:
        """Override di generazione per singolo meeting (keyed by meeting_id)."""
        return self.get_config().get("generation_overrides", {})


config_loader = ConfigLoader()