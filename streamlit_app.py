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

@st.cache_data(ttl=3600)
def get_detail_data(fund_code):
    try:
        df = ak.fund_portfolio_hold_em(symbol=fund_code, indicator="1")
        if df.empty: return None, "无持仓数据", None
        date_col = next((c for c in df.columns if '报告期' in c), None)
        if date_col:
            df[date_col] = pd.to_datetime(df[date_col])
            df = df[df[date_col] == df[date_col].max()].copy()
            report_date = df[date_col].iloc[0].strftime('%Y-%m-%d')
        else:
            report_date = "最新一期"
        cols_map = {'股票代码':'stock_code','股票名称':'stock_name','占净值比例':'curr_weight'}
        df = df[[k for k in cols_map.keys() if k in df.columns]].rename(columns=cols_map)
        df['curr_weight'] = pd.to_numeric(df.get('curr_weight', 0), errors='coerce').fillna(0)
        return df, report_date, None
    except Exception as e:
        return None, f"获取失败: {str(e)}", None

def get_fund_realtime_info(fund_code):
    try:
        hist = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
        if hist.empty: return "N/A", "N/A", "数据空"
        nav = hist.iloc[0]['单位净值']
        date = hist.iloc[0]['净值日期']
        return f"{nav:.4f}", f"(截至{date})", None if not is_trading_time() else "⚠️ 盘中估算维护中"
    except: return "N/A", "N/A", None

# --- 收藏功能（核心修复）---
def load_favs():
    if os.path.exists(CSV_FILE):
        df = pd.read_csv(CSV_FILE, dtype={'code': str})
        return df if 'name' in df.columns else pd.DataFrame(columns=['code','name'])
    return pd.DataFrame(columns=['code','name'])

def save_favs(df):
    df.to_csv(CSV_FILE, index=False, encoding='utf-8-sig')

def add_to_favs(code, name):
    df = load_favs()
    if code not in df['code'].values:
        df = pd.concat([df, pd.DataFrame([{'code': code, 'name': name}])], ignore_index=True)
        save_favs(df)
        return True
    return False

def remove_from_favs(code):
    df = load_favs()
    df = df[df['code'] != code].reset_index(drop=True)
    save_favs(df)

# --- 侧边栏：搜索 + 收藏管理 ---
with st.sidebar:
    st.title("🔍 基金搜索")
    search_input = st.text_input("输入代码或名称", placeholder="161725 / 招商白酒")
    
    st.markdown("---")
    st.title("⭐ 我的收藏")
    favs = load_favs()
    if len(favs) > 0:
        for idx, row in favs.iterrows():
            col1, col2 = st.columns([4,1])
            with col1:
                st.write(f"`{row['code']}` {row['name']}")
            with col2:
                if st.button("🗑️", key=f"del_{row['code']}", help="删除"):
                    remove_from_favs(row['code'])
                    st.rerun()
    else:
        st.info("暂无收藏，搜索后点击⭐添加")
    
    st.markdown("---")
    st.title("☁️ 数据同步")
    uploaded = st.file_uploader("上传CSV备份", type="csv")
    if uploaded:
        try:
            pd.read_csv(uploaded).to_csv(CSV_FILE, index=False, encoding='utf-8-sig')
            st.success("导入成功！")
            st.rerun()
        except Exception as e:
            st.error(f"导入失败: {e}")
    
    if st.button("📥 导出收藏列表"):
        if os.path.exists(CSV_FILE):
            with open(CSV_FILE, "rb") as f:
                st.download_button("下载CSV", f, file_name="my_funds.csv", mime="text/csv")
        else:
            st.warning("收藏列表为空")

# --- 主界面：查询逻辑 ---
if search_input:
    # 智能识别：代码 or 名称
    if search_input.isdigit() and len(search_input) == 6:
        fund_code, fund_name = search_input, "未知基金"
    else:
        try:
            all_funds = ak.fund_em_fund_name()
            match = all_funds[all_funds['基金简称'] == search_input]
            if not match.empty:
                fund_code, fund_name = match.iloc[0]['基金代码'], search_input
            else:
                st.error("❌ 未找到该基金，请检查名称或输入6位代码")
                st.stop()
        except Exception as e:
            st.error(f"搜索接口异常: {e}")
            st.stop()
    
    # 获取数据
    with st.spinner(f"加载 {fund_name} ({fund_code})..."):
        hold_df, report_date, err = get_detail_data(fund_code)
        nav, note, warn = get_fund_realtime_info(fund_code)
    
    if err:
        st.error(err)
    else:
        # 显示结果
        st.subheader(f"{fund_name} (`{fund_code}`)")
        col1, col2, col3 = st.columns(3)
        with col1: st.metric("报告期", report_date)
        with col2: st.metric("单位净值", nav, note)
        with col3:
            if add_to_favs(fund_code, fund_name):
                st.success("✅ 已添加到收藏")
            else:
                st.info("⭐ 已在收藏中")
            if st.button("⭐ 收藏到列表", key="add_btn"):
                if add_to_favs(fund_code, fund_name):
                    st.rerun()
        
        if warn: st.warning(warn)
        st.dataframe(
            hold_df,
            column_config={
                "stock_code": "股票代码",
                "stock_name": "股票名称",
                "curr_weight": st.column_config.NumberColumn("占比(%)", format="%.2f%%")
            },
            hide_index=True,
            use_container_width=True
        )
