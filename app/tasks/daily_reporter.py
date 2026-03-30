# app/tasks/daily_reporter.py
import requests
import logging
import time
from datetime import datetime
from chinese_calendar import is_workday

class DailyReporter:
    def __init__(self, config, notifier):
        self.config = config
        self.notifier = notifier
        self.base_url = "http://qt.gtimg.cn/q="
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def _is_trading_day(self):
        today = datetime.now().date()
        if not is_workday(today):
            logging.info("😴 今天是法定节假日或休息日，A股休市")
            return False
        if today.weekday() >= 5:
            logging.info("😴 今天是调休上班日(周末)，A股休市")
            return False
        return True

    def _get_price(self, symbol):
        try:
            url = f"{self.base_url}{symbol}"
            resp = requests.get(url, headers=self.headers, timeout=5)
            try:
                content = resp.content.decode('gbk').strip()
            except UnicodeDecodeError:
                content = resp.text.strip()

            if '="' not in content: return None, 0.0
            data_str = content.split('="')[1].split('"')[0]
            if not data_str: return None, 0.0
            fields = data_str.split("~")
            if len(fields) < 10: return None, 0.0

            current_price = float(fields[3])
            prev_close = float(fields[4])
            if current_price == 0: current_price = prev_close

            change_pct = 0.0
            if prev_close > 0:
                change_pct = ((current_price - prev_close) / prev_close) * 100
            
            return current_price, round(change_pct, 2)
        except Exception as e:
            logging.error(f"获取行情失败 {symbol}: {e}")
            return None, 0.00

    def run(self):
        if not self._is_trading_day():
            return

        logging.info("开始执行 [日报任务]...")
        lines = []
        
        for item in self.config['holdings']:
            name = item['name']
            symbol = item['symbol_ref']
            
            price, day_change = self._get_price(symbol)
            if price is None or price == 0: continue
            
            # --- 飞书视觉美化逻辑 (A股红涨绿跌) ---
            if day_change > 0:
                color = "red"
                icon = "📈" 
                sign = "+"
            elif day_change < 0:
                color = "green"
                icon = "📉" 
                sign = "" 
            else:
                color = "grey"
                icon = "⚪" 
                sign = ""

            # 飞书 Markdown 格式：
            # **红利低波50ETF**
            # 现价: 1.05  |  波动: <font color='red'>+1.2%</font> 📈
            line = f"**{name}**\n现价: `{price}`  |  波动: <font color='{color}'>{sign}{day_change}%</font> {icon}"
            lines.append(line)
            
        if not lines:
            logging.warning("日报内容为空，跳过发送")
            return

        # 使用飞书卡片的横线分隔符
        report_content = "\n\n---\n\n".join(lines)
        
        current_time = time.strftime("%Y-%m-%d %H:%M")
        title = f"💷 收盘日报 ({current_time})"
        
        # 调用飞书卡片，顶栏使用高级灰蓝色 (watchet)
        self.notifier.send_card(title=title, markdown_content=report_content, template="watchet")