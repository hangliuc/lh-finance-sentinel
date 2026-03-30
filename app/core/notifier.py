# app/core/notifier.py
import requests
import logging

class FeishuNotifier:
    def __init__(self, config):
        self.webhook_url = config['url']
        self.headers = {"Content-Type": "application/json"}

    def send_card(self, title, markdown_content=None, elements=None, template="blue"):
        """
        发送飞书互动卡片 (支持高级 Grid 布局)
        """
        card_elements = []
        
        # 兼容旧版的简单 Markdown 传入
        if markdown_content:
            card_elements.append({
                "tag": "markdown",
                "content": markdown_content
            })
            
        # 拼接高级元素 (如 div, fields, note 等)
        if elements:
            card_elements.extend(elements)

        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {
                    "wide_screen_mode": True  # 强制开启宽屏，卡片更紧凑，防止文字换行
                },
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title
                    },
                    "template": template
                },
                "elements": card_elements
            }
        }
        
        try:
            resp = requests.post(self.webhook_url, json=payload, headers=self.headers, timeout=10)
            result = resp.json()
            if result.get('code') == 0:
                logging.info(f"飞书卡片推送成功: {title}")
            else:
                logging.error(f"飞书推送失败: {result}")
        except Exception as e:
            logging.error(f"飞书网络异常: {e}")