import os
import json
import uuid
import logging
import re
import binascii
import base64

import requests
import yaml
from flask import Flask, request, render_template, make_response, send_from_directory, jsonify

# 你的转换器模块，确保它们在正确的路径下
from converter.parsers import parse_link
from converter.generators import generate_clash_config, CLASH_TEMPLATE

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__, static_url_path='/static')
app.secret_key = os.urandom(24)

# --- 数据存储 ---
DATA_FILE = 'data.json'


def load_data():
    """加载数据，并确保新字段存在，以实现向后兼容"""
    default_data = {'subscriptions': [], 'aggregation_enabled': [], 'global_filter_keywords': '',
                    'global_filter_enabled': False}
    if not os.path.exists(DATA_FILE):
        return default_data

    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # --- 兼容性检查和升级 ---
            if 'subscriptions' in data and isinstance(data['subscriptions'], list):
                for sub in data['subscriptions']:
                    if 'filter_keywords' not in sub:
                        sub['filter_keywords'] = ''
                    if 'filter_enabled' not in sub:
                        sub['filter_enabled'] = False  # 为旧数据添加开关字段

            if 'global_filter_keywords' not in data:
                data['global_filter_keywords'] = ''
            if 'global_filter_enabled' not in data:
                data['global_filter_enabled'] = False  # 为旧数据添加开关字段

            if 'aggregation_enabled' not in data:
                data['aggregation_enabled'] = []

            return data
    except (json.JSONDecodeError, FileNotFoundError):
        return default_data


def save_data(data):
    """保存订阅数据"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# --- 核心过滤函数 ---
def apply_filter(nodes, keywords_str):
    """根据关键词字符串过滤节点列表"""
    if not keywords_str or not isinstance(keywords_str, str):
        return nodes

    keywords = [k.strip().lower() for k in re.split(r'[,\s\n]+', keywords_str) if k.strip()]
    if not keywords:
        return nodes

    logging.info(f"应用过滤，排除包含以下关键词的节点: {keywords}")

    filtered_nodes = []
    for node in nodes:
        node_name_lower = node.get('name', '').lower()
        if not any(keyword in node_name_lower for keyword in keywords):
            filtered_nodes.append(node)
        else:
            logging.debug(f"节点 '{node.get('name')}' 因匹配关键词被过滤。")

    return filtered_nodes


# --- 页面路由 ---
@app.route('/')
def index():
    return render_template('index.html')


# --- API 路由 ---
@app.route('/api/data', methods=['GET'])
def get_data():
    data = load_data()
    return jsonify(data)


@app.route('/api/subscriptions', methods=['POST'])
def add_sub():
    req_data = request.get_json()
    name = req_data.get('name')
    url = req_data.get('url')

    if not name or not url:
        return jsonify({'status': 'error', 'message': '订阅名称和地址都不能为空！'}), 400

    data = load_data()
    new_sub = {
        'id': str(uuid.uuid4()),
        'name': name,
        'url': url,
        'filter_keywords': '',
        'filter_enabled': False  # 新增时默认关闭
    }
    data.get('subscriptions', []).append(new_sub)
    save_data(data)
    return jsonify({'status': 'success', 'message': f'成功添加订阅: {name}', 'subscription': new_sub})


@app.route('/api/subscriptions/<sub_id>', methods=['PUT'])
def edit_sub(sub_id):
    req_data = request.get_json()
    new_name = req_data.get('name')
    new_url = req_data.get('url')
    new_filter_keywords = req_data.get('filter_keywords')
    new_filter_enabled = req_data.get('filter_enabled')  # 接收开关状态

    if not new_name or not new_url:
        return jsonify({'status': 'error', 'message': '订阅名称和地址都不能为空！'}), 400

    data = load_data()
    sub_to_edit = next((sub for sub in data['subscriptions'] if sub['id'] == sub_id), None)

    if not sub_to_edit:
        return jsonify({'status': 'error', 'message': '未找到要编辑的订阅。'}), 404

    sub_to_edit['name'] = new_name
    sub_to_edit['url'] = new_url

    if new_filter_keywords is not None:
        sub_to_edit['filter_keywords'] = new_filter_keywords
    if new_filter_enabled is not None:
        sub_to_edit['filter_enabled'] = new_filter_enabled

    save_data(data)
    return jsonify({'status': 'success', 'message': f'成功修改订阅: {new_name}', 'subscription': sub_to_edit})


@app.route('/api/subscriptions/<sub_id>', methods=['DELETE'])
def delete_sub(sub_id):
    data = load_data()
    if data['subscriptions']:
        sub_to_delete = next((sub for sub in data['subscriptions'] if sub['id'] == sub_id), None)
        if sub_to_delete:
            original_name = sub_to_delete.get("name", "未知")
            data['subscriptions'] = [sub for sub in data['subscriptions'] if sub['id'] != sub_id]
            if sub_id in data.get('aggregation_enabled', []):
                data['aggregation_enabled'].remove(sub_id)
            save_data(data)
            return jsonify({'status': 'success', 'message': f'成功删除订阅: {original_name}'})
    return jsonify({'status': 'error', 'message': '未找到要删除的订阅。'}), 404


@app.route('/api/aggregation', methods=['POST'])
def save_aggregation():
    req_data = request.get_json()
    enabled_ids = req_data.get('enabled_ids', [])
    data = load_data()
    data['aggregation_enabled'] = enabled_ids
    save_data(data)
    return jsonify({'status': 'success', 'message': '聚合配置已更新！'})


@app.route('/api/global_filter', methods=['POST'])
def save_global_filter():
    """(API) 保存全局过滤器，包括关键词和开关状态"""
    req_data = request.get_json()
    keywords = req_data.get('keywords', '')
    enabled = req_data.get('enabled', False)
    data = load_data()
    data['global_filter_keywords'] = keywords
    data['global_filter_enabled'] = enabled
    save_data(data)
    return jsonify({'status': 'success', 'message': '全局过滤配置已保存！'})


# --- 聚合链接路由 (集成带开关的双重过滤) ---
@app.route('/aggregate/clash.yaml')
def aggregate_clash():
    logging.info("=" * 50)
    logging.info("收到新的 /aggregate/clash.yaml 请求")
    data = load_data()
    enabled_ids = set(data.get('aggregation_enabled', []))
    subscriptions_to_aggregate = [sub for sub in data.get('subscriptions', []) if sub['id'] in enabled_ids]

    global_filter_keywords = data.get('global_filter_keywords', '')
    global_filter_enabled = data.get('global_filter_enabled', False)

    if not subscriptions_to_aggregate:
        return make_response("没有启用的订阅，无法生成聚合配置。", 404)

    all_nodes = []
    headers = {'User-Agent': 'Clash/2023.08.17'}

    for sub_info in subscriptions_to_aggregate:
        sub_url = sub_info['url']
        sub_name = sub_info['name']
        sub_filter_keywords = sub_info.get('filter_keywords', '')
        sub_filter_enabled = sub_info.get('filter_enabled', False)

        logging.info(f"  - 正在处理订阅 '{sub_name}': {sub_url}")

        try:
            sub_response = requests.get(sub_url, timeout=15, headers=headers)
            sub_response.raise_for_status()
            raw_content = sub_response.text
            nodes_from_sub = []

            try:
                clash_config = yaml.safe_load(raw_content)
                if 'proxies' in clash_config and isinstance(clash_config['proxies'], list):
                    nodes_from_sub = clash_config['proxies']
            except (yaml.YAMLError, AttributeError, TypeError):
                try:
                    content = base64.b64decode(raw_content).decode('utf-8')
                except (binascii.Error, UnicodeDecodeError):
                    content = raw_content
                links = content.splitlines()
                for link in links:
                    if link.strip():
                        node = parse_link(link.strip())
                        if node: nodes_from_sub.append(node)

            for node in nodes_from_sub:
                node['name'] = f"[{sub_name}] {node['name']}"

            logging.info(f"    - 从 '{sub_name}' 原始获取 {len(nodes_from_sub)} 个节点。")

            # === 第一层过滤：订阅内过滤 (带开关) ===
            if sub_filter_enabled and sub_filter_keywords:
                nodes_after_sub_filter = apply_filter(nodes_from_sub, sub_filter_keywords)
                logging.info(f"    - 订阅内过滤器已开启，过滤后剩余 {len(nodes_after_sub_filter)} 个节点。")
                all_nodes.extend(nodes_after_sub_filter)
            else:
                logging.info("    - 订阅内过滤器关闭或无关键词，跳过。")
                all_nodes.extend(nodes_from_sub)

        except requests.RequestException as e:
            logging.error(f"  - 下载订阅 '{sub_name}' 失败: {e}")
        except Exception as e:
            logging.error(f"  - 处理订阅 '{sub_name}' 时发生未知错误: {e}", exc_info=True)

    logging.info(f"所有订阅处理完毕，合并后共 {len(all_nodes)} 个节点。")

    # === 第二层过滤：全局聚合过滤 (带开关) ===
    if global_filter_enabled and global_filter_keywords:
        final_nodes = apply_filter(all_nodes, global_filter_keywords)
        logging.info(f"全局过滤器已开启，过滤后最终剩余 {len(final_nodes)} 个节点。")
    else:
        final_nodes = all_nodes
        logging.info("全局过滤器关闭或无关键词，跳过。")

    if not final_nodes:
        return make_response("所有节点均被过滤，无法生成有效配置。", 400)

    try:
        final_config = generate_clash_config(final_nodes, CLASH_TEMPLATE)
        response = make_response(final_config)
        response.headers['Content-Disposition'] = f'attachment; filename="clash_aggregated.yaml"'
        response.headers['Content-Type'] = 'text/plain; charset=utf-8'
        logging.info("配置生成成功，返回响应。")
        return response
    except Exception as e:
        logging.error(f"生成最终配置文件时出错: {e}", exc_info=True)
        return make_response(jsonify({'error': f'服务器内部错误: {e}'}), 500)


# --- 静态文件 ---
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico',
                               mimetype='image/vnd.microsoft.icon')


if __name__ == '__main__':
    # 首次运行时创建具有完整结构的data.json
    if not os.path.exists(DATA_FILE):
        save_data({'subscriptions': [], 'aggregation_enabled': [], 'global_filter_keywords': '',
                   'global_filter_enabled': False})
    app.run(host='0.0.0.0', port=5000, debug=True)
