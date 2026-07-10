
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

from oscHandler import VRCParamController
from qtUIWindow import MainWindow

from pathlib import Path
import platform

from configHandler import config

from connection_manager import connected_clients

async def handle_client(websocket):
    auth_msg = await websocket.recv()
    auth_data = json.loads(auth_msg)

    expected_hash = hashlib.sha256(config.SECRET_PASSWORD.encode()).hexdigest()
    if auth_data.get("auth") != expected_hash:
        print("Authentication failed")
        await websocket.close()
        return

    connected_clients.add(websocket)
    try:
        async for message in websocket:
            data = json.loads(message)
            if config.PRINT_LOG:
                print(f"Data received: {data}")
            await sync.process_incoming_data(data)
    except websockets.ConnectionClosed:
        print("Client disconnected")
    finally:
        connected_clients.remove(websocket)

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


async def run_sync():
    printintro()
    global sync
    await sync.setup_osc()

    if config.IS_HOST:
        async with websockets.serve(handle_client, "0.0.0.0", config.WS_PORT):
            print(f"Server started on port {config.WS_PORT} (host mode — forward this port)")
            await asyncio.Future()
    else:
        asyncio.create_task(sync.connect_to_friend_retry())
        await asyncio.Future()


def main():
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    global sync, window
    sync = VRCParamController()
    window = MainWindow(sync)
    window.show()

    with loop:
        loop.create_task(run_sync())
        loop.run_forever()


if __name__ == "__main__":
    main()
