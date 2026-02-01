import streamlit as st
import pandas as pd
import os
import akshare as ak
import inspect

# --- 1. 页面配置 ---
st.set_page_config(page_title="基金持仓分析 (本地版)", layout="wide")
st.title("📈 基金持仓实时深度分析 (本地版)")

# --- 2. 辅助函数：判断是否为交易日 ---
def is_trading_day(date_to_check):
    if date_to_check.weekday() > 4:  # 5=周六, 6=周日
        return False
    return True

# --- 3. 核心抓取函数 (AkShare) ---
@st.cache_data(ttl=3600)
def get_detail_data(fund_code):
    try:
        df = ak.fund_portfolio_hold_em(symbol=fund_code)
        if df.empty:
            return None, "未找到持仓数据", None
        
        # 处理日期列（兼容不同基金的字段差异）
        date_cols = [col for col in df.columns if '时间' in col or '日期' in col or 'quarter' in col.lower() or 'date' in col.lower()]
        if not date_cols:
            latest_df = df.copy()
            report_date = "最新一期"
        else:
            date_col = date_cols[0]
            latest_date = df[date_col].max()
            latest_df = df[df[date_col] == latest_date].copy()
            report_date = str(latest_date)
        
        # 检查必要字段
        required_cols = ['股票代码', '股票名称', '占净值比例']
        if not all(col in latest_df.columns for col in required_cols):
            missing = [col for col in required_cols if col not in latest_df.columns]
            return None, f"数据格式不匹配，缺少字段: {missing}", None
        
        # 清洗数据
        latest_df = latest_df[required_cols].copy()
        latest_df.rename(columns={'占净值比例': 'curr_weight'}, inplace=True)
        latest_df['curr_weight'] = pd.to_numeric(latest_df['curr_weight'], errors='coerce').fillna(0)
        
        return latest_df, report_date, None
    except Exception as e:
        return None, f"AkShare 获取失败: {str(e)}", None

# --- 4. 获取实时净值/涨跌幅 ---
def get_fund_realtime_info(fund_code, is_today_trading_day):
    try:
        sig = inspect.signature(ak.fund_open_fund_info_em)
        params = list(sig.parameters.keys())
        
        # 动态匹配基金代码的参数名（兼容AkShare版本差异）
        fund_param_name = next((name for name in ['symbol', 'code', 'fund_code', 'fund'] if name in params), None)
        if not fund_param_name:
            print(f"DEBUG: 未找到基金代码参数。可用参数: {params}")
            return "N/A", "N/A"
        
        call_kwargs = {fund_param_name: fund_code, 'indicator': '单位净值走势'}
        hist_df = ak.fund_open_fund_info_em(**call_kwargs)
        
        if hist_df.empty:
            print(f"DEBUG: 基金 {fund_code} 数据为空")
            return "N/A", "N/A"
        
        # 匹配日期列和净值列
        date_col = next((col for col in hist_df.columns if '净值日期' in col or 'date' in col.lower() or '日期' in col), None)
        nav_col = next((col for col in hist_df.columns if '单位净值' in col or '估算' in col), None)
        
        if not date_col or not nav_col:
            print(f"DEBUG: 基金 {fund_code} 列匹配失败。日期列: {date_col}, 净值列: {nav_col}")
            return "N/A", "N/A"
        
        # 排序并计算涨跌幅
        hist_df.sort_values(by=date_col, ascending=False, inplace=True)
        hist_df.reset_index(drop=True, inplace=True)
        nav_series = hist_df[nav_col].dropna()
        
        if len(nav_series) < 2:
            print(f"DEBUG: 基金 {fund_code} 数据不足")
            return "N/A", "N/A"
        
        current_nav = nav_series.iloc[0]
        prev_nav = nav_series.iloc[1]
        daily_growth = ((current_nav - prev_nav) / prev_nav) * 100 if prev_nav != 0 else 0
        
        return f"{current_nav:.4f}", f"{daily_growth:+.2f}%"
    except Exception as e:
        print(f"DEBUG: 基金 {fund_code} 错误: {e}")
        return "N/A", "N/A"

# --- 5. 基金列表与收藏管理 ---
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
        # 兼容旧版CSV（无“涨跌幅”列）
        if '涨跌幅' not in df.columns:
            df['涨跌幅'] = 'N/A'
        return df[['代码', '名称', '涨跌幅']]
    return pd.DataFrame(columns=['代码', '名称', '涨跌幅'])

def save_favs(df):
    df.to_csv(CSV_FILE, index=False)

# --- 6. 侧边栏：搜索与导入导出 ---
st.sidebar.header("⭐ 基金搜索与管理")

# 【修复点1】导入CSV逻辑（增加列检查）
uploaded_file = st.sidebar.file_uploader("导入收藏列表 (CSV)", type="csv")
if uploaded_file is not None:
    try:
        temp_df = pd.read_csv(uploaded_file)
        # 确保CSV包含必要列（代码、名称）
        if '代码' in temp_df.columns and '名称' in temp_df.columns:
            # 保留原“涨跌幅”列，无则补N/A
            if '涨跌幅' not in temp_df.columns:
                temp_df['涨跌幅'] = 'N/A'
            temp_df = temp_df[['代码', '名称', '涨跌幅']]
            save_favs(temp_df)
            st.sidebar.success("导入成功！")
        else:
            st.sidebar.error("CSV需包含【代码】和【名称】列！")
    except Exception as e:
        st.sidebar.error(f"导入失败: {e}")

# 【修复点2】基金搜索逻辑（禁止用.iloc[列名]）
all_funds = get_all_funds()
search = st.sidebar.text_input("🔍 输入名称或代码 (如: 161725)")
f_code, f_name = "", ""

if search:
    # 筛选匹配的基金（代码或简称包含搜索词）
    res = all_funds[
        (all_funds['基金代码'].str.contains(search, na=False)) | 
        (all_funds['基金简称'].str.contains(search, na=False))
    ]
    if not res.empty:
        # 【核心修复】用 .loc 或 .iloc[位置, 列名] 取值
        f_code = res.iloc[0]['基金代码']  # 第0行的“基金代码”
        f_name = res.iloc[0]['基金简称']  # 第0行的“基金简称”
        st.sidebar.success(f"已选: {f_name}")

# 【修复点3】导出CSV按钮
if st.sidebar.button("导出收藏列表"):
    fav_df = load_favs()
    if not fav_df.empty:
        # 生成CSV并提供下载
        csv = fav_df.to_csv(index=False).encode('utf-8-sig')  # utf-8-sig避免Excel乱码
        st.sidebar.download_button(
            label="下载CSV",
            data=csv,
            file_name=f"fund_favs_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.sidebar.warning("无收藏数据可导出！")

# --- 7. 主界面：显示收藏列表（示例逻辑，需结合业务完善） ---
st.subheader("我的收藏")
fav_df = load_favs()
if not fav_df.empty:
    st.dataframe(fav_df)
else:
    st.info("暂无收藏基金，可在侧边栏搜索后添加！")
