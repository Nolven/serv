from pathlib import Path

import yaml
from utils import info

ROOT = Path(__file__).resolve().parents[2]

# assume all the fields are there
def configure(config: dict, general: dict) -> dict:
    with open(ROOT / "components" / "frigate" / "compose.yaml", "r") as f:
        data = yaml.safe_load(f)
        info(f'Initial docker-compose:\n{yaml.safe_dump(data, sort_keys=False)}')

    return
