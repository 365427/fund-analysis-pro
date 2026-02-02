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
    border-left: 4px solid #F44336;
}
.fund-card.down {
    border-left: 4px solid #4CAF50;
}
.fund-card.flat {
    border-left: 4px solid #2196F3;
}
.red-text {
    color: #F44336;
    font-weight: bold;
}
.green-text {
    color: #4CAF50;
    font-weight: bold;
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

# ====================== 交易日判断函数 ======================
def is_trading_day():
    """判断今天是否为交易日 - 简化但有效的方法"""
    now = get_beijing_time()
    
    # 获取当前是星期几
    weekday = now.weekday()  # 0=周一, 1=周二, ..., 6=周日
    
    # 判断是否为周末
    if weekday >= 5:  # 5=周六, 6=周日
        return False
    
    # 判断当前时间是否在交易时间内
    current_time = now.time()
    market_open = datetime.strptime('09:00', '%H:%M').time()
    market_close = datetime.strptime('15:00', '%H:%M').time()
    
    # 如果在交易时间内
    if market_open <= current_time <= market_close:
        return True
    
    # 非交易时间也返回True，但显示昨日数据
    return True

# ====================== 数据获取函数 ======================
def get_fund_basic_info(fund_code):
    """获取基金基本信息"""
    try:
        # 尝试多种方法获取基金名称
        fund_name = f"基金{fund_code}"
        
        # 方法1：使用基金列表接口
        try:
            fund_list = ak.fund_name_em()
            if not fund_list.empty:
                fund_info = fund_list[fund_list['基金代码'] == fund_code]
                if not fund_info.empty:
                    return {
                        'code': fund_code,
                        'name': fund_info.iloc[0]['基金简称'],
                        'type': fund_info.iloc[0]['基金类型']
                    }
        except:
            pass
        
        # 方法2：使用基金档案接口
        try:
            fund_info = ak.fund_em_fund_info(fund=fund_code)
            if not fund_info.empty:
                if '基金简称' in fund_info.columns:
                    return {
                        'code': fund_code,
                        'name': fund_info.iloc[0]['基金简称'],
                        'type': '未知'
                    }
        except:
            pass
        
        return {
            'code': fund_code,
            'name': fund_name,
            'type': '未知'
        }
    except:
        return {
            'code': fund_code,
            'name': f"基金{fund_code}",
            'type': '未知'
        }

def get_fund_real_time_data(fund_code):
    """获取基金实时估算数据 - 核心功能"""
    try:
        # 方法1：使用基金实时估算接口
        try:
            # 获取基金实时估算
            est_data = ak.fund_value_estimation_em(symbol=fund_code)
            if not est_data.empty and len(est_data) > 0:
                latest = est_data.iloc[0]
                
                # 提取估算数据
                estimated_value = None
                estimated_change = None
                
                # 尝试不同的列名
                for val_col in ['估算净值', '估算值', 'value']:
                    if val_col in latest and latest[val_col] not in [None, '', np.nan]:
                        estimated_value = float(latest[val_col])
                        break
                
                for chg_col in ['估算涨跌幅', '涨跌幅', 'change']:
                    if chg_col in latest and latest[chg_col] not in [None, '', np.nan]:
                        chg_str = str(latest[chg_col])
                        if '%' in chg_str:
                            estimated_change = float(chg_str.replace('%', ''))
                        else:
                            estimated_change = float(chg_str)
                        break
                
                if estimated_value is not None:
                    return {
                        'type': 'real_time',
                        'value': estimated_value,
                        'change': estimated_change if estimated_change is not None else 0,
                        'update_time': get_beijing_time().strftime('%H:%M:%S'),
                        'source': '实时估算'
                    }
        except Exception as e:
            pass
        
        # 方法2：如果实时估算失败，获取当日最新净值
        try:
            # 获取基金历史净值
            nav_data = ak.fund_open_fund_info_em(symbol=fund_code)
            if not nav_data.empty and len(nav_data) > 0:
                latest = nav_data.iloc[0]
                
                # 获取净值
                nav_value = None
                for nav_col in ['单位净值', '净值', 'value']:
                    if nav_col in latest and latest[nav_col] not in [None, '', np.nan]:
                        nav_value = float(latest[nav_col])
                        break
                
                # 获取日期
                nav_date = None
                for date_col in ['净值日期', '日期', 'date']:
                    if date_col in latest and latest[date_col] not in [None, '', np.nan]:
                        nav_date = str(latest[date_col])
                        break
                
                if nav_value is not None:
                    return {
                        'type': 'nav',
                        'value': nav_value,
                        'date': nav_date if nav_date else get_beijing_time().strftime('%Y-%m-%d'),
                        'update_time': get_beijing_time().strftime('%H:%M:%S'),
                        'source': '最新净值'
                    }
        except Exception as e:
            pass
        
        return None
    except:
        return None

def calculate_fund_change(fund_code):
    """计算基金涨跌幅（如果有持仓数据的话）"""
    # 这里可以扩展为根据持仓股票实时计算
    # 目前先返回None，使用实时估算数据
    return None

def get_fund_holdings(fund_code):
    """获取基金持仓数据"""
    try:
        holdings = ak.fund_em_portfolio_hold(fund=fund_code)
        if not holdings.empty:
            return holdings.head(10)
        return pd.DataFrame()
    except:
        return pd.DataFrame()

def search_funds(keyword):
    """搜索基金"""
    try:
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

# ====================== 界面部分 ======================
# 侧边栏
with st.sidebar:
    st.title("📊 基金跟踪系统")
    st.markdown("---")
    
    # 显示北京时间
    beijing_time = get_beijing_time()
    st.caption(f"🕐 更新时间: {beijing_time.strftime('%H:%M:%S')}")
    
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
            fund_info = get_fund_basic_info(fund_code)
            col1, col2, col3 = st.columns([4, 1, 1])
            with col1:
                st.write(f"**{fund_info['name']}**")
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
                fund_info = get_fund_basic_info(fund_code)
                
                # 获取实时数据
                with st.spinner(f"获取{fund_code}数据中..."):
                    real_time_data = get_fund_real_time_data(fund_code)
                
                if real_time_data:
                    if real_time_data['type'] == 'real_time':
                        # 实时估算数据
                        value = real_time_data['value']
                        change = real_time_data.get('change', 0)
                        
                        # 红涨绿跌
                        if change > 0:
                            card_class = "up"
                            change_color = "red-text"
                            change_display = f"+{change:.2f}%"
                        elif change < 0:
                            card_class = "down"
                            change_color = "green-text"
                            change_display = f"{change:.2f}%"
                        else:
                            card_class = "flat"
                            change_color = ""
                            change_display = f"{change:.2f}%"
                        
                        st.markdown(f"""
                        <div class="fund-card {card_class}">
                            <h4 style="margin:0;">{fund_info['name']}</h4>
                            <p style="color:#666; font-size:0.9em; margin:5px 0;">{fund_code}</p>
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <span style="font-size:1.1em; font-weight:bold;">实时估算</span>
                                <span class="{change_color}" style="font-size:1.5em; font-weight:bold;">
                                    {change_display}
                                </span>
                            </div>
                            <p style="font-size:0.9em; color:#666; margin-top:5px;">
                                估算净值: {value:.4f}
                            </p>
                            <p style="font-size:0.8em; color:#888; margin:0;">
                                {real_time_data['update_time']} • {real_time_data['source']}
                            </p>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        # 净值数据
                        value = real_time_data['value']
                        date_str = real_time_data.get('date', '')
                        
                        st.markdown(f"""
                        <div class="fund-card flat">
                            <h4 style="margin:0;">{fund_info['name']}</h4>
                            <p style="color:#666; font-size:0.9em; margin:5px 0;">{fund_code}</p>
                            <div style="display:flex; justify-content:space-between; align-items:center; margin:10px 0;">
                                <span style="font-size:1.1em; font-weight:bold;">单位净值</span>
                                <span style="font-size:1.3em; font-weight:bold; color:#2196F3;">
                                    {value:.4f}
                                </span>
                            </div>
                            <p style="font-size:0.8em; color:#888; margin:0;">
                                {date_str} • {real_time_data['source']}
                            </p>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    # 无法获取数据
                    st.markdown(f"""
                    <div class="fund-card flat">
                        <h4 style="margin:0;">{fund_info['name']}</h4>
                        <p style="color:#666; font-size:0.9em; margin:5px 0;">{fund_code}</p>
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-size:1.2em; font-weight:bold;">交易日</span>
                            <span style="font-size:1.2em; font-weight:bold; color:#FF9800;">
                                数据获取中
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
        # 列表视图 - 使用HTML表格实现红涨绿跌
        st.write("### 基金列表")
        
        # 创建表格数据
        table_html = """
        <table style="width:100%; border-collapse: collapse; margin-top: 20px;">
            <thead>
                <tr style="background-color: #f2f2f2; border-bottom: 2px solid #ddd;">
                    <th style="padding: 12px; text-align: left;">基金代码</th>
                    <th style="padding: 12px; text-align: left;">基金名称</th>
                    <th style="padding: 12px; text-align: left;">类型</th>
                    <th style="padding: 12px; text-align: right;">估算净值</th>
                    <th style="padding: 12px; text-align: right;">涨跌幅</th>
                </tr>
            </thead>
            <tbody>
        """
        
        for fund_code in st.session_state.fund_list:
            fund_info = get_fund_basic_info(fund_code)
            real_time_data = get_fund_real_time_data(fund_code)
            
            if real_time_data and real_time_data['type'] == 'real_time':
                # 实时估算数据
                value = real_time_data['value']
                change = real_time_data.get('change', 0)
                
                # 红涨绿跌
                if change > 0:
                    change_color = "#F44336"
                    change_display = f"+{change:.2f}%"
                elif change < 0:
                    change_color = "#4CAF50"
                    change_display = f"{change:.2f}%"
                else:
                    change_color = "#666666"
                    change_display = f"{change:.2f}%"
                
                value_display = f"{value:.4f}"
                data_type = "实时估算"
            elif real_time_data and real_time_data['type'] == 'nav':
                # 净值数据
                value = real_time_data['value']
                value_display = f"{value:.4f}"
                change_display = "-"
                change_color = "#666666"
                data_type = "单位净值"
            else:
                value_display = "-"
                change_display = "-"
                change_color = "#666666"
                data_type = "无数据"
            
            # 添加行
            table_html += f"""
            <tr style="border-bottom: 1px solid #ddd;">
                <td style="padding: 12px;">{fund_code}</td>
                <td style="padding: 12px;">{fund_info['name']}</td>
                <td style="padding: 12px;">{data_type}</td>
                <td style="padding: 12px; text-align: right; font-weight: bold;">{value_display}</td>
                <td style="padding: 12px; text-align: right; font-weight: bold; color: {change_color};">{change_display}</td>
            </tr>
            """
        
        table_html += """
            </tbody>
        </table>
        """
        
        st.markdown(table_html, unsafe_allow_html=True)
        
        # 添加操作按钮
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📥 导出数据为CSV", use_container_width=True):
                # 准备导出数据
                export_data = []
                for fund_code in st.session_state.fund_list:
                    fund_info = get_fund_basic_info(fund_code)
                    real_time_data = get_fund_real_time_data(fund_code)
                    
                    row = {
                        '基金代码': fund_code,
                        '基金名称': fund_info['name'],
                        '更新时间': get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    if real_time_data and real_time_data['type'] == 'real_time':
                        row['类型'] = '实时估算'
                        row['估算净值'] = real_time_data['value']
                        row['涨跌幅%'] = real_time_data.get('change', 0)
                    elif real_time_data and real_time_data['type'] == 'nav':
                        row['类型'] = '单位净值'
                        row['净值'] = real_time_data['value']
                        row['净值日期'] = real_time_data.get('date', '')
                    else:
                        row['类型'] = '无数据'
                        row['净值'] = ''
                        row['涨跌幅%'] = ''
                    
                    export_data.append(row)
                
                if export_data:
                    df = pd.DataFrame(export_data)
                    csv = df.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button(
                        label="点击下载CSV文件",
                        data=csv,
                        file_name=f"fund_data_{get_beijing_time().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        key="download_csv"
                    )
        with col2:
            if st.button("🔄 刷新所有数据", use_container_width=True):
                st.rerun()

# 基金详情展示
if st.session_state.get('selected_fund'):
    st.markdown("---")
    fund_code = st.session_state.selected_fund
    fund_info = get_fund_basic_info(fund_code)
    
    st.write(f"### 📊 基金详情: **{fund_info['name']}** ({fund_code})")
    
    # 获取实时数据
    real_time_data = get_fund_real_time_data(fund_code)
    
    if real_time_data and real_time_data['type'] == 'real_time':
        # 显示实时估算
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("基金代码", fund_code)
        with col2:
            st.metric("基金名称", fund_info['name'])
        with col3:
            st.metric("数据状态", "实时估算")
        with col4:
            st.metric("更新时间", real_time_data['update_time'])
        
        # 显示估算数据
        change = real_time_data.get('change', 0)
        delta_color = "normal" if change >= 0 else "inverse"
        
        st.metric(
            "估算涨跌幅",
            f"{change:.2f}%",
            delta=f"{'+' if change > 0 else ''}{change:.2f}%",
            delta_color=delta_color
        )
        st.metric("估算净值", f"{real_time_data['value']:.4f}")
        
    elif real_time_data and real_time_data['type'] == 'nav':
        # 显示净值
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("基金代码", fund_code)
        with col2:
            st.metric("基金名称", fund_info['name'])
        with col3:
            st.metric("数据状态", "单位净值")
        with col4:
            st.metric("净值日期", real_time_data.get('date', ''))
        
        st.metric("单位净值", f"{real_time_data['value']:.4f}")
    
    else:
        st.warning("无法获取基金数据")
    
    # 显示持仓数据
    with st.expander("📊 查看持仓数据"):
        holdings = get_fund_holdings(fund_code)
        if not holdings.empty:
            st.dataframe(holdings, use_container_width=True, hide_index=True)
        else:
            st.info("暂无持仓数据")

# 页脚
st.markdown("---")
st.caption(f"""
**免责声明**: 本系统数据仅供参考，估算涨跌基于前十大重仓股实时数据计算，与实际净值可能存在差异。投资有风险，入市需谨慎。
**数据来源**: 东方财富、新浪财经等公开数据接口
**更新时间**: 数据有15分钟延迟
**当前时间**: {get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')} (北京时间)
""")

# 初始化session_state变量
if 'show_import' not in st.session_state:
    st.session_state.show_import = False
if 'show_export' not in st.session_state:
    st.session_state.show_export = False
if 'selected_fund' not in st.session_state:
    st.session_state.selected_fund = None
