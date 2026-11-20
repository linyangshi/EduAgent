"""
OAuth第三方登录路由 - 微信和QQ
OAuth Third-party Login Routes - WeChat and QQ
"""

import os
import requests
from flask import Blueprint, request, redirect, url_for, jsonify, session, render_template
from flask_login import login_user, current_user, login_required
from models.user import db, User
from config.settings import (
    WECHAT_APP_ID, WECHAT_APP_SECRET, WECHAT_CALLBACK_URL,
    QQ_APP_ID, QQ_APP_SECRET, QQ_CALLBACK_URL
)
import uuid

oauth_bp = Blueprint('oauth', __name__)

# ============ WeChat OAuth ============

@oauth_bp.route('/auth/wechat')
def wechat_login():
    """重定向到微信OAuth授权页面"""
    if not WECHAT_APP_ID or not WECHAT_APP_SECRET:
        return render_template('oauth_error.html',
                             title='微信登录未配置',
                             heading='⚠️ 微信登录未配置',
                             description='管理员尚未配置微信OAuth凭证。',
                             config_vars=['WECHAT_APP_ID = "your_app_id"', 'WECHAT_APP_SECRET = "your_secret"'],
                             button_color='#07c160',
                             button_hover_color='#06ad56'), 503
    
    
    # 生成state参数用于防CSRF攻击
    state = str(uuid.uuid4())
    session['wechat_oauth_state'] = state
    
    # 微信OAuth授权URL
    auth_url = (
        f"https://open.weixin.qq.com/connect/qrconnect?"
        f"appid={WECHAT_APP_ID}&"
        f"redirect_uri={WECHAT_CALLBACK_URL}&"
        f"response_type=code&"
        f"scope=snsapi_login&"
        f"state={state}#wechat_redirect"
    )
    
    return redirect(auth_url)


@oauth_bp.route('/auth/wechat/callback')
def wechat_callback():
    """处理微信OAuth回调"""
    code = request.args.get('code')
    state = request.args.get('state')
    
    # 验证state参数
    if state != session.get('wechat_oauth_state'):
        return jsonify({'error': 'Invalid state parameter'}), 400
    
    if not code:
        return jsonify({'error': '微信授权失败'}), 400
    
    try:
        # 1. 获取access_token
        token_url = (
            f"https://api.weixin.qq.com/sns/oauth2/access_token?"
            f"appid={WECHAT_APP_ID}&"
            f"secret={WECHAT_APP_SECRET}&"
            f"code={code}&"
            f"grant_type=authorization_code"
        )
        
        token_response = requests.get(token_url)
        token_data = token_response.json()
        
        if 'errcode' in token_data:
            return jsonify({'error': f'获取access_token失败: {token_data.get("errmsg")}'}), 400
        
        access_token = token_data.get('access_token')
        openid = token_data.get('openid')
        
        # 2. 获取用户信息
        user_info_url = (
            f"https://api.weixin.qq.com/sns/userinfo?"
            f"access_token={access_token}&"
            f"openid={openid}"
        )
        
        user_info_response = requests.get(user_info_url)
        user_info = user_info_response.json()
        
        if 'errcode' in user_info:
            return jsonify({'error': f'获取用户信息失败: {user_info.get("errmsg")}'}), 400
        
        # 3. 查找或创建用户
        user = User.query.filter_by(wechat_openid=openid).first()
        
        if user:
            # 已存在的微信账号，直接登录
            login_user(user, remember=False)
            return redirect(url_for('index'))
        else:
            # 新用户，创建账号
            nickname = user_info.get('nickname', f'微信用户_{openid[:8]}')
            avatar = user_info.get('headimgurl', '')
            
            new_user = User(
                username=f'wechat_{openid[:16]}',
                email=f'{openid}@wechat.oauth',  # 临时邮箱
                wechat_openid=openid,
                full_name=nickname,
                avatar_url=avatar
            )
            new_user.set_password(str(uuid.uuid4()))  # 随机密码
            
            db.session.add(new_user)
            db.session.commit()
            
            login_user(new_user, remember=False)
            return redirect(url_for('index'))
            
    except Exception as e:
        print(f"❌ 微信OAuth错误: {e}")
        return jsonify({'error': f'登录失败: {str(e)}'}), 500


# ============ QQ OAuth ============

@oauth_bp.route('/auth/qq')
def qq_login():
    """重定向到QQ OAuth授权页面"""
    # 暂时禁用QQ登录
    return render_template('oauth_error.html',
                         title='QQ登录暂未开放',
                         heading='🚧 QQ登录暂未开放',
                         description='QQ登录接口正在接入中，敬请期待。请使用微信登录或账号密码登录。',
                         config_vars=[],
                         button_color='#6c757d',
                         button_hover_color='#5a6268'), 503
    
    # Original implementation commented out
    """
    if not QQ_APP_ID or not QQ_APP_SECRET:
        return render_template('oauth_error.html',
                             title='QQ登录未配置',
                             heading='⚠️ QQ登录未配置',
                             description='管理员尚未配置QQ OAuth凭证。',
                             config_vars=['QQ_APP_ID = "your_app_id"', 'QQ_APP_SECRET = "your_secret"'],
                             button_color='#12B7F5',
                             button_hover_color='#0fa3dc'), 503
    
    state = str(uuid.uuid4())
    session['qq_oauth_state'] = state
    
    auth_url = (
        f"https://graph.qq.com/oauth2.0/authorize?"
        f"response_type=code&"
        f"client_id={QQ_APP_ID}&"
        f"redirect_uri={QQ_CALLBACK_URL}&"
        f"state={state}&"
        f"scope=get_user_info"
    )
    
    return redirect(auth_url)
    """


@oauth_bp.route('/auth/qq/callback')
def qq_callback():
    """处理QQ OAuth回调"""
    code = request.args.get('code')
    state = request.args.get('state')
    
    if state != session.get('qq_oauth_state'):
        return jsonify({'error': 'Invalid state parameter'}), 400
    
    if not code:
        return jsonify({'error': 'QQ授权失败'}), 400
    
    try:
        # 1. 获取access_token
        token_url = (
            f"https://graph.qq.com/oauth2.0/token?"
            f"grant_type=authorization_code&"
            f"client_id={QQ_APP_ID}&"
            f"client_secret={QQ_APP_SECRET}&"
            f"code={code}&"
            f"redirect_uri={QQ_CALLBACK_URL}"
        )
        
        token_response = requests.get(token_url)
        # QQ返回的是URL参数格式
        from urllib.parse import parse_qs
        token_params = parse_qs(token_response.text)
        access_token = token_params.get('access_token', [None])[0]
        
        if not access_token:
            return jsonify({'error': '获取access_token失败'}), 400
        
        # 2. 获取OpenID
        openid_url = f"https://graph.qq.com/oauth2.0/me?access_token={access_token}"
        openid_response = requests.get(openid_url)
        # QQ返回JSONP格式，需要提取JSON
        openid_text = openid_response.text
        openid_json = openid_text[openid_text.index('{'):openid_text.rindex('}')+1]
        import json
        openid_data = json.loads(openid_json)
        openid = openid_data.get('openid')
        
        # 3. 获取用户信息
        user_info_url = (
            f"https://graph.qq.com/user/get_user_info?"
            f"access_token={access_token}&"
            f"oauth_consumer_key={QQ_APP_ID}&"
            f"openid={openid}"
        )
        
        user_info_response = requests.get(user_info_url)
        user_info = user_info_response.json()
        
        # 4. 查找或创建用户
        user = User.query.filter_by(qq_openid=openid).first()
        
        if user:
            login_user(user, remember=False)
            return redirect(url_for('index'))
        else:
            nickname = user_info.get('nickname', f'QQ用户_{openid[:8]}')
            avatar = user_info.get('figureurl_qq_2', '')  # QQ头像
            
            new_user = User(
                username=f'qq_{openid[:16]}',
                email=f'{openid}@qq.oauth',
                qq_openid=openid,
                full_name=nickname,
                avatar_url=avatar
            )
            new_user.set_password(str(uuid.uuid4()))
            
            db.session.add(new_user)
            db.session.commit()
            
            login_user(new_user, remember=False)
            return redirect(url_for('index'))
            
    except Exception as e:
        print(f"❌ QQ OAuth错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'登录失败: {str(e)}'}), 500


# ============ Binding/Unbinding APIs ============

@oauth_bp.route('/api/bind/wechat', methods=['POST'])
@login_required
def bind_wechat():
    """绑定微信到当前账号"""
    # 这个流程需要前端先发起wechat_login，然后在callback中检测已登录用户
    # 如果已登录，则绑定而不是创建新用户
    # 简化实现：直接返回绑定URL
    return jsonify({
        'success': True,
        'bind_url': url_for('oauth.wechat_login', _external=True) + '?action=bind'
    })


@oauth_bp.route('/api/bind/qq', methods=['POST'])
@login_required
def bind_qq():
    """绑定QQ到当前账号"""
    return jsonify({
        'success': True,
        'bind_url': url_for('oauth.qq_login', _external=True) + '?action=bind'
    })


@oauth_bp.route('/api/unbind/wechat', methods=['POST'])
@login_required
def unbind_wechat():
    """解绑微信"""
    current_user.wechat_openid = None
    db.session.commit()
    return jsonify({'success': True, 'message': '微信解绑成功'})


@oauth_bp.route('/api/unbind/qq', methods=['POST'])
@login_required
def unbind_qq():
    """解绑QQ"""
    current_user.qq_openid = None
    db.session.commit()
    return jsonify({'success': True, 'message': 'QQ解绑成功'})
