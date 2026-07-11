import os
import configparser
from pathlib import Path

DEFAULT_BLACKLIST = []

DEFAULT_CONFIG = {
    "is_host": "False",
    "cooldown": "0.03",
    "friend_ip": "127.0.0.1",
    "ws_port": "38955",
    "secretpassword": "a1very5long2password77with8some8words8andnumbers764138catsareawesome",
    "blacklist": "",
    "blacklist_sending": "",
    "blacklist_receiving": "",
    "whitelist": "",
    "printlog": "False",
    "ping_compensation": "1.5"
}


# Remove the # at the start of the next line to enable the syncing feature.
#Enable_Syncing = True

CONFIG_DEFAULT_TEXT = """
# =============================
# VRChat OSC Sync Configuration
# =============================

[settings]
# Set this to True if this computer is the host.
# The host must port forward the desired port, 38955 by default.
is_host = False

# If you are not the host, enter the host's IP address here.
friend_ip = 127.0.0.1

# You can choose a custom port. Make sure everyone is using the same port.
ws_port = 38955

# As a security measure you can have a custom password. Only use letters and numbers (no spaces or special characters).
secretpassword = yourpasswordhere

# Optional: Increase this value if your connection feels delayed.
# Higher values compensate for network latency but may make syncing feel less responsive.
#ping_compensation = 1.5

# If you would like to prevent certain parameters from being synced, add them to the blacklist.
# Separate multiple parameters with commas.
# Example: GestureLeft, GestureRight, VelocityX
blacklist = 

# Prevent these parameters from being sent to other users.
blacklist_sending = 

# Prevent these parameters from being received from other users.
blacklist_receiving = 

# Alternatively, you can use a whitelist.
# When a whitelist is set, only parameters listed here will be synced.
whitelist = 
"""


class Config:
    def __init__(self):
        debug_file = Path("debugconfig.ini")
        self.config_file = debug_file if debug_file.exists() else Path("config.ini")

        self.create_config()

        parser = configparser.ConfigParser()
        parser.read_dict({"settings": DEFAULT_CONFIG})


        if self.config_file.exists():
            parser.read(str(self.config_file))

        settings = parser["settings"]

        self.COOLDOWN = float(settings["cooldown"])
        self.WS_PORT = int(settings["ws_port"])
        self.URI = f'ws://{settings["friend_ip"]}:{self.WS_PORT}'
        self.SECRET_PASSWORD = settings["secretpassword"]

        self.PRINT_LOG = settings.getboolean("printlog")
        self.ACTIVITY_TIMEOUT = float(settings["ping_compensation"])
        self.IS_HOST = settings.getboolean("is_host")

        self.BLACKLIST = []
        self.blacklist_sending = []
        self.blacklist_receiving = []
        self.whitelist = []
        self.BLACKLIST = DEFAULT_BLACKLIST + [
            x.strip()
            for x in settings["blacklist"].split(",")
            if x.strip()
        ]

        self.blacklist_sending = (
            DEFAULT_BLACKLIST + [
                x.strip()
                for x in settings["blacklist_sending"].split(",")
                if x.strip()
            ]
            if settings["blacklist_sending"].strip()
            else self.BLACKLIST
        )

        self.blacklist_receiving = (
            DEFAULT_BLACKLIST + [
                x.strip()
                for x in settings["blacklist_receiving"].split(",")
                if x.strip()
            ]
            if settings["blacklist_receiving"].strip()
            else self.BLACKLIST
        )

        self.whitelist = {
            x.strip()
            for x in settings["whitelist"].split(",")
            if x.strip()
        }

    def create_config(self):
        if not self.config_file.exists():
            self.config_file.write_text(CONFIG_DEFAULT_TEXT, encoding="utf-8")
            print("Created config.ini")

config = Config()
