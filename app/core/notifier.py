# app/core/notifier.py
import requests
import logging

class FeishuNotifier:
    def __init__(self, config):
        self.webhook_url = config['url']
        self.headers = {"Content-Type": "application/json"}

    def send_card(self, title, markdown_content, template="blue"):
        """
        发送飞书互动卡片
        :param title: 卡片标题
        :param markdown_content: 卡片正文 (支持飞书 Markdown)
        :param template: 顶栏颜色 (blue, watchet, red, green, orange 等)
        """
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title
                    },
                    "template": template
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": markdown_content
                    }
                ]
            }
        }
        
        try:
            resp = requests.post(self.webhook_url, json=payload, headers=self.headers, timeout=10)
            result = resp.json()
            # 飞书成功的 code 是 0
            if result.get('code') == 0:
                logging.info(f"飞书卡片推送成功: {title}")
            else:
                logging.error(f"飞书推送失败: {result}")
        except Exception as e:
            logging.error(f"飞书网络异常: {e}")