"""
凭证加密工具
Credential Encryption Utility

用于安全地加密和解密用户凭证（自动填充功能）
"""

import base64
import json
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from config.settings import SECRET_KEY


class CredentialEncryptor:
    """凭证加密器"""
    
    def __init__(self):
        # 使用SECRET_KEY派生加密密钥
        self.key = self._derive_key(SECRET_KEY)
        self.fernet = Fernet(self.key)
    
    def _derive_key(self, secret: str) -> bytes:
        """从密钥派生Fernet密钥"""
        # 使用固定盐（因为需要解密）
        salt = b'EduAgent_AutoFill_Salt_2026'
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
        return key
    
    def encrypt_credentials(self, username: str, password: str) -> str:
        """
        加密用户凭证
        
        Args:
            username: 用户名
            password: 密码
            
        Returns:
            加密后的字符串
        """
        try:
            data = json.dumps({
                'username': username,
                'password': password
            })
            encrypted = self.fernet.encrypt(data.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            print(f"加密凭证失败: {e}")
            return None
    
    def decrypt_credentials(self, encrypted_data: str) -> dict:
        """
        解密用户凭证
        
        Args:
            encrypted_data: 加密的字符串
            
        Returns:
            包含 username 和 password 的字典，失败返回 None
        """
        try:
            encrypted = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted = self.fernet.decrypt(encrypted)
            return json.loads(decrypted.decode())
        except Exception as e:
            print(f"解密凭证失败: {e}")
            return None


# 全局实例
credential_encryptor = CredentialEncryptor()
