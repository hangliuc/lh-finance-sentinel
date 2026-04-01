# app/core/notifier.py
import requests
import logging
import time

class FeishuNotifier:
    def __init__(self, config):
        self.webhook_url = config['url']
        self.headers = {"Content-Type": "application/json"}

    def send_card(self, title, markdown_content=None, elements=None, template="blue", max_retries=3):
        """
        发送飞书互动卡片 (支持高级 Grid 布局与自动重试机制)
        """
        card_elements = []
        
        if markdown_content:
            card_elements.append({
                "tag": "markdown",
                "content": markdown_content
            })
            
        if elements:
            card_elements.extend(elements)

        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {
                    "wide_screen_mode": True  
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
        
        # --- SRE 标准重试机制 (Exponential Backoff) ---
        for attempt in range(max_retries):
            try:
                resp = requests.post(self.webhook_url, json=payload, headers=self.headers, timeout=10)
                result = resp.json()
                
                # 1. 发送成功，直接跳出循环
                if result.get('code') == 0:
                    logging.info(f"✅ 飞书卡片推送成功: {title}")
                    return 
                    
                # 2. 触发飞书限流，执行退避重试
                elif result.get('code') == 11232:
                    wait_time = 2 ** attempt  # 指数退避: 1s, 2s, 4s
                    logging.warning(f"⚠️ 飞书触发限流 (尝试 {attempt+1}/{max_retries})，等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                    continue
                    
                # 3. 其他类型的 API 报错（如配置错误等），重试也没用，直接报错并跳出
                else:
                    logging.error(f"❌ 飞书推送失败 (致命错误): {result}")
                    break 

            # 4. 捕获网络层面的异常（如 DNS 解析失败、超时等）
            except requests.exceptions.RequestException as e:
                wait_time = 2 ** attempt
                logging.warning(f"⚠️ 网络请求异常 ({e}) (尝试 {attempt+1}/{max_retries})，等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)

        # 如果循环结束还没 return，说明重试次数用光了
        logging.error(f"🚨 飞书推送彻底失败: {title}，已达到最大重试次数 ({max_retries})。")