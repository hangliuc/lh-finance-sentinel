# app/tasks/daily_reporter.py
import requests
import logging
import re
import time
from datetime import datetime
from html.parser import HTMLParser
from chinese_calendar import is_workday


class _FundNavTableParser(HTMLParser):
    """提取搜狐基金净值列表中的日期和单位净值。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


class DailyReporter:
    def __init__(self, config, notifier):
        self.config = config
        self.notifier = notifier
        self.base_url = "http://qt.gtimg.cn/q="
        self.fund_nav_url = "https://q.fund.sohu.com/q/vl.php"
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
            min_fields = 6 if symbol.startswith("gz") else 10
            if len(fields) < min_fields: return None, 0.0

            current_price = float(fields[3])

            # 腾讯全球指数(gz*)返回“涨跌额、涨跌幅”，而非昨收价。
            if symbol.startswith("gz"):
                change_pct = float(fields[5]) if fields[5] else 0.0
            else:
                prev_close = float(fields[4])
                if current_price == 0: current_price = prev_close

                change_pct = 0.0
                if prev_close > 0:
                    change_pct = ((current_price - prev_close) / prev_close) * 100
            
            return current_price, round(change_pct, 2)
        except Exception as e:
            logging.error(f"获取行情失败 {symbol}: {e}")
            return None, 0.00

    def _get_historical_changes(self, symbol):
        """按基金单位净值计算最近两日涨跌幅，返回 [T-1, T-2]。"""
        try:
            match = re.search(r"(\d{6})$", symbol)
            if not match:
                return []

            resp = requests.get(
                self.fund_nav_url,
                params={"code": match.group(1)},
                headers=self.headers,
                timeout=5,
            )
            parser = _FundNavTableParser()
            parser.feed(resp.text)

            today = datetime.now().date()
            nav_by_date = {}
            for row in parser.rows:
                if len(row) < 2:
                    continue
                date_match = re.search(r"\d{4}-\d{2}-\d{2}", row[0])
                value_match = re.search(r"\d+(?:\.\d+)?", row[1])
                if not date_match or not value_match:
                    continue
                trade_date = datetime.strptime(date_match.group(), "%Y-%m-%d").date()
                nav = float(value_match.group())
                if trade_date < today and nav > 0:
                    nav_by_date[trade_date] = nav

            navs = sorted(nav_by_date.items(), reverse=True)
            if len(navs) < 3:
                return []

            changes = []
            for (_, current_nav), (_, previous_nav) in zip(navs, navs[1:]):
                if previous_nav > 0:
                    changes.append(round((current_nav - previous_nav) / previous_nav * 100, 2))

            return changes[:2]
        except Exception as e:
            logging.error(f"获取基金净值失败 {symbol}: {e}")
            return []

    @staticmethod
    def _change_text(change):
        if change is None:
            return "—"
        if change > 0:
            return f"+{change:.2f}%"
        elif change < 0:
            return f"{change:.2f}%"
        return "0.00%"

    @classmethod
    def _format_change(cls, change, emphasized=False):
        """按中国市场习惯显示涨跌：红涨、绿跌，缺失值使用中性灰。"""
        if change is None:
            return "<font color='grey'>—</font>"

        color = "red" if change > 0 else "green" if change < 0 else "grey"
        content = cls._change_text(change)
        if emphasized:
            return f"**<font color='{color}'>{content}</font>**"
        return f"<font color='{color}'>{content}</font>"

    @staticmethod
    def _value_markdown(content, text_align="center"):
        return {"tag": "markdown", "content": content, "text_align": text_align}

    @classmethod
    def _build_table_header(cls):
        """用灰底建立表头，让表格和顶部指数区块形成统一的卡片层级。"""
        return {
            "tag": "column_set",
            "flex_mode": "none",
            "background_style": "grey",
            "horizontal_spacing": "small",
            "columns": [
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 3,
                    "vertical_align": "center",
                    "elements": [cls._value_markdown("**❤️ 我的持仓**", "left")],
                },
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 2,
                    "vertical_align": "center",
                    "elements": [cls._value_markdown("**T 日**\n<font color='grey'>场内</font>")],
                },
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 2,
                    "vertical_align": "center",
                    "elements": [cls._value_markdown("**T-1**\n<font color='grey'>净值</font>")],
                },
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 2,
                    "vertical_align": "center",
                    "elements": [cls._value_markdown("**T-2**\n<font color='grey'>净值</font>")],
                },
            ],
        }

    @classmethod
    def _build_holding_row(cls, row):
        return {
            "tag": "column_set",
            "flex_mode": "none",
            "horizontal_spacing": "small",
            "columns": [
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 3,
                    "vertical_align": "center",
                    "elements": [cls._value_markdown(f"**{row['name']}**", "left")],
                },
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 2,
                    "vertical_align": "center",
                    "elements": [
                        cls._value_markdown(cls._format_change(row["change"], emphasized=True))
                    ],
                },
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 2,
                    "vertical_align": "center",
                    "elements": [cls._value_markdown(cls._format_change(row["t1_change"]))],
                },
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 2,
                    "vertical_align": "center",
                    "elements": [cls._value_markdown(cls._format_change(row["t2_change"]))],
                },
            ],
        }

    def _build_index_column(self, item):
        """构造顶部大盘指数列 (居中展示，配色 + 箭头)"""
        name = item['name']
        flag = item.get('flag', '')
        symbol = item['symbol_ref']

        price, day_change = self._get_price(symbol)
        if price is None or price == 0:
            return None

        if day_change > 0:
            color = "red"
            arrow = "▲"
        elif day_change < 0:
            color = "green"
            arrow = "▼"
        else:
            color = "grey"
            arrow = "•"

        # 指数(如上证 3000+)用千分位，ETF/个股保留两位小数即可
        if price >= 1000:
            price_str = f"{price:,.2f}"
        else:
            price_str = f"{price}"

        content = (
            f"<font color='grey'>{flag} {name}</font>\n"
            f"**{price_str}**\n"
            f"<font color='{color}'>{arrow} {self._change_text(day_change)}</font>"
        )

        return {
            "tag": "column",
            "width": "weighted",
            "weight": 1,
            "vertical_align": "center",
            "elements": [
                {"tag": "markdown", "content": content, "text_align": "center"}
            ]
        }

    def run(self):
        if not self._is_trading_day():
            return

        logging.info("开始执行 [日报任务]...")

        elements = []

        # ============ 1. 顶部大盘指数 (动态卡片) ============
        index_columns = []
        for item in self.config.get('indices', []):
            col = self._build_index_column(item)
            if col is not None:
                index_columns.append(col)

        if index_columns:
            elements.append({
                "tag": "column_set",
                "flex_mode": "stretch",
                "background_style": "grey",
                "horizontal_spacing": "small",
                "columns": index_columns
            })
            elements.append({"tag": "hr"})

        # ============ 2. 持仓列表表头 ============
        elements.append(self._build_table_header())
        elements.append({"tag": "hr"})

        valid_items = 0

        # ============ 3. 持仓数据行 (按涨跌幅由大到小排序，每行后加分割线) ============
        holdings = self.config.get('holdings', [])

        # 3.1 取 T 日场内行情，并读取 T-1/T-2 基金单位净值
        rows = []
        for item in holdings:
            name = item['name'].replace(" 指数", "")
            symbol = item['symbol_ref']
            price, day_change = self._get_price(symbol)
            if price is None or price == 0:
                continue
            history_changes = self._get_historical_changes(symbol)
            rows.append({
                "name": name,
                "change": day_change,
                "t1_change": history_changes[0] if len(history_changes) > 0 else None,
                "t2_change": history_changes[1] if len(history_changes) > 1 else None,
            })

        # 3.2 按涨跌幅由大到小排序 (涨幅最大在最上)
        rows.sort(key=lambda r: r["change"], reverse=True)

        # 3.3 渲染
        for idx, row in enumerate(rows):
            valid_items += 1

            elements.append(self._build_holding_row(row))
            # 每行后加一条淡分割线 (最后一行不加，由底部 hr 收尾)
            if idx < len(rows) - 1:
                elements.append({"tag": "hr"})

        if valid_items == 0:
            logging.warning("日报内容为空，跳过发送")
            return

        # ============ 4. 底部风控纪律 ============
        elements.append({"tag": "hr"})
        elements.append({
            "tag": "note",
            "elements": [
                {
                    "tag": "lark_md",
                    "content": "💡 按 T 日涨跌排序 · 红涨绿跌 · 净值数据为 T-1 / T-2"
                }
            ]
        })

        current_time = time.strftime("%Y-%m-%d %H:%M")
        title = f"📊 收盘日报 ({current_time})"

        self.notifier.send_card(title=title, elements=elements, template="indigo")
