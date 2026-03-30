# app/tasks/gold_watcher.py
import requests
import logging
import datetime

class GoldWatcher:
    def __init__(self, config, notifier):
        self.notifier = notifier
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        self.alerted_levels = set()
        self.baseline_price = None
        self.last_reset_date = datetime.date.today()

    def _check_reset(self):
        today = datetime.date.today()
        if today != self.last_reset_date:
            logging.info(f"📅 日期变更，重置黄金报警状态")
            self.alerted_levels.clear()
            self.baseline_price = None 
            self.last_reset_date = today

    def _get_price(self):
        url = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU/USD"
        try:
            resp = requests.get(url, headers=self.headers, timeout=30)
            data = resp.json()
            if not data: return 0.0
            quote = data[0]['spreadProfilePrices'][0]
            bid = float(quote['bid'])
            ask = float(quote['ask'])
            return (bid + ask) / 2
        except Exception as e:
            logging.error(f"⚠️ 黄金接口异常: {e}")
            return 0.0

    def run(self):
        self._check_reset()

        price = self._get_price()
        if price == 0: return

        if self.baseline_price is None:
            self.baseline_price = price
            logging.info(f"⚓️ 黄金基准价已锁定: {price:.2f}")
            return

        pct = ((price - self.baseline_price) / self.baseline_price) * 100
        logging.info(f"🔎 黄金当前: {price:.2f}, 波动: {pct:+.2f}%")

        level = 0
        step = 1.0 

        if pct >= 1.0:
            level = int(pct / step) 
        elif pct <= -1.0:
            level = int(pct / step)
        
        if level != 0 and level not in self.alerted_levels:
            trigger_val = abs(level * step)
            
            # --- 飞书卡片动态视觉 ---
            if level > 0:
                direction = "暴涨"
                icon = "🚀"
                template = "red"  # 红色顶栏
                color = "red"     # 红色文字
            else:
                direction = "跳水"
                icon = "📉"
                template = "green" # 绿色顶栏
                color = "green"    # 绿色文字
            
            title = f"{icon} 黄金风控警报 🚨"
            
            # 飞书 Markdown 高亮排版
            md_content = (
                f"**标的**： 伦敦金 (XAU)\n"
                f"**动态**： <font color='{color}'>{direction}超 {trigger_val:.1f}%</font>\n"
                f"**现价**： `{price:.2f}`\n"
                f"**今日波动**： <font color='{color}'>{pct:+.2f}%</font>"
            )
            
            self.notifier.send_card(title=title, markdown_content=md_content, template=template)
            
            self.alerted_levels.add(level)
            if level > 0:
                for i in range(1, level): self.alerted_levels.add(i)
            elif level < 0:
                for i in range(level + 1, 0): self.alerted_levels.add(i)