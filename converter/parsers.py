# converter/parsers.py

import base64
import json
import logging
import binascii
from urllib.parse import urlparse, parse_qs, unquote


def parse_link(link: str):
    """
    一个分发器函数，根据链接的协议头调用相应的解析器。
    """
    try:
        if link.startswith('ss://'):
            return _parse_ss(link)
        if link.startswith('vmess://'):
            return _parse_vmess(link)
        if link.startswith('vless://'):
            return _parse_vless(link)
        if link.startswith('hysteria2://'):
            return _parse_hy2(link)
        logging.warning(f"跳过不支持的协议: {link[:30]}...")
        return None
    except Exception as e:
        logging.error(f"解析链接时发生未知错误: {link} -> {e}", exc_info=False)
        return None


def _parse_ss(link: str):
    """
    解析Shadowsocks链接。
    能够同时处理凭证为明文或Base64的两种情况。
    """
    try:
        main_part, name = link[5:].split('#', 1)
        name = unquote(name.strip())
        user_info, server_info = main_part.rsplit('@', 1)
        server, port = server_info.rsplit(':', 1)
        try:
            decoded_info = base64.urlsafe_b64decode(user_info + '=' * (-len(user_info) % 4)).decode()
            method, password = decoded_info.split(':', 1)
        except (binascii.Error, ValueError):
            user_info = unquote(user_info)
            method, password = user_info.split(':', 1)

        return {
            'name': name, 'type': 'ss', 'server': server, 'port': int(port),
            'cipher': method, 'password': password
        }
    except Exception as e:
        logging.warning(f"SS链接解析失败，已跳过: {link} -> 错误: {e}")
        return None


def _parse_vmess(link: str):
    """
    解析VMess链接。
    [ 这是修复后的版本 ]
    确保 ws-opts.headers.Host 永远不会是 null。
    """
    try:
        decoded_part = base64.b64decode(link[8:]).decode()
        vmess_config = json.loads(decoded_part)

        server_addr = vmess_config.get('add')

        ws_opts = None
        if vmess_config.get('net') == 'ws':
            # 获取 host，如果为空，则使用服务器地址作为备用
            host = vmess_config.get('host', '').strip()
            if not host:
                host = server_addr

            ws_opts = {
                'path': vmess_config.get('path', '/'),
                'headers': {'Host': host}
            }

        return {
            'name': vmess_config.get('ps'), 'type': 'vmess',
            'server': server_addr, 'port': int(vmess_config.get('port')),
            'uuid': vmess_config.get('id'), 'alterId': int(vmess_config.get('aid', 0)),
            'cipher': vmess_config.get('scy', 'auto'),
            'tls': vmess_config.get('tls') == 'tls',
            'network': vmess_config.get('net'),
            'ws-opts': ws_opts
        }
    except Exception as e:
        logging.warning(f"VMess链接解析失败，已跳过: {link} -> 错误: {e}")
        return None


def _parse_vless(link: str):
    """
    解析VLESS链接。
    [ 这是修复后的版本 ]
    确保 ws-opts.headers.Host 永远不会是 null。
    """
    try:
        parsed_url = urlparse(link)
        params = parse_qs(parsed_url.query)

        name = unquote(parsed_url.fragment.strip())
        server = parsed_url.hostname

        ws_opts = None
        if params.get('type') == ['ws']:
            sni = params.get('sni', [None])[0]
            # 优先用 host 参数，其次用 sni 参数，最后用服务器地址
            host = params.get('host', [None])[0]
            if not host:
                host = sni if sni else server

            ws_opts = {
                'path': params.get('path', ['/'])[0],
                'headers': {'Host': host}
            }

        return {
            'name': name, 'type': 'vless',
            'server': server, 'port': parsed_url.port,
            'uuid': parsed_url.username,
            'tls': params.get('security', ['none'])[0] == 'tls',
            'network': params.get('type', ['tcp'])[0],
            # SNI也需要一个备用值，通常是服务器地址
            'servername': params.get('sni', [server])[0],
            'ws-opts': ws_opts
        }
    except Exception as e:
        logging.warning(f"VLESS链接解析失败，已跳过: {link} -> 错误: {e}")
        return None


# converter/parsers.py (修正后的代码)

def _parse_hy2(link: str):
    """解析Hysteria2链接。"""
    try:
        parsed_url = urlparse(link)
        params = parse_qs(parsed_url.query)
        name = unquote(parsed_url.fragment.strip())

        # 修正：如果链接中没有提供 sni，则默认使用服务器域名 (hostname)
        sni_value = params.get('sni', [parsed_url.hostname])[0]

        return {
            'name': name, 'type': 'hysteria2',
            'server': parsed_url.hostname, 'port': parsed_url.port,
            'password': parsed_url.username,
            'sni': sni_value, # 使用修正后的 sni_value
            'skip-cert-verify': params.get('insecure', ['0'])[0] == '1'
        }
    except Exception as e:
        logging.warning(f"Hysteria2链接解析失败，已跳过: {link} -> 错误: {e}")
        return None


