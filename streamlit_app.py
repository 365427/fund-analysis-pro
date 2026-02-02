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
import re
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
    
    # 2024年A股交易日历（主要节假日，实际应更详细）
    holidays_2024 = [
        '2024-01-01',  # 元旦
        '2024-02-10', '2024-02-11', '2024-02-12', '2024-02-13', '2024-02-14', '2024-02-15', '2024-02-16', '2024-02-17',  # 春节
        '2024-04-04', '2024-04-05', '2024-04-06',  # 清明节
        '2024-05-01', '2024-05-02', '2024-05-03', '2024-05-04', '2024-05-05',  # 劳动节
        '2024-06-10',  # 端午节
        '2024-09-15', '2024-09-16', '2024-09-17',  # 中秋节
        '2024-10-01', '2024-10-02', '2024-10-03', '2024-10-04', '2024-10-05', '2024-10-06', '2024-10-07',  # 国庆节
    ]
    
    today_str = now.strftime('%Y-%m-%d')
    if today_str in holidays_2024:
        return False
    
    return True

def is_trading_hours():
    """判断当前是否在交易时间内"""
    now = get_beijing_time()
    current_time = now.time()
    
    # A股交易时间：上午9:30-11:30，下午13:00-15:00
    morning_start = datetime.strptime('09:30', '%H:%M').time()
    morning_end = datetime.strptime('11:30', '%H:%M').time()
    afternoon_start = datetime.strptime('13:00', '%H:%M').time()
    afternoon_end = datetime.strptime('15:00', '%H:%M').time()
    
    return (morning_start <= current_time <= morning_end) or (afternoon_start <= current_time <= afternoon_end)

# ====================== 数据获取函数 ======================
def get_fund_basic_info(fund_code):
    """获取基金基本信息"""
    try:
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
        
        return {
            'code': fund_code,
            'name': f"基金{fund_code}",
            'type': '未知'
        }
    except:
        return {
            'code': fund_code,
            'name': f"基金{fund_code}",
            'type': '未知'
        }

def get_fund_estimation_from_api(fund_code):
    """从API获取基金实时估算数据"""
    try:
        # 方法1：使用基金实时估算接口
        est_data = ak.fund_value_estimation_em(symbol=fund_code)
        
        if not est_data.empty and len(est_data) > 0:
            # 找到最新的估算数据
            latest = None
            
            # 检查数据中是否有今天的数据
            current_date = get_beijing_time().strftime('%Y-%m-%d')
            
            for _, row in est_data.iterrows():
                # 检查是否有估算数据
                has_estimation = False
                for col in ['估算净值', '估算值']:
                    if col in row and pd.notna(row[col]) and row[col] != '':
                        has_estimation = True
                        break
                
                if has_estimation:
                    latest = row
                    break
            
            if latest is not None:
                # 提取估算数据
                estimated_value = None
                estimated_change = None
                
                # 提取估算净值
                for val_col in ['估算净值', '估算值']:
                    if val_col in latest and latest[val_col] not in [None, '', np.nan]:
                        try:
                            estimated_value = float(latest[val_col])
                        except:
                            pass
                        break
                
                # 提取涨跌幅
                for chg_col in ['估算涨跌幅', '涨跌幅']:
                    if chg_col in latest and latest[chg_col] not in [None, '', np.nan]:
                        chg_str = str(latest[chg_col])
                        # 清理百分比符号和空格
                        chg_str = chg_str.replace('%', '').replace(' ', '').strip()
                        try:
                            estimated_change = float(chg_str)
                        except:
                            pass
                        break
                
                if estimated_value is not None:
                    return {
                        'type': 'real_time',
                        'value': estimated_value,
                        'change': estimated_change if estimated_change is not None else 0,
                        'update_time': get_beijing_time().strftime('%Y-%m-%d %H:%M:%S'),
                        'source': '实时估算'
                    }
        
        return None
    except Exception as e:
        print(f"获取基金{fund_code}实时估算失败: {e}")
        return None

def get_fund_nav_data(fund_code):
    """获取基金净值数据"""
    try:
        # 获取基金净值
        nav_data = ak.fund_open_fund_info_em(symbol=fund_code)
        
        if not nav_data.empty and len(nav_data) > 0:
            # 获取最新净值
            latest = nav_data.iloc[0]
            
            # 提取净值数据
            nav_value = None
            nav_date = None
            
            for nav_col in ['单位净值', '净值']:
                if nav_col in latest and latest[nav_col] not in [None, '', np.nan]:
                    try:
                        nav_value = float(latest[nav_col])
                    except:
                        pass
                    break
            
            for date_col in ['净值日期', '日期']:
                if date_col in latest and latest[date_col] not in [None, '', np.nan]:
                    nav_date = str(latest[date_col])
                    break
            
            if nav_value is not None:
                return {
                    'type': 'nav',
                    'value': nav_value,
                    'date': nav_date if nav_date else '',
                    'source': '单位净值'
                }
        
        return None
    except Exception as e:
        print(f"获取基金{fund_code}净值失败: {e}")
        return None

def calculate_fund_estimation(fund_code):
    """通过持仓计算基金估算涨跌幅"""
    try:
        # 获取基金持仓
        holdings = ak.fund_em_portfolio_hold(fund=fund_code)
        
        if holdings.empty or len(holdings) == 0:
            return None
        
        # 获取前十大持仓
        top_holdings = holdings.head(10)
        
        # 提取股票代码
        stock_codes = []
        stock_weights = []
        
        for _, row in top_holdings.iterrows():
            stock_code = row.get('股票代码', '')
            weight_str = str(row.get('占净值比例', '0')).replace('%', '').strip()
            
            if stock_code and weight_str and weight_str != '---':
                try:
                    weight = float(weight_str)
                    stock_codes.append(stock_code)
                    stock_weights.append(weight)
                except:
                    continue
        
        if len(stock_codes) == 0:
            return None
        
        # 获取股票实时数据
        stock_data = {}
        try:
            # 获取A股实时数据
            market_data = ak.stock_zh_a_spot_em()
            
            for code, weight in zip(stock_codes, stock_weights):
                # 标准化股票代码
                clean_code = str(code).replace('SH', '').replace('SZ', '').strip()
                
                # 在市场中查找股票
                for _, stock_row in market_data.iterrows():
                    market_code = str(stock_row['代码']).strip()
                    
                    # 匹配股票代码
                    if market_code.endswith(clean_code) or market_code == clean_code:
                        # 获取涨跌幅
                        change_str = str(stock_row.get('涨跌幅', '0')).replace('%', '').strip()
                        try:
                            change = float(change_str)
                            stock_data[code] = {
                                'change': change,
                                'weight': weight
                            }
                        except:
                            pass
                        break
        except Exception as e:
            print(f"获取股票数据失败: {e}")
            return None
        
        if len(stock_data) == 0:
            return None
        
        # 计算加权涨跌幅
        total_weight = sum([data['weight'] for data in stock_data.values()])
        if total_weight == 0:
            return None
        
        weighted_change = sum([data['change'] * data['weight'] for data in stock_data.values()]) / total_weight
        
        # 获取基金最新净值作为基础
        nav_data = get_fund_nav_data(fund_code)
        if nav_data and nav_data['type'] == 'nav':
            base_value = nav_data['value']
            estimated_value = base_value * (1 + weighted_change / 100)
        else:
            base_value = 1.0
            estimated_value = 1.0 * (1 + weighted_change / 100)
        
        return {
            'type': 'real_time_calc',
            'value': estimated_value,
            'change': weighted_change,
            'update_time': get_beijing_time().strftime('%Y-%m-%d %H:%M:%S'),
            'source': '持仓计算',
            'stock_count': len(stock_data),
            'total_weight': total_weight
        }
        
    except Exception as e:
        print(f"计算基金{fund_code}估算失败: {e}")
        return None

def get_fund_real_time_data(fund_code):
    """获取基金实时数据 - 主函数"""
    current_time = get_beijing_time()
    current_date = current_time.strftime('%Y-%m-%d')
    
    # 检查是否为交易日且在交易时间内
    if is_trading_day() and is_trading_hours():
        # 交易日交易时间：优先获取实时估算
        
        # 1. 从API获取实时估算
        est_data = get_fund_estimation_from_api(fund_code)
        if est_data and est_data['type'] == 'real_time':
            return est_data
        
        # 2. 如果API失败，通过持仓计算
        calc_data = calculate_fund_estimation(fund_code)
        if calc_data and calc_data['type'] == 'real_time_calc':
            return calc_data
        
        # 3. 如果都无法获取实时数据，获取最新净值
        nav_data = get_fund_nav_data(fund_code)
        if nav_data:
            # 在交易日交易时间显示净值，但标明是非实时
            nav_data['source'] = '最新净值(非实时)'
            nav_data['update_time'] = f"{current_date} {current_time.strftime('%H:%M:%S')}"
            return nav_data
    
    # 非交易时间或非交易日：显示最新净值
    nav_data = get_fund_nav_data(fund_code)
    if nav_data:
        # 如果净值数据有日期，使用净值日期，否则使用当前日期
        if nav_data.get('date'):
            nav_data['update_time'] = nav_data['date']
        else:
            nav_data['update_time'] = current_date
        return nav_data
    
    # 如果都无法获取，返回空
    return None

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
    st.caption(f"🕐 系统时间: {beijing_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 判断交易日状态
    trading_day = is_trading_day()
    trading_hours = is_trading_hours()
    
    if trading_day and trading_hours:
        st.success("✅ 交易日交易时间")
    elif trading_day and not trading_hours:
        st.info("📅 交易日非交易时间")
    else:
        st.info("📅 非交易日")
    
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
    
    # 创建表格数据
    table_data = []
    
    # 显示加载状态
    if len(st.session_state.fund_list) > 0:
        progress_bar = st.progress(0)
        status_text = st.empty()
    
    for idx, fund_code in enumerate(st.session_state.fund_list):
        if len(st.session_state.fund_list) > 0:
            status_text.text(f"正在获取 {fund_code} 的数据... ({idx+1}/{len(st.session_state.fund_list)})")
        
        # 获取基金基本信息
        fund_info = get_fund_basic_info(fund_code)
        
        # 获取实时数据
        real_time_data = get_fund_real_time_data(fund_code)
        
        # 准备表格行数据
        row_data = {
            '基金代码': fund_code,
            '基金名称': fund_info['name']
        }
        
        if real_time_data:
            if real_time_data['type'] in ['real_time', 'real_time_calc']:
                # 实时估算数据
                change = real_time_data.get('change', 0)
                
                # 设置涨跌幅度显示（红涨绿跌）
                if change > 0:
                    change_display = f"<span class='red-text'>+{change:.2f}%</span>"
                elif change < 0:
                    change_display = f"<span class='green-text'>{change:.2f}%</span>"
                else:
                    change_display = f"{change:.2f}%"
                
                row_data['更新时间'] = real_time_data.get('update_time', '')
                row_data['涨跌幅度'] = change_display
                row_data['估算净值'] = f"{real_time_data.get('value', 0):.4f}"
                row_data['数据状态'] = real_time_data.get('source', '实时估算')
                
            else:
                # 净值数据
                row_data['更新时间'] = real_time_data.get('update_time', '')
                row_data['涨跌幅度'] = '-'
                row_data['估算净值'] = f"{real_time_data.get('value', 0):.4f}"
                row_data['数据状态'] = real_time_data.get('source', '单位净值')
        else:
            row_data['更新时间'] = '暂无数据'
            row_data['涨跌幅度'] = '-'
            row_data['估算净值'] = '-'
            row_data['数据状态'] = '无数据'
        
        table_data.append(row_data)
        if len(st.session_state.fund_list) > 0:
            progress_bar.progress((idx + 1) / len(st.session_state.fund_list))
    
    if len(st.session_state.fund_list) > 0:
        status_text.text("数据加载完成！")
    
    # 创建DataFrame
    if table_data:
        df = pd.DataFrame(table_data)
        
        # 重新排序列顺序
        df = df[['基金代码', '基金名称', '更新时间', '涨跌幅度', '估算净值', '数据状态']]
        
        # 使用st.dataframe显示，允许HTML渲染
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "基金代码": st.column_config.TextColumn("基金代码", width="small"),
                "基金名称": st.column_config.TextColumn("基金名称"),
                "更新时间": st.column_config.TextColumn("更新时间", width="medium"),
                "涨跌幅度": st.column_config.TextColumn("涨跌幅度", width="small"),
                "估算净值": st.column_config.TextColumn("估算净值", width="small"),
                "数据状态": st.column_config.TextColumn("数据状态", width="small")
            }
        )
        
        # 操作按钮
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📥 导出表格为CSV", use_container_width=True):
                # 准备导出数据（去掉HTML标签）
                export_data = []
                for row in table_data:
                    export_row = row.copy()
                    # 清理涨跌幅度的HTML标签
                    if '涨跌幅度' in export_row and export_row['涨跌幅度'] != '-':
                        # 去掉HTML标签
                        clean_change = re.sub(r'<[^>]+>', '', export_row['涨跌幅度'])
                        export_row['涨跌幅度'] = clean_change
                    export_data.append(export_row)
                
                export_df = pd.DataFrame(export_data)
                export_df = export_df[['基金代码', '基金名称', '更新时间', '涨跌幅度', '估算净值', '数据状态']]
                csv = export_df.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="点击下载CSV文件",
                    data=csv,
                    file_name=f"fund_data_{get_beijing_time().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    key="download_csv"
                )
        
        with col2:
            if st.button("🔄 刷新数据", use_container_width=True):
                st.rerun()
    else:
        st.info("暂无数据")

# 基金详情展示
if st.session_state.get('selected_fund'):
    st.markdown("---")
    fund_code = st.session_state.selected_fund
    fund_info = get_fund_basic_info(fund_code)
    
    st.write(f"### 📊 基金详情: **{fund_info['name']}** ({fund_code})")
    
    # 获取实时数据
    real_time_data = get_fund_real_time_data(fund_code)
    
    if real_time_data and real_time_data['type'] in ['real_time', 'real_time_calc']:
        # 显示实时估算
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("基金代码", fund_code)
        with col2:
            st.metric("基金名称", fund_info['name'])
        with col3:
            st.metric("数据状态", real_time_data.get('source', '实时估算'))
        with col4:
            st.metric("更新时间", real_time_data.get('update_time', ''))
        
        # 显示估算数据
        change = real_time_data.get('change', 0)
        delta_color = "normal" if change >= 0 else "inverse"
        
        st.metric(
            "估算涨跌幅",
            f"{change:.2f}%",
            delta=f"{'+' if change > 0 else ''}{change:.2f}%",
            delta_color=delta_color
        )
        st.metric("估算净值", f"{real_time_data.get('value', 0):.4f}")
        
    elif real_time_data and real_time_data['type'] == 'nav':
        # 显示净值
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("基金代码", fund_code)
        with col2:
            st.metric("基金名称", fund_info['name'])
        with col3:
            st.metric("数据状态", real_time_data.get('source', '单位净值'))
        with col4:
            st.metric("更新时间", real_time_data.get('update_time', ''))
        
        st.metric("单位净值", f"{real_time_data.get('value', 0):.4f}")
    
    else:
        st.warning("无法获取基金数据")

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
