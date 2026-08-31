import yaml

from utils import info
import config

class Site:
    port = 1
    prefix = "x"
 # gradually filled during component setup
 # allows component setup in arbitrary order
sites = []

if __name__ == "__main__":
    # check for the active components
    info(f"reading config {config.CONFIG}")
    with open("./config.yaml") as f:
        cfg : dict = yaml.safe_load(f)
        print(yaml.dump(cfg))
        # for key, value in cfg["components"].items():
        #     pass

