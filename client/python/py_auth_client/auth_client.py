"""
Python授权客户端模块
供其他软件使用，用于检查设备授权状态

缓存机制：
- 缓存有效期：7天
- 始终向服务端发送请求并更新本地缓存
- 如果在线验证失败但缓存仍在有效期内，使用缓存结果作为后备
- 缓存文件经过混淆加密，隐藏在系统目录中

网络传输：
- 使用AES加密保护请求和响应数据
"""
import requests
import logging
import platform
import socket
import hashlib
import uuid
import json
import os
import time
import struct
import zlib
import base64
from typing import Optional, Dict, Any
from pathlib import Path
import psutil
from cryptography.fernet import Fernet
import logging

from .device_utils import (
    build_device_id,
    build_device_info,
    collect_device_facts,
)

class AuthCache:
    """授权缓存管理（混淆加密）"""
    
    def __init__(
        self, 
        cache_dir: Optional[str] = None, 
        device_id: str = "",
        server_url: str = "",
        software_name: str = "",
        cache_validity_days: int = 7,
        check_interval_days: int = 2
    ):
        """
        初始化缓存管理器
        
        Args:
            cache_dir: 缓存目录，默认使用系统隐藏目录
            device_id: 设备ID，用于生成缓存文件名和加密密钥
            server_url: 服务器URL，用于生成加密密钥
            software_name: 软件名称（必填），用于区分不同软件的缓存
            cache_validity_days: 缓存有效期（天），默认7天
            check_interval_days: 检查间隔（天），默认2天
        """
        self.cache_validity_days = cache_validity_days
        self.cache_validity_seconds = cache_validity_days * 24 * 60 * 60
        self.check_interval_days = check_interval_days
        self.check_interval_seconds = check_interval_days * 24 * 60 * 60
        self.device_id = device_id
        self.software_name = software_name
        
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            system = platform.system()
            home = Path.home()
            windows_base = Path(os.environ.get('LOCALAPPDATA', home / 'AppData' / 'Local'))
            self.cache_dir = {
                'Windows': windows_base / "Microsoft/CLR_v4.0",
                'Darwin': Path(f"{home}/Library/Caches/.com.apple.metadata"),
            }.get(system, Path(f"{home}/.cache/.fontconfig"))
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成看起来像系统文件的文件名（基于 device_id + software_name，确保不同软件使用不同缓存）
        cache_key = f"{device_id}:{self.software_name}"
        file_hash = hashlib.md5(cache_key.encode()).hexdigest()[:12]
        cache_filename = f"runtime_{file_hash}.dat"
        self.cache_filename = cache_filename
        self.cache_file = self.cache_dir / cache_filename
        
        # 生成加密密钥（基于设备ID、软件名称和服务器URL）
        encrypt_material = f"{server_url}:{device_id}:{self.software_name}:obfuscate_v1"
        self.encrypt_key = hashlib.sha256(encrypt_material.encode()).digest()
        self.logger = logging.getLogger("py_auth_client")
    
    def _obfuscate(self, data: bytes) -> bytes:
        """
        混淆数据（XOR加密 + 压缩 + Base64变种）
        
        Args:
            data: 原始数据
            
        Returns:
            混淆后的数据
        """
        # 1. 压缩数据
        compressed = zlib.compress(data, level=9)
        
        # 2. XOR混淆
        key = self.encrypt_key
        key_len = len(key)
        xored = bytes([compressed[i] ^ key[i % key_len] for i in range(len(compressed))])
        
        # 3. 添加随机前缀（基于时间的伪随机，但可重复）
        time_seed = int(time.time()) // 3600  # 每小时变化
        prefix_seed = hashlib.md5(f"{self.device_id}:{self.software_name}:{time_seed}".encode()).digest()[:4]
        
        # 4. 打包：前缀(4) + 长度(4) + 数据
        packed = prefix_seed + struct.pack('>I', len(xored)) + xored
        
        # 5. 再次XOR整体
        final_key = hashlib.sha256(self.encrypt_key + prefix_seed).digest()
        final = bytes([packed[i] ^ final_key[i % len(final_key)] for i in range(len(packed))])
        
        return final
    
    def _deobfuscate(self, data: bytes) -> Optional[bytes]:
        """
        解除混淆
        
        Args:
            data: 混淆后的数据
            
        Returns:
            原始数据或None（如果解密失败）
        """
        try:
            if len(data) < 8:
                return None
            
            # 尝试多个可能的time_seed（允许小时偏差）
            current_hour = int(time.time()) // 3600
            # 允许更宽的偏移（覆盖完整缓存有效期），避免超过2小时后无法解密
            max_offset = max(2, self.cache_validity_days * 24 + 12)  # 7天≈168小时
            for hour_offset in range(-max_offset, max_offset + 1):
                time_seed = current_hour + hour_offset
                prefix_seed = hashlib.md5(f"{self.device_id}:{self.software_name}:{time_seed}".encode()).digest()[:4]
                
                # 1. 解除最外层XOR
                final_key = hashlib.sha256(self.encrypt_key + prefix_seed).digest()
                unpacked = bytes([data[i] ^ final_key[i % len(final_key)] for i in range(len(data))])
                
                # 2. 验证前缀
                if unpacked[:4] != prefix_seed:
                    continue
                
                # 3. 解包长度和数据
                length = struct.unpack('>I', unpacked[4:8])[0]
                if length > len(unpacked) - 8:
                    continue
                
                xored = unpacked[8:8+length]
                
                # 4. 解除XOR混淆
                key = self.encrypt_key
                key_len = len(key)
                compressed = bytes([xored[i] ^ key[i % key_len] for i in range(len(xored))])
                
                # 5. 解压
                try:
                    original = zlib.decompress(compressed)
                    return original
                except:
                    continue
            
            return None
        except Exception:
            try:
                self.logger.debug("缓存解密失败")
            except Exception:
                pass
            return None
    
    def get_cache(self) -> Optional[Dict[str, Any]]:
        """
        获取缓存数据
        
        Returns:
            缓存数据或None（如果缓存不存在或无法读取）
        """
        try:
            if not self.cache_file.exists():
                return None
            
            with open(self.cache_file, 'rb') as f:
                encrypted_data = f.read()
            
            try:
                self.logger.debug(f"缓存文件: {self.cache_file} 大小: {len(encrypted_data)} bytes")
            except Exception:
                pass
            
            decrypted = self._deobfuscate(encrypted_data)
            if not decrypted:
                try:
                    self.logger.debug("缓存解密结果为空")
                except Exception:
                    pass
                return None
            
            cache_data = json.loads(decrypted.decode('utf-8'))
            
            return {
                'authorized': cache_data.get('a'),
                'message': cache_data.get('m'),
                'cached_at': cache_data.get('c'),
                'last_check': cache_data.get('l')
            }
        except Exception as e:
            try:
                self.logger.debug(f"读取缓存异常: {e}")
            except Exception:
                pass
            return None
    
    def save_cache(
        self, 
        authorized: bool, 
        message: str,
        *,
        cached_at: Optional[float] = None,
        last_check: Optional[float] = None
    ) -> bool:
        """
        保存缓存数据（混淆加密）
        
        Args:
            authorized: 授权状态
            message: 消息
            
        Returns:
            是否保存成功
        """
        try:
            now = time.time()
            cached_ts = cached_at if cached_at is not None else now
            last_check_ts = last_check if last_check is not None else now
            
            # 使用简短的键名减少特征
            cache_data = {
                'a': authorized,      # authorized
                'm': message,         # message
                'c': cached_ts,       # cached_at
                'l': last_check_ts,   # last_check
                # 添加一些干扰数据
                'v': 2,               # version (干扰)
                'f': hashlib.md5(str(time.time()).encode()).hexdigest()[:8]  # 干扰
            }
            
            json_data = json.dumps(cache_data, ensure_ascii=False, separators=(',', ':'))
            
            encrypted = self._obfuscate(json_data.encode('utf-8'))
            
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            
            try:
                with open(self.cache_file, 'wb') as f:
                    f.write(encrypted)
            except (PermissionError, OSError) as e:
                try:
                    self.logger.debug(f"写入缓存失败，尝试删除后重新创建: {e}")
                    if self.cache_file.exists():
                        # 尝试移除只读属性（Windows）
                        if platform.system() == 'Windows':
                            try:
                                import ctypes
                                ctypes.windll.kernel32.SetFileAttributesW(str(self.cache_file), 0x80)  # NORMAL
                            except:
                                pass
                        self.cache_file.unlink()
                        self.logger.debug("已删除旧缓存文件")
                    with open(self.cache_file, 'wb') as f:
                        f.write(encrypted)
                    self.logger.debug("重新创建缓存文件成功")
                except Exception as retry_e:
                    try:
                        self.logger.debug(f"删除并重新创建缓存文件失败: {retry_e}")
                    except Exception:
                        pass
                    raise e
            
            # 尝试隐藏文件（Windows）
            if platform.system() == 'Windows':
                try:
                    import ctypes
                    ctypes.windll.kernel32.SetFileAttributesW(str(self.cache_file), 0x02)  # HIDDEN
                except:
                    pass
            
            return True
        except Exception as e:
            try:
                self.logger.debug(f"保存缓存失败: {e}")
            except Exception:
                pass
            return False
    
    def update_last_check(self) -> bool:
        """
        更新最后检查时间
        
        Returns:
            是否更新成功
        """
        try:
            cache = self.get_cache()
            if cache:
                return self.save_cache(
                    cache.get('authorized', False),
                    cache.get('message', ''),
                    cached_at=cache.get('cached_at', time.time()),
                    last_check=time.time()
                )
            return False
        except Exception:
            return False
    
    def is_cache_valid(self) -> bool:
        """
        检查缓存是否在有效期内
        
        Returns:
            缓存是否有效
        """
        cache = self.get_cache()
        if not cache:
            return False
        
        cached_at = cache.get('cached_at', 0)
        elapsed = time.time() - cached_at
        
        return elapsed < self.cache_validity_seconds
    
    def needs_check(self) -> bool:
        """
        检查是否需要在线验证（超过检查间隔）
        
        Returns:
            是否需要检查
        """
        cache = self.get_cache()
        if not cache:
            return True
        
        last_check = cache.get('last_check', 0)
        elapsed = time.time() - last_check
        
        return elapsed >= self.check_interval_seconds
    
    def get_cached_result(self) -> Optional[Dict[str, Any]]:
        """
        获取缓存的授权结果
        
        Returns:
            缓存的授权结果或None
        """
        cache = self.get_cache()
        if not cache:
            return None
        
        return {
            'authorized': cache.get('authorized', False),
            'message': cache.get('message', ''),
            'from_cache': True,
            'cached_at': cache.get('cached_at', 0),
            'last_check': cache.get('last_check', 0)
        }
    
    def clear_cache(self) -> bool:
        """
        清除缓存
        
        Returns:
            是否清除成功
        """
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
            return True
        except Exception:
            return False


class AuthClient:
    """授权客户端（带缓存功能）"""
    
    def __init__(
        self, 
        server_url: str, 
        software_name: str,
        device_id: Optional[str] = None, 
        device_info: Optional[Dict[str, Any]] = None,
        client_secret: Optional[str] = None,
        cache_dir: Optional[str] = None,
        enable_cache: bool = True,
        cache_validity_days: int = 7,
        check_interval_days: int = 2,
        debug: bool = False,
        software_version: Optional[str] = "0.0.0"
    ):
        """
        初始化授权客户端
        
        Args:
            server_url: 授权服务器地址，例如: http://localhost:8000
            software_name: 软件名称（必填）
            device_id: 设备ID，如果不提供则自动生成
            device_info: 设备附加信息（可选），如果不提供则自动收集系统信息
            client_secret: 客户端密钥（用于AES加密），如果不提供则从环境变量CLIENT_SECRET读取
            cache_dir: 缓存目录（可选）
            enable_cache: 是否启用缓存，默认True
            cache_validity_days: 缓存有效期（天），默认7天
            check_interval_days: 检查间隔（天），默认2天
            debug: 是否输出调试日志
        """
        self.debug = debug
        self.logger = logging.getLogger("py_auth_client")
        if debug:
            if not self.logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter("[py-auth-client][%(levelname)s] %(message)s")
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
            self.logger.setLevel(logging.DEBUG)
            self.logger.propagate = False
        
        self.server_url = server_url.rstrip('/')
        system = platform.system()
        facts = collect_device_facts()
        mac_value = facts.get("mac")
        
        self.software_name = software_name
        self.software_version = software_version
        
        # 生成 device_id 时包含 software_name，确保同一设备上的不同软件有不同的 device_id
        self.device_id = build_device_id(self.server_url, device_id, facts, software_name)
        
        try:
            self.hostname = socket.gethostname()
        except Exception:
            try:
                self.hostname = facts.get("hostname_value") or "Unknown"
            except Exception:
                self.hostname = "Unknown"
        
        if device_info is not None:
            self.device_info = dict(device_info)
        else:
            self.device_info = build_device_info(facts, device_info)
        self.device_info["software_version"] = self.software_version
        self.client_secret = client_secret or os.getenv("CLIENT_SECRET", "")
        if not self.client_secret:
            raise ValueError(
                "CLIENT_SECRET未配置！请在初始化时传入client_secret参数，"
                "或设置环境变量CLIENT_SECRET。这是安全要求，必须配置。"
            )
        
        self._init_encryption_key()
        
        self.enable_cache = enable_cache
        if enable_cache:
            self.cache = AuthCache(
                cache_dir, 
                self.device_id,
                self.server_url,
                self.software_name,
                cache_validity_days=cache_validity_days,
                check_interval_days=check_interval_days
            )
        else:
            self.cache = None
    
    def _log_debug(self, message: str):
        if self.debug:
            try:
                self.logger.debug(message)
            except Exception:
                pass
    
    def _format_remaining_time(self, cached_at: float) -> str:
        """
        格式化剩余时间（从缓存时间开始计算）
        
        Args:
            cached_at: 缓存时间戳
            
        Returns:
            格式化的剩余时间字符串，如 "5天12小时30分钟"
        """
        if not cached_at or cached_at <= 0:
            return "未知"
        
        if not self.cache:
            return "未知"
        
        now = time.time()
        elapsed = now - cached_at
        remaining = self.cache.cache_validity_seconds - elapsed
        
        if remaining <= 0:
            return "已过期"
        
        days = int(remaining // 86400)
        hours = int((remaining % 86400) // 3600)
        minutes = int((remaining % 3600) // 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0 or not parts:
            parts.append(f"{minutes}分钟")
        
        return "".join(parts) if parts else "0分钟"
    
    def _get_mac_address(self) -> Optional[str]:
        """获取主网卡MAC地址"""
        try:
            mac_int = uuid.getnode()
            # 检查是否是随机生成的MAC（第8位为1表示随机）
            if (mac_int >> 40) & 1:
                return None
            mac = ':'.join(['{:02x}'.format((mac_int >> elements) & 0xff) 
                           for elements in range(0, 2*6, 2)][::-1])
            return mac
        except Exception:
            return None
    
    def _init_encryption_key(self):
        """初始化AES加密密钥"""
        # 直接使用CLIENT_SECRET的SHA256哈希作为密钥
        key_bytes = hashlib.sha256(self.client_secret.encode('utf-8')).digest()
        key = base64.urlsafe_b64encode(key_bytes)
        self.cipher = Fernet(key)
    
    def _encrypt_data(self, data: Dict[str, Any]) -> str:
        """加密数据"""
        json_str = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        return self.cipher.encrypt(json_str.encode('utf-8')).decode('utf-8')
    
    def _decrypt_data(self, encrypted_data: str) -> Optional[Dict[str, Any]]:
        """解密数据"""
        try:
            decrypted = self.cipher.decrypt(encrypted_data.encode('utf-8'))
            return json.loads(decrypted.decode('utf-8'))
        except Exception:
            return None
    
    def _check_online(self) -> Dict[str, Any]:
        """在线检查授权状态（使用AES加密）"""
        try:
            self._log_debug("开始在线订阅请求...")
            request_data = {
                "device_id": self.device_id,
                "software_name": self.software_name,
                "device_info": self.device_info
            }
            
            response = requests.post(
                f"{self.server_url}/api/auth/heartbeat",
                json={"encrypted_data": self._encrypt_data(request_data)},
                timeout=10
            )
            
            if response.status_code == 200:
                decrypted = self._decrypt_data(response.json().get("encrypted_data", ""))
                if decrypted:
                    self._log_debug(f"在线订阅成功，authorized={decrypted.get('authorized')}")
                    return {
                        'authorized': decrypted.get('authorized', False),
                        'message': decrypted.get('message', ''),
                        'success': True,
                        'from_cache': False
                    }
                self._log_debug("在线订阅响应解密失败")
                return {'authorized': False, 'message': '解密响应失败', 'success': False, 'from_cache': False}
            
            error_msg = response.json().get('detail', f'服务器错误: {response.status_code}') if response.status_code == 403 else f'服务器错误: {response.status_code}'
            self._log_debug(f"在线订阅失败，status={response.status_code}, message={error_msg}")
            return {
                'authorized': False,
                'message': error_msg,
                'success': False,
                'from_cache': False,
                'is_auth_error': response.status_code == 403
            }
        except requests.exceptions.RequestException as e:
            self._log_debug(f"在线订阅请求异常: {str(e)}")
            return {'authorized': False, 'message': f'连接失败: {str(e)}', 'success': False, 'from_cache': False}
        except Exception as e:
            self._log_debug(f"在线订阅未知异常: {str(e)}")
            return {'authorized': False, 'message': f'未知错误: {str(e)}', 'success': False, 'from_cache': False}
    
    def check_authorization(self, force_online: bool = False) -> Dict[str, Any]:
        """
        检查设备授权状态（带缓存）
        
        缓存策略：
        - 优先检查本地缓存，缓存有效（7天内）则直接返回授权结果并刷新last_check
        - 缓存失效时才向服务端发起订阅请求，成功则更新缓存
        - 订阅（在线）失败不修改/清空缓存，直接返回失败结果
        
        Args:
            force_online: 强制在线检查（已弃用，始终在线检查）
        
        Returns:
            dict: {
                'authorized': bool,  # 是否授权
                'message': str,      # 消息
                'success': bool,     # 请求是否成功
                'from_cache': bool   # 是否来自缓存
            }
        """
        if not self.enable_cache or self.cache is None:
            return self._check_online()
        
        cache_data = None
        try:
            self._log_debug(f"尝试读取缓存: {self.cache.cache_file}")
            self._log_debug(f"缓存文件存在: {self.cache.cache_file.exists()}")
            cache_data = self.cache.get_cache()
        except Exception:
            self._log_debug("读取缓存异常")
            cache_data = None
        
        # 若标准读取失败，尝试宽松解密一次（可能存在旧格式或偏移）
        if cache_data is None and self.cache.cache_file.exists():
            try:
                self._log_debug("尝试宽松解密缓存（直接读原始文件）")
                with open(self.cache.cache_file, 'rb') as f:
                    encrypted_data = f.read()
                decrypted = self.cache._deobfuscate(encrypted_data)
                if decrypted:
                    raw = json.loads(decrypted.decode('utf-8'))
                    cache_data = {
                        'authorized': raw.get('a', False),
                        'message': raw.get('m', ''),
                        'cached_at': raw.get('c', 0),
                        'last_check': raw.get('l', 0),
                    }
                else:
                    self._log_debug("宽松解密失败（结果为空）")
            except Exception as e:
                self._log_debug(f"宽松解密异常: {e}")
        
        # 缓存有效时，先返回缓存结果，然后继续尝试在线订阅来更新订阅
        cache_valid = False
        if cache_data:
            cached_at = cache_data.get('cached_at', 0)
            if cached_at > 0:
                elapsed = time.time() - cached_at
                if elapsed < self.cache.cache_validity_seconds:
                    cache_valid = True
                    self._log_debug("命中有效缓存，直接授权通过")
        
        
        if cache_valid:
            self._log_debug("缓存有效，继续尝试在线订阅来更新订阅")
        else:
            if cache_data:
                self._log_debug("缓存存在但已过期，准备发起在线订阅请求")
            else:
                self._log_debug("未找到缓存，准备发起在线订阅请求")
        
        online_result = self._check_online()
        
        if online_result['success']:
            self._log_debug("在线订阅成功，更新缓存")
            saved = self.cache.save_cache(online_result['authorized'], online_result['message'])
            self._log_debug(f"写入缓存结果: {saved} -> {self.cache.cache_file}")
            return online_result
        
        if cache_valid:
            cached_at = cache_data.get('cached_at', 0)
            remaining = self._format_remaining_time(cached_at)
            self._log_debug(f"在线订阅失败，但缓存有效，使用缓存结果: {online_result.get('message')}，订阅剩余时间: {remaining}")
            return {
                'authorized': cache_data.get('authorized', False),
                'message': cache_data.get('message', ''),
                'success': True,
                'from_cache': True
            }
        
        if cache_data:
            cached_at = cache_data.get('cached_at', 0)
            remaining = self._format_remaining_time(cached_at)
            self._log_debug(f"在线订阅失败，缓存已过期，返回失败结果: {online_result.get('message')}，订阅剩余时间: {remaining}")
        else:
            self._log_debug(f"在线订阅失败，返回失败结果: {online_result.get('message')}")
        return online_result
    
    def require_authorization(self, raise_exception: bool = True, force_online: bool = False) -> bool:
        """
        要求授权，如果未授权则抛出异常或返回False
        
        Args:
            raise_exception: 如果未授权是否抛出异常
            force_online: 强制在线检查
            
        Returns:
            bool: 是否已授权
            
        Raises:
            AuthorizationError: 如果未授权且raise_exception=True
        """
        result = self.check_authorization(force_online=force_online)
        
        if not result['success']:
            if raise_exception:
                raise AuthorizationError(
                    message=result['message'],
                    result=result,
                    device_id=self.device_id,
                    server_url=self.server_url
                )
            return False
        
        if not result['authorized']:
            if raise_exception:
                raise AuthorizationError(
                    message=result['message'],
                    result=result,
                    device_id=self.device_id,
                    server_url=self.server_url
                )
            return False
        
        return True
    
    def clear_cache(self) -> bool:
        """
        清除本地缓存
        
        Returns:
            是否清除成功
        """
        if self.cache:
            return self.cache.clear_cache()
        return True
    
    def get_authorization_info(self) -> Dict[str, Any]:
        """
        获取授权信息（用户友好的格式）
        
        Returns:
            授权信息字典，包含授权状态、剩余时间、缓存信息等
        """
        result = self.check_authorization()
        
        info = {
            'authorized': result.get('authorized', False),
            'success': result.get('success', False),
            'from_cache': result.get('from_cache', False),
            'message': result.get('message', ''),
            'device_id': self.device_id,
            'server_url': self.server_url,
        }
        
        if self.cache:
            cache = self.cache.get_cache()
            if cache:
                cached_at = cache.get('cached_at', 0)
                remaining = self._format_remaining_time(cached_at)
                info['remaining_time'] = remaining
                info['cache_valid'] = self.cache.is_cache_valid()
                info['cached_at'] = cached_at
                if cached_at > 0:
                    info['cached_at_readable'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(cached_at))
            else:
                info['remaining_time'] = '无缓存'
                info['cache_valid'] = False
        
        return info
    
    def get_cache_info(self) -> Optional[Dict[str, Any]]:
        """
        获取缓存信息（用于调试）
        
        Returns:
            缓存信息
        """
        if not self.cache:
            return None
        
        cache = self.cache.get_cache()
        if not cache:
            return None
        
        now = time.time()
        cached_at = cache.get('cached_at', 0)
        last_check = cache.get('last_check', 0)
        
        return {
            'authorized': cache.get('authorized'),
            'message': cache.get('message'),
            'cached_at': cached_at,
            'last_check': last_check,
            'cache_age_days': (now - cached_at) / 86400,
            'last_check_age_days': (now - last_check) / 86400,
            'cache_valid': self.cache.is_cache_valid(),
            'needs_check': self.cache.needs_check(),
            'cache_file': str(self.cache.cache_file)
        }


class AuthorizationError(Exception):
    """
    授权错误异常
    
    当设备未授权或授权验证失败时抛出此异常。
    
    属性:
        message: 错误消息
        result: 授权检查结果字典（可选）
        device_id: 设备ID（可选）
        server_url: 服务器URL（可选）
    """
    
    def __init__(
        self, 
        message: str, 
        result: Optional[Dict[str, Any]] = None,
        device_id: Optional[str] = None,
        server_url: Optional[str] = None
    ):
        """
        初始化授权错误异常
        
        Args:
            message: 错误消息
            result: 授权检查结果字典，包含 'authorized', 'message', 'success', 'from_cache' 等字段
            device_id: 设备ID
            server_url: 服务器URL
        """
        self.message = message
        self.result = result
        self.device_id = device_id
        self.server_url = server_url
        super().__init__(self.message)
    
    def __str__(self) -> str:
        """返回错误消息"""
        return self.message
    
    def __repr__(self) -> str:
        """返回异常的详细表示"""
        parts = [f"AuthorizationError('{self.message}'"]
        if self.device_id:
            parts.append(f", device_id='{self.device_id}'")
        if self.server_url:
            parts.append(f", server_url='{self.server_url}'")
        parts.append(")")
        return ", ".join(parts)
    
    @property
    def is_network_error(self) -> bool:
        """
        判断是否为网络错误
        
        Returns:
            如果是网络连接错误返回True，否则返回False
        """
        message_lower = self.message.lower()
        check_message = (self.result.get('message', '').lower() if self.result else '')
        
        network_keywords = ['连接失败', '连接', 'network', 'timeout', 'connection']
        return any(keyword in check_message or keyword in message_lower for keyword in network_keywords)
    
    @property
    def is_unauthorized(self) -> bool:
        """
        判断是否为未授权错误（设备未授权或被禁用）
        
        Returns:
            如果是未授权错误返回True，否则返回False
        """
        if self.result:
            return not self.result.get('authorized', False) and self.result.get('success', False)
        return '未授权' in self.message or '禁用' in self.message
    
    @property
    def is_validation_error(self) -> bool:
        """
        判断是否为验证错误（无法验证授权）
        
        Returns:
            如果是验证错误返回True，否则返回False
        """
        if self.result:
            return not self.result.get('success', False)
        return '无法验证授权' in self.message or '验证失败' in self.message


def check_authorization(
    server_url: str, 
    software_name: str,
    device_id: Optional[str] = None, 
    enable_cache: bool = True,
    force_online: bool = False
) -> bool:
    """
    便捷函数：检查授权状态
    
    Args:
        server_url: 授权服务器地址
        software_name: 软件名称（必填）
        device_id: 设备ID（可选）
        enable_cache: 是否启用缓存
        force_online: 强制在线检查
        
    Returns:
        bool: 是否已授权
    """
    client = AuthClient(server_url, software_name, device_id, enable_cache=enable_cache)
    result = client.check_authorization(force_online=force_online)
    return result.get('authorized', False) and result.get('success', False)
