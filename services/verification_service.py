"""
验证码服务
Verification Service
"""

import random
import string
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from flask import request
from models.user import EmailVerification, User, db
from services.email_service import EmailService


class VerificationService:
    """验证码服务类"""
    
    def __init__(self):
        self.email_service = EmailService()
        self.code_length = 6
        self.code_expiry_minutes = 10
        self.max_attempts_per_hour = 5  # 每小时最大发送次数
        self.max_attempts_per_day = 20  # 每天最大发送次数
    
    def generate_verification_code(self) -> str:
        """生成验证码"""
        return ''.join(random.choices(string.digits, k=self.code_length))
    
    def check_rate_limit(self, email: str, ip_address: str = None) -> Dict[str, Any]:
        """检查发送频率限制"""
        try:
            now = datetime.utcnow()
            one_hour_ago = now - timedelta(hours=1)
            one_day_ago = now - timedelta(days=1)
            
            # 检查每小时限制
            hourly_count = EmailVerification.query.filter(
                EmailVerification.email == email,
                EmailVerification.created_at >= one_hour_ago
            ).count()
            
            print(f"🔍 频率检查 - 邮箱: {email}, 最近1小时发送次数: {hourly_count}/{self.max_attempts_per_hour}")
            
            if hourly_count >= self.max_attempts_per_hour:
                # 查找最近一次发送时间
                recent_verification = EmailVerification.query.filter(
                    EmailVerification.email == email,
                    EmailVerification.created_at >= one_hour_ago
                ).order_by(EmailVerification.created_at.desc()).first()
                
                if recent_verification:
                    # 计算距离下次可发送的时间
                    time_since_last = now - recent_verification.created_at
                    remaining_seconds = 3600 - time_since_last.total_seconds()  # 1小时 = 3600秒
                    remaining_minutes = max(1, int(remaining_seconds / 60))
                    return {
                        'allowed': False,
                        'error': f'发送过于频繁，请{remaining_minutes}分钟后再试'
                    }
                else:
                    return {
                        'allowed': False,
                        'error': '发送过于频繁，请1小时后再试'
                    }
            
            # 检查每天限制
            daily_count = EmailVerification.query.filter(
                EmailVerification.email == email,
                EmailVerification.created_at >= one_day_ago
            ).count()
            
            print(f"🔍 频率检查 - 邮箱: {email}, 最近24小时发送次数: {daily_count}/{self.max_attempts_per_day}")
            
            if daily_count >= self.max_attempts_per_day:
                return {
                    'allowed': False,
                    'error': '今日发送次数已达上限，请明天再试'
                }
            
            # 检查IP限制（可选）
            if ip_address:
                ip_hourly_count = EmailVerification.query.filter(
                    EmailVerification.ip_address == ip_address,
                    EmailVerification.created_at >= one_hour_ago
                ).count()
                
                print(f"🔍 频率检查 - IP: {ip_address}, 最近1小时发送次数: {ip_hourly_count}/{self.max_attempts_per_hour * 2}")
                
                if ip_hourly_count >= self.max_attempts_per_hour * 2:  # IP限制更宽松
                    return {
                        'allowed': False,
                        'error': 'IP发送过于频繁，请稍后再试'
                    }
            
            print(f"✅ 频率检查通过 - 邮箱: {email}")
            return {'allowed': True}
            
        except Exception as e:
            print(f"❌ 频率检查失败: {e}")
            return {
                'allowed': False,
                'error': f'检查频率限制失败: {str(e)}'
            }
    
    def send_verification_code(self, email: str, code_type: str = 'register', username: str = None) -> Dict[str, Any]:
        """发送验证码"""
        try:
            # 验证邮箱格式
            if not self._validate_email(email):
                return {'success': False, 'error': '邮箱格式不正确'}
            
            # 检查邮箱是否已注册
            if code_type == 'register' and User.query.filter_by(email=email).first():
                return {'success': False, 'error': '该邮箱已被注册'}
            
            # 对于密码重置，检查邮箱是否已注册
            if code_type == 'reset_password' and not User.query.filter_by(email=email).first():
                return {'success': False, 'error': '该邮箱未注册'}
            
            # 获取客户端信息
            ip_address = request.remote_addr if request else None
            user_agent = request.headers.get('User-Agent') if request else None
            
            # 检查发送频率限制
            rate_limit = self.check_rate_limit(email, ip_address)
            if not rate_limit['allowed']:
                return {'success': False, 'error': rate_limit['error']}
            
            # 生成验证码
            verification_code = self.generate_verification_code()
            
            # 计算过期时间
            expires_at = datetime.utcnow() + timedelta(minutes=self.code_expiry_minutes)
            
            # 创建验证码记录
            verification = EmailVerification(
                email=email,
                verification_code=verification_code,
                code_type=code_type,
                ip_address=ip_address,
                user_agent=user_agent,
                expires_at=expires_at
            )
            
            db.session.add(verification)
            db.session.commit()
            
            # 发送邮件
            email_result = self.email_service.send_verification_email(
                email=email,
                code=verification_code,
                username=username,
                code_type=code_type
            )
            
            if not email_result['success']:
                # 如果邮件发送失败，删除验证码记录
                db.session.delete(verification)
                db.session.commit()
                return email_result
            
            return {
                'success': True,
                'message': '验证码已发送到您的邮箱',
                'expires_in': self.code_expiry_minutes * 60,  # 秒
                'code': verification_code
            }
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': f'发送验证码失败: {str(e)}'}
    
    def verify_code(self, email: str, code: str, code_type: str = 'register') -> Dict[str, Any]:
        """验证验证码"""
        try:
            if not email or not code:
                return {'success': False, 'error': '邮箱和验证码不能为空'}
            
            # 查找验证码记录
            verification = EmailVerification.query.filter_by(
                email=email,
                verification_code=code,
                code_type=code_type
            ).order_by(EmailVerification.created_at.desc()).first()
            
            if not verification:
                return {'success': False, 'error': '验证码不存在'}
            
            if verification.is_used:
                return {'success': False, 'error': '验证码已使用'}
            
            if verification.is_expired():
                return {'success': False, 'error': '验证码已过期'}
            
            # 标记验证码为已使用
            verification.mark_as_used()
            
            return {
                'success': True,
                'message': '验证码验证成功',
                'verification_id': verification.id
            }
            
        except Exception as e:
            return {'success': False, 'error': f'验证失败: {str(e)}'}
    
    def resend_verification_code(self, email: str, code_type: str = 'register') -> Dict[str, Any]:
        """重新发送验证码"""
        try:
            # 检查是否有未使用的验证码
            existing_verification = EmailVerification.query.filter_by(
                email=email,
                code_type=code_type,
                is_used=False
            ).order_by(EmailVerification.created_at.desc()).first()
            
            if existing_verification and not existing_verification.is_expired():
                remaining_time = (existing_verification.expires_at - datetime.utcnow()).seconds
                return {
                    'success': False,
                    'error': f'验证码仍有效，请{remaining_time // 60 + 1}分钟后再试'
                }
            
            # 发送新的验证码
            return self.send_verification_code(email, code_type)
            
        except Exception as e:
            return {'success': False, 'error': f'重新发送失败: {str(e)}'}
    
    def cleanup_expired_codes(self) -> int:
        """清理过期的验证码"""
        try:
            expired_codes = EmailVerification.query.filter(
                EmailVerification.expires_at < datetime.utcnow()
            ).all()
            
            count = len(expired_codes)
            for code in expired_codes:
                db.session.delete(code)
            
            db.session.commit()
            return count
            
        except Exception as e:
            db.session.rollback()
            return 0
    
    def get_verification_stats(self, email: str) -> Dict[str, Any]:
        """获取验证码统计信息"""
        try:
            now = datetime.utcnow()
            one_hour_ago = now - timedelta(hours=1)
            one_day_ago = now - timedelta(days=1)
            
            # 统计各种状态
            total_codes = EmailVerification.query.filter_by(email=email).count()
            used_codes = EmailVerification.query.filter_by(email=email, is_used=True).count()
            expired_codes = EmailVerification.query.filter(
                EmailVerification.email == email,
                EmailVerification.expires_at < now
            ).count()
            
            # 最近发送的验证码
            recent_codes = EmailVerification.query.filter(
                EmailVerification.email == email,
                EmailVerification.created_at >= one_hour_ago
            ).order_by(EmailVerification.created_at.desc()).all()
            
            return {
                'total_codes': total_codes,
                'used_codes': used_codes,
                'expired_codes': expired_codes,
                'recent_codes': [code.to_dict() for code in recent_codes]
            }
            
        except Exception as e:
            return {'error': f'获取统计信息失败: {str(e)}'}
    
    def _validate_email(self, email: str) -> bool:
        """验证邮箱格式"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
