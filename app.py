import os
import json
import logging
import base64
import yaml
import binascii
import time
from urllib.parse import urlparse, parse_qs, unquote
from flask import Flask, request, jsonify, make_response, render_template
import requests

# --- 基础设置 ---
app = Flask(__name__, static_folder='static', template_folder='templates')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- 文件路径 ---
DATA_FILE = 'data.json'
CLASH_TEMPLATE_FILE = 'clash_template.yaml'

# =================================================================================
# 辅助函数
# =================================================================================

def load_data():
    """从 data.json 加载数据，如果文件不存在则返回默认结构"""
    if not os.path.exists(DATA_FILE):
        return {
            "subscriptions": [],
            "aggregation_enabled": [],
            "global_filter_enabled": False,
            "global_filter_keywords": ""
        }
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {
            "subscriptions": [],
            "aggregation_enabled": [],
            "global_filter_enabled": False,
            "global_filter_keywords": ""
        }

def save_data(data):
    """将数据保存到 data.json"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def parse_link(link):
    """解析单个代理链接 (ss, vmess, trojan) 为 Clash 字典格式"""
    try:
        if link.startswith('vmess://'):
            encoded_data = link[8:]
            # 修复可能的b64padding问题
            padding = len(encoded_data) % 4
            if padding:
                encoded_data += '=' * (4 - padding)
            decoded_data = base64.b64decode(encoded_data).decode('utf-8')
            vmess_data = json.loads(decoded_data)
            return {
                'name': vmess_data.get('ps'),
                'type': 'vmess',
                'server': vmess_data.get('add'),
                'port': int(vmess_data.get('port')),
                'uuid': vmess_data.get('id'),
                'alterId': int(vmess_data.get('aid')),
                'cipher': vmess_data.get('scy', 'auto'),
                'tls': vmess_data.get('tls') == 'tls',
                'network': vmess_data.get('net'),
                'ws-opts': {'path': vmess_data.get('path'), 'headers': {'Host': vmess_data.get('host')}} if vmess_data.get('net') == 'ws' else {},
                'servername': vmess_data.get('host') if vmess_data.get('tls') == 'tls' else None
            }
        elif link.startswith('ss://'):
            main_part, name_part = link[5:].split('#', 1)
            name = unquote(name_part)

            if '@' in main_part:
                encoded_credentials, server_info = main_part.split('@', 1)
                server, port = server_info.split(':')

                padding = len(encoded_credentials) % 4
                if padding:
                    encoded_credentials += '=' * (4 - padding)
                credentials = base64.b64decode(encoded_credentials).decode('utf-8')
                cipher, password = credentials.split(':', 1)
            else:
                return None

            return {
                'name': name,
                'type': 'ss',
                'server': server,
                'port': int(port),
                'cipher': cipher,
                'password': password
            }
        elif link.startswith('trojan://'):
            parsed_url = urlparse(link)
            params = parse_qs(parsed_url.query)
            return {
                'name': unquote(parsed_url.fragment),
                'type': 'trojan',
                'server': parsed_url.hostname,
                'port': parsed_url.port,
                'password': parsed_url.username,
                'sni': params.get('sni', [None])[0] or params.get('peer', [None])[0] or parsed_url.hostname,
                'alpn': params.get('alpn', [None])[0].split(',') if params.get('alpn') else None,
                'skip-cert-verify': params.get('allowInsecure', ['0'])[0] in ['1', 'true']
            }
    except Exception as e:
        logging.warning(f"解析链接失败: {link[:30]}... - 错误: {e}")
    return None

def apply_filter(nodes, keywords_str):
    """根据关键词过滤节点，支持逗号、空格、换行作为分隔符"""
    keywords = [kw.strip().lower() for kw in keywords_str.replace('\n', ',').replace(' ', ',').split(',') if kw.strip()]
    if not keywords:
        return nodes
    
    filtered_nodes = [node for node in nodes if not any(kw in node.get('name', '').lower() for kw in keywords)]
    return filtered_nodes

def generate_clash_config(nodes, template_str):
    """将节点列表注入到Clash模板中"""
    try:
        config = yaml.safe_load(template_str)
    except yaml.YAMLError as e:
        logging.error(f"Clash模板解析失败: {e}")
        # 如果模板损坏，提供一个基础的、能工作的模板作为后备
        config = {'proxies': [], 'proxy-groups':[], 'rules':[]}

    all_node_names = [node['name'] for node in nodes]
    
    config['proxies'] = nodes

    if 'proxy-groups' in config and isinstance(config['proxy-groups'], list):
        for group in config['proxy-groups']:
            if 'proxies' in group and isinstance(group['proxies'], list):
                if 'SELECT' in group['proxies']:
                    # 保持原有策略组的其他节点，并替换SELECT
                    original_proxies = [p for p in group['proxies'] if p != 'SELECT']
                    group['proxies'] = original_proxies + all_node_names

    return yaml.dump(config, allow_unicode=True, sort_keys=False, default_flow_style=False)

# =================================================================================
# 主路由和聚合逻辑
# =================================================================================

@app.route('/')
def index():
    """主页路由，渲染 index.html 模板"""
    return render_template('index.html')

@app.route('/aggregate/clash.yaml')
def aggregate_clash():
    """核心聚合路由，生成最终的Clash配置文件"""
    logging.info("=" * 50)
    logging.info("收到新的 /aggregate/clash.yaml 请求")
    data = load_data()
    enabled_ids = set(data.get('aggregation_enabled', []))
    subscriptions_to_aggregate = [sub for sub in data.get('subscriptions', []) if sub.get('id') in enabled_ids]

    global_filter_keywords = data.get('global_filter_keywords', '')
    global_filter_enabled = data.get('global_filter_enabled', False)

    if not subscriptions_to_aggregate:
        return make_response("没有启用的订阅，无法生成聚合配置。", 404)

    all_nodes = []
    headers = {'User-Agent': 'Clash/2023.08.17'}

    for sub_info in subscriptions_to_aggregate:
        sub_url = sub_info.get('url', '').strip()
        sub_name = sub_info.get('name', 'Unnamed')
        sub_filter_keywords = sub_info.get('filter_keywords', '')
        sub_filter_enabled = sub_info.get('filter_enabled', False)

        if not sub_url:
            logging.warning(f"  - 订阅 '{sub_name}' 的URL为空，已跳过。")
            continue

        logging.info(f"  - 正在处理订阅 '{sub_name}': {sub_url[:70]}...")

        try:
            sub_response = requests.get(sub_url, timeout=20, headers=headers)
            sub_response.raise_for_status()

            raw_content = sub_response.text
            nodes_from_sub = []

            # 尝试解析为Clash配置
            try:
                clash_config = yaml.safe_load(raw_content)
                if 'proxies' in clash_config and isinstance(clash_config['proxies'], list):
                    nodes_from_sub = clash_config['proxies']
            # 如果不是Clash配置，则尝试解析为节点列表
            except (yaml.YAMLError, AttributeError, TypeError):
                try:
                    content = base64.b64decode(raw_content).decode('utf-8')
                except (binascii.Error, UnicodeDecodeError):
                    content = raw_content
                
                links = content.splitlines()
                for link in links:
                    if link.strip():
                        node = parse_link(link.strip())
                        if node:
                            nodes_from_sub.append(node)

            # 为节点名称添加前缀
            for node in nodes_from_sub:
                if 'name' in node and not node['name'].startswith(f"[{sub_name}] "):
                    node['name'] = f"[{sub_name}] " + node['name']

            logging.info(f"    - 从 '{sub_name}' 原始获取 {len(nodes_from_sub)} 个节点。")

            # 执行订阅内过滤
            if sub_filter_enabled and sub_filter_keywords:
                nodes_after_sub_filter = apply_filter(nodes_from_sub, sub_filter_keywords)
                logging.info(f"    - 订阅内过滤器已开启，过滤后剩余 {len(nodes_after_sub_filter)} 个节点。")
                all_nodes.extend(nodes_after_sub_filter)
            else:
                all_nodes.extend(nodes_from_sub)

        except requests.RequestException as e:
            logging.error(f"  - 下载或处理订阅 '{sub_name}' 失败: {e}. 已跳过此订阅。")
            continue
        except Exception as e:
            logging.error(f"  - 处理订阅 '{sub_name}' 时发生未知错误: {e}", exc_info=False)
            continue

    logging.info(f"所有订阅处理完毕，合并后共 {len(all_nodes)} 个节点。")
    final_nodes = all_nodes

    # 执行全局过滤
    if global_filter_enabled and global_filter_keywords:
        final_nodes = apply_filter(all_nodes, global_filter_keywords)
        logging.info(f"全局过滤后，最终剩余 {len(final_nodes)} 个节点。")
    
    if not final_nodes:
        return make_response("所有节点均被过滤或获取失败，无法生成有效配置。", 400)
    
    # 生成最终配置文件
    try:
        if os.path.exists(CLASH_TEMPLATE_FILE):
             with open(CLASH_TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                template_content = f.read()
        else:
            logging.warning(f"未找到 '{CLASH_TEMPLATE_FILE}'，将使用内置的默认模板。")
            template_content = """port: 7890\nsocks-port: 7891\nallow-lan: true\nmode: rule\nlog-level: info\nexternal-controller: '0.0.0.0:9090'\ndns:\n  enable: true\n  enhanced-mode: redir-host\n  fallback:\n    - 8.8.8.8\n  nameserver:\n    - 223.5.5.5\nproxies: []\nproxy-groups:\n  - name: "PROXY"\n    type: select\n    proxies:\n      - "♻️ 自动选择"\n      - "DIRECT"\n      - "REJECT"\n      - "SELECT"\n  - name: "♻️ 自动选择"\n    type: url-test\n    url: http://www.gstatic.com/generate_204\n    interval: 300\n    proxies:\n      - "SELECT"\nrules:\n  - 'MATCH,PROXY'"""
        
        final_config_str = generate_clash_config(final_nodes, template_content)
        
        response = make_response(final_config_str)
        response.headers['Content-Type'] = 'text/plain; charset=utf-8'
        response.headers['Content-Disposition'] = 'attachment; filename=clash.yaml'
        logging.info("配置生成成功，返回响应。")
        return response

    except Exception as e:
        logging.critical(f"生成最终配置文件时发生严重错误: {e}", exc_info=True)
        return make_response(f"服务器错误: {e}", 500)

# =================================================================================
# API 路由
# =================================================================================

@app.route('/api/data', methods=['GET'])
def get_data():
    """获取所有数据"""
    return jsonify(load_data())

@app.route('/api/subscriptions', methods=['POST'])
def add_subscription():
    """添加新订阅"""
    data = load_data()
    req_data = request.get_json()
    if not req_data or not req_data.get('name') or not req_data.get('url'):
        return jsonify({"message": "请求数据不完整"}), 400
    
    new_sub = {
        "id": str(int(time.time() * 1000)),
        "name": req_data['name'],
        "url": req_data['url'],
        "filter_enabled": False,
        "filter_keywords": ""
    }
    data['subscriptions'].append(new_sub)
    save_data(data)
    return jsonify({"message": "订阅添加成功"}), 201

@app.route('/api/subscriptions/<sub_id>', methods=['PUT'])
def update_subscription(sub_id):
    """更新指定订阅（包括名称、URL和过滤设置）"""
    data = load_data()
    req_data = request.get_json()
    
    for sub in data['subscriptions']:
        if sub['id'] == sub_id:
            sub['name'] = req_data.get('name', sub['name'])
            sub['url'] = req_data.get('url', sub['url'])
            sub['filter_enabled'] = req_data.get('filter_enabled', sub['filter_enabled'])
            sub['filter_keywords'] = req_data.get('filter_keywords', sub['filter_keywords'])
            save_data(data)
            return jsonify({"message": "订阅更新成功"})
    
    return jsonify({"message": "未找到订阅"}), 404

@app.route('/api/subscriptions/<sub_id>', methods=['DELETE'])
def delete_subscription(sub_id):
    """删除指定订阅"""
    data = load_data()
    original_len = len(data['subscriptions'])
    data['subscriptions'] = [sub for sub in data['subscriptions'] if sub['id'] != sub_id]
    
    if len(data['subscriptions']) < original_len:
        if 'aggregation_enabled' in data:
            data['aggregation_enabled'] = [id_ for id_ in data['aggregation_enabled'] if id_ != sub_id]
        save_data(data)
        return jsonify({"message": "订阅删除成功"})
    
    return jsonify({"message": "未找到订阅"}), 404

@app.route('/api/aggregation', methods=['POST'])
def save_aggregation_settings():
    """保存聚合选择"""
    data = load_data()
    req_data = request.get_json()
    data['aggregation_enabled'] = req_data.get('enabled_ids', [])
    save_data(data)
    return jsonify({"message": "聚合选择已保存"})

@app.route('/api/global_filter', methods=['POST'])
def save_global_filter():
    """保存全局过滤设置"""
    data = load_data()
    req_data = request.get_json()
    data['global_filter_enabled'] = req_data.get('enabled', False)
    data['global_filter_keywords'] = req_data.get('keywords', '')
    save_data(data)
    return jsonify({"message": "全局过滤器已保存"})

# --- 主程序入口 ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
