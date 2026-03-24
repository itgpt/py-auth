__version__ = '0.1.3'
import copy
import logging
import threading
import platform
import socket
import sys
import hashlib
import json
import os
import time
import base64
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from .device_utils import _PERSISTED_DEVICE_ID_NOT_PREFETCHED, build_device_id, build_device_info, collect_device_facts, fetch_public_ip, load_persisted_device_id
from .state_bundle import BUNDLE_PRODUCT_DEVICE_INFO_SNAPSHOT_KEY, BUNDLE_PRODUCT_REVOKE_KEYS, BUNDLE_ROOT_STRAY_KEYS, bundle_path, commit_apps_map, get_client_storage_root, load_apps_map, read_state_dict, row_device_id_str, row_last_success_ts, write_state_dict

_SECONDS_PER_MINUTE = 60
_SECONDS_PER_HOUR = 3600
_SECONDS_PER_DAY = 86400
_DEFAULT_HEARTBEAT_TIMEOUT_SEC = (0.9, 0.9)
_ONLINE_CHECK_WALL_DEADLINE_SEC = 1.75
_ONLINE_CHECK_WALL_MIN_WHEN_DEVICE_INFO_DEFERRED_SEC = 12.0
_ONLINE_CHECK_FAST_WALL_SEC = 4.0

def _online_check_wall_deadline_sec() -> float:
    raw = os.environ.get('PY_AUTH_ONLINE_WALL_SEC', '').strip()
    if raw:
        try:
            v = float(raw)
            if 1.0 <= v <= 30.0:
                return v
        except ValueError:
            pass
    return _ONLINE_CHECK_WALL_DEADLINE_SEC

def _online_check_effective_wall_sec(device_info_deferred: bool) -> float:
    base = _online_check_wall_deadline_sec()
    if not device_info_deferred:
        return base
    floor = float(_ONLINE_CHECK_WALL_MIN_WHEN_DEVICE_INFO_DEFERRED_SEC)
    raw = os.environ.get('PY_AUTH_ONLINE_WALL_DEFERRED_MIN_SEC', '').strip()
    if raw:
        try:
            v = float(raw)
            if 1.0 <= v <= 60.0:
                floor = v
        except ValueError:
            pass
    return max(base, floor)


def _device_info_lacks_nonblank_public_ip(device_info: Dict[str, Any]) -> bool:
    nw = device_info.get('network')
    if not isinstance(nw, dict):
        return True
    p = nw.get('public_ip')
    return not (isinstance(p, str) and bool(p.strip()))


_background_auth_executor: Optional[ThreadPoolExecutor] = None
_background_auth_lock = threading.Lock()

def get_auth_background_executor() -> ThreadPoolExecutor:
    global _background_auth_executor
    with _background_auth_lock:
        if _background_auth_executor is None:
            n = min(32, (os.cpu_count() or 2) + 4)
            _background_auth_executor = ThreadPoolExecutor(max_workers=max(4, n), thread_name_prefix='py_auth_client')
        return _background_auth_executor

def shutdown_auth_background_executor(*, wait: bool=True, cancel_futures: bool=False) -> None:
    global _background_auth_executor
    with _background_auth_lock:
        if _background_auth_executor is None:
            return
        try:
            _background_auth_executor.shutdown(wait=wait, cancel_futures=cancel_futures)
        except TypeError:
            _background_auth_executor.shutdown(wait=wait)
        _background_auth_executor = None


class AuthCache:

    def __init__(self, storage_base: Path, device_id: str='', server_url: str='', software_name: str='', cache_validity_days: int=7, check_interval_days: int=2):
        self.cache_validity_days = cache_validity_days
        self.cache_validity_seconds = cache_validity_days * _SECONDS_PER_DAY
        self.check_interval_days = check_interval_days
        self.check_interval_seconds = check_interval_days * _SECONDS_PER_DAY
        self.device_id = device_id
        self.server_url = (server_url or '').rstrip('/')
        self._software_name = software_name
        self.logger = logging.getLogger('py_auth_client')
        self.cache_dir = storage_base
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = bundle_path(self.server_url, self.cache_dir)

    def _read_full(self) -> Optional[Dict[str, Any]]:
        return read_state_dict(self.server_url, base_dir=self.cache_dir)

    def _write_bundle_with_retry(self, data: Dict[str, Any]) -> bool:
        for attempt in range(2):
            if write_state_dict(self.server_url, data, base_dir=self.cache_dir):
                if platform.system() == 'Windows':
                    try:
                        import ctypes
                        ctypes.windll.kernel32.SetFileAttributesW(str(self.cache_file), 2)
                    except Exception:
                        pass
                return True
            if attempt == 0 and platform.system() == 'Windows' and self.cache_file.exists():
                try:
                    import ctypes
                    ctypes.windll.kernel32.SetFileAttributesW(str(self.cache_file), 128)
                    self.cache_file.unlink()
                except Exception:
                    pass
        return False

    def _read_row(self) -> Optional[Dict[str, Any]]:
        d = self._read_full()
        if not d:
            return None
        row = load_apps_map(d).get(self._software_name)
        if not row or not isinstance(row, dict):
            return None
        return row

    def _cache_dict_from_row(self, row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        ts = row_last_success_ts(row)
        if ts is None:
            return None
        return {'authorized': True, 'message': '设备已授权', 'cached_at': ts}

    def _is_cache_valid_dict(self, cache: Optional[Dict[str, Any]]) -> bool:
        if not cache:
            return False
        cached_at = cache.get('cached_at', 0)
        try:
            ca = float(cached_at)
        except (TypeError, ValueError):
            return False
        if ca <= 0:
            return False
        return time.time() - ca < self.cache_validity_seconds

    def _snapshot_auth_row(self) -> tuple[Optional[Dict[str, Any]], int]:
        row = self._read_row()
        if row_last_success_ts(row) is None:
            return (None, 0)
        raw = row.get('heartbeat_times')
        try:
            n = int(raw)
        except (TypeError, ValueError):
            self.clear_cache()
            return (None, 0)
        if n < 1:
            self.clear_cache()
            return (None, 0)
        return (self._cache_dict_from_row(row), n)

    def get_stored_heartbeat_times(self) -> int:
        try:
            _, n = self._snapshot_auth_row()
            return n
        except Exception:
            return 0

    def get_cache(self) -> Optional[Dict[str, Any]]:
        try:
            return self._cache_dict_from_row(self._read_row())
        except Exception as e:
            try:
                self.logger.debug(f'读取缓存异常: {e}')
            except Exception:
                pass
            return None

    def save_cache(self, authorized: bool, message: str, *, last_success_at: Optional[float]=None, heartbeat_times: Optional[int]=None, device_info_snapshot: Optional[Dict[str, Any]]=None) -> bool:
        try:
            now = time.time()
            ts = last_success_at if last_success_at is not None else now
            d = dict(self._read_full() or {})
            for k in BUNDLE_ROOT_STRAY_KEYS:
                d.pop(k, None)
            apps_m = load_apps_map(d)
            sub = dict(apps_m.get(self._software_name, {}))
            sub.pop('software_name', None)
            if not authorized:
                for k in BUNDLE_PRODUCT_REVOKE_KEYS:
                    sub.pop(k, None)
                sub['device_id'] = self.device_id
            else:
                sub['device_id'] = self.device_id
                sub['last_success_at'] = ts
                if heartbeat_times is not None:
                    sub['heartbeat_times'] = heartbeat_times
                if device_info_snapshot is not None and isinstance(device_info_snapshot, dict) and (len(device_info_snapshot) > 0):
                    sub[BUNDLE_PRODUCT_DEVICE_INFO_SNAPSHOT_KEY] = copy.deepcopy(device_info_snapshot)
            apps_m[self._software_name] = sub
            commit_apps_map(d, apps_m)
            return self._write_bundle_with_retry(d)
        except Exception as e:
            try:
                self.logger.debug(f'保存缓存失败: {e}')
            except Exception:
                pass
            return False

    def load_device_info_snapshot(self) -> Optional[Dict[str, Any]]:
        try:
            row = self._read_row()
            if not row:
                return None
            v = row.get(BUNDLE_PRODUCT_DEVICE_INFO_SNAPSHOT_KEY)
            if v is None:
                return None
            if isinstance(v, str):
                if not v.strip():
                    return None
                try:
                    out = json.loads(v)
                except json.JSONDecodeError:
                    return None
                return copy.deepcopy(out) if isinstance(out, dict) else None
            if isinstance(v, dict):
                return copy.deepcopy(v)
            return None
        except Exception:
            return None

    def update_last_check(self) -> bool:
        try:
            cache = self.get_cache()
            if cache:
                return self.save_cache(True, '', last_success_at=time.time())
            return False
        except Exception:
            return False

    def is_cache_valid(self) -> bool:
        return self._is_cache_valid_dict(self.get_cache())

    def needs_check(self) -> bool:
        cache = self.get_cache()
        if not cache:
            return True
        cached_at = cache.get('cached_at', 0)
        try:
            ts = float(cached_at)
        except (TypeError, ValueError):
            return True
        if ts <= 0:
            return True
        elapsed = time.time() - ts
        return elapsed >= self.check_interval_seconds

    def clear_cache(self) -> bool:
        try:
            d = self._read_full()
            if not d:
                return True
            for k in BUNDLE_ROOT_STRAY_KEYS:
                d.pop(k, None)
            apps_m = load_apps_map(d)
            sub = dict(apps_m.get(self._software_name, {}))
            sub.pop('software_name', None)
            for k in BUNDLE_PRODUCT_REVOKE_KEYS:
                sub.pop(k, None)
            sub['device_id'] = self.device_id
            apps_m[self._software_name] = sub
            commit_apps_map(d, apps_m)
            any_app_device = any((isinstance(v, dict) and bool(row_device_id_str(v)) for v in apps_m.values()))
            if not any_app_device:
                if self.cache_file.exists():
                    self.cache_file.unlink()
                return True
            return self._write_bundle_with_retry(d)
        except Exception:
            return False


class AuthClient:

    def __init__(self, server_url: str, software_name: str, device_id: Optional[str]=None, device_info: Optional[Dict[str, Any]]=None, client_secret: Optional[str]=None, cache_validity_days: int=7, check_interval_days: int=2, debug: bool=False, software_version: Optional[str]='0.0.0'):
        self.debug = debug
        self.logger = logging.getLogger('py_auth_client')
        if debug:
            if not self.logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter('[py][%(levelname)s] %(message)s')
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
            self.logger.setLevel(logging.DEBUG)
            self.logger.propagate = False
        self.server_url = server_url.rstrip('/')
        self.software_name = software_name
        self.software_version = software_version
        self._storage_base = get_client_storage_root()
        _state_path = bundle_path(self.server_url, self._storage_base)
        self._state_bundle_existed_before_init = _state_path.exists()
        facts: Optional[Dict[str, Any]] = None
        if device_id:
            _loaded_pid: Any = _PERSISTED_DEVICE_ID_NOT_PREFETCHED
        else:
            _loaded_pid = load_persisted_device_id(self.server_url, software_name, base_dir=self._storage_base)
        need_facts_for_new_id = not device_id and _loaded_pid is not _PERSISTED_DEVICE_ID_NOT_PREFETCHED and (not _loaded_pid)
        _prefetch_ex: Optional[ThreadPoolExecutor] = None
        _prefetch_fut: Optional[Future] = None
        if need_facts_for_new_id:
            facts = collect_device_facts(for_device_id=True)
            _prefetch_ex = ThreadPoolExecutor(max_workers=1)
            _prefetch_fut = _prefetch_ex.submit(collect_device_facts)
        self.device_id = build_device_id(self.server_url, device_id, facts if facts is not None else {}, software_name, base_dir=self._storage_base, persisted_device_id=_loaded_pid if not device_id else _PERSISTED_DEVICE_ID_NOT_PREFETCHED)
        try:
            self.hostname = socket.gethostname()
        except Exception:
            try:
                self.hostname = (facts or {}).get('hostname_value') or 'Unknown'
            except Exception:
                self.hostname = 'Unknown'
        self._device_info_deferred = False
        if device_info is not None:
            self.device_info = dict(device_info)
        elif need_facts_for_new_id:
            self._device_info_deferred = True
            self.device_info = {}
        elif facts is not None:
            self.device_info = build_device_info(facts, device_info)
        else:
            self._device_info_deferred = True
            self.device_info = {}
        self.device_info['software_version'] = self.software_version
        self.device_info['sdk'] = {'language': 'python', 'sdk_name': 'py_auth_client', 'sdk_version': __version__, 'runtime': f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'}
        self.client_secret = client_secret or os.getenv('CLIENT_SECRET', '')
        if not self.client_secret:
            raise ValueError('CLIENT_SECRET未配置！请在初始化时传入client_secret参数，或设置环境变量CLIENT_SECRET。这是安全要求，必须配置。')
        self._cipher: Optional[Any] = None
        self.cache = AuthCache(self._storage_base, self.device_id, self.server_url, software_name=self.software_name, cache_validity_days=cache_validity_days, check_interval_days=check_interval_days)
        self._facts_prefetch_executor: Optional[ThreadPoolExecutor] = None
        self._facts_prefetch_future: Optional[Future] = None
        if self._device_info_deferred:
            _snap = self.cache.load_device_info_snapshot()
            if _snap:
                self.device_info = _snap
                self.device_info['software_version'] = self.software_version
                self.device_info['sdk'] = {'language': 'python', 'sdk_name': 'py_auth_client', 'sdk_version': __version__, 'runtime': f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'}
                self._device_info_deferred = False
        if self._device_info_deferred:
            if need_facts_for_new_id and _prefetch_fut is not None:
                self._facts_prefetch_future = _prefetch_fut
                self._facts_prefetch_executor = _prefetch_ex
            else:
                self._facts_prefetch_executor = ThreadPoolExecutor(max_workers=1)
                self._facts_prefetch_future = self._facts_prefetch_executor.submit(collect_device_facts)

    def _log_debug(self, message: str):
        if self.debug:
            try:
                self.logger.debug(message)
            except Exception:
                pass

    def _ensure_full_device_info(self) -> None:
        if not self._device_info_deferred:
            return
        fut = self._facts_prefetch_future
        self._facts_prefetch_future = None
        ex = self._facts_prefetch_executor
        self._facts_prefetch_executor = None
        if fut is not None:
            try:
                facts = fut.result()
            except Exception:
                facts = collect_device_facts()
            if ex is not None:
                try:
                    ex.shutdown(wait=False)
                except Exception:
                    pass
        else:
            facts = collect_device_facts()
        self.device_info = build_device_info(facts, None)
        self.device_info['software_version'] = self.software_version
        self.device_info['sdk'] = {'language': 'python', 'sdk_name': 'py_auth_client', 'sdk_version': __version__, 'runtime': f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'}
        self._device_info_deferred = False

    def _format_remaining_time(self, cached_at: float) -> str:
        if not cached_at or cached_at <= 0:
            return '未知'
        now = time.time()
        elapsed = now - cached_at
        remaining = self.cache.cache_validity_seconds - elapsed
        if remaining <= 0:
            return '已过期'
        days = int(remaining // _SECONDS_PER_DAY)
        hours = int(remaining % _SECONDS_PER_DAY // _SECONDS_PER_HOUR)
        minutes = int(remaining % _SECONDS_PER_HOUR // _SECONDS_PER_MINUTE)
        parts = []
        if days > 0:
            parts.append(f'{days}天')
        if hours > 0:
            parts.append(f'{hours}小时')
        if minutes > 0 or not parts:
            parts.append(f'{minutes}分钟')
        return ''.join(parts) if parts else '0分钟'

    def _ensure_cipher(self) -> None:
        if self._cipher is not None:
            return
        from cryptography.fernet import Fernet
        key_bytes = hashlib.sha256(self.client_secret.encode('utf-8')).digest()
        key = base64.urlsafe_b64encode(key_bytes)
        self._cipher = Fernet(key)

    def _encrypt_data(self, data: Dict[str, Any]) -> str:
        self._ensure_cipher()
        json_str = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        return self._cipher.encrypt(json_str.encode('utf-8')).decode('utf-8')

    def _decrypt_data(self, encrypted_data: str) -> Optional[Dict[str, Any]]:
        self._ensure_cipher()
        try:
            decrypted = self._cipher.decrypt(encrypted_data.encode('utf-8'))
            return json.loads(decrypted.decode('utf-8'))
        except Exception:
            return None

    def _post_heartbeat(self, di: Dict[str, Any], heartbeat_times: int) -> Dict[str, Any]:
        import requests

        di = copy.deepcopy(di) if di else {}
        sk = dict(di.get('sdk') or {})
        sk['heartbeat_times'] = heartbeat_times
        di['sdk'] = sk
        request_data = {'device_id': self.device_id, 'software_name': self.software_name, 'device_info': di}
        try:
            response = requests.post(f'{self.server_url}/api/auth/heartbeat', json={'encrypted_data': self._encrypt_data(request_data)}, timeout=_DEFAULT_HEARTBEAT_TIMEOUT_SEC)
            if response.status_code == 200:
                decrypted = self._decrypt_data(response.json().get('encrypted_data', ''))
                if decrypted:
                    self._log_debug(f"在线订阅成功，authorized={decrypted.get('authorized')}")
                    return {'authorized': decrypted.get('authorized', False), 'message': decrypted.get('message', ''), 'success': True, 'from_cache': False}
                self._log_debug('在线订阅响应解密失败')
                return {'authorized': False, 'message': '解密响应失败', 'success': False, 'from_cache': False}
            error_msg = response.json().get('detail', f'服务器错误: {response.status_code}') if response.status_code == 403 else f'服务器错误: {response.status_code}'
            self._log_debug(f'在线订阅失败，status={response.status_code}, message={error_msg}')
            return {'authorized': False, 'message': error_msg, 'success': False, 'from_cache': False, 'is_auth_error': response.status_code == 403}
        except requests.exceptions.RequestException as e:
            self._log_debug(f'在线订阅请求异常: {str(e)}')
            return {'authorized': False, 'message': f'连接失败: {str(e)}', 'success': False, 'from_cache': False}
        except Exception as e:
            self._log_debug(f'在线订阅未知异常: {str(e)}')
            return {'authorized': False, 'message': f'未知错误: {str(e)}', 'success': False, 'from_cache': False}

    def _check_online_worker(self, heartbeat_times: int) -> Dict[str, Any]:
        from concurrent.futures import ALL_COMPLETED, wait

        _need_pub = self._device_info_deferred or _device_info_lacks_nonblank_public_ip(self.device_info)
        try:
                                                                             
            _pool = ThreadPoolExecutor(max_workers=2)
            try:
                _fe = _pool.submit(self._ensure_full_device_info)
                _fi = _pool.submit(fetch_public_ip) if _need_pub else None
                _futs = [_fe] + ([_fi] if _fi is not None else [])
                wait(_futs, return_when=ALL_COMPLETED)
                _fe.result()
                pub = _fi.result() if _fi is not None else ''
            finally:
                _pool.shutdown(wait=False)
            self._log_debug('开始在线订阅请求...')
            di = dict(self.device_info)
            nw = dict(di.get('network') or {})
            if pub:
                nw['public_ip'] = pub
            if nw:
                di['network'] = nw
            if pub:
                self.device_info['network'] = dict(nw)
            return self._post_heartbeat(di, heartbeat_times)
        except Exception as e:
            self._log_debug(f'在线订阅未知异常: {str(e)}')
            return {'authorized': False, 'message': f'未知错误: {str(e)}', 'success': False, 'from_cache': False}

    def _check_online_fast_worker(self, heartbeat_times: int) -> Dict[str, Any]:
        self._log_debug('轻量在线订阅请求（不等待全量 device_info / 公网 IP）...')
        di = copy.deepcopy(self.device_info) if self.device_info else {}
        di['software_version'] = self.software_version
        _base_sdk = {'language': 'python', 'sdk_name': 'py_auth_client', 'sdk_version': __version__, 'runtime': f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'}
        sk = dict(di.get('sdk') or {})
        for _k, _v in _base_sdk.items():
            sk.setdefault(_k, _v)
        di['sdk'] = sk
        if not di.get('hostname'):
            di['hostname'] = self.hostname
        di.setdefault('platform', platform.platform())
        return self._post_heartbeat(di, heartbeat_times)

    def _check_online_fast(self, heartbeat_times: int) -> Dict[str, Any]:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FuturesTimeout

        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(self._check_online_fast_worker, heartbeat_times)
            try:
                return future.result(timeout=_ONLINE_CHECK_FAST_WALL_SEC)
            except _FuturesTimeout:
                self._log_debug(f'轻量在线订阅超出时限 {_ONLINE_CHECK_FAST_WALL_SEC:g}s')
                return {'authorized': False, 'message': f'连接失败: 轻量请求超时（{_ONLINE_CHECK_FAST_WALL_SEC:g}s）', 'success': False, 'from_cache': False}
        finally:
            executor.shutdown(wait=False)

    def _check_online(self, heartbeat_times: int) -> Dict[str, Any]:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FuturesTimeout
        _wall = _online_check_effective_wall_sec(self._device_info_deferred or _device_info_lacks_nonblank_public_ip(self.device_info))
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(self._check_online_worker, heartbeat_times)
            try:
                return future.result(timeout=_wall)
            except _FuturesTimeout:
                self._log_debug(f'在线订阅超出总时限 {_wall}s（含 device_info 推迟时的全量采集 + 公网 IP + 心跳；Windows 等对无服务地址的 TCP 重传可能绕过单阶段 timeout）')
                return {'authorized': False, 'message': f'连接失败: 请求超时（在线阶段墙钟上限 {_wall:g}s）', 'success': False, 'from_cache': False}
        finally:
            executor.shutdown(wait=False)

    def _write_check_cache_retries(self, online_result: Dict[str, Any], heartbeat_times_if_authorized: Optional[int]) -> bool:
        hb = heartbeat_times_if_authorized if online_result.get('authorized') else None
        snap = copy.deepcopy(self.device_info) if online_result.get('authorized') else None
        saved = False
        for _attempt in range(3):
            if self.cache.save_cache(online_result['authorized'], '', heartbeat_times=hb, device_info_snapshot=snap):
                saved = True
                break
            time.sleep(0.05)
        self._log_debug(f'写入缓存结果: {saved} -> {self.cache.cache_file}')
        return saved

    def check_authorization_progressive(self, force_online: bool=False) -> Dict[str, Any]:
        cache_data = None
        stored_hb = 0
        try:
            if self.debug:
                cf = self.cache.cache_file
                now = cf.exists()
                pre = self._state_bundle_existed_before_init
                if now and pre:
                    state_desc = '启动前已存在'
                elif now and (not pre):
                    state_desc = '启动前不存在，构造客户端时已新建（device_id 持久化）'
                elif not now and pre:
                    state_desc = '启动前曾有，当前缺失（异常）'
                else:
                    state_desc = '不存在（持久化可能失败）'
                try:
                    raw_sz = cf.stat().st_size if cf.exists() else 0
                except Exception:
                    raw_sz = 0
                self._log_debug(f'状态包: {cf} | {state_desc} | 密文 {raw_sz} bytes')
            cache_data, stored_hb = self.cache._snapshot_auth_row()
        except Exception:
            self._log_debug('读取缓存异常')
            cache_data = None
            stored_hb = 0
        cache_valid = self.cache._is_cache_valid_dict(cache_data)
        if cache_valid:
            self._log_debug('本地缓存仍在有效期内（在线失败时可作后备）')
            self._log_debug('缓存有效，继续尝试在线订阅来更新订阅')
        elif cache_data:
            self._log_debug('缓存存在但已过期，准备发起在线订阅请求')
        else:
            self._log_debug('未找到缓存，准备发起在线订阅请求')
        next_hb = stored_hb + 1
        _ = force_online

        r_fast = self._check_online_fast(next_hb)
        if r_fast.get('success'):
            if r_fast.get('authorized'):
                self._log_debug('在线订阅成功，更新缓存')
                self._write_check_cache_retries(r_fast, next_hb)
                self._log_debug('轻量心跳已落盘，发起全量 device_info 补全心跳...')
                r_full = self._check_online(next_hb + 1)
                if r_full.get('success'):
                    self._log_debug('在线订阅成功，更新缓存')
                    self._write_check_cache_retries(r_full, (next_hb + 1) if r_full.get('authorized') else None)
                    return r_full
                gc = self.cache.get_cache()
                if gc and self.cache.is_cache_valid():
                    remaining = self._format_remaining_time(gc.get('cached_at', 0))
                    self._log_debug(f'补全心跳失败，沿用轻量结果，订阅剩余时间: {remaining}')
                    return {'authorized': True, 'message': gc.get('message', ''), 'success': True, 'from_cache': True}
                return r_full
            self._write_check_cache_retries(r_fast, None)
            return r_fast

        online_result = self._check_online(next_hb)
        if online_result['success']:
            self._log_debug('在线订阅成功，更新缓存')
            self._write_check_cache_retries(online_result, next_hb if online_result['authorized'] else None)
            return online_result
        if cache_valid:
            cached_at = cache_data.get('cached_at', 0)
            remaining = self._format_remaining_time(cached_at)
            self._log_debug(f"在线订阅失败，但缓存有效，使用缓存结果: {online_result.get('message')}，订阅剩余时间: {remaining}")
            return {'authorized': True, 'message': cache_data.get('message', ''), 'success': True, 'from_cache': True}
        if cache_data:
            cached_at = cache_data.get('cached_at', 0)
            remaining = self._format_remaining_time(cached_at)
            self._log_debug(f"在线订阅失败，缓存已过期，返回失败结果: {online_result.get('message')}，订阅剩余时间: {remaining}")
        else:
            self._log_debug(f"在线订阅失败，返回失败结果: {online_result.get('message')}")
        return online_result

    def check_authorization(self, force_online: bool=False) -> Dict[str, Any]:
        cache_data = None
        stored_hb = 0
        try:
            if self.debug:
                cf = self.cache.cache_file
                now = cf.exists()
                pre = self._state_bundle_existed_before_init
                if now and pre:
                    state_desc = '启动前已存在'
                elif now and (not pre):
                    state_desc = '启动前不存在，构造客户端时已新建（device_id 持久化）'
                elif not now and pre:
                    state_desc = '启动前曾有，当前缺失（异常）'
                else:
                    state_desc = '不存在（持久化可能失败）'
                try:
                    raw_sz = cf.stat().st_size if cf.exists() else 0
                except Exception:
                    raw_sz = 0
                self._log_debug(f'状态包: {cf} | {state_desc} | 密文 {raw_sz} bytes')
            cache_data, stored_hb = self.cache._snapshot_auth_row()
        except Exception:
            self._log_debug('读取缓存异常')
            cache_data = None
            stored_hb = 0
        cache_valid = self.cache._is_cache_valid_dict(cache_data)
        if cache_valid:
            self._log_debug('本地缓存仍在有效期内（在线失败时可作后备）')
            self._log_debug('缓存有效，继续尝试在线订阅来更新订阅')
        elif cache_data:
            self._log_debug('缓存存在但已过期，准备发起在线订阅请求')
        else:
            self._log_debug('未找到缓存，准备发起在线订阅请求')
        next_hb = stored_hb + 1
        _ = force_online
        online_result = self._check_online(next_hb)
        if online_result['success']:
            self._log_debug('在线订阅成功，更新缓存')
            self._write_check_cache_retries(online_result, next_hb if online_result['authorized'] else None)
            return online_result
        if cache_valid:
            cached_at = cache_data.get('cached_at', 0)
            remaining = self._format_remaining_time(cached_at)
            self._log_debug(f"在线订阅失败，但缓存有效，使用缓存结果: {online_result.get('message')}，订阅剩余时间: {remaining}")
            return {'authorized': True, 'message': cache_data.get('message', ''), 'success': True, 'from_cache': True}
        if cache_data:
            cached_at = cache_data.get('cached_at', 0)
            remaining = self._format_remaining_time(cached_at)
            self._log_debug(f"在线订阅失败，缓存已过期，返回失败结果: {online_result.get('message')}，订阅剩余时间: {remaining}")
        else:
            self._log_debug(f"在线订阅失败，返回失败结果: {online_result.get('message')}")
        return online_result

    def require_authorization(self, raise_exception: bool=True, force_online: bool=False) -> bool:
        result = self.check_authorization(force_online=force_online)
        if not result['success'] or not result['authorized']:
            if raise_exception:
                raise AuthorizationError(message=result['message'], result=result, device_id=self.device_id, server_url=self.server_url)
            return False
        return True

    def can_soft_launch(self) -> bool:
        c = self.cache.get_cache()
        return bool(c and c.get("authorized") and self.cache.is_cache_valid())

    def submit_check_authorization(self, force_online: bool=False) -> Future:
        return get_auth_background_executor().submit(self.check_authorization, force_online)

    def submit_check_authorization_progressive(self, force_online: bool=False) -> Future:
        return get_auth_background_executor().submit(self.check_authorization_progressive, force_online)

    def submit_require_authorization(self, *, raise_exception: bool=True, force_online: bool=False) -> Future:
        return get_auth_background_executor().submit(self.require_authorization, raise_exception, force_online)

    def start_background_refresh(self, *, force_online: bool=False, on_done: Optional[Callable[[Dict[str, Any]], None]]=None) -> tuple[bool, Future]:
        soft = self.can_soft_launch()
        fut = self.submit_check_authorization_progressive(force_online)
        if on_done is not None:

            def _cb(f: Future) -> None:
                try:
                    on_done(f.result())
                except Exception as e:
                    on_done({'authorized': False, 'success': False, 'from_cache': False, 'message': str(e)})
            fut.add_done_callback(_cb)
        return (soft, fut)

    def clear_cache(self) -> bool:
        return self.cache.clear_cache()

    def get_authorization_info(self) -> Dict[str, Any]:
        cache = self.cache.get_cache()
        if cache:
            info = {'authorized': cache.get('authorized', False), 'success': True, 'from_cache': True, 'message': cache.get('message', ''), 'device_id': self.device_id, 'server_url': self.server_url}
            cached_at = cache.get('cached_at', 0)
            remaining = self._format_remaining_time(cached_at)
            info['remaining_time'] = remaining
            info['cache_valid'] = self.cache.is_cache_valid()
            info['cached_at'] = cached_at
            if cached_at > 0:
                info['cached_at_readable'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(cached_at))
        else:
            info = {'authorized': False, 'success': False, 'from_cache': False, 'message': '无本地授权缓存', 'device_id': self.device_id, 'server_url': self.server_url, 'remaining_time': '无缓存', 'cache_valid': False}
        if self.debug:
            try:
                blob = json.dumps(info, ensure_ascii=False, indent=2)
                print(f'[py][DEBUG] 授权信息摘要:\n{blob}')
            except Exception:
                pass
        return info

    def get_cache_info(self) -> Optional[Dict[str, Any]]:
        cache = self.cache.get_cache()
        if not cache:
            return None
        now = time.time()
        cached_at = cache.get('cached_at', 0)
        return {'authorized': cache.get('authorized'), 'message': cache.get('message'), 'cached_at': cached_at, 'last_success_at': cached_at, 'cache_age_days': (now - cached_at) / _SECONDS_PER_DAY, 'cache_valid': self.cache.is_cache_valid(), 'needs_check': self.cache.needs_check(), 'cache_file': str(self.cache.cache_file)}

class AuthorizationError(Exception):

    def __init__(self, message: str, result: Optional[Dict[str, Any]]=None, device_id: Optional[str]=None, server_url: Optional[str]=None):
        self.message = message
        self.result = result
        self.device_id = device_id
        self.server_url = server_url
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message

    def __repr__(self) -> str:
        parts = [f"AuthorizationError('{self.message}'"]
        if self.device_id:
            parts.append(f", device_id='{self.device_id}'")
        if self.server_url:
            parts.append(f", server_url='{self.server_url}'")
        parts.append(')')
        return ', '.join(parts)

    @property
    def is_network_error(self) -> bool:
        message_lower = self.message.lower()
        check_message = self.result.get('message', '').lower() if self.result else ''
        network_keywords = ['连接失败', '连接', 'network', 'timeout', 'connection']
        return any((keyword in check_message or keyword in message_lower for keyword in network_keywords))

    @property
    def is_unauthorized(self) -> bool:
        if self.result:
            return not self.result.get('authorized', False) and self.result.get('success', False)
        return '未授权' in self.message or '禁用' in self.message

    @property
    def is_validation_error(self) -> bool:
        if self.result:
            return not self.result.get('success', False)
        return '无法验证授权' in self.message or '验证失败' in self.message

def check_authorization(server_url: str, software_name: str, device_id: Optional[str]=None, force_online: bool=False) -> bool:
    client = AuthClient(server_url, software_name, device_id)
    result = client.check_authorization(force_online=force_online)
    return result.get('authorized', False) and result.get('success', False)
