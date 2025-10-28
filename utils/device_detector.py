"""
设备检测工具
Device Detector Utility
"""

import re
import hashlib
from typing import Dict, Optional


class DeviceDetector:
    """设备检测类 - 用于识别设备型号、浏览器和操作系统"""
    
    # 操作系统检测模式
    OS_PATTERNS = [
        (r'Windows NT 10\.0', 'Windows 10'),
        (r'Windows NT 6\.3', 'Windows 8.1'),
        (r'Windows NT 6\.2', 'Windows 8'),
        (r'Windows NT 6\.1', 'Windows 7'),
        (r'Windows NT 6\.0', 'Windows Vista'),
        (r'Windows NT 5\.1', 'Windows XP'),
        (r'Mac OS X ([\d_]+)', 'macOS'),
        (r'iPhone OS ([\d_]+)', 'iOS'),
        (r'iPad.*OS ([\d_]+)', 'iPadOS'),
        (r'Android ([\d\.]+)', 'Android'),
        (r'Linux', 'Linux'),
        (r'Ubuntu', 'Ubuntu'),
        (r'CrOS', 'Chrome OS'),
    ]
    
    # 浏览器检测模式
    BROWSER_PATTERNS = [
        (r'Edg/([\d\.]+)', 'Edge'),
        (r'Chrome/([\d\.]+)', 'Chrome'),
        (r'Firefox/([\d\.]+)', 'Firefox'),
        (r'Safari/([\d\.]+)', 'Safari'),
        (r'Opera/([\d\.]+)', 'Opera'),
        (r'MSIE ([\d\.]+)', 'IE'),
        (r'Trident/.*rv:([\d\.]+)', 'IE'),
    ]
    
    # 设备类型检测模式
    DEVICE_PATTERNS = [
        (r'iPhone', 'iPhone'),
        (r'iPad', 'iPad'),
        (r'iPod', 'iPod'),
        (r'Android.*Mobile', 'Android手机'),
        (r'Android', 'Android设备'),
        (r'Mobile', '移动设备'),
        (r'Tablet', '平板设备'),
    ]
    
    @staticmethod
    def detect_os(user_agent: str) -> tuple:
        """检测操作系统
        
        Args:
            user_agent: 用户代理字符串
            
        Returns:
            (操作系统名称, 版本号)
        """
        if not user_agent:
            return ('未知系统', '')
        
        for pattern, name in DeviceDetector.OS_PATTERNS:
            match = re.search(pattern, user_agent)
            if match:
                version = match.group(1).replace('_', '.') if match.groups() else ''
                return (name, version)
        
        return ('未知系统', '')
    
    @staticmethod
    def detect_browser(user_agent: str) -> tuple:
        """检测浏览器
        
        Args:
            user_agent: 用户代理字符串
            
        Returns:
            (浏览器名称, 版本号)
        """
        if not user_agent:
            return ('未知浏览器', '')
        
        for pattern, name in DeviceDetector.BROWSER_PATTERNS:
            match = re.search(pattern, user_agent)
            if match:
                version = match.group(1) if match.groups() else ''
                # 只保留主版本号和次版本号
                if version:
                    version_parts = version.split('.')[:2]
                    version = '.'.join(version_parts)
                return (name, version)
        
        return ('未知浏览器', '')
    
    @staticmethod
    def detect_device_type(user_agent: str) -> str:
        """检测设备类型
        
        Args:
            user_agent: 用户代理字符串
            
        Returns:
            设备类型
        """
        if not user_agent:
            return '未知设备'
        
        for pattern, device_type in DeviceDetector.DEVICE_PATTERNS:
            if re.search(pattern, user_agent, re.IGNORECASE):
                return device_type
        
        return '桌面设备'
    
    @staticmethod
    def get_device_name(user_agent: str) -> str:
        """获取友好的设备名称
        
        Args:
            user_agent: 用户代理字符串
            
        Returns:
            设备友好名称，如 "Chrome 120 on Windows 10"
        """
        if not user_agent:
            return '未知设备'
        
        device_type = DeviceDetector.detect_device_type(user_agent)
        browser_name, browser_version = DeviceDetector.detect_browser(user_agent)
        os_name, os_version = DeviceDetector.detect_os(user_agent)
        
        # 构建设备名称
        if device_type in ['iPhone', 'iPad', 'iPod']:
            # iOS设备：显示设备类型 + 系统版本
            if os_version:
                return f"{device_type} (iOS {os_version})"
            return device_type
        elif 'Android' in device_type:
            # Android设备：显示Android + 版本
            if os_version:
                return f"{device_type} (Android {os_version})"
            return device_type
        else:
            # 桌面设备：显示浏览器 + 操作系统
            parts = []
            if browser_name and browser_name != '未知浏览器':
                if browser_version:
                    parts.append(f"{browser_name} {browser_version}")
                else:
                    parts.append(browser_name)
            
            if os_name and os_name != '未知系统':
                parts.append(os_name)
            
            if parts:
                return ' on '.join(parts) if len(parts) > 1 else parts[0]
            
            return '桌面设备'
    
    @staticmethod
    def generate_device_fingerprint(user_agent: str, ip_address: Optional[str] = None) -> str:
        """生成设备指纹
        
        通过user_agent和IP地址生成唯一的设备指纹，用于识别同一设备
        
        Args:
            user_agent: 用户代理字符串
            ip_address: IP地址（可选）
            
        Returns:
            设备指纹（32位MD5哈希）
        """
        if not user_agent:
            user_agent = 'unknown'
        
        # 标准化user_agent，移除版本号中的小版本以提高匹配率
        # 例如：Chrome/120.0.6099.109 -> Chrome/120.0
        normalized_ua = user_agent
        
        # 移除浏览器的小版本号（保留主版本号和次版本号）
        for pattern, _ in DeviceDetector.BROWSER_PATTERNS:
            match = re.search(pattern, normalized_ua)
            if match and match.groups():
                full_version = match.group(1)
                # 只保留前两位版本号
                major_minor = '.'.join(full_version.split('.')[:2])
                normalized_ua = normalized_ua.replace(full_version, major_minor)
        
        # 组合指纹数据（只使用user_agent，不使用IP，因为IP可能变化）
        fingerprint_data = normalized_ua.lower().strip()
        
        # 生成MD5哈希
        fingerprint = hashlib.md5(fingerprint_data.encode('utf-8')).hexdigest()
        
        return fingerprint
    
    @staticmethod
    def parse_device_info(user_agent: str, ip_address: Optional[str] = None) -> Dict[str, str]:
        """解析完整的设备信息
        
        Args:
            user_agent: 用户代理字符串
            ip_address: IP地址（可选）
            
        Returns:
            包含设备信息的字典
        """
        device_type = DeviceDetector.detect_device_type(user_agent)
        browser_name, browser_version = DeviceDetector.detect_browser(user_agent)
        os_name, os_version = DeviceDetector.detect_os(user_agent)
        device_name = DeviceDetector.get_device_name(user_agent)
        device_fingerprint = DeviceDetector.generate_device_fingerprint(user_agent, ip_address)
        
        return {
            'device_type': device_type,
            'device_name': device_name,
            'browser_name': browser_name,
            'browser_version': browser_version,
            'os_name': os_name,
            'os_version': os_version,
            'device_fingerprint': device_fingerprint,
            'user_agent': user_agent,
            'ip_address': ip_address or ''
        }


# 便捷函数
def get_device_name(user_agent: str) -> str:
    """获取设备名称的便捷函数"""
    return DeviceDetector.get_device_name(user_agent)


def get_device_fingerprint(user_agent: str, ip_address: Optional[str] = None) -> str:
    """获取设备指纹的便捷函数"""
    return DeviceDetector.generate_device_fingerprint(user_agent, ip_address)


def parse_device_info(user_agent: str, ip_address: Optional[str] = None) -> Dict[str, str]:
    """解析设备信息的便捷函数"""
    return DeviceDetector.parse_device_info(user_agent, ip_address)

