import streamlit as st
import pandas as pd
import os
import datetime
import akshare as ak

# --- 配置 ---
st.set_page_config(page_title="基金持仓分析 Pro", layout="wide")
st.title("📈 基金持仓实时深度分析")
CSV_FILE = 'fund_favs.csv'

# --- 辅助函数 ---
def is_trading_time():
    now = datetime.datetime.now()
    if now.weekday() >= 5: return False
    h, m = now.hour, now.minute
    return (9 <= h < 11 or (h == 11 and m <= 30)) or (13 <= h < 15)

# 修正数据获取函数
@st.cache_data(ttl=3600)
def get_fund_detail(fund_code):
    """
    获取基金持仓详情
    使用 akshare 的 fund_em_portfolio_hold 接口
    """
    try:
        # 接口参数调整：symbol为基金代码，indicator为"1"表示按季度持仓
        df = ak.fund_portfolio_hold_em(symbol=fund_code, indicator="1")
        
        if df.empty:
            return None, "无持仓数据", None
            
        # 处理日期列
        date_col = next((c for c in df.columns if '报告期' in c), None)
        if date_col:
            df[date_col] = pd.to_datetime(df[date_col])
        
        # 获取基金名称
        name_df = ak.fund_em_fund_name()
        fund_name_df = name_df[name_df['基金代码'] == fund_code]
        fund_name = fund_name_df['基金简称'].values[0] if not fund_name_df.empty else "未知基金"
        
        return df, fund_name, date_col
        
    except Exception as e:
        st.error(f"数据获取错误: {e}")
        return None, "数据获取失败", None

# --- 收藏管理 ---
def load_favorites():
    if os.path.exists(CSV_FILE):
        return pd.read_csv(CSV_FILE)
    return pd.DataFrame(columns=['基金代码', '基金名称', '添加时间'])

def save_favorites(df):
    df.to_csv(CSV_FILE, index=False)

# --- 主界面 ---
with st.sidebar:
    st.header("🔍 基金搜索")
    search_input = st.text_input("输入代码或名称", placeholder="例如: 163406")
    search_btn = st.button("搜索")

    st.header("⭐ 我的收藏")
    favs = load_favorites()
    if not favs.empty:
        for idx, row in favs.iterrows():
            col1, col2 = st.columns([3,1])
            with col1:
                st.write(f"{row['基金名称']} ({row['基金代码']})")
            with col2:
                # 删除按钮
                if st.button("删除", key=f"del_{idx}"):
                    favs = favs.drop(idx)
                    save_favorites(favs)
                    st.experimental_rerun()
    else:
        st.info("暂无收藏，搜索后点击★收藏")

    st.header("☁️ 数据同步")
    uploaded = st.file_uploader("上传CSV备份")
    if uploaded:
        df = pd.read_csv(uploaded)
        save_favorites(df)
        st.success("导入成功！")
    
    if st.button("导出收藏列表"):
        if not favs.empty:
            csv = favs.to_csv(index=False)
            st.download_button(
                label="下载CSV",
                data=csv,
                file_name="fund_favs.csv",
                mime="text/csv"
            )

# --- 主内容区 ---
if search_btn or 'fund_code' in st.session_state:
    code = search_input.strip()
    if not code:
        st.warning("请输入基金代码或名称")
    else:
        # 搜索逻辑
        if 'fund_code' not in st.session_state or st.session_state.fund_code != code:
            st.session_state.fund_code = code
            
            # 根据输入内容获取基金代码和名称
            name_df = ak.fund_em_fund_name()
            matched = name_df[
                (name_df['基金代码'] == code) | 
                (name_df['基金简称'] == code)
            ]
            
            if not matched.empty:
                st.session_state.fund_code = matched['基金代码'].values[0]
                st.session_state.fund_name = matched['基金简称'].values[0]
            else:
                st.session_state.fund_code = code
                st.session_state.fund_name = "未知基金"
        
        # 获取持仓数据
        code = st.session_state.fund_code
        df, name, date_col = get_fund_detail(code)
        
        st.subheader(f"{name} ({code})")
        
        if df is not None:
            # 显示持仓数据
            st.dataframe(df)
            
            # 收藏按钮
            if st.button("★ 收藏"):
                new_row = {
                    '基金代码': code,
                    '基金名称': name,
                    '添加时间': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                favs = load_favorites()
                if not favs[(favs['基金代码'] == code)].empty:
                    st.warning("已在收藏列表中")
                else:
                    favs = favs.append(new_row, ignore_index=True)
                    save_favorites(favs)
                    st.success("收藏成功！")
        else:
            st.error("未找到该基金数据，请检查代码或名称")
