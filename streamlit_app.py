import streamlit as st
import pandas as pd
import os
import time
import requests
import akshare as ak
import inspect
import datetime
from io import StringIO

# --- 1. 页面配置 ---
st.set_page_config(page_title="基金持仓分析 (本地版)", layout="wide")
st.title("📈 基金持仓实时深度分析 (本地版)")

# --- 2. 辅助函数：判断是否为交易日 ---
def is_trading_day(date_to_check):
    """简单的交易日判断，排除周六周日。可进一步扩展节假日数据库。"""
    # 0=Monday, 6=Sunday
    if date_to_check.weekday() > 4:
        return False
    return True

# --- 3. 核心抓取函数 (使用 AkShare, 修复字段问题) ---
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
        
        # 查找日期列
        date_col_candidates = [col for col in hist_df.columns if '净值日期' in col or 'date' in col.lower() or '日期' in col]
        if not date_col_candidates:
            print(f"DEBUG: 基金 {fund_code} 未找到日期列。列名为: {list(hist_df.columns)}")
            return "N/A", "N/A"
        date_col = date_col_candidates

        # 查找净值列
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

# --- 6. 搜索与收藏逻辑 (已修改) ---
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

# --- 7. 侧边栏交互 (增加导入导出) ---
st.sidebar.header("⭐ 基金搜索与管理")

# 导入功能
uploaded_file = st.sidebar.file_uploader("📂 导入收藏列表 (CSV)", type=["csv"], key="import")
if uploaded_file is not None:
    try:
        imported_df = pd.read_csv(uploaded_file)
        # 确保列名正确
        if '代码' in imported_df.columns and '名称' in imported_df.columns:
            # 合并并去重
            current_favs = load_favs()
            combined = pd.concat([current_favs, imported_df]).drop_duplicates(subset=['代码']).reset_index(drop=True)
            save_favs(combined)
            st.sidebar.success("导入成功！")
            st.rerun() # 刷新页面以显示新数据
        else:
            st.sidebar.error("文件格式错误，需包含'代码'和'名称'列")
    except Exception as e:
        st.sidebar.error(f"导入失败: {e}")

# 导出功能
fav_df = load_favs()
if not fav_df.empty:
    csv = fav_df.to_csv(index=False)
    st.sidebar.download_button(
        label="📤 导出收藏列表",
        data=csv,
        file_name='我的基金收藏.csv',
        mime='text/csv',
    )

all_funds = get_all_funds()

search = st.sidebar.text_input("🔍 输入名称或代码 (如: 161725)")
f_code, f_name = "", ""
if search:
    res = all_funds[(all_funds['基金代码'].str.contains(search)) | (all_funds['基金简称'].str.contains(search))]
    if not res.empty:
        f_code, f_name = res.iloc['基金代码'], res.iloc['基金简称']
        st.sidebar.success(f"已选: {f_name}")

# --- 8. 主界面：显示收藏列表 ---
st.subheader("📊 我的收藏基金")
if not fav_df.empty:
    # 更新收藏列表中的涨跌幅
    updated_favs = fav_df.copy()
    today_is_trading = is_trading_day(datetime.date.today())
    
    for idx, row in updated_favs.iterrows():
        nav, growth = get_fund_realtime_info(row['代码'], today_is_trading)
        updated_favs.at[idx, '涨跌幅'] = growth
    
    save_favs(updated_favs) # 保存更新后的数据
    st.dataframe(updated_favs, use_container_width=True)
else:
    st.info("暂无收藏基金，请在侧边栏搜索并添加。")

# --- 9. 主界面：基金详情分析 ---
if f_code and f_name:
    st.subheader(f"🔍 分析基金: {f_name} ({f_code})")
    
    # 获取持仓数据
    with st.spinner('正在获取持仓数据...'):
        detail_df, report_date, err = get_detail_data(f_code)
    
    if detail_df is not None:
        st.write(f"**报告期**: {report_date}")
        st.dataframe(detail_df, use_container_width=True)
        
        # 显示前五大重仓股
        top5 = detail_df.nlargest(5, 'curr_weight')
        st.write("**前五大重仓股**:")
        for _, row in top5.iterrows():
            st.markdown(f"- {row['股票名称']} ({row['股票代码']}): {row['curr_weight']:.2f}%")
    else:
        st.error(f"获取持仓数据失败: {err}")
