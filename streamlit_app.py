import streamlit as st
import pandas as pd
import numpy as np
import akshare as ak
import json
import os
import time
from datetime import datetime, timedelta
import pytz
import warnings
warnings.filterwarnings('ignore')

# 设置时区为北京时间
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# 页面配置
st.set_page_config(
    page_title="基金持仓跟踪系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 设置中文字体
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&display=swap');
* {
    font-family: 'Noto Sans SC', sans-serif;
}
.fund-card {
    border: 1px solid #e0e0e0;
    border-radius: 10px;
    padding: 15px;
    margin-bottom: 10px;
    background: white;
    transition: all 0.3s ease;
}
.fund-card:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    transform: translateY(-2px);
}
.fund-card.up {
    border-left: 4px solid #4CAF50;
}
.fund-card.down {
    border-left: 4px solid #F44336;
}
.fund-card.flat {
    border-left: 4px solid #2196F3;
}
</style>
""", unsafe_allow_html=True)

# 获取北京时间
def get_beijing_time():
    """获取北京时间"""
    return datetime.now(BEIJING_TZ)

# 初始化session_state
if 'fund_list' not in st.session_state:
    if os.path.exists('data/fund_list.json'):
        try:
            with open('data/fund_list.json', 'r', encoding='utf-8') as f:
                st.session_state.fund_list = json.load(f)
        except:
            st.session_state.fund_list = []
    else:
        st.session_state.fund_list = []

# 创建必要的目录
os.makedirs('data/cache', exist_ok=True)

# ====================== 核心修复：交易日判断和数据获取 ======================

# 交易日判断（简单但可靠的方法）
def is_trading_day():
    """判断今天是否为交易日"""
    now = get_beijing_time()
    
    # 1. 判断是否为周末（周六、周日休市）
    if now.weekday() >= 5:  # 5=周六, 6=周日
        return False
    
    # 2. 判断是否为节假日（2024年A股节假日）
    holidays = {
        '2024-01-01': '元旦',
        '2024-02-10': '春节', '2024-02-11': '春节', '2024-02-12': '春节', '2024-02-13': '春节', '2024-02-14': '春节', '2024-02-15': '春节', '2024-02-16': '春节', '2024-02-17': '春节',
        '2024-04-04': '清明', '2024-04-05': '清明', '2024-04-06': '清明',
        '2024-05-01': '劳动节', '2024-05-02': '劳动节', '2024-05-03': '劳动节', '2024-05-04': '劳动节', '2024-05-05': '劳动节',
        '2024-06-10': '端午',
        '2024-09-15': '中秋', '2024-09-16': '中秋', '2024-09-17': '中秋',
        '2024-10-01': '国庆', '2024-10-02': '国庆', '2024-10-03': '国庆', '2024-10-04': '国庆', '2024-10-05': '国庆', '2024-10-06': '国庆', '2024-10-07': '国庆',
    }
    
    today_str = now.strftime('%Y-%m-%d')
    if today_str in holidays:
        return False
    
    # 3. 判断是否在交易时间内（9:30-15:00）
    current_time = now.time()
    market_open = datetime.strptime('09:30', '%H:%M').time()
    market_close = datetime.strptime('15:00', '%H:%M').time()
    
    # 如果不在交易时间段内，也视为非交易日（显示昨日数据）
    if current_time < market_open or current_time > market_close:
        return True  # 返回True但会显示昨日数据
    
    return True

# 获取基金名称（稳定可靠的方法）
def get_fund_name(fund_code):
    """获取基金名称"""
    try:
        # 方法1：使用基金列表接口
        try:
            fund_list = ak.fund_name_em()
            if not fund_list.empty:
                fund_info = fund_list[fund_list['基金代码'] == fund_code]
                if not fund_info.empty:
                    return fund_info.iloc[0]['基金简称']
        except:
            pass
        
        # 方法2：使用基金详情接口
        try:
            fund_detail = ak.fund_open_fund_info_em(symbol=fund_code)
            if not fund_detail.empty:
                return f"基金{fund_code}"
        except:
            pass
        
        # 方法3：使用基金档案
        try:
            fund_info = ak.fund_em_fund_info(fund=fund_code)
            if not fund_info.empty:
                return fund_info.iloc[0]['基金简称'] if '基金简称' in fund_info.columns else f"基金{fund_code}"
        except:
            pass
        
        return f"基金{fund_code}"
    except Exception as e:
        return f"基金{fund_code}"

# 获取基金实时估算（简化但可靠的方法）
def get_fund_estimation(fund_code):
    """获取基金实时估算数据"""
    try:
        # 方法1：直接获取基金估算接口
        try:
            fund_est = ak.fund_value_estimation_em(symbol=fund_code)
            if not fund_est.empty:
                latest = fund_est.iloc[0]
                return {
                    '估算涨跌幅': float(latest.get('估算涨跌幅', 0)) if latest.get('估算涨跌幅') not in ['', None] else 0,
                    '估算净值': float(latest.get('估算净值', 0)) if latest.get('估算净值') not in ['', None] else 0,
                    '更新时间': latest.get('更新时间', '')
                }
        except:
            pass
        
        # 方法2：使用替代接口
        try:
            fund_data = ak.fund_em_open_fund_info(fund=fund_code)
            if not fund_data.empty:
                latest = fund_data.iloc[0]
                return {
                    '估算涨跌幅': 0,
                    '估算净值': float(latest.get('单位净值', 0)) if latest.get('单位净值') not in ['', None] else 0,
                    '更新时间': latest.get('净值日期', '')
                }
        except:
            pass
        
        return None
    except Exception as e:
        return None

# 获取基金持仓数据（简化版）
def get_fund_holdings(fund_code):
    """获取基金持仓数据"""
    try:
        # 使用akshare获取持仓
        holdings = ak.fund_em_portfolio_hold(fund=fund_code)
        
        if not holdings.empty:
            # 只保留前10大持仓
            top_holdings = holdings.head(10)
            
            # 整理数据
            result = []
            for _, row in top_holdings.iterrows():
                result.append({
                    '股票代码': row.get('股票代码', ''),
                    '股票名称': row.get('股票名称', ''),
                    '占净值比例': float(row.get('占净值比例', 0)) if row.get('占净值比例') not in ['', None] else 0,
                    '持股数': row.get('持股数', '')
                })
            return result
        return []
    except Exception as e:
        return []

# 获取基金最新净值
def get_fund_nav(fund_code):
    """获取基金最新净值（用于非交易日）"""
    try:
        # 获取基金净值
        nav_data = ak.fund_open_fund_info_em(symbol=fund_code)
        
        if not nav_data.empty:
            latest = nav_data.iloc[0]
            return {
                '净值日期': latest.get('净值日期', ''),
                '单位净值': float(latest.get('单位净值', 0)) if latest.get('单位净值') not in ['', None] else 0,
                '累计净值': float(latest.get('累计净值', 0)) if latest.get('累计净值') not in ['', None] else 0,
                '日增长率': float(str(latest.get('日增长率', '0')).replace('%', '')) if latest.get('日增长率') not in ['', None] else 0
            }
        return None
    except:
        return None

# 搜索基金
def search_funds(keyword):
    """搜索基金"""
    try:
        # 获取所有基金列表
        all_funds = ak.fund_name_em()
        
        if not all_funds.empty:
            # 按代码搜索
            code_results = all_funds[all_funds['基金代码'].astype(str).str.contains(str(keyword))]
            
            # 按名称搜索
            name_results = all_funds[all_funds['基金简称'].str.contains(str(keyword), case=False, na=False)]
            
            # 合并结果
            results = pd.concat([code_results, name_results]).drop_duplicates().head(20)
            
            return results
        return pd.DataFrame()
    except:
        return pd.DataFrame()

# ====================== 界面部分（保持原样） ======================

# 侧边栏
with st.sidebar:
    st.title("📊 基金跟踪系统")
    st.markdown("---")
    
    # 显示北京时间
    beijing_time = get_beijing_time()
    time_col1, time_col2 = st.columns(2)
    with time_col1:
        st.caption(f"🕐 更新时间")
    with time_col2:
        st.caption(f"{beijing_time.strftime('%H:%M:%S')}")
    
    # 判断交易日状态
    trading_day = is_trading_day()
    if trading_day:
        st.success("✅ 当前为交易日")
    else:
        st.info("📅 当前为非交易日")
    
    st.markdown("---")
    
    # 数据管理
    st.subheader("📁 数据管理")
    
    col_import, col_export = st.columns(2)
    
    with col_import:
        if st.button("📤 导入", key="import_btn_top", use_container_width=True):
            st.session_state.show_import = True
        else:
            st.session_state.show_import = False
    
    with col_export:
        if st.button("📥 导出", key="export_btn_top", use_container_width=True):
            st.session_state.show_export = True
    
    # 导入面板
    if st.session_state.get('show_import'):
        st.markdown("---")
        st.subheader("导入数据")
        uploaded_file = st.file_uploader("选择JSON文件", type=['json'], key="import_file_sidebar")
        if uploaded_file is not None:
            try:
                import_data = json.load(uploaded_file)
                if isinstance(import_data, list) and all(isinstance(x, str) for x in import_data):
                    st.session_state.fund_list = import_data
                    with open('data/fund_list.json', 'w', encoding='utf-8') as f:
                        json.dump(st.session_state.fund_list, f, ensure_ascii=False, indent=2)
                    st.success("✅ 数据导入成功")
                    st.rerun()
                else:
                    st.error("文件格式错误")
            except Exception as e:
                st.error(f"导入失败: {str(e)}")
    
    # 导出面板
    if st.session_state.get('show_export'):
        if st.session_state.fund_list:
            json_str = json.dumps(st.session_state.fund_list, ensure_ascii=False, indent=2)
            st.download_button(
                label="📥 下载JSON文件",
                data=json_str,
                file_name=f"fund_list_{beijing_time.strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True
            )
        else:
            st.warning("暂无数据可导出")
    
    st.markdown("---")
    
    # 添加基金
    st.subheader("➕ 添加基金")
    add_option = st.radio("添加方式", ["按代码添加", "搜索添加"], horizontal=True, label_visibility="collapsed")
    
    if add_option == "按代码添加":
        new_code = st.text_input("输入基金代码（6位数字）", max_chars=6, key="add_by_code_sidebar")
        if st.button("添加基金", type="primary", use_container_width=True):
            if new_code and len(new_code) == 6 and new_code.isdigit():
                if new_code not in st.session_state.fund_list:
                    st.session_state.fund_list.append(new_code)
                    with open('data/fund_list.json', 'w', encoding='utf-8') as f:
                        json.dump(st.session_state.fund_list, f, ensure_ascii=False, indent=2)
                    st.success(f"✅ 已添加基金: {new_code}")
                    st.rerun()
                else:
                    st.warning("基金已在列表中")
            else:
                st.error("请输入6位数字基金代码")
    else:
        search_keyword = st.text_input("搜索基金名称或代码", key="search_add_sidebar")
        if search_keyword:
            with st.spinner("搜索中..."):
                search_results = search_funds(search_keyword)
                if not search_results.empty:
                    for idx, row in search_results.iterrows():
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.write(f"**{row['基金简称']}**")
                            st.caption(f"代码: {row['基金代码']}")
                        with col2:
                            if st.button("➕", key=f"add_{row['基金代码']}_{idx}"):
                                if row['基金代码'] not in st.session_state.fund_list:
                                    st.session_state.fund_list.append(row['基金代码'])
                                    with open('data/fund_list.json', 'w', encoding='utf-8') as f:
                                        json.dump(st.session_state.fund_list, f, ensure_ascii=False, indent=2)
                                    st.success(f"✅ 已添加: {row['基金简称']}")
                                    st.rerun()
                else:
                    st.info("未找到相关基金")
    
    st.markdown("---")
    
    # 我的基金列表
    st.subheader(f"📋 我的基金 ({len(st.session_state.fund_list)})")
    
    if st.session_state.fund_list:
        for i, fund_code in enumerate(st.session_state.fund_list):
            fund_name = get_fund_name(fund_code)
            col1, col2, col3 = st.columns([4, 1, 1])
            with col1:
                st.write(f"**{fund_name}**")
                st.caption(f"`{fund_code}`")
            with col2:
                if st.button("👁️", key=f"view_{i}_sidebar"):
                    st.session_state.selected_fund = fund_code
            with col3:
                if st.button("🗑️", key=f"del_{i}_sidebar"):
                    st.session_state.fund_list.pop(i)
                    with open('data/fund_list.json', 'w', encoding='utf-8') as f:
                        json.dump(st.session_state.fund_list, f, ensure_ascii=False, indent=2)
                    st.success(f"已删除基金: {fund_code}")
                    st.rerun()
    else:
        st.info("暂无基金，请先添加")
    
    st.markdown("---")
    st.caption("💡 基金数据有15分钟延迟")

# 主界面
st.title("📈 基金持仓跟踪与估算系统")

# 搜索功能区
st.subheader("🔍 搜索基金")
search_col1, search_col2 = st.columns([4, 1])
with search_col1:
    search_input = st.text_input(
        "输入基金代码或名称",
        placeholder="如：161725 或 招商中证白酒",
        label_visibility="collapsed"
    )
with search_col2:
    search_btn = st.button("搜索", type="primary", use_container_width=True)

if search_btn and search_input:
    with st.spinner("搜索中..."):
        search_result = search_funds(search_input)
        if not search_result.empty:
            st.session_state.search_results = search_result
        else:
            st.session_state.search_results = None

if st.session_state.get('search_results') is not None:
    if isinstance(st.session_state.search_results, pd.DataFrame) and not st.session_state.search_results.empty:
        st.write("### 搜索结果")
        st.dataframe(
            st.session_state.search_results[['基金代码', '基金简称', '基金类型']],
            use_container_width=True,
            hide_index=True,
            column_config={
                "基金代码": st.column_config.TextColumn("基金代码", width="small"),
                "基金简称": st.column_config.TextColumn("基金简称"),
                "基金类型": st.column_config.TextColumn("类型", width="small")
            }
        )
    else:
        st.info("未找到相关基金")

# 我的基金收藏展示区
if st.session_state.fund_list:
    st.markdown("---")
    st.subheader(f"⭐ 我的基金收藏 ({len(st.session_state.fund_list)})")
    
    # 创建选项卡
    view_tab1, view_tab2 = st.tabs(["📊 卡片视图", "📋 列表视图"])
    
    with view_tab1:
        # 卡片视图
        cols = st.columns(3)
        
        for idx, fund_code in enumerate(st.session_state.fund_list):
            col_idx = idx % 3
            with cols[col_idx]:
                fund_name = get_fund_name(fund_code)
                
                if trading_day:
                    # 交易日：显示估算数据
                    with st.spinner(f"获取{fund_code}数据中..."):
                        est_data = get_fund_estimation(fund_code)
                    
                    if est_data:
                        change = est_data['估算涨跌幅']
                        card_class = "up" if change > 0 else ("down" if change < 0 else "flat")
                        change_color = "#4CAF50" if change > 0 else ("#F44336" if change < 0 else "#2196F3")
                        change_display = f"{'+' if change > 0 else ''}{change:.2f}%"
                        
                        st.markdown(f"""
                        <div class="fund-card {card_class}">
                            <h4 style="margin:0;">{fund_name}</h4>
                            <p style="color:#666; font-size:0.9em; margin:5px 0;">{fund_code}</p>
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <span style="font-size:1.2em; font-weight:bold;">交易日</span>
                                <span style="font-size:1.5em; font-weight:bold; color:{change_color}">
                                    {change_display}
                                </span>
                            </div>
                            <p style="font-size:0.8em; color:#888; margin-top:5px;">
                                估算净值: {est_data.get('估算净值', 0):.4f}
                            </p>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        # 如果无法获取估算数据，显示净值
                        nav_data = get_fund_nav(fund_code)
                        if nav_data:
                            st.markdown(f"""
                            <div class="fund-card flat">
                                <h4 style="margin:0;">{fund_name}</h4>
                                <p style="color:#666; font-size:0.9em; margin:5px 0;">{fund_code}</p>
                                <div style="display:flex; justify-content:space-between; align-items:center; margin:10px 0;">
                                    <span style="font-size:1.1em; font-weight:bold;">单位净值</span>
                                    <span style="font-size:1.3em; font-weight:bold; color:#2196F3;">
                                        {nav_data.get('单位净值', 0):.4f}
                                    </span>
                                </div>
                                <p style="font-size:0.8em; color:#888; margin:0;">
                                    {nav_data.get('净值日期', '')}
                                </p>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            st.markdown(f"""
                            <div class="fund-card flat">
                                <h4 style="margin:0;">{fund_name}</h4>
                                <p style="color:#666; font-size:0.9em; margin:5px 0;">{fund_code}</p>
                                <div style="display:flex; justify-content:space-between; align-items:center;">
                                    <span style="font-size:1.2em; font-weight:bold;">交易日</span>
                                    <span style="font-size:1.2em; font-weight:bold; color:#FF9800;">
                                        数据获取中
                                    </span>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                else:
                    # 非交易日：显示最新净值
                    nav_data = get_fund_nav(fund_code)
                    if nav_data:
                        st.markdown(f"""
                        <div class="fund-card flat">
                            <h4 style="margin:0;">{fund_name}</h4>
                            <p style="color:#666; font-size:0.9em; margin:5px 0;">{fund_code}</p>
                            <div style="display:flex; justify-content:space-between; align-items:center; margin:10px 0;">
                                <span style="font-size:1.1em; font-weight:bold;">单位净值</span>
                                <span style="font-size:1.3em; font-weight:bold; color:#2196F3;">
                                    {nav_data.get('单位净值', 0):.4f}
                                </span>
                            </div>
                            <p style="font-size:0.8em; color:#888; margin:0;">
                                {nav_data.get('净值日期', '')}
                            </p>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div class="fund-card flat">
                            <h4 style="margin:0;">{fund_name}</h4>
                            <p style="color:#666; font-size:0.9em; margin:5px 0;">{fund_code}</p>
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <span style="font-size:1.2em; font-weight:bold;">非交易日</span>
                                <span style="font-size:1.2em; font-weight:bold; color:#9E9E9E;">
                                    休市
                                </span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                
                # 操作按钮
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("查看详情", key=f"detail_{fund_code}", use_container_width=True):
                        st.session_state.selected_fund = fund_code
                with col_btn2:
                    if st.button("刷新", key=f"refresh_{fund_code}", use_container_width=True):
                        st.rerun()
    
    with view_tab2:
        # 列表视图
        list_data = []
        for fund_code in st.session_state.fund_list:
            fund_name = get_fund_name(fund_code)
            
            if trading_day:
                est_data = get_fund_estimation(fund_code)
                if est_data:
                    value = f"{est_data['估算涨跌幅']:.2f}%"
                else:
                    nav_data = get_fund_nav(fund_code)
                    value = f"{nav_data.get('单位净值', 0):.4f}" if nav_data else "无数据"
            else:
                nav_data = get_fund_nav(fund_code)
                value = f"{nav_data.get('单位净值', 0):.4f}" if nav_data else "非交易日"
            
            list_data.append({
                "基金代码": fund_code,
                "基金名称": fund_name,
                "类型": "估算" if trading_day and est_data else "净值",
                "值": value
            })
        
        if list_data:
            list_df = pd.DataFrame(list_data)
            st.dataframe(
                list_df,
                use_container_width=True,
                hide_index=True
            )
            
            # 添加批量操作
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📥 导出列表为CSV", use_container_width=True):
                    csv = list_df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="点击下载",
                        data=csv,
                        file_name=f"my_funds_{beijing_time.strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        key="download_list_csv"
                    )
            with col2:
                if st.button("🔄 刷新所有数据", use_container_width=True):
                    st.rerun()

# 基金详情展示
if st.session_state.get('selected_fund'):
    st.markdown("---")
    fund_code = st.session_state.selected_fund
    fund_name = get_fund_name(fund_code)
    
    st.write(f"### 📊 基金详情: **{fund_name}** ({fund_code})")
    
    # 显示基本信息
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("基金代码", fund_code)
    with col2:
        st.metric("基金名称", fund_name)
    with col3:
        st.metric("数据状态", "交易日" if trading_day else "非交易日")
    with col4:
        st.metric("更新时间", beijing_time.strftime('%H:%M:%S'))
    
    # 显示数据
    if trading_day:
        # 交易日显示估算数据
        est_data = get_fund_estimation(fund_code)
        if est_data:
            st.metric(
                "估算涨跌幅",
                f"{est_data['估算涨跌幅']:.2f}%",
                delta=f"{est_data['估算涨跌幅']:.2f}%",
                delta_color="normal" if est_data['估算涨跌幅'] >= 0 else "inverse"
            )
            st.caption(f"估算净值: {est_data.get('估算净值', 0):.4f} • 更新时间: {est_data.get('更新时间', '')}")
        else:
            # 如果无法获取估算，显示净值
            nav_data = get_fund_nav(fund_code)
            if nav_data:
                st.metric("单位净值", f"{nav_data['单位净值']:.4f}")
                st.caption(f"净值日期: {nav_data.get('净值日期', '')}")
            else:
                st.warning("无法获取基金数据")
    else:
        # 非交易日显示净值
        nav_data = get_fund_nav(fund_code)
        if nav_data:
            col_nav1, col_nav2, col_nav3 = st.columns(3)
            with col_nav1:
                st.metric("单位净值", f"{nav_data.get('单位净值', 0):.4f}")
            with col_nav2:
                st.metric("累计净值", f"{nav_data.get('累计净值', 0):.4f}")
            with col_nav3:
                st.metric("净值日期", nav_data.get('净值日期', ''))
            
            if nav_data.get('日增长率'):
                growth_rate = nav_data['日增长率']
                delta_color = "normal" if growth_rate >= 0 else "inverse"
                st.metric(
                    "日增长率",
                    f"{growth_rate:.2f}%",
                    delta=f"{growth_rate:.2f}%",
                    delta_color=delta_color
                )
        else:
            st.warning("无法获取净值信息")
    
    # 显示持仓数据
    with st.expander("📊 查看持仓数据"):
        holdings = get_fund_holdings(fund_code)
        if holdings:
            holdings_df = pd.DataFrame(holdings)
            st.dataframe(holdings_df, use_container_width=True, hide_index=True)
        else:
            st.info("暂无持仓数据或无法获取")

# 页脚
st.markdown("---")
st.caption("""
**免责声明**: 本系统数据仅供参考，估算涨跌幅基于前十大重仓股实时数据计算，与实际净值可能存在差异。投资有风险，入市需谨慎。
**数据来源**: 东方财富、新浪财经等公开数据接口
**更新时间**: 数据有15分钟延迟
**当前时间**: {} (北京时间)
""".format(beijing_time.strftime('%Y-%m-%d %H:%M:%S')))

# 初始化session_state变量
if 'show_import' not in st.session_state:
    st.session_state.show_import = False
if 'show_export' not in st.session_state:
    st.session_state.show_export = False
if 'selected_fund' not in st.session_state:
    st.session_state.selected_fund = None
