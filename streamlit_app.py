import streamlit as st
import pandas as pd
import os
import akshare as ak
import datetime

# --- 1. 页面配置 ---
st.set_page_config(page_title="基金持仓分析 (本地版)", layout="wide")
st.title("📈 基金持仓实时深度分析 (本地版)")

# --- 2. 全局变量 ---
CSV_FILE = 'fund_favs.csv'

# --- 3. 辅助函数：获取所有基金列表（带 Streamlit 缓存）---
@st.cache_data(ttl=3600)  # 修正为 st.cache_data（双下划线）
def get_all_funds():
    try:
        # 获取场外基金列表
        df = ak.fund_name_em()
        return df[['基金代码', '基金简称']]
    except Exception as e:
        st.warning(f"无法获取基金列表: {e}")
        return pd.DataFrame(columns=['基金代码', '基金简称'])

# --- 4. 辅助函数：管理收藏夹文件 ---
def load_favs():
    """读取收藏夹文件"""
    if os.path.exists(CSV_FILE):
        df = pd.read_csv(CSV_FILE, dtype={'代码': str})
        # 确保列存在
        if '涨跌幅' not in df.columns:
            df['涨跌幅'] = 'N/A'
        return df[['代码', '名称', '涨跌幅']]
    else:
        return pd.DataFrame(columns=['代码', '名称', '涨跌幅'])

def save_favs(df):
    """保存收藏夹文件"""
    df.to_csv(CSV_FILE, index=False)

# --- 5. 侧边栏：基金搜索与收藏 ---
st.sidebar.header("⭐ 基金搜索")
all_funds = get_all_funds()
fav_df = load_favs()

# 搜索框
search = st.sidebar.text_input("🔍 输入名称或代码 (如: 161725)")
if search:
    # 筛选匹配的基金（代码或简称包含搜索词）
    res = all_funds[
        (all_funds['基金代码'].str.contains(search)) | 
        (all_funds['基金简称'].str.contains(search))
    ]
    if not res.empty:
        # 取第一个匹配的基金
        f_code = res['基金代码'].iloc[0]
        f_name = res['基金简称'].iloc[0]
        st.sidebar.success(f"已选: {f_name}")
        
        # 【关键】自动将搜索结果加入收藏夹
        if f_code not in fav_df['代码'].values:
            new_row = pd.DataFrame([{'代码': f_code, '名称': f_name, '涨跌幅': 'N/A'}])
            fav_df = pd.concat([fav_df, new_row], ignore_index=True)
            save_favs(fav_df)
            st.sidebar.success(f"已自动收藏: {f_name}")

# 导入/导出收藏
if st.sidebar.button("导入收藏"):
    st.sidebar.info("导入功能需额外实现（如文件上传）")
if st.sidebar.button("导出收藏"):
    st.sidebar.download_button("下载收藏.csv", fav_df.to_csv(index=False), file_name="收藏.csv")

# --- 6. 主界面：显示收藏列表与持仓详情 ---
st.header("⭐ 我的收藏")
if not fav_df.empty:
    # 显示收藏列表（可点击查看详情）
    for idx, row in fav_df.iterrows():
        code, name, growth = row['代码'], row['名称'], row['涨跌幅']
        # 点击基金名称触发详情显示
        if st.button(f"{name} ({code})  涨跌幅: {growth}", key=f"fund_{code}"):
            # 显示该基金的持仓详情
            st.subheader(f"📊 {name} ({code}) 持仓详情")
            try:
                # 获取持仓数据（示例：用 AkShare 获取）
                df = ak.fund_portfolio_hold_em(symbol=code)
                if not df.empty:
                    st.dataframe(df.head(10))  # 显示前10条持仓
                else:
                    st.warning("暂无持仓数据")
            except Exception as e:
                st.error(f"获取持仓失败: {e}")
else:
    st.info("收藏列表为空，可在侧边栏搜索基金后自动收藏")

# --- 7. 核心抓取函数（修复字段问题）---
@st.cache_data(ttl=3600)
def get_detail_data(fund_code):
    try:
        df = ak.fund_portfolio_hold_em(symbol=fund_code)
        if df.empty:
            return None, "未找到持仓数据", None
        
        # 处理日期列（取最新一期）
        date_cols = [col for col in df.columns if '时间' in col or '日期' in col or 'quarter' in col.lower() or 'date' in col.lower()]
        if not date_cols:
            latest_df = df.copy()
            report_date = "最新一期"
        else:
            date_col = date_cols[0]
            latest_date = df[date_col].max()
            latest_df = df[df[date_col] == latest_date].copy()
            report_date = str(latest_date)
        
        # 检查必填字段
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
