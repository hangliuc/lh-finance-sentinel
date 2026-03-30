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
        
        # 1. 构造完美的表格头部 (使用权重 3:2:2 控制列宽)
        elements = [
            {
                "tag": "column_set",
                "flex_mode": "none",
                "columns": [
                    {"tag": "column", "width": "weighted", "weight": 3, "elements": [{"tag": "markdown", "content": "**📊 标的**"}]},
                    {"tag": "column", "width": "weighted", "weight": 2, "elements": [{"tag": "markdown", "content": "**💰 现价**"}]},
                    {"tag": "column", "width": "weighted", "weight": 2, "elements": [{"tag": "markdown", "content": "**📈 涨跌**"}]}
                ]
            },
            {"tag": "hr"} # 表头下的分割线
        ]
        
        valid_items = 0

        # 2. 构造表格数据行
        for item in self.config['holdings']:
            name = item['name']
            # 为了表格紧凑，如果名字里有"指数"两个字可以自动去掉（可选优化）
            name = name.replace(" 指数", "") 
            symbol = item['symbol_ref']
            
            price, day_change = self._get_price(symbol)
            if price is None or price == 0: continue
            valid_items += 1
            
            if day_change > 0:
                color = "red"
                sign = "+"
            elif day_change < 0:
                color = "green"
                sign = "" 
            else:
                color = "grey"
                sign = ""

            # 每一行都是一个 column_set，保证绝对的垂直对齐
            # 去掉了花哨的 emoji，回归纯粹的数据展示
            elements.append({
                "tag": "column_set",
                "flex_mode": "none",
                "columns": [
                    {"tag": "column", "width": "weighted", "weight": 3, "elements": [{"tag": "markdown", "content": f"**{name}**"}]},
                    {"tag": "column", "width": "weighted", "weight": 2, "elements": [{"tag": "markdown", "content": f"{price}"}]},
                    {"tag": "column", "width": "weighted", "weight": 2, "elements": [{"tag": "markdown", "content": f"<font color='{color}'>{sign}{day_change}%</font>"}]}
                ]
            })
            
        if valid_items == 0:
            logging.warning("日报内容为空，跳过发送")
            return

        # 3. 底部风控纪律
        elements.append({"tag": "hr"})
        elements.append({
            "tag": "note",
            "elements": [
                {
                    "tag": "lark_md",
                    "content": "💡 **风控纪律**: 优质资产越跌越买，做时间的朋友"
                }
            ]
        })
        
        current_time = time.strftime("%Y-%m-%d %H:%M")
        title = f"💷 收盘日报 ({current_time})"
        
        self.notifier.send_card(title=title, elements=elements, template="watchet")