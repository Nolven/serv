import yaml

from utils import info
from pathlib import Path

import frigate

ROOT = Path(__file__).resolve().parents[2]

with open(ROOT / "config.yaml", "r") as file:
    data = yaml.safe_load(file)
    info(f'Initial config:\n {yaml.safe_dump(data, sort_keys=False)}')

    if "frigate" in data:
        info("Frigate found")
        frigate.configure()
