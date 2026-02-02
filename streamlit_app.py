import streamlit as st
import pandas as pd
import os
import time
import requests
import akshare as ak
import datetime
import io

# --- 1. 页面配置 ---
st.set_page_config(page_title="基金持仓分析 Pro", layout="wide")
st.title("📈 基金持仓实时深度分析")

# --- 2. 核心函数：获取基金数据 ---
@st.cache_data(ttl=300) # 缓存5分钟
def get_fund_data(fund_code_or_name):
    try:
        # 1. 获取基金基础信息 (根据名称或代码搜索)
        # 注意：AkShare 的搜索接口有时候不稳定，这里做容错
        search_df = ak.fund_em_fund_name()
        # 筛选匹配的基金
        matched = search_df[
            (search_df['基金代码'] == fund_code_or_name) | 
            (search_df['基金简称'] == fund_code_or_name)
        ]
        
        if matched.empty:
            return None, f"未找到基金：{fund_code_or_name}"
        
        # 取第一个匹配结果
        fund_info = matched.iloc[0]
        fund_code = fund_info['基金代码']
        fund_name = fund_info['基金简称']
        
        # 2. 获取持仓详情
        # AkShare 的持仓接口参数经常变，这里使用较新的写法
        # indicator="1" 代表股票持仓
        portfolio_df = ak.fund_portfolio_hold_em(symbol=fund_code, indicator="1")
        
        if portfolio_df.empty:
            return None, "该基金暂无持仓数据或接口异常。"
        
        # 3. 数据清洗
        # 提取最新的报告期数据
        # 通常报告期列名包含 "报告期"
        date_col = None
        for col in portfolio_df.columns:
            if "报告期" in col:
                date_col = col
                break
        
        if date_col:
            # 转换为日期格式并排序，取最新的
            portfolio_df[date_col] = pd.to_datetime(portfolio_df[date_col])
            latest_date = portfolio_df[date_col].max()
            latest_df = portfolio_df[portfolio_df[date_col] == latest_date]
        else:
            # 如果没有日期列，直接使用全部数据
            latest_df = portfolio_df
        
        # 4. 计算实时估值 (估算)
        # 获取上个交易日的净值
        # AkShare 的历史净值接口
        try:
            # 获取单位净值走势
            hist_df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
            if not hist_df.empty:
                # 通常第一行就是最新的
                latest_nav = hist_df.iloc[0]['单位净值']
                # 估算涨跌幅: 这里简化处理，实际需要抓取持仓股实时行情计算
                # 由于 AkShare 的实时估算接口不稳定，这里直接显示历史涨跌幅
                change_pct = hist_df.iloc[0]['日增长率']
            else:
                latest_nav = "N/A"
                change_pct = "N/A"
        except:
            latest_nav = "N/A"
            change_pct = "N/A"
        
        return {
            "code": fund_code,
            "name": fund_name,
            "portfolio": latest_df,
            "nav": latest_nav,
            "change": change_pct
        }, ""
    
    except Exception as e:
        return None, f"数据处理出错: {str(e)}"

# --- 3. 主程序逻辑 ---
def main():
    # 创建搜索栏
    st.header("基金查询")
    search_input = st.text_input("请输入基金代码或名称", placeholder="例如: 161725 或 招商中证白酒")
    
    if st.button("查询"):
        if not search_input:
            st.error("请输入基金代码或名称！")
            return
        
        with st.spinner("正在努力加载数据..."):
            data, error_msg = get_fund_data(search_input)
        
        if error_msg:
            st.error(error_msg)
            return
        
        # --- 展示结果 ---
        st.success(f"成功获取: {data['name']} ({data['code']}) 的数据")
        
        # 显示基本信息
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("最新单位净值", data['nav'])
        with col2:
            st.metric("日增长率", data['change'])
        
        # 显示持仓表格
        st.subheader("📊 最新持仓明细")
        # 只展示关键列
        display_cols = []
        for col in ['股票代码', '股票名称', '占净值比例', '持仓市值(万元)']:
            if col in data['portfolio'].columns:
                display_cols.append(col)
        
        if display_cols:
            st.dataframe(data['portfolio'][display_cols])
        else:
            st.write("持仓数据字段暂不支持展示，请稍后重试。")

# --- 4. 启动应用 ---
if __name__ == "__main__":
    main()
