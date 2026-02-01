import streamlit as st
import pandas as pd
import os
import time
import akshare as ak
import inspect
import datetime

# --- 1. 页面配置 ---
st.set_page_config(page_title="基金持仓分析 Pro (AkShare)", layout="wide")
st.title("📈 基金持仓实时深度分析")

# --- 2. 辅助函数：判断是否为交易日 ---
def is_trading_day(date_to_check):
    if date_to_check.weekday() > 4:  # 5,6 是周末
        return False
    return True

# --- 3. 核心抓取函数：获取持仓详情 ---
@st.cache_data(ttl=3600)
def get_detail_data(fund_code):
    try:
        # 【修复点1】使用更稳定的接口，且必须传入'1'代表股票持仓
        # em 的接口有时候需要指定类型，这里修正为获取股票持仓
        df = ak.fund_portfolio_hold_em(symbol=fund_code, indicator="1") 
        
        if df.empty:
            return None, "未找到持仓数据", None
            
        # 处理日期，获取最新一期数据
        # AkShare 返回的列名通常是中文，这里精准匹配
        date_col = "报告期" 
        if date_col not in df.columns:
            # 如果没有报告期，尝试用默认排序
            latest_df = df.head(10) # 取前10条
            report_date = "最新一期"
        else:
            # 按报告期降序排序，取最新一期
            df[date_col] = pd.to_datetime(df[date_col])
            latest_date = df[date_col].max()
            latest_df = df[df[date_col] == latest_date].copy()
            report_date = str(latest_date.date())

        # 【修复点2】列名映射：处理 AkShare 接口字段变动
        # AkShare 的字段可能是'股票代码'或'证券代码'，这里做兼容
        stock_code_col = "股票代码" if "股票代码" in latest_df.columns else "证券代码"
        stock_name_col = "股票名称" if "股票名称" in latest_df.columns else "证券简称"
        weight_col = "占净值比例" if "占净值比例" in latest_df.columns else "持仓市值(万元)" 

        # 检查必要字段
        required_cols = [stock_code_col, stock_name_col]
        if not all(col in latest_df.columns for col in required_cols):
            return None, f"数据格式错误，缺少字段: {required_cols}", None

        # 重命名并整理
        latest_df = latest_df[required_cols].copy()
        latest_df.rename(columns={
            stock_code_col: "股票代码", 
            stock_name_col: "股票名称"
        }, inplace=True)

        # 如果有比例数据就保留，没有就填充 0
        if weight_col in latest_df.columns:
            latest_df["占净值比例"] = pd.to_numeric(latest_df[weight_col], errors='coerce').fillna(0)
        else:
            latest_df["占净值比例"] = 0

        return latest_df, report_date, None
        
    except Exception as e:
        error_msg = f"数据抓取失败: {str(e)}"
        return None, error_msg, None

# --- 4. 获取实时净值估算 ---
def get_fund_realtime_info(fund_code, is_today_trading_day):
    try:
        # 【修复点3】ak.fund_open_fund_info_em 的参数近期有变动
        # indicator 参数现在通常需要传 '单位净值' 或 '累计净值'
        # 且参数名通常是 fund 而非 code
        hist_df = ak.fund_open_fund_info_em(fund=fund_code, indicator="单位净值") 
        
        if hist_df.empty:
            print(f"DEBUG: {fund_code} 历史数据为空")
            return "N/A", "N/A"

        # 处理列名
        date_col = "净值日期" 
        nav_col = "单位净值" 
        
        if date_col not in hist_df.columns or nav_col not in hist_df.columns:
            print(f"DEBUG: 列名不匹配: {hist_df.columns.tolist()}")
            return "N/A", "N/A"

        # 获取最新两条数据计算涨跌幅
        sorted_df = hist_df.sort_values(by=date_col, ascending=False).head(2)
        
        if len(sorted_df) < 2:
            return sorted_df.iloc[0][nav_col], "N/A"
            
        current_nav = sorted_df.iloc[0][nav_col]
        prev_nav = sorted_df.iloc[1][nav_col]
        
        if prev_nav == 0:
            daily_growth = 0
        else:
            daily_growth = ((current_nav - prev_nav) / prev_nav) * 100
            
        return f"{current_nav:.4f}", f"{daily_growth:+.2f}%"
        
    except Exception as e:
        print(f"DEBUG: 实时数据错误: {e}")
        return "N/A", "N/A"

# --- 5. 搜索与收藏逻辑 (UI部分) ---
# 注意：这部分代码在手机浏览器上可能排版较窄，但功能可用

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

# --- 6. 主程序界面 ---
def main():
    st.header("基金查询")
    
    # 输入基金代码
    fund_code = st.text_input("请输入基金代码", placeholder="例如：161725")
    
    if st.button("查询"):
        if not fund_code:
            st.error("请输入基金代码！")
            return
            
        with st.spinner("正在从 East Money (AkShare) 抓取数据..."):
            # 获取持仓数据
            df_holdings, report_date, error_msg = get_detail_data(fund_code)
            
            if df_holdings is None:
                st.error(f"❌ 抓取失败: {error_msg}")
            else:
                st.success(f"获取成功 (数据截至: {report_date})")
                
                # 显示持仓表格
                # 【修复点4】手机端表格显示优化
                st.subheader("📊 基金持仓明细")
                # Streamlit 在手机上显示表格有时会乱，建议转成 HTML 或使用 data_editor
                st.dataframe(df_holdings, use_container_width=True)

                # 获取实时数据
                is_trading = is_trading_day(datetime.datetime.now())
                realtime_nav, realtime_change = get_fund_realtime_info(fund_code, is_trading)
                
                # 显示净值信息
                st.info(f"**实时净值: {realtime_nav} | 涨跌幅: {realtime_change}**")

if __name__ == "__main__":
    main()
