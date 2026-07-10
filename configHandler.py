import os
import configparser

DEFAULT_BLACKLIST = [
    "AngularY", "AngularX", "AngularZ",
    "PositionX", "PositionY", "PositionZ",
    "GestureLeft", "GestureRight",
    "VelocityX", "VelocityY", "VelocityZ",
    "Grounded", "Seated", "AFK"
]

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


class Config:
    def __init__(self):
        config_file = "debugconfig.ini" if os.path.exists("debugconfig.ini") else "config.ini"

        parser = configparser.ConfigParser()
        parser.read_dict({"settings": DEFAULT_CONFIG})

        if os.path.exists(config_file):
            parser.read(config_file)

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



config = Config()
