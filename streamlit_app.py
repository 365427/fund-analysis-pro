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

# --- 3. 辅助函数：获取所有基金列表 ---
@st_cache_data(ttl=3600)  # 使用 Streamlit 的缓存
def get_all_funds():
    try:
        # 获取场外基金列表
        return ak.fund_name_em()[['基金代码', '基金简称']]
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

# --- 5. 核心抓取函数 (AkShare) ---
@st_cache_data(ttl=3600)
def get_detail_data(fund_code):
    try:
        df = ak.fund_portfolio_hold_em(symbol=fund_code)
        if df.empty:
            return None, "未找到持仓数据", None
        
        # 简单的最新一期判断（按季度排序）
        if '报告期' in df.columns:
            df['报告期'] = pd.to_datetime(df['报告期'])
            latest_df = df.sort_values(by='报告期', ascending=False).head(1)
        else:
            latest_df = df.head(1)
        
        # 提取关键字段
        required_cols = ['股票代码', '股票名称', '占净值比例']
        if not all(col in latest_df.columns for col in required_cols):
            return None, "数据格式错误，缺少必要字段", None
            
        latest_df = latest_df[required_cols].copy()
        latest_df.rename(columns={'占净值比例': 'curr_weight'}, inplace=True)
        latest_df['curr_weight'] = pd.to_numeric(latest_df['curr_weight'], errors='coerce').fillna(0)
        
        return latest_df, str(latest_df['报告期'].iloc[0].date()) if '报告期' in latest_df else "未知日期", None
        
    except Exception as e:
        return None, f"数据获取失败: {str(e)}", None

# --- 6. 侧边栏：搜索与收藏 ---
st.sidebar.header("⭐ 基金搜索与管理")
all_funds = get_all_funds()
fav_df = load_favs()

# 搜索框
search = st.sidebar.text_input("🔍 输入名称或代码 (如: 161725 或 中欧医疗)")
if search:
    # 模糊匹配基金
    res = all_funds[
        (all_funds['基金代码'].str.contains(search, case=False)) | 
        (all_funds['基金简称'].str.contains(search, case=False))
    ]
    
    if not res.empty:
        # 显示匹配结果（仅显示前5个）
        st.sidebar.write("搜索结果：")
        for idx, row in res.head(5).iterrows():
            # 点击基金即可添加到收藏并显示详情
            if st.sidebar.button(f"➕ {row['基金简称']} ({row['基金代码']})"):
                # 检查是否已收藏
                if row['基金代码'] not in fav_df['代码'].values:
                    # 新增收藏行
                    new_row = pd.DataFrame([{
                        '代码': row['基金代码'], 
                        '名称': row['基金简称'], 
                        '涨跌幅': 'N/A'
                    }])
                    fav_df = pd.concat([fav_df, new_row], ignore_index=True)
                    save_favs(fav_df)
                    st.sidebar.success(f"已添加：{row['基金简称']}")
                else:
                    st.sidebar.info(f"已存在：{row['基金简称']}")

# 导入/导出按钮
if st.sidebar.button("📥 导出收藏"):
    st.sidebar.download_button(
        label="下载收藏列表",
        data=fav_df.to_csv(index=False),
        file_name="fund_favs.csv",
        mime="text/csv"
    )

if st.sidebar.button("📤 导入收藏"):
    uploaded_file = st.sidebar.file_uploader("上传 CSV 文件")
    if uploaded_file is not None:
        try:
            new_df = pd.read_csv(uploaded_file, dtype={'代码': str})
            # 合并去重
            fav_df = pd.concat([fav_df, new_df]).drop_duplicates(subset=['代码'])
            save_favs(fav_df)
            st.sidebar.success("导入成功！")
        except Exception as e:
            st.sidebar.error(f"导入失败：{e}")

# --- 7. 主界面：显示收藏列表与详情 ---
st.header("⭐ 我的收藏")

if not fav_df.empty:
    # 显示收藏表格
    st.dataframe(fav_df, use_container_width=True)
    
    # 选择查看某只基金的详情
    selected_fund = st.selectbox("选择基金查看详情", fav_df['名称'].values)
    if selected_fund:
        code = fav_df[fav_df['名称'] == selected_fund]['代码'].values[0]
        st.subheader(f"📊 {selected_fund} ({code}) 持仓详情")
        
        with st.spinner("正在加载持仓数据..."):
            detail_df, report_date, error_msg = get_detail_data(code)
            if detail_df is not None:
                st.write(f"**报告期：** {report_date}")
                st.dataframe(detail_df, use_container_width=True)
            else:
                st.warning(error_msg)
else:
    st.info("收藏夹为空，请在侧边栏搜索基金并点击'➕'添加。")
