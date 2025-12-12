import requests
import json
import time
import random
from web3 import Web3
from eth_account.messages import encode_defunct
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta
import os
import sys
import pickle
import hashlib
from urllib.parse import urlparse
import threading

class SessionManager:
    """Manajer session yang lebih cerdas"""
    def __init__(self):
        self.sessions_file = 'sessions.dat'
        self.sessions = {}
        self.lock = threading.Lock()
        self.load_sessions()
    
    def get_session_key(self, address: str) -> str:
        return hashlib.md5(address.lower().encode()).hexdigest()[:16]
    
    def load_sessions(self):
        try:
            if os.path.exists(self.sessions_file):
                with open(self.sessions_file, 'rb') as f:
                    self.sessions = pickle.load(f)
                print(f"Loaded {len(self.sessions)} saved sessions")
        except Exception as e:
            print(f"Error loading sessions: {e}")
            self.sessions = {}
    
    def save_sessions(self):
        try:
            with open(self.sessions_file, 'wb') as f:
                pickle.dump(self.sessions, f)
        except Exception as e:
            print(f"Error saving sessions: {e}")
    
    def get_session(self, address: str) -> Optional[Dict]:
        key = self.get_session_key(address)
        with self.lock:
            return self.sessions.get(key)
    
    def update_session(self, address: str, data: Dict):
        key = self.get_session_key(address)
        with self.lock:
            if key not in self.sessions:
                self.sessions[key] = {
                    'created_at': datetime.now().isoformat(),
                    'login_attempts': 0,
                    'last_success': None,
                    'failures': 0
                }
            self.sessions[key].update(data)
            self.sessions[key]['last_updated'] = datetime.now().isoformat()
            self.sessions[key]['failures'] = 0
            self.save_sessions()
    
    def increment_failures(self, address: str):
        key = self.get_session_key(address)
        with self.lock:
            if key in self.sessions:
                self.sessions[key]['failures'] = self.sessions[key].get('failures', 0) + 1
                self.sessions[key]['last_failure'] = datetime.now().isoformat()
                self.save_sessions()
    
    def should_retry_login(self, address: str) -> Tuple[bool, int]:
        key = self.get_session_key(address)
        session = self.sessions.get(key, {})
        failures = session.get('failures', 0)
        delay = min(300, 5 * (3 ** min(failures, 4)))
        if failures > 5:
            wait_hours = (failures - 5) * 2
            delay = max(delay, wait_hours * 3600)
        return (failures < 10, delay)

class SmartRequestManager:
    """Manajer request adaptif"""
    def __init__(self):
        self.request_history = {}
        self.proxy_status = {}
        self.min_delay = 2
        self.max_delay = 10
    
    def get_adaptive_delay(self, address: str, endpoint: str) -> float:
        key = f"{address}_{endpoint}"
        now_ts = time.time()
        if key in self.request_history and now_ts - self.request_history[key] > 3600:
            del self.request_history[key]
        if key in self.request_history:
            last_request = self.request_history[key]
            elapsed = now_ts - last_request
            if elapsed < 30:
                return random.uniform(3, 7)
        self.request_history[key] = now_ts
        return random.uniform(self.min_delay, self.max_delay)
    
    def mark_proxy_failure(self, proxy: str):
        if proxy not in self.proxy_status:
            self.proxy_status[proxy] = {'failures': 0, 'last_failure': time.time()}
        self.proxy_status[proxy]['failures'] += 1
        self.proxy_status[proxy]['last_failure'] = time.time()
    
    def is_proxy_healthy(self, proxy: str) -> bool:
        if not proxy or proxy not in self.proxy_status:
            return True
        status = self.proxy_status[proxy]
        failures = status.get('failures', 0)
        last_failure = status.get('last_failure', 0)
        if failures > 5 and time.time() - last_failure < 600:
            return False
        if time.time() - last_failure > 1800:
            self.proxy_status[proxy]['failures'] = 0
        return True

class PipWorldAutoTask:
    def __init__(self):
        self.wallets = []
        self.proxies = {}
        self.session_manager = SessionManager()
        self.request_manager = SmartRequestManager()
        self.results = []
        self.sessions = {}
        self.AUTO_CLAIMABLE_TASKS = [
            "h8i9j0k1-l2m3-n4o5-p6q7-r8s9t0u1v2w3"
        ]
        self.SKIP_TASKS = [
            "a1b2c3d4-e5f6-7g8h-9i0j-k1l2m3n4o5p6",
            "f7g8h9i0-j1k2-l3m4-n5o6-p7q8r9s0t1u2",
            "g1r2u3s4-h5x6-p7t8-a9s0-k1b2c3d4e5f6",
        ]
    
    def print_color(self, text, color="white"):
        colors = {
            "red": "\033[91m",
            "green": "\033[92m",
            "yellow": "\033[93m",
            "blue": "\033[94m",
            "purple": "\033[95m",
            "cyan": "\033[96m",
            "white": "\033[97m",
            "reset": "\033[0m"
        }
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"{colors.get(color, colors['white'])}[{timestamp}] {text}{colors['reset']}")
    
    def load_wallets_and_proxies(self) -> bool:
        loaded_count = 0
        try:
            with open('wallets.txt', 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith(';') or line.startswith('//'):
                        continue
                    parts = [p.strip() for p in line.split(',') if p.strip()]
                    if len(parts) >= 2:
                        address = parts[0]
                        private_key = parts[1]
                        if not address.startswith('0x') or len(address) != 42:
                            self.print_color(f"Invalid address on line {line_num}: {address}", "yellow")
                            continue
                        proxy = None
                        if len(parts) >= 3:
                            proxy = parts[2]
                            if proxy and not self.validate_proxy_format(proxy):
                                self.print_color(f"Invalid proxy format on line {line_num}", "yellow")
                                proxy = None
                        self.wallets.append({
                            'address': address,
                            'private_key': private_key,
                            'proxy': proxy,
                            'index': len(self.wallets) + 1
                        })
                        if proxy:
                            self.proxies[address.lower()] = proxy
                        loaded_count += 1
                    else:
                        self.print_color(f"Invalid format on line {line_num}", "yellow")
            self.print_color(f"Successfully loaded {loaded_count}/{len(self.wallets)} wallets", "green")
            if self.proxies:
                self.print_color(f"Loaded {len(self.proxies)} proxies", "green")
            return len(self.wallets) > 0
        except FileNotFoundError:
            self.print_color("File wallets.txt not found", "red")
            return False
        except Exception as e:
            self.print_color(f"Error loading wallets: {e}", "red")
            return False
    
    def validate_proxy_format(self, proxy: str) -> bool:
        try:
            if proxy.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
                parsed = urlparse(proxy)
                return bool(parsed.hostname and parsed.port)
            return False
        except:
            return False
    
    def get_session_for_wallet(self, address: str):
        if address not in self.sessions:
            session = requests.Session()
            session.headers.update({
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-site',
            })
            adapter = requests.adapters.HTTPAdapter(max_retries=3, pool_connections=10, pool_maxsize=10)
            session.mount('https://', adapter)
            session.mount('http://', adapter)
            self.sessions[address] = session
        return self.sessions[address]
    
    def make_intelligent_request(self, method, url, wallet_address=None, max_retries=5, **kwargs):
        session = self.get_session_for_wallet(wallet_address) if wallet_address else requests.Session()
        proxy = kwargs.pop('proxy', None)
        if proxy and not self.request_manager.is_proxy_healthy(proxy):
            self.print_color(f"Proxy {proxy[:50]}... marked as unhealthy, trying without", "yellow")
            proxy = None
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    endpoint = url.split('/')[-1] if '/' in url else url
                    delay = self.request_manager.get_adaptive_delay(wallet_address or 'global', endpoint)
                    delay *= (attempt + 1)
                    self.print_color(f"Retry {attempt}/{max_retries-1} in {delay:.1f}s...", "yellow")
                    time.sleep(delay)
                if proxy:
                    kwargs['proxies'] = {'http': proxy, 'https': proxy}
                if 'timeout' not in kwargs:
                    kwargs['timeout'] = (15, 30)
                response = session.request(method, url, **kwargs)
                if response.status_code == 429:
                    retry_after = response.headers.get('Retry-After', 60)
                    wait_time = min(300, int(retry_after) * (attempt + 1))
                    self.print_color(f"Rate limited, waiting {wait_time}s...", "yellow")
                    time.sleep(wait_time)
                    continue
                elif response.status_code == 401:
                    self.print_color("Session expired, will re-login", "yellow")
                    return response
                elif response.status_code >= 500:
                    wait_time = min(120, 10 * (attempt + 1))
                    self.print_color(f"Server error {response.status_code}, waiting {wait_time}s...", "yellow")
                    time.sleep(wait_time)
                    continue
                elif response.status_code == 403:
                    if proxy:
                        self.request_manager.mark_proxy_failure(proxy)
                        self.print_color("Proxy blocked, marking as unhealthy", "yellow")
                        proxy = None
                        kwargs.pop('proxies', None)
                    wait_time = 30 * (attempt + 1)
                    self.print_color(f"Access forbidden, waiting {wait_time}s...", "yellow")
                    time.sleep(wait_time)
                    continue
                return response
            except requests.exceptions.ProxyError as e:
                if proxy:
                    self.request_manager.mark_proxy_failure(proxy)
                    self.print_color(f"Proxy error: {e}", "yellow")
                    proxy = None
                    kwargs.pop('proxies', None)
                continue
            except requests.exceptions.ConnectionError as e:
                wait_time = min(60, 5 * (attempt + 1))
                self.print_color(f"Connection error: {e}", "yellow")
                time.sleep(wait_time)
                continue
            except requests.exceptions.Timeout as e:
                wait_time = min(60, 10 * (attempt + 1))
                self.print_color(f"Timeout: {e}", "yellow")
                time.sleep(wait_time)
                continue
            except Exception as e:
                self.print_color(f"Request error: {e}", "yellow")
                if attempt == max_retries - 1:
                    raise
        return None
    
    def smart_login(self, wallet: Dict) -> Optional[Dict]:
        address = wallet['address']
        private_key = wallet['private_key']
        proxy = wallet.get('proxy')
        should_retry, wait_time = self.session_manager.should_retry_login(address)
        if not should_retry:
            self.print_color(f"Too many failures for {address[:10]}, skipping...", "red")
            return None
        if wait_time > 0:
            self.print_color(f"Waiting {wait_time}s before login (exponential backoff)...", "yellow")
            time.sleep(wait_time)
        saved_token = self.load_saved_token(address)
        if saved_token:
            self.print_color(f"Trying saved token for {address[:10]}...", "cyan")
            if self.verify_token(saved_token, proxy):
                self.print_color("Saved token still valid!", "green")
                self.session_manager.update_session(address, {
                    'last_success': datetime.now().isoformat(),
                    'login_attempts': 0,
                    'token': saved_token
                })
                return {'token': saved_token, 'user_id': 'from_saved'}
        self.print_color(f"Starting login for {address[:10]}...", "cyan")
        login_strategies = [self.login_normal_flow, self.login_with_different_headers, self.login_with_delayed_retry]
        for strategy_num, strategy in enumerate(login_strategies, 1):
            self.print_color(f"Trying strategy {strategy_num}/{len(login_strategies)}...", "blue")
            result = strategy(address, private_key, proxy)
            if result and result.get('success'):
                token = result.get('token')
                user_id = result.get('user_id')
                if token:
                    self.save_token(address, user_id, token)
                    self.session_manager.update_session(address, {
                        'last_success': datetime.now().isoformat(),
                        'login_attempts': 0,
                        'token': token,
                        'strategy_used': f'strategy_{strategy_num}'
                    })
                    self.print_color(f"Login successful with strategy {strategy_num}!", "green")
                    return result
            if strategy_num < len(login_strategies):
                delay = random.uniform(5, 10)
                self.print_color(f"Strategy {strategy_num} failed, trying next in {delay:.1f}s...", "yellow")
                time.sleep(delay)
        self.print_color(f"All login strategies failed for {address[:10]}", "red")
        self.session_manager.increment_failures(address)
        return None
    
    def login_normal_flow(self, address: str, private_key: str, proxy=None) -> Optional[Dict]:
        try:
            init_data = self.init_siwe(address, proxy)
            if not init_data:
                return None
            nonce = init_data.get('nonce')
            issued_at = init_data.get('issued_at') or init_data.get('expires_at')
            if not nonce or not issued_at:
                return None
            message = self.create_siwe_message(address, nonce, issued_at)
            signature = self.sign_message(private_key, message)
            if not signature:
                return None
            auth_result = self.authenticate_siwe(address, message, signature, proxy)
            if auth_result and auth_result.get('success'):
                return auth_result
            return None
        except Exception as e:
            self.print_color(f"Normal login error: {e}", "yellow")
            return None
    
    def login_with_different_headers(self, address: str, private_key: str, proxy=None) -> Optional[Dict]:
        try:
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
                'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/537.36'
            ]
            for ua in user_agents:
                self.print_color(f"Trying User-Agent: {ua[:50]}...", "blue")
                session = self.get_session_for_wallet(address)
                session.headers.update({'User-Agent': ua})
                result = self.login_normal_flow(address, private_key, proxy)
                if result:
                    return result
                time.sleep(2)
            return None
        except Exception as e:
            self.print_color(f"Alternative headers error: {e}", "yellow")
            return None
    
    def login_with_delayed_retry(self, address: str, private_key: str, proxy=None) -> Optional[Dict]:
        max_retries = 3
        base_delay = 10
        for retry in range(max_retries):
            self.print_color(f"Delayed retry {retry+1}/{max_retries}...", "blue")
            if retry > 0:
                delay = base_delay * (2 ** retry)
                delay = min(delay, 60)
                self.print_color(f"Waiting {delay}s before retry...", "yellow")
                time.sleep(delay)
            result = self.login_normal_flow(address, private_key, proxy)
            if result:
                return result
        return None
    
    def load_saved_token(self, address: str) -> Optional[str]:
        try:
            if not os.path.exists('tokens'):
                return None
            token_files = [f for f in os.listdir('tokens') if f.startswith(address[:10])]
            if not token_files:
                return None
            latest_file = max(token_files, key=lambda x: int(x.split('_')[-1].replace('.txt', '')))
            with open(f'tokens/{latest_file}', 'r', encoding='utf-8') as f:
                data = json.load(f)
                saved_at = datetime.fromisoformat(data.get('saved_at', '2000-01-01'))
                age_hours = (datetime.now() - saved_at).total_seconds() / 3600
                if age_hours < 12:
                    return data.get('token')
            return None
        except:
            return None
    
    def save_token(self, address: str, user_id: str, token: str):
        try:
            os.makedirs('tokens', exist_ok=True)
            timestamp = int(time.time())
            filename = f"tokens/{address[:10]}_{timestamp}.txt"
            data = {
                'address': address,
                'user_id': user_id,
                'token': token,
                'saved_at': datetime.now().isoformat(),
                'version': '2.0'
            }
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            with open('tokens_all.txt', 'a', encoding='utf-8') as f:
                f.write(f"{address},{user_id},{token},{timestamp}\n")
            return True
        except Exception as e:
            self.print_color(f"Error saving token: {e}", "yellow")
            return False
    
    def verify_token(self, token: str, proxy=None) -> bool:
        try:
            url = "https://api-mm.pip.world/account"
            headers = {'Accept': 'application/json, text/plain, */*', 'Cookie': f'privy-token={token}'}
            response = self.make_intelligent_request('GET', url, headers=headers, timeout=10, proxy=proxy)
            return response is not None and response.status_code == 200
        except:
            return False
    
    def init_siwe(self, address, proxy=None):
        try:
            url = "https://privy.pip.world/api/v1/siwe/init"
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Origin': 'https://mm.pip.world',
                'Referer': 'https://mm.pip.world/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'privy-app-id': 'cmd5wk49c01qejr0m6tun1ri5',
                'privy-ca-id': '57e973d5-e48f-4e5f-9f26-0576573aa378',
                'privy-client': 'react-auth:2.13.7'
            }
            response = self.make_intelligent_request('POST', url, wallet_address=address, json={"address": address}, headers=headers, timeout=30, proxy=proxy)
            if response and response.status_code == 200:
                return response.json()
            if response:
                self.print_color(f"SIWE init failed: {response.status_code}", "yellow")
            return None
        except Exception as e:
            self.print_color(f"Init SIWE error: {e}", "yellow")
            return None
    
    def create_siwe_message(self, address: str, nonce: str, issued_at: str) -> str:
        return f"mm.pip.world wants you to sign in with your Ethereum account:\n{address}\n\nBy signing, you are proving you own this wallet and logging in. This does not initiate a transaction or cost any fees.\n\nURI: https://mm.pip.world\nVersion: 1\nChain ID: 1\nNonce: {nonce}\nIssued At: {issued_at}\nResources:\n- https://privy.io"
    
    def sign_message(self, private_key: str, message: str) -> Optional[str]:
        try:
            w3 = Web3()
            if not private_key.startswith('0x'):
                private_key = '0x' + private_key
            if len(private_key) != 66:
                self.print_color("Invalid private key length", "yellow")
                return None
            message_hash = encode_defunct(text=message)
            signed = w3.eth.account.sign_message(message_hash, private_key=private_key)
            return "0x" + signed.signature.hex()
        except Exception as e:
            self.print_color(f"Sign error: {e}", "yellow")
            return None
    
    def authenticate_siwe(self, address: str, message: str, signature: str, proxy=None):
        try:
            url = "https://privy.pip.world/api/v1/siwe/authenticate"
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Origin': 'https://mm.pip.world',
                'Referer': 'https://mm.pip.world/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'privy-app-id': 'cmd5wk49c01qejr0m6tun1ri5',
                'privy-ca-id': '57e973d5-e48f-4e5f-9f26-0576573aa378',
                'privy-client': 'react-auth:2.13.7'
            }
            payload = {
                "chainId": "eip155:1",
                "connectorType": "injected",
                "message": message,
                "mode": "no-signup",
                "signature": signature,
                "walletClientType": "rabby_wallet"
            }
            response = self.make_intelligent_request('POST', url, wallet_address=address, json=payload, headers=headers, timeout=30, proxy=proxy)
            if response and response.status_code == 200:
                data = response.json()
                token = data.get('token')
                if token:
                    return {
                        'success': True,
                        'user_id': data.get('user', {}).get('id', ''),
                        'token': token,
                        'user_data': data.get('user', {})
                    }
            return None
        except Exception as e:
            self.print_color(f"Auth error: {e}", "yellow")
            return None
    
    def get_tasks(self, token: str, address: str, proxy=None):
        try:
            url = "https://api-mm.pip.world/xp-tasks"
            headers = {'Accept': 'application/json, text/plain, */*', 'Cookie': f'privy-token={token}'}
            response = self.make_intelligent_request('GET', url, wallet_address=address, headers=headers, timeout=30, proxy=proxy)
            if response and response.status_code == 200:
                return response.json()
            elif response and response.status_code == 401:
                self.print_color("Token expired, needs re-login", "yellow")
                return None
            else:
                if response:
                    self.print_color(f"Failed to get tasks: {response.status_code}", "yellow")
                return None
        except Exception as e:
            self.print_color(f"Error getting tasks: {e}", "yellow")
            return None
    
    def claim_task(self, token: str, task_id: str, address: str, task_name: str = "", proxy=None):
        try:
            url = f"https://api-mm.pip.world/xp/tasks/{task_id}"
            headers = {'Accept': 'application/json, text/plain, */*', 'Content-Type': 'application/json', 'Cookie': f'privy-token={token}'}
            response = self.make_intelligent_request('POST', url, wallet_address=address, headers=headers, json={}, timeout=30, proxy=proxy)
            if response and response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return data
                else:
                    error_msg = data.get('error', 'Unknown error')
                    self.print_color(f"Claim failed: {error_msg}", "yellow")
                    return None
            elif response and response.status_code == 400:
                self.print_color(f"Already claimed or not eligible", "yellow")
                return None
            else:
                if response:
                    self.print_color(f"Claim failed: {response.status_code}", "yellow")
                return None
        except Exception as e:
            self.print_color(f"Error claiming: {e}", "yellow")
            return None
    
    def process_wallet_tasks(self, wallet: Dict):
        address = wallet['address']
        proxy = wallet.get('proxy')
        self.print_color(f"\n{'='*60}", "cyan")
        self.print_color(f"PROCESSING WALLET #{wallet['index']}: {address[:10]}...", "cyan")
        if proxy:
            self.print_color(f"Using proxy: {proxy[:50]}...", "blue")
        self.print_color(f"{'='*60}", "cyan")
        login_result = self.smart_login(wallet)
        if not login_result:
            self.print_color("Failed to login, skipping wallet", "red")
            return False
        token = login_result.get('token')
        if not token:
            self.print_color("No token received", "red")
            return False
        tasks = None
        for attempt in range(3):
            self.print_color(f"Getting tasks (attempt {attempt+1}/3)...", "yellow")
            tasks = self.get_tasks(token, address, proxy)
            if tasks:
                break
            elif attempt < 2:
                delay = random.uniform(10, 20)
                self.print_color(f"Waiting {delay:.1f}s before retry...", "yellow")
                time.sleep(delay)
        if not tasks:
            self.print_color("Failed to get tasks after retries", "red")
            return False
        self.print_color(f"Found {len(tasks)} tasks", "green")
        daily_claimed = False
        claimed_count = 0
        total_xp = 0
        for task in tasks:
            task_id = task.get('id')
            task_name = task.get('name', 'Unknown Task')
            task_xp = task.get('xp', 0)
            is_done = task.get('done', False)
            if is_done:
                continue
            if task_id in self.SKIP_TASKS:
                self.print_color(f"Skipping: {task_name}", "blue")
                continue
            self.print_color(f"Attempting: {task_name} (+{task_xp} XP)", "cyan")
            claim_result = self.claim_task(token, task_id, address, task_name, proxy)
            if claim_result and claim_result.get('success'):
                earned_xp = claim_result.get('xp', task_xp)
                self.print_color(f"Claimed! +{earned_xp} XP", "green")
                claimed_count += 1
                total_xp += earned_xp
                delay = random.uniform(1, 3)
                time.sleep(delay)
                if task_id == "h8i9j0k1-l2m3-n4o5-p6q7-r8s9t0u1v2w3":
                    daily_claimed = True
            else:
                self.print_color("Could not claim", "yellow")
        self.print_color(f"\n{'='*60}", "green")
        self.print_color(f"WALLET #{wallet['index']} SUMMARY:", "green")
        self.print_color(f"Tasks claimed: {claimed_count}", "green")
        self.print_color(f"Total XP earned: {total_xp}", "green")
        self.print_color(f"Daily check-in: {'✓' if daily_claimed else '✗'}", "green" if daily_claimed else "red")
        self.print_color(f"{'='*60}", "green")
        return daily_claimed
    
    def run_continuous(self):
        print("\033c")
        self.print_color("="*80, "cyan")
        self.print_color("PIP.WORLD AUTO TASK BOT AND CEKIN DAILY - BACTIAR291", "cyan")
        self.print_color("="*80, "cyan")
        if not self.load_wallets_and_proxies():
            return
        if not self.wallets:
            self.print_color("No valid wallets found", "red")
            return
        self.print_color("CONFIGURATION:", "yellow")
        self.print_color(f"Total wallets: {len(self.wallets)}", "yellow")
        self.print_color("Session manager: Active", "yellow")
        self.print_color("Smart requests: Enabled", "yellow")
        input("Press Enter to start automation...")
        cycle = 1
        successful_cycles = 0
        while True:
            try:
                self.print_color(f"\n{'='*80}", "purple")
                self.print_color(f"CYCLE #{cycle} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "purple")
                self.print_color(f"{'='*80}", "purple")
                daily_success_count = 0
                total_wallets = len(self.wallets)
                for wallet in self.wallets:
                    try:
                        success = self.process_wallet_tasks(wallet)
                        if success:
                            daily_success_count += 1
                        if wallet['index'] < total_wallets:
                            delay = random.uniform(5, 15)
                            self.print_color(f"Next wallet in {delay:.1f}s...", "blue")
                            time.sleep(delay)
                    except Exception as e:
                        self.print_color(f"Error processing wallet: {e}", "red")
                        continue
                self.print_color(f"\n{'='*80}", "green")
                self.print_color(f"CYCLE #{cycle} COMPLETE:", "green")
                self.print_color(f"Successful daily check-ins: {daily_success_count}/{total_wallets}", "green" if daily_success_count == total_wallets else "yellow")
                self.print_color("Next cycle in ~24 hours", "cyan")
                self.print_color(f"{'='*80}", "green")
                if daily_success_count == total_wallets:
                    successful_cycles += 1
                next_run = datetime.now() + timedelta(hours=24, minutes=random.randint(1, 30))
                self.countdown_timer(next_run, "Next cycle at")
                cycle += 1
            except KeyboardInterrupt:
                self.print_color("\n\nBot stopped by user", "yellow")
                break
            except Exception as e:
                self.print_color(f"Cycle error: {e}", "red")
                self.print_color("Retrying in 5 minutes...", "yellow")
                time.sleep(300)
    
    def countdown_timer(self, target_time: datetime, message: str = "Next check"):
        while datetime.now() < target_time:
            remaining = (target_time - datetime.now()).total_seconds()
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            seconds = int(remaining % 60)
            total_seconds = 24 * 3600
            progress = int(((total_seconds - remaining) / total_seconds) * 50)
            progress_bar = "■" * progress + "·" * (50 - progress)
            print(f"\r{message}: {hours:02d}:{minutes:02d}:{seconds:02d} [{progress_bar}]", end='', flush=True)
            time.sleep(1)
        print()
    
def create_wallet_file():
    sample_content = "0xYOUR_ADDRESS_HERE,YOUR_PRIVATE_KEY_HERE\n"
    if not os.path.exists('wallets.txt'):
        with open('wallets.txt', 'w', encoding='utf-8') as f:
            f.write(sample_content)
        print("File wallets.txt telah dibuat (edit dengan format: address,private_key[,proxy_url])")
        return False
    with open('wallets.txt', 'r', encoding='utf-8') as f:
        content = f.read()
        if 'YOUR_ADDRESS_HERE' in content or 'YOUR_PRIVATE_KEY_HERE' in content:
            print("File wallets.txt masih berisi contoh. Harap edit file dengan data wallet Anda.")
            return False
    return True

def main():
    print("\033c")
    print("PIP.WORLD AUTO BOT")
    print("="*50)
    try:
        from web3 import Web3
        from eth_account.messages import encode_defunct
    except ImportError:
        print("Missing dependencies! Install dengan: pip install web3 requests")
        return
    os.makedirs('tokens', exist_ok=True)
    if not create_wallet_file():
        return
    bot = PipWorldAutoTask()
    try:
        bot.run_continuous()
    except KeyboardInterrupt:
        bot.print_color("\n\nBot stopped by user", "red")
    except Exception as e:
        bot.print_color(f"Fatal error: {e}", "red")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
