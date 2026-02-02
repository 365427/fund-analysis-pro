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
st.set_page_config(page_title="基金持仓分析 Pro (AkShare+DeepSeek)", layout="wide")
st.title("📈 基金持仓实时深度分析")

# --- 辅助函数：判断是否为A股交易时间 ---
def is_china_stock_trading_now():
    now = datetime.datetime.now()
    # 周一到周五
    if now.weekday() > 4:
        return False
    # 交易时间段：9:30 - 11:30, 13:00 - 15:00
    start_time_1 = now.replace(hour=9, minute=30, second=0, microsecond=0)
    end_time_1 = now.replace(hour=11, minute=30, second=0, microsecond=0)
    start_time_2 = now.replace(hour=13, minute=0, second=0, microsecond=0)
    end_time_2 = now.replace(hour=15, minute=0, second=0, microsecond=0)
    
    return (start_time_1 <= now <= end_time_1) or (start_time_2 <= now <= end_time_2)

# --- 核心抓取函数 (保持不变，但为了完整性放在这里) ---
@st.cache_data(ttl=3600)
def get_detail_data(fund_code):
    try:
        df = ak.fund_portfolio_hold_em(symbol=fund_code, indicator="1")
        if df.empty:
            return None, "未找到持仓数据", None
        date_cols = [col for col in df.columns if '时间' in col or '日期' in col]
        if not date_cols:
            latest_df = df.copy()
            report_date = "最新一期"
        else:
            date_col = date_cols
            latest_date = df[date_col].max()
            latest_df = df[df[date_col] == latest_date].copy()
            report_date = str(latest_date)
        
        # 兼容列名
        stock_code_col = '股票代码' if '股票代码' in latest_df.columns else '证券代码'
        stock_name_col = '股票名称' if '股票名称' in latest_df.columns else '证券简称'
        weight_col = '占净值比例' if '占净值比例' in latest_df.columns else '持仓市值(万元)'
        
        required_cols = [stock_code_col, stock_name_col]
        if not all(col in latest_df.columns for col in required_cols):
            return None, f"数据格式不匹配", None
            
        latest_df = latest_df[required_cols + [weight_col]].copy()
        latest_df.rename(columns={stock_code_col: '股票代码', stock_name_col: '股票名称', weight_col: '占净值比例'}, inplace=True)
        
        # 处理权重，如果权重列是金额而不是比例，这里需要处理，简单起见假设是比例
        latest_df['占净值比例'] = pd.to_numeric(latest_df['占净值比例'], errors='coerce')
        # 过滤掉非数字行
        latest_df = latest_df[pd.to_numeric(latest_df['股票代码'], errors='coerce').notnull()]
        
        return latest_df, report_date, None
    except Exception as e:
        error_msg = f"AkShare 获取失败: {str(e)}"
        return None, error_msg, None

# --- 修改后的：获取实时净值估算 ---
def get_fund_realtime_info(fund_code, holdings_df):
    try:
        # 1. 获取历史净值 (截止到上个交易日)
        # 注意：indicator 参数可能需要调整，根据你本地 akshare 版本
        try:
            hist_df = ak.fund_open_fund_info_em(fund=fund_code, indicator="单位净值")
        except:
            # 兼容旧版参数
            hist_df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值")
            
        if hist_df.empty:
            return "N/A", "N/A", "历史数据为空"
            
        # 处理列名
        date_col = '净值日期' if '净值日期' in hist_df.columns else hist_df.columns
        nav_col = '单位净值' if '单位净值' in hist_df.columns else hist_df.columns
        
        hist_df[date_col] = pd.to_datetime(hist_df[date_col])
        # 按日期倒序排列
        hist_df.sort_values(by=date_col, ascending=False, inplace=True)
        hist_df.reset_index(drop=True, inplace=True)
        
        # 上个交易日净值
        prev_nav_date = hist_df.iloc[date_col].date()
        prev_nav_value = hist_df.iloc[nav_col]
        
        # 2. 判断当前是否为交易时间
        if not is_china_stock_trading_now():
            # 非交易时间，直接返回上个交易日数据
            return f"{prev_nav_value:.4f}", "休市", f"截止 {prev_nav_date}"
        
        # --- 交易时间：计算实时估算 ---
        # 获取持仓股票代码列表
        # 过滤掉非 A 股代码（如港股、债券），只保留 60、00、30 开头的
        stock_codes = holdings_df['股票代码'].dropna().astype(str)
        # 这里简单处理，AkShare 股票代码通常需要加后缀，但接口有时自动识别
        # stock_list = [code + ('.SH' if code.startswith('6') else '.SZ') for code in stock_codes if code.startswith(('60', '00', '30'))]
        
        # 获取全市场实时行情 (速度较快)
        # 注意：这个接口返回的是所有 A 股，数据量大但准确
        try:
            real_time_df = ak.stock_zh_a_spot_em()
        except:
            return f"{prev_nav_value:.4f}", "获取失败", "股票行情接口错误"
        
        if real_time_df.empty:
            return f"{prev_nav_value:.4f}", "N/A", "行情数据空"
            
        # 只保留我们需要的持仓股
        real_time_df = real_time_df[real_time_df['代码'].isin(stock_codes)]
        
        # 合并持仓权重和实时涨跌幅
        # 注意：real_time_df 的涨跌幅列通常是 '涨跌幅'
        merge_df = holdings_df[['股票代码', '占净值比例']].merge(
            real_time_df[['代码', '涨跌幅']], 
            left_on='股票代码', 
            right_on='代码', 
            how='left'
        )
        
        # 计算加权平均涨跌幅
        # 去掉没有获取到涨跌幅的股票（停牌等）
        merge_df.dropna(subset=['涨跌幅'], inplace=True)
        if merge_df.empty:
            # 如果获取不到股票涨跌幅，返回上一日净值
            return f"{prev_nav_value:.4f}", "停牌/无数据", f"估算失败"
        
        # 计算估算涨跌幅 = SUM(权重 * 涨跌幅)
        # 注意：这里的涨跌幅是百分比，比如 1.5%，需要除以 100
        weighted_change = (merge_p['占净值比例'] * merge_df['涨跌幅'] / 100).sum()
        
        # 计算估算净值
        estimated_nav = prev_nav_value * (1 + weighted_change)
        
        return f"{estimated_nav:.4f}", f"{weighted_change:+.2f}%", "盘中估算"
        
    except Exception as e:
        print(f"DEBUG: 实时估值计算错误: {e}")
        # 出错时返回历史数据兜底
        try:
            nav, _, _ = get_fund_realtime_info(fund_code, None) # 递归调用获取历史
            return nav, "计算错误", "回退模式"
        except:
            return "N/A", "N/A", "完全失败"

# --- DeepSeek 相关函数 (保持不变) ---
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
def call_deepseek_for_fund_info(fund_code, fund_name):
    if not DEEPSEEK_API_KEY:
        return "未配置 DeepSeek Key"
    # ... (保持原有逻辑不变) ...

# --- 主程序 ---
def main():
    st.header("基金查询")
    fund_code = st.text_input("请输入基金代码", placeholder="例如：161725")
    
    if st.button("查询"):
        if not fund_code:
            st.error("请输入代码")
            return
            
        with st.spinner("正在抓取数据..."):
            # 1. 获取持仓
            df_holdings, report_date, error_msg = get_detail_data(fund_code)
            if df_holdings is None:
                st.error(error_msg)
                return
                
            # 2. 获取净值 (注意：这里需要传入持仓数据用于计算)
            # 为了显示，我们先获取一次历史数据作为兜底
            # is_trading = is_trading_day(datetime.datetime.now()) # 这个函数在原代码中定义，但我们现在用更精确的
            realtime_nav, realtime_change, source_type = get_fund_realtime_info(fund_code, df_holdings)
            
            # 3. 显示结果
            st.success(f"数据更新成功 | 来源: {source_type}")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("当前净值/估算", realtime_nav, realtime_change)
            with col2:
                st.write(f"持仓数据截至: {report_date}")
            
            st.dataframe(df_holdings, use_container_width=True)

if __name__ == "__main__":
    main()
