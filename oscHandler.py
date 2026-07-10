
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
import traceback

from pathlib import Path
import platform
import qasync
import sys
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QGridLayout, 
                             QPushButton, QSlider, QLabel, QScrollArea, QMainWindow)
from PyQt5.QtCore import Qt, QObject, pyqtSignal

from qtUIWindow import MainWindow

from pathlib import Path
import platform


from connection_manager import connected_clients
from configHandler import config
OSC_PORT = 9001
UDPCLIENT_PORT = 9000 


class VRCParamController(QObject):
    parameter_updated = pyqtSignal(str, str)
    parameter_value_changed = pyqtSignal(str, object)
    clear_parameters = pyqtSignal()
    
    def __init__(self):
        super().__init__()  
        self.vrchat_client = udp_client.SimpleUDPClient("127.0.0.1", UDPCLIENT_PORT)
        self.last_times = {}   # last send time
        self.last_values = {}  # last sent value
        self.transport = ""    # these help with keeping alive the connection, possibly
        self.protocol = ""     # ^
        self.friend_ws_connection = None
        self.zero_send_count = {}  # Track how many times we've sent zero for each param
        self.authority_remote_detection = {}
        self.last_activity = {}  # Track when each param was last changed
        self.authority_timers = {}  # Track authority timers
        self.clientid = str(uuid.uuid4())[:8]
        self.editable_params = None       # list of param dicts
        self.editable_param_names = set() # fast lookup set of names
        self.list_of_avatar_params = None

    async def setup_osc(self):
        dispatch = dispatcher.Dispatcher()

        def callback(addr, *args):
            #print(f"Changed: {addr}\n with args: {args}\n\n")
            asyncio.create_task(self._handle_network_param_change(addr, *args))

        def avatar_change_callback(addr, *args):
            asyncio.create_task(self._handle_avatar_change(args))

        dispatch.map("/avatar/parameters/*", callback)
        dispatch.map("/avatar/change", avatar_change_callback)
        
        server = osc_server.AsyncIOOSCUDPServer(("127.0.0.1", OSC_PORT), dispatch, asyncio.get_event_loop())
        self.transport, self.protocol = await server.create_serve_endpoint()
        print(f"OSC server started on {OSC_PORT}")
        print(f"Whitelist: {config.whitelist if config.whitelist else 'disabled'}"
              f"\nBlacklist: {config.BLACKLIST}")

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
        '''
        Reads VRChat's auto-generated OSC config JSON for the current avatar (found under .../OSC/usr_.../Avatars/*.json). For every parameter in that file, it grabs the name, type, and the input/output addresses. It then filters that list down to only params that have an input_addr, these are the parameters VRChat will actually accept OSC writes for. It sorts them by name and stores that filtered list in self.editable_params.
        '''
        #print(f"[DEBUG] Trying to read: {json_file}")
        try:
            with json_file.open("r", encoding="utf-8-sig") as fh:
                j = json.load(fh)
                params = []
                for entry in j.get("parameters", []):
                    pname = entry.get("name") or entry.get("parameter") or entry.get("id")
                    ptype = None
                    # pick type if present in input/output
                    if "input" in entry and isinstance(entry["input"], dict):
                        ptype = entry["input"].get("type", ptype)
                    if "output" in entry and isinstance(entry["output"], dict):
                        ptype = entry["output"].get("type", ptype)
                    params.append({
                        "name": pname,
                        "type": ptype,
                        "input_addr": entry.get("input", {}).get("address") if isinstance(entry.get("input"), dict) else None,
                        "output_addr": entry.get("output", {}).get("address") if isinstance(entry.get("output"), dict) else None,
                    })
            
            print(f"[DEBUG] Successfully parsed {len(params)} parameters")

            #create editable params list
            editable_params = []
            for p in params:
                input_addr = p.get("input_addr")
                if input_addr is None:
                    continue
                editable_params.append(p)
                #print(f"  - {p['name']} (type: {p.get('type','?')})  input: {input_addr}")
            editable_params.sort(key=lambda p: p["name"].lower())
            self.editable_params = editable_params
            print(f"[DEBUG] Returning {len(editable_params)} editable parameters")
            return self.editable_params
                
        except Exception as e:
            # skip bad files
            print(f"Failed to read candidate OSC config {json_file}: {e}")
            
            traceback.print_exc()

        print("[DEBUG] No valid avatar config found, returning None")
        return None


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


#==================

    async def _handle_avatar_change(self, args):
        if not args:
            return
        avatar_id = args[0]
        if isinstance(avatar_id, bytes):
            avatar_id = avatar_id.decode(errors="ignore")
        self.editable_params = None
        self.editable_param_names = set()
        self.clear_parameters.emit()
        print(f"Avatar changed to: {avatar_id!r} — reloading editable params...")
        await self.load_parameters_from_local_osc_config(avatar_id)

        if self.editable_params:
            self.editable_param_names = { 
                p["name"] for p in self.editable_params if p.get("name")
            }
            for p in self.editable_params:
                self.parameter_updated.emit(p["name"], p.get("type") or "")


    async def _handle_network_param_change(self, addr, *args):

        param_name = addr
        if addr.startswith('/avatar/parameters/'):
            param_name = addr[len('/avatar/parameters/'):]
        #print(f"Parameter update: {param_name} = {args[0]}")

        if config.whitelist and param_name not in config.whitelist:
            return
        if param_name in config.blacklist_sending:
            return
        if self.editable_param_names and param_name not in self.editable_param_names:
            return


        namespace = param_name.split('/', 1)[0] if '/' in param_name else param_name
        namespaceblacklist = ['touch', 'Go']
        if namespace.lower() in namespaceblacklist:
            return


        value = args[0]
        self.parameter_value_changed.emit(param_name, value) 
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
            or (value != last_value and (now - last_time) > config.COOLDOWN)
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

    async def send_parameter(self, param_name, value):
        """Called by the UI when the user drags a slider/toggles a button"""
        addr = f"/avatar/parameters/{param_name}"
        self.vrchat_client.send_message(addr, value)
        print(f"[UI SEND] {param_name} = {value}")



    async def process_incoming_data(self, data):
        for param, value in data.items():
            if param in config.blacklist_receiving:
                continue
            if config.whitelist and param not in config.whitelist:
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
        
        await asyncio.sleep(config.ACTIVITY_TIMEOUT)
        
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
                    print(f"Trying to connect to friend at {config.URI}...")
                    self.friend_ws_connection = await websockets.connect(config.URI)
                    # Send auth immediately
                    auth_msg = json.dumps({"auth": hashlib.sha256(config.SECRET_PASSWORD.encode()).hexdigest()})
                    await self.friend_ws_connection.send(auth_msg)
                    print(f"Connected and authenticated to friend at {config.URI}")
                    asyncio.create_task(self.receive_from_friend())
                except (ConnectionRefusedError, OSError) as e:
                    print(f"Connection failed: {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                except Exception as e:
                    print(f"Unexpected error: {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
            else:
                await asyncio.sleep(delay)
