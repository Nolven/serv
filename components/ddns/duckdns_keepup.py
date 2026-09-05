import time
import requests
import logging
import os

log = logging.getLogger('DDNS')
log.setLevel(logging.INFO)

try:
    from systemd.journal import JournalHandler
    log.addHandler(JournalHandler())
except ImportError as e:
    log.addHandler(logging.StreamHandler())
    log.error(e.msg)

current_ip = "127.0.0.1"

# consts
ddns_poll_timeout = 3600
ddns_retry_num = 5
some_url = 'https://api.ipify.org' # used to get the public api

# ddns configs
# better to put into .service file, buh m lazy
domain = "domain"
token = "token"

def updateDDNS(ip, verbose = True, clear = False):
    return requests.get("https://www.duckdns.org/update", {
        "domains": domain,
        "token": token,
        "verbose": "True" if verbose else "False",
        "clear": "True" if clear else "False"
    }).text

if __name__ == "__main__":
    while True:
        # do not sleep initially
        if not current_ip == "127.0.0.1": time.sleep(ddns_poll_timeout)
        ip = requests.get(some_url).content.decode('utf8')
        if ip != current_ip:
            log.warning(f"ip changed {current_ip} to {ip}")
            for n in range(ddns_retry_num):
                response = updateDDNS(ip)
                if response.startswith("OK"): break
                log.error(f"{n} ddns update FAILED {response}")
            if response.startswith("OK"):
                log.info("DDNS updated")
                current_ip = ip
