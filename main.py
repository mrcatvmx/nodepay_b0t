import os
import subprocess
import asyncio
import requests
import json
import time
import uuid
import websockets
from loguru import logger
from websockets_proxy import Proxy, proxy_connect
from urllib.parse import urlparse
import readline

# Introduction and user confirmation
def print_intro():
    print("════════════════════════════════════════════════════════════")
    print("║       Welcome to NodePay BOT!                            ║")
    print("║                                                          ║")
    print("║     Follow us on Twitter:                                ║")
    print("║     https://twitter.com/cipher_airdrop                   ║")
    print("║                                                          ║")
    print("║     Join us on Telegram:                                 ║")
    print("║     - https://t.me/+tFmYJSANTD81MzE1                     ║")
    print("╚════════════════════════════════════════════════════════════")
    answer = input('Will you F** NODEPAY Airdrop? (Y/N): ')
    if answer.lower() != 'y':
        print('Aborting installation.')
        exit(1)

# Ensure tmux is installed
def ensure_tmux_installed():
    result = subprocess.run(['which', 'tmux'], stdout=subprocess.PIPE)
    if result.returncode != 0:
        logger.info("tmux is not installed. Installing tmux...")
        subprocess.run(['apt-get', 'update'])
        subprocess.run(['apt-get', 'install', '-y', 'tmux'])
    else:
        logger.info("tmux is already installed.")

# Run script in a new tmux session
def run_in_tmux(session_name, script_path):
    subprocess.run(['tmux', 'new-session', '-d', '-s', session_name, 'python3', script_path])
    logger.info(f"Started tmux session '{session_name}' running the script.")

def get_user_input():
    user_id = input("Enter USER_ID: ")
    np_token = input("Enter NP_TOKEN: ")
    proxy_file = input("Enter the directory of the proxy list file: ")
    return user_id, np_token, proxy_file

def load_proxies(proxy_file):
    try:
        with open(proxy_file, 'r') as file:
            proxies = file.read().splitlines()
        return proxies
    except Exception as e:
        logger.error(f"Failed to load proxies: {e}")
        raise SystemExit("Exiting due to failure in loading proxies")

def is_valid_proxy(proxy):
    try:
        result = urlparse(proxy)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

async def call_api_info(token):
    return {
        "code": 0,
        "data": {
            "uid": 1253451318412967936,
        }
    }

async def connect_socket_proxy(proxy, token, reconnect_interval=60, ping_interval=10):
    if not is_valid_proxy(proxy):
        logger.error(f"Invalid proxy URL: {proxy}")
        return None

    browser_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, proxy))
    logger.info(f"Browser ID: {browser_id}")

    try:
        proxy_instance = Proxy.from_url(proxy)
        async with proxy_connect("wss://nw.nodepay.ai:4576/websocket", proxy=proxy_instance) as websocket:
            logger.info(f"Connected to WebSocket via proxy {proxy}")

            async def send_ping(guid, options={}):
                payload = {
                    "id": guid,
                    "action": "PING",
                    **options,
                }
                await websocket.send(json.dumps(payload))

            async def send_pong(guid):
                payload = {
                    "id": guid,
                    "origin_action": "PONG",
                }
                await websocket.send(json.dumps(payload))

            async for message in websocket:
                data = json.loads(message)

                if data["action"] == "PONG":
                    await send_pong(data["id"])
                    await asyncio.sleep(ping_interval)  # Wait before sending ping
                    await send_ping(data["id"])

                elif data["action"] == "AUTH":
                    api_response = await call_api_info(token)
                    if api_response["code"] == 0 and api_response["data"]["uid"]:
                        user_info = api_response["data"]
                        auth_info = {
                            "user_id": user_info["uid"],
                            "browser_id": browser_id,
                            "user_agent": "Mozilla/5.0",
                            "timestamp": int(time.time()),
                            "device_type": "extension",
                            "version": "extension_version",
                            "token": token,
                            "origin_action": "AUTH",
                        }
                        await send_ping(data["id"], auth_info)
                    else:
                        logger.error("Failed to authenticate")

    except websockets.InvalidStatusCode as e:
        logger.error(f"Connection error (InvalidStatusCode): {e.status_code} for proxy {proxy}")
        if e.status_code == 403:
            logger.error("HTTP 403 Forbidden: Check your token or proxy authorization.")
    except Exception as e:
        logger.error(f"Connection error: {e}", exc_info=True)
    return proxy

async def shutdown(loop, signal=None):
    if signal:
        logger.info(f"Received exit signal {signal.name}...")

    logger.info("Napping for 3 seconds before shutdown...")
    await asyncio.sleep(3)
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    logger.info(f"Cancelling {len(tasks)} outstanding tasks")
    [task.cancel() for task in tasks]

    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("All tasks cancelled, stopping loop")
    loop.stop()

async def main(user_id, np_token, proxy_file):
    proxies = load_proxies(proxy_file)
    active_proxies = [proxy for proxy in proxies if is_valid_proxy(proxy)]
    
    if not active_proxies:
        logger.error("No valid proxies found.")
        raise SystemExit("Exiting due to no valid proxies")

    logger.debug(f"Valid proxies: {active_proxies}")

    tasks = {asyncio.create_task(connect_socket_proxy(proxy, np_token)): proxy for proxy in active_proxies}

    if not tasks:
        logger.error("No tasks created for proxies.")
        raise SystemExit("Exiting due to no tasks created for proxies")

    while True:
        done, pending = await asyncio.wait(tasks.keys(), return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            failed_proxy = tasks[task]
            logger.info(f"Proxy {failed_proxy} failed. Retrying in 60 seconds...")
            await asyncio.sleep(60)  # Wait before retrying
            new_task = asyncio.create_task(connect_socket_proxy(failed_proxy, np_token))
            tasks[new_task] = failed_proxy
            tasks.pop(task)

        await asyncio.sleep(3)  # Prevent tight loop in case of rapid failures

if __name__ == '__main__':
    print_intro()
    ensure_tmux_installed()
    user_id, np_token, proxy_file = get_user_input()
    script_path = os.path.abspath(__file__)
    run_in_tmux('Nodepay', script_path)

    try:
        asyncio.run(main(user_id, np_token, proxy_file))
    except (KeyboardInterrupt, SystemExit):
        logger.info("Program terminated by user.")
