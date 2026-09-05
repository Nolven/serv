A simple script to update ip on **duckdns** ddns.
***
Better to know:
- Suitable for servers behind a router. It uses reponse from https://api.ipify.org to retrieve servers public ipv4
- On POSIX systems uses journald for logging
- GET with params is used (instead of `duck/update/token/ipv4...`)
- The code is bad but simple
***
Dependencies:
- import time
- import requests
- import logging
- import os
- from systemd.journal import JournalHandler