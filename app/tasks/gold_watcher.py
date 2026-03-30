# app/tasks/gold_watcher.py
import requests
import logging
import datetime
import json
import os

DATA_FILE = "/app/data/gold_state.json"

class GoldWatcher:
    def __init__(self, config, notifier):
        self.notifier = notifier
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        self.alerted_levels = set()
        self.baseline_price = None
        self.last_reset_date = datetime.date.today()
        
        self._load_state()

    def _load_state(self):
        if not os.path.exists(DATA_FILE): return
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                if data.get('date') == str(datetime.date.today()):
                    self.baseline_price = data.get('baseline')
                    self.alerted_levels = set(data.get('levels', []))
                    logging.info(f"💾 已从磁盘恢复今日状态: 黄金基准价 {self.baseline_price}")
        except Exception as e:
            logging.error(f"读取状态失败: {e}")

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
            data = {
                'date': str(self.last_reset_date),
                'baseline': self.baseline_price,
                'levels': list(self.alerted_levels)
            }
            with open(DATA_FILE, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logging.error(f"保存状态失败: {e}")

    def _check_reset(self):
        today = datetime.date.today()
        if today != self.last_reset_date:
            logging.info(f"📅 日期变更，重置黄金报警状态")
            self.alerted_levels.clear()
            self.baseline_price = None 
            self.last_reset_date = today

    def _get_swissquote_data(self, instrument):
        """通用瑞讯银行接口抓取"""
        url = f"https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/{instrument}"
        try:
            resp = requests.get(url, headers=self.headers, timeout=10)
            data = resp.json()
            if not data: return 0.0
            quote = data[0]['spreadProfilePrices'][0]
            return (float(quote['bid']) + float(quote['ask'])) / 2
        except Exception as e:
            logging.error(f"⚠️ 接口异常 ({instrument}): {e}")
            return 0.0

    def run(self):
        self._check_reset()

        # 1. 获取伦敦金(USD/oz) 和 离岸人民币汇率(USD/CNH)
        xau_price = self._get_swissquote_data("XAU/USD")
        if xau_price == 0: return
        
        usd_cnh = self._get_swissquote_data("USD/CNH")
        if usd_cnh == 0: usd_cnh = 7.25 # 极端情况下的保底汇率
        
        # 2. 国际标准换算：计算国内 AU9999 (元/克)
        # 1 金衡盎司(Troy Ounce) = 31.1034768 克
        au9999_price = (xau_price / 31.1034768) * usd_cnh

        if self.baseline_price is None:
            self.baseline_price = xau_price
            self._save_state() 
            logging.info(f"⚓️ 黄金基准价已锁定: {xau_price:.2f} USD/oz")
            return

        pct = ((xau_price - self.baseline_price) / self.baseline_price) * 100
        logging.info(f"🔎 黄金当前: {xau_price:.2f}, 折合 {au9999_price:.2f} 元/克, 波动: {pct:+.2f}%")

        level = 0
        step = 1.0

        if pct >= 1.0:
            level = int(pct / step) 
        elif pct <= -1.0:
            level = int(pct / step)
        
        # 3. 触发飞书高级卡片报警
        if level != 0 and level not in self.alerted_levels:
            trigger_val = abs(level * step)
            
            if level > 0:
                direction = "暴涨"
                icon = "🚀"
                template = "red" 
                color = "red"    
                sign = "+"
            else:
                direction = "跳水"
                icon = "📉"
                template = "green" 
                color = "green"    
                sign = ""

            title = f"{icon} 黄金风控警报 🚨"
            
            # 使用飞书的 fields 布局，实现完美的双列 Key-Value 仪表盘
            elements = [
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {"tag": "lark_md", "content": "**📌 监控标的**\n伦敦金 (XAU)"}
                        },
                        {
                            "is_short": True,
                            "text": {"tag": "lark_md", "content": f"**⏱ 触发动态**\n<font color='{color}'>{direction}超 {trigger_val:.1f}%</font>"}
                        },
                        {
                            "is_short": True,
                            "text": {"tag": "lark_md", "content": f"**💵 现价 (USD/oz)**\n`{xau_price:.2f}`"}
                        },
                        {
                            "is_short": True,
                            "text": {"tag": "lark_md", "content": f"**💴 折合 (AU9999/克)**\n`¥ {au9999_price:.2f}`"}
                        },
                        {
                            "is_short": False, # 单独占一行
                            "text": {"tag": "lark_md", "content": f"**📈 今日波动**\n<font color='{color}'>{sign}{pct:.2f}%</font>"}
                        }
                    ]
                },
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [{"tag": "lark_md", "content": "💡 **风控纪律**: 黄金避险盾适用「532战法」，切勿一次性卖出"}]
                }
            ]
            
            # 推送卡片 (基于修改后的 notifier.py 支持 elements 参数)
            self.notifier.send_card(title=title, elements=elements, template=template)
            
            self.alerted_levels.add(level)
            if level > 0:
                for i in range(1, level): self.alerted_levels.add(i)
            elif level < 0:
                for i in range(level + 1, 0): self.alerted_levels.add(i)
            
            self._save_state()