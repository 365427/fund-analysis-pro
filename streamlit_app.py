import streamlit as st
import pandas as pd
import os
import time
import requests
import akshare as ak
import inspect
import datetime
import io

# --- 1. 页面配置 ---
st.set_page_config(page_title="基金持仓分析 Pro (AkShare)", layout="wide")
st.title("📈 基金持仓实时深度分析")

# --- 2. 辅助函数：判断是否为交易日 ---
def is_trading_day(date_to_check):
    if date_to_check.weekday() > 4:
        return False
    return True

# --- 3. 核心抓取函数 ---
@st.cache_data(ttl=3600)
def get_detail_data(fund_code):
    try:
        df = ak.fund_portfolio_hold_em(symbol=fund_code)
        if df.empty:
            return None, "未找到持仓数据", None
        date_cols = [col for col in df.columns if '时间' in col or '日期' in col or 'quarter' in col.lower() or 'date' in col.lower()]
        if not date_cols:
            latest_df = df.copy()
            report_date = "最新一期"
        else:
            date_col = date_cols
            latest_date = df[date_col].max()
            latest_df = df[df[date_col] == latest_date].copy()
            report_date = str(latest_date)
        required_cols = ['股票代码', '股票名称', '占净值比例']
        if not all(col in latest_df.columns for col in required_cols):
            missing = [col for col in required_cols if col not in latest_df.columns]
            return None, f"数据格式不匹配，缺少字段: {missing}", None
        latest_df = latest_df[required_cols].copy()
        latest_df.rename(columns={'占净值比例': 'curr_weight'}, inplace=True)
        latest_df['curr_weight'] = pd.to_numeric(latest_df['curr_weight'], errors='coerce').fillna(0)
        return latest_df, report_date, None
    except Exception as e:
        error_msg = f"AkShare 获取失败: {str(e)}"
        return None, error_msg, None

# --- 4. 获取实时净值估算或历史涨跌幅 ---
def get_fund_realtime_info(fund_code, is_today_trading_day):
    try:
        sig = inspect.signature(ak.fund_open_fund_info_em)
        params = list(sig.parameters.keys())
        fund_param_name = None
        for name in ['symbol', 'code', 'fund_code', 'fund']:
            if name in params:
                fund_param_name = name
                break
        if not fund_param_name:
            print(f"DEBUG: 未找到基金代码对应的参数名。可用参数: {params}")
            return "N/A", "N/A"
        call_kwargs = {fund_param_name: fund_code, 'indicator': '单位净值走势'}
        hist_df = ak.fund_open_fund_info_em(**call_kwargs)
        if hist_df.empty:
            print(f"DEBUG: 基金 {fund_code} 的历史数据为空。")
            return "N/A", "N/A"
        date_col_candidates = [col for col in hist_df.columns if '净值日期' in col or 'date' in col.lower() or '日期' in col]
        if not date_col_candidates:
            print(f"DEBUG: 基金 {fund_code} 未找到日期列。列名为: {list(hist_df.columns)}")
            return "N/A", "N/A"
        date_col = date_col_candidates
        nav_col_candidates = [col for col in hist_df.columns if '单位净值' in col or '估算' in col]
        if not nav_col_candidates:
             print(f"DEBUG: 基金 {fund_code} 未找到净值列。列名为: {list(hist_df.columns)}")
             return "N/A", "N/A"
        nav_col = nav_col_candidates
        hist_df.sort_values(by=date_col, ascending=False, inplace=True)
        hist_df.reset_index(drop=True, inplace=True)
        nav_series = hist_df[nav_col].dropna()
        if len(nav_series) < 2:
            print(f"DEBUG: 基金 {fund_code} 数据不足，无法计算涨跌幅。")
            return "N/A", "N/A"
        current_nav = nav_series.iloc
        prev_nav = nav_series.iloc
        if prev_nav == 0:
            daily_growth = 0
        else:
            daily_growth = ((current_nav - prev_nav) / prev_nav) * 100
        formatted_nav = f"{current_nav:.4f}"
        formatted_growth = f"{daily_growth:+.2f}%"
        return formatted_nav, formatted_growth
    except KeyError as e:
        print(f"DEBUG: 基金 {fund_code} 发生 KeyError: {e}.")
        return "N/A", "N/A"
    except IndexError as e:
        print(f"DEBUG: 基金 {fund_code} 发生 IndexError: {e}.")
        return "N/A", "N/A"
    except Exception as e:
        print(f"DEBUG: 基金 {fund_code} 发生未知错误: {e}")
        return "N/A", "N/A"

# --- 6. 搜索与收藏逻辑 ---
@st.cache_data(ttl=3600)
def get_all_funds():
    try:
        return ak.fund_name_em()[['基金代码', '基金简称']]
    except Exception as e:
        st.warning(f"无法获取基金列表: {e}")
        return pd.DataFrame(columns=['基金代码', '基金简称'])

CSV_FILE = 'fund_favs.csv'

def load_favs(): 
    if os.path.exists(CSV_FILE):
        df = pd.read_csv(CSV_FILE, dtype={'代码': str})
        if '涨跌幅' not in df.columns:
            df['涨跌幅'] = 'N/A'
        return df[['代码', '名称', '涨跌幅']]
    else:
        return pd.DataFrame(columns=['代码', '名称', '涨跌幅'])

def save_favs(df): 
    df.to_csv(CSV_FILE, index=False)

# --- 8. 主程序逻辑 (需要根据实际情况补充UI部分) ---
# 注意：原代码中没有展示UI部分，这里仅保留数据逻辑
# 你需要确保在 Streamlit 界面中调用 get_detail_data 和 get_fund_realtime_info 即可
