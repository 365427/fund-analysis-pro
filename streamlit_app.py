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
st.set_page_config(page_title="基金持仓分析 Pro", layout="wide")
st.title("📈 基金持仓实时深度分析")

# --- 2. 辅助函数：判断是否为交易时间 ---
def is_trading_time():
    """判断当前时间是否为 A 股交易时间 (周一至周五 9:30-11:30, 13:00-15:00)"""
    now = datetime.datetime.now()
    weekday = now.weekday()  # 周一为 0
    hour, minute = now.hour, now.minute
    
    # 周末直接返回 False
    if weekday >= 5:
        return False
    
    # 周一到周五
    morning_start = hour == 9 and minute >= 30
    morning_end = hour < 11 or (hour == 11 and minute <= 30)
    afternoon_start = hour >= 13
    afternoon_end = hour < 15
    
    is_morning = morning_start and morning_end
    is_afternoon = afternoon_start and afternoon_end
    
    return is_morning or is_afternoon

# --- 3. 核心抓取函数：获取持仓详情 ---
@st.cache_data(ttl=3600)
def get_detail_data(fund_code):
    try:
        # 【修复】指定 indicator="1" 获取股票持仓
        df = ak.fund_portfolio_hold_em(symbol=fund_code, indicator="1") 
        
        if df.empty:
            return None, "未找到持仓数据", None
            
        # 处理日期，获取最新一期
        date_cols = [col for col in df.columns if '报告期' in col or '时间' in col]
        if not date_cols:
            report_date = "最新一期"
            latest_df = df.copy()
        else:
            date_col = date_cols[0]
            df[date_col] = pd.to_datetime(df[date_col])
            latest_date = df[date_col].max()
            latest_df = df[df[date_col] == latest_date].copy()
            report_date = str(latest_date.strftime('%Y-%m-%d'))

        # 确保必要的列存在
        required_cols = ['股票代码', '股票名称', '占净值比例']
        if not all(col in latest_df.columns for col in required_cols):
            # 尝试匹配列名（处理接口字段微调）
            col_mapping = {
                '占净值比例': 'curr_weight',
                '股票代码': 'stock_code',
                '股票名称': 'stock_name'
            }
            latest_df.rename(columns=col_mapping, inplace=True)
            if not all(col in latest_df.columns for col in col_mapping.values()):
                missing = [col for col in required_cols if col not in latest_df.columns]
                return None, f"数据格式不匹配，缺少字段: {missing}", None

        # 清洗数据
        latest_df['curr_weight'] = pd.to_numeric(latest_df['curr_weight'], errors='coerce').fillna(0)
        # 过滤掉权重为 0 的
        latest_df = latest_df[latest_df['curr_weight'] > 0].copy()

        return latest_df, report_date, None
        
    except Exception as e:
        error_msg = f"获取持仓失败: {str(e)}"
        return None, error_msg, None

# --- 4. 获取基金实时/历史信息 ---
def get_fund_realtime_info(fund_code):
    try:
        # 1. 先获取历史净值数据，获取最新的单位净值
        # 注意：AkShare 接口参数可能变动，这里使用较新的调用方式
        fund_info = ak.fund_open_fund_info_em(fund_code=fund_code, indicator="单位净值走势")
        
        if fund_info.empty:
            return "N/A", "N/A", None

        # 查找日期列和净值列
        date_col = '净值日期' if '净值日期' in fund_info.columns else None
        if not date_col:
            # 尝试兼容旧版列名
            date_col = [col for col in fund_info.columns if '日期' in col]
            date_col = date_col[0] if date_col else None
            
        nav_col = '单位净值' if '单位净值' in fund_info.columns else None
        if not nav_col:
            nav_col = [col for col in fund_info.columns if '净值' in col]
            nav_col = nav_col[0] if nav_col else None

        if not date_col or not nav_col:
            return "N/A", "N/A", None

        # 按日期排序，获取最新一条数据（通常是昨天的收盘数据）
        fund_info[date_col] = pd.to_datetime(fund_info[date_col])
        latest_info = fund_info.sort_values(by=date_col, ascending=False).iloc[0]
        
        prev_nav = latest_info[nav_col]
        prev_date = latest_info[date_col].strftime('%Y-%m-%d')

        # 如果是交易时间，尝试估算实时净值
        if is_trading_time():
            # 【此处可以扩展：调用股票实时行情计算估算值】
            # 为了稳定性，这里暂时只返回历史数据，避免实时接口报错
            # 进阶版可参考之前的持仓加权计算逻辑
            return f"{prev_nav:.4f}", f"(截至{prev_date})", "⚠️ 盘中估算功能暂维护"
        else:
            # 非交易时间直接返回昨日收盘
            return f"{prev_nav:.4f}", f"(截至{prev_date})", None

    except Exception as e:
        return "N/A", "N/A", str(e)

# --- 5. 搜索与主程序逻辑 (关键修复部分) ---
def main():
    # --- 左侧边栏：搜索与配置 ---
    with st.sidebar:
        st.header("基金查询")
        # 允许输入代码或名称
        search_input = st.text_input("请输入基金代码或名称", placeholder="例如: 161725 或 中证白酒")
        search_btn = st.button("🔍 查询")

        st.markdown("---")
        st caption("提示")
        st.write("1. 支持输入代码(如 161725)或名称(如 白酒)")
        st.write("2. 交易时间(9:30-15:00)显示实时估算")

    # --- 主界面 ---
    if search_input:
        # 尝试识别输入的是代码还是名称
        fund_code = None
        fund_name = None
        
        # 如果输入的是数字，假设是代码
        if search_input.isdigit():
            fund_code = search_input
        else:
            # 如果是文字，尝试搜索代码
            try:
                # 这里使用 AkShare 获取全市场基金列表进行模糊匹配
                all_funds_df = ak.fund_name_em()
                matched_df = all_funds_df[all_funds_df['基金简称'].str.contains(search_input)]
                if not matched_df.empty:
                    # 取第一个匹配结果
                    fund_code = matched_df.iloc[0]['基金代码']
                    fund_name = matched_df.iloc[0]['基金简称']
                    st.write(f"✅ 匹配到基金: **{fund_name} ({fund_code})**")
                else:
                    st.error("未找到该名称的基金，请检查输入。")
            except:
                st.error("基金名称搜索接口异常，请直接输入基金代码。")

        if fund_code:
            # 展示加载状态
            with st.spinner(f'正在加载 {fund_code} 的持仓数据...'):
                # 获取持仓数据
                hold_df, report_date, err_msg = get_detail_data(fund_code)
                
                if err_msg:
                    st.error(err_msg)
                elif hold_df is not None and not hold_df.empty:
                    st.success(f'持仓数据更新于: {report_date}')
                    
                    # 显示持仓表格
                    st.dataframe(
                        hold_df,
                        column_config={
                            "stock_code": "股票代码",
                            "stock_name": "股票名称",
                            "curr_weight": st.column_config.NumberColumn(
                                "占净值比例",
                                format="%.2f%%",
                            ),
                        },
                        hide_index=True,
                        use_container_width=True
                    )
                    
                    # 获取并显示基金实时信息
                    realtime_nav, nav_note, warn_msg = get_fund_realtime_info(fund_code)
                    if warn_msg:
                        st.warning(warn_msg)
                        
                    st.metric(
                        label="当前估值/净值", 
                        value=realtime_nav, 
                        delta=nav_note
                    )
                    
                else:
                    st.info("该基金暂无持仓数据。")

if __name__ == "__main__":
    main()
