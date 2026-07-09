
import threading
from pythonosc import udp_client, dispatcher, osc_server
import time
import asyncio
import os
import json
import websockets
import hashlib
import configparser
import uuid

from pathlib import Path
import platform

#DEFAULT_BLACKLIST = ["AngularY", "AngularX", "AngularZ", "PositionX", "PositionY", "PositionZ", "GestureLeft", "GestureRight", "GestureRightWeight", "GestureLeftWeight",
#        "VelocityX", "VelocityY", "VelocityZ", "Grounded", "Seated", "AFK", "IsLocal", "VoiceGain", "VoiceOn", "Viseme", "MouthOpen", "MouthForm", "BlinkLeft", "BlinkRight",
#        "VelocityMagnitude", "Upright", "Voice", "InStation", "VRMode", "TrackingType", "Viseme"]
DEFAULT_BLACKLIST = []
DEFAULT_WHITELIST = []  # empty = disabled

# use debug config file if it exists
if os.path.exists("debugconfig.ini"):
    CONFIG_FILE = "debugconfig.ini"
else:
    CONFIG_FILE = "config.ini"

DEFAULT_CONFIG = {
    "is_host": "False",
    "cooldown": "0.03",
    "friend_ip": "127.0.0.1",
    "ws_port": "38955",
    "secretpassword": "a1very5long2password77with8some8words8andnumbers764138catsareawesome", # no % signs
    "blacklist": "",
    "blacklist_sending": "",
    "blacklist_receiving": "",
    "whitelist": "",
    "printlog": "False",
    "ping_compensation": "1.5"
}

config = configparser.ConfigParser()
config.read_dict({"settings": DEFAULT_CONFIG})

if os.path.exists(CONFIG_FILE):
    config.read(CONFIG_FILE)

COOLDOWN = float(config["settings"]["cooldown"])
WS_PORT = int(config["settings"]["ws_port"])
URI = (f'ws://{config["settings"]["friend_ip"]}:{WS_PORT}')
SECRET_PASSWORD = config["settings"]["secretpassword"]
PRINT_LOG = config["settings"].getboolean("printlog") # getboolean() will accept True, true, 1, yes, on as True, and False, false, 0, no, off as False. # very neat !!!
ACTIVITY_TIMEOUT = float(config["settings"]["ping_compensation"])
IS_HOST = config["settings"].getboolean("is_host")

BLACKLIST = DEFAULT_BLACKLIST + [s.strip() for s in config["settings"]["blacklist"].split(",") if s.strip()]
user_blacklist_sending = [s.strip() for s in config["settings"]["blacklist_sending"].split(",") if s.strip()]
user_blacklist_receiving = [s.strip() for s in config["settings"]["blacklist_receiving"].split(",") if s.strip()]
blacklist_sending = DEFAULT_BLACKLIST + user_blacklist_sending if user_blacklist_sending else BLACKLIST
blacklist_receiving = DEFAULT_BLACKLIST + user_blacklist_receiving if user_blacklist_receiving else BLACKLIST

whitelist = [s.strip() for s in config["settings"]["whitelist"].split(",") if s.strip()]
whitelist = set(whitelist) if whitelist else set()  # empty = disabled

OSC_PORT = 9001
UDPCLIENT_PORT = 9000 

connected_clients = set()

class VRChatSync:
    def __init__(self):
        self.vrchat_client = udp_client.SimpleUDPClient("127.0.0.1", UDPCLIENT_PORT)
        self.last_times = {}   # last send time
        self.last_values = {}  # last sent value
        self.transport = ""    # these help with keeping alive the connection, possibly
        self.protocol = ""     # ^
        self.friend_ws_connection = None
        self.printlog = True 
        self.zero_send_count = {}  # Track how many times we've sent zero for each param
        self.authority_remote_detection = {}
        self.last_activity = {}  # Track when each param was last changed
        self.authority_timers = {}  # Track authority timers
        self.clientid = str(uuid.uuid4())[:8]
        self.editable_params = None       # list of param dicts
        self.editable_param_names = set() # fast lookup set of names


    async def setup_osc(self):
        dispatch = dispatcher.Dispatcher()

        def callback(addr, *args):
            #print(f"Changed: {addr}\n with args: {args}\n\n")
            asyncio.create_task(self.on_vrchat_parameter(addr, *args))

        def avatar_change_callback(addr, *args):
            asyncio.create_task(self._handle_avatar_change(args))

        dispatch.map("/avatar/parameters/*", callback)
        dispatch.map("/avatar/change", avatar_change_callback)   # add this line
        
        server = osc_server.AsyncIOOSCUDPServer(("127.0.0.1", OSC_PORT), dispatch, asyncio.get_event_loop())
        self.transport, self.protocol = await server.create_serve_endpoint()
        print(f"OSC server started on {OSC_PORT}")
        print(f"Whitelist: {whitelist if whitelist else 'disabled'}"
              f"\nBlacklist: {BLACKLIST}")

    async def find_osc_folder(self):
        home = Path.home()
        system = platform.system().lower()
        if system == "windows":
            osc_root = home / "AppData" / "LocalLow" / "VRChat" / "VRChat" / "OSC"
        elif system == "darwin":
            osc_root = home / "Library" / "Application Support" / "VRChat" / "OSC"
        elif system == "linux":
            osc_root = home / ".local" / "share" / "VRChat" / "OSC"
        else:
            osc_root = home
        if not osc_root.exists():
            print("[WARN] OSC directory not found.")
            return None
        return osc_root

    def json_parse_parameters(self, json_file):
        try:
            with json_file.open("r", encoding="utf-8-sig") as fh:
                j = json.load(fh)
                params = []
                for entry in j.get("parameters", []):
                    pname = entry.get("name") or entry.get("parameter") or entry.get("id")
                    input_addr = entry.get("input", {}).get("address") if isinstance(entry.get("input"), dict) else None
                    if input_addr is None:
                        continue  # not editable, skip
                    params.append({"name": pname, "input_addr": input_addr})
                self.editable_params = params
                self.editable_param_names = {p["name"] for p in params}
                print(f"[DEBUG] Loaded {len(params)} editable parameters")
        except Exception as e:
            print(f"Failed to read OSC config {json_file}: {e}")

    async def load_parameters_from_local_osc_config(self, avatar_id):
        osc_root = await self.find_osc_folder()
        if not osc_root:
            return
        user_dirs = list(osc_root.glob("usr_*"))
        if not user_dirs:
            return
        current_user_dir = max(user_dirs, key=lambda d: (d / "Avatars").stat().st_mtime if (d / "Avatars").exists() else 0)
        json_file = next(current_user_dir.rglob(f"**/Avatars/*{avatar_id}*.json"), None)
        if not json_file:
            print(f"[DEBUG] No JSON found for avatar {avatar_id}")
            return
        await asyncio.to_thread(self.json_parse_parameters, json_file)

    async def _handle_avatar_change(self, args):
        if not args:
            return
        avatar_id = args[0]
        if isinstance(avatar_id, bytes):
            avatar_id = avatar_id.decode(errors="ignore")
        self.editable_params = None
        self.editable_param_names = set()
        print(f"Avatar changed to: {avatar_id!r} — reloading editable params...")
        await self.load_parameters_from_local_osc_config(avatar_id)

#==================

    async def on_vrchat_parameter(self, addr, *args):
        param_name = addr
        if addr.startswith('/avatar/parameters/'):
            param_name = addr[len('/avatar/parameters/'):]
        #print(f"Parameter update: {param_name} = {args[0]}")

        if whitelist and param_name not in whitelist:
            return
        if param_name in blacklist_sending:
            return

        namespace = param_name.split('/', 1)[0] if '/' in param_name else param_name
        namespaceblacklist = ['touch', 'go']
        if namespace.lower() in namespaceblacklist:
            return

        value = args[0]
        now = time.time()
        self.last_activity[param_name] = now
        should_update = False 

        # --- normalize value ---
        """Snap values close to 0 or 1 to exact values"""
        if isinstance(value, float):
            value = round(value, 2)  # Apply to all values first
            if value <= 0.3:  # Near zero region
                snap_threshold_near_zero = 0.05
                if abs(value - 0.0) < snap_threshold_near_zero:
                    value = 0.0
            elif value >= 0.8:  # Near one region  
                snap_threshold_near_one = 0.01
                if abs(value - 1.0) < snap_threshold_near_one:
                    value = 1.0
            # No snapping in middle range (0.3 to 0.8)
            
        MAX_ZERO_SENDS = 20
        if value == 0.0: # Special handling for zero values
            zero_count = self.zero_send_count.get(param_name, 0)
            if zero_count < MAX_ZERO_SENDS:
                self.zero_send_count[param_name] = zero_count + 1
                should_update = True
        else:
            # Reset zero counter when value is not zero
            if param_name in self.zero_send_count:
                del self.zero_send_count[param_name]


        # --- immediate send decision ---
        last_time = self.last_times.get(param_name, 0)
        last_value = self.last_values.get(param_name)

        if ( # should we push the update
            last_value is None
            or (value != last_value and (now - last_time) > COOLDOWN)
            or should_update
        ): 
            self.last_values[param_name] = value
            self.last_times[param_name] = now
            await self.send_to_friend(param_name, value)

        # --- authority scheduling ---
        if param_name in self.authority_timers:
            self.authority_timers[param_name].cancel()
        self.authority_timers[param_name] = asyncio.create_task(
            self._assert_authority(param_name, value, now)
        )
    
    async def process_incoming_data(self, data):
        for param, value in data.items():
            if param in blacklist_receiving:
                continue
            if whitelist and param not in whitelist:
                continue
            last_value = self.last_values.get(param)
            if value != last_value:
                print(f"[RECEIVED] {param} = {value}")
                self.last_values[param] = value
                self.last_times[param] = time.time()
                self.authority_remote_detection[param] = True
                self.vrchat_client.send_message(f"/avatar/parameters/{param}", value)


    async def send_to_friend(self, param_name, value):
        message = json.dumps({param_name: value})
        print(f"[SENDING] {param_name} = {value}")
        self.authority_remote_detection[param_name] = False
        # Send to local connected clients, idk why but this helps
        for client in connected_clients:
            try:
                await client.send(message)
            except:
                pass
        # Send to connected friend
        if self.friend_ws_connection:
            try:
                await self.friend_ws_connection.send(message)
            except Exception as e:
                print(f"Error sending to friend: {e}")

    async def receive_from_friend(self):
        while self.friend_ws_connection:
            try:
                message = await self.friend_ws_connection.recv()
                data = json.loads(message)
                await self.process_incoming_data(data)
            except websockets.ConnectionClosed as e:
                print(f"Connection lost to friend: {e.code} ({e.reason})")
                self.friend_ws_connection = None
                break
            except Exception as e:
                print(f"Error receiving from friend: {e}")
                await asyncio.sleep(1)

    async def _assert_authority(self, param_name, final_value, authority_start_time):
        """Assert authority over final value after user stops changing it"""

        if self.authority_remote_detection.get(param_name):
            #print(f"[AUTHORITY] Skipping authority assertion for {param_name} due to recent remote update")
            # Don't assert authority for remote updates
            return
        
        await asyncio.sleep(ACTIVITY_TIMEOUT)
        
        now = time.time()
        last_change = self.last_activity.get(param_name, 0)

        # Only assert if no recent activity
        if last_change <= authority_start_time:
            print(f"[AUTHORITY]: {param_name} = {final_value}")
            # Force send the final value regardless of thresholds
            self.last_values[param_name] = final_value
            self.last_times[param_name] = now
            await self.send_to_friend(param_name, final_value)
        
        # Clean up timer
        if param_name in self.authority_timers:
            del self.authority_timers[param_name]

    async def connect_to_friend_retry(self, delay=3):
        while True:
            if self.friend_ws_connection is None:
                try:
                    print(f"Trying to connect to friend at {URI}...")
                    self.friend_ws_connection = await websockets.connect(URI)
                    # Send auth immediately
                    auth_msg = json.dumps({"auth": hashlib.sha256(SECRET_PASSWORD.encode()).hexdigest()})
                    await self.friend_ws_connection.send(auth_msg)
                    print(f"Connected and authenticated to friend at {URI}")
                    asyncio.create_task(self.receive_from_friend())
                except (ConnectionRefusedError, OSError) as e:
                    print(f"Connection failed: {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                except Exception as e:
                    print(f"Unexpected error: {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
            else:
                await asyncio.sleep(delay)


async def handle_client(websocket):
    auth_msg = await websocket.recv()
    auth_data = json.loads(auth_msg)

    expected_hash = hashlib.sha256(SECRET_PASSWORD.encode()).hexdigest()
    if auth_data.get("auth") != expected_hash:
        print("Authentication failed")
        await websocket.close()
        return

    connected_clients.add(websocket)
    try:
        async for message in websocket:
            data = json.loads(message)
            if PRINT_LOG:
                print(f"Data received: {data}")
            await sync.process_incoming_data(data)
    except websockets.ConnectionClosed:
        print("Client disconnected")
    finally:
        connected_clients.remove(websocket)



async def main():
    printintro()
    global sync
    sync = VRChatSync()
    await sync.setup_osc()

    if IS_HOST:
        async with websockets.serve(handle_client, "0.0.0.0", WS_PORT):
            print(f"Server started on port {WS_PORT} (host mode — forward this port)")
            await asyncio.Future()
    else:
        asyncio.create_task(sync.connect_to_friend_retry())
        await asyncio.Future()# run forever

def printintro():
    print("=" * 47)
    print()
    print("     Welcome to VRChat OSC Parameter Sync!")
    print()
    print("=" * 47)
    print("  1. Open config.ini in your preffered text editor.")
    print("  2. One person must set IS_HOST = True.")
    print("     - They must port forward the configured port")
    print("  3. The other person must set HOST_IP to the host's public IP address.")
    print("     - Make sure the port matches the host's configuration.")
    print("If the connection fails, double-check:")
    print("  • The host's public IP")
    print("  • Port forwarding")
    print("  • Windows Firewall")
    print("  • That both people are using the same port")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())

