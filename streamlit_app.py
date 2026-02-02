import streamlit as st
import pandas as pd
import numpy as np
import akshare as ak
import json
import os
import time
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import warnings
warnings.filterwarnings('ignore')

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
.css-1d391kg, .css-12oz5g7, .css-1vq4p4l, .css-18e3th9 {
    font-family: 'Noto Sans SC', sans-serif;
}
</style>
""", unsafe_allow_html=True)

# 初始化session_state
if 'fund_list' not in st.session_state:
    if os.path.exists('data/fund_list.json'):
        with open('data/fund_list.json', 'r', encoding='utf-8') as f:
            st.session_state.fund_list = json.load(f)
    else:
        st.session_state.fund_list = []

if 'fund_data_cache' not in st.session_state:
    st.session_state.fund_data_cache = {}

if 'search_results' not in st.session_state:
    st.session_state.search_results = None

# 创建必要的目录
os.makedirs('data/cache', exist_ok=True)

# 交易日判断（简单版，可优化为接入节假日API）
def is_trading_day(date=None):
    """判断是否为交易日（简单判断周末，实际应接入节假日API）"""
    if date is None:
        date = datetime.now()
    
    # 判断是否为周末
    if date.weekday() >= 5:  # 5=周六, 6=周日
        return False
    
    # 这里可以添加节假日判断（需要接入第三方API）
    # 简单示例：排除一些固定假日
    holidays = [
        '2024-01-01', '2024-02-10', '2024-02-11', '2024-02-12',
        '2024-04-04', '2024-05-01', '2024-06-10', '2024-09-17',
        '2024-10-01', '2024-10-02', '2024-10-03'
    ]
    if date.strftime('%Y-%m-%d') in holidays:
        return False
    
    return True

def get_fund_basic_info(fund_code):
    """获取基金基本信息"""
    try:
        # 尝试多种接口获取基金信息
        try:
            fund_info = ak.fund_info_em(fund_code)
            if not fund_info.empty:
                return fund_info.iloc[0]
        except:
            pass
        
        # 备用接口
        try:
            fund_info = ak.fund_open_fund_info_em(symbol=fund_code)
            if not fund_info.empty:
                return fund_info.iloc[0]
        except:
            pass
        
        return pd.Series({'基金代码': fund_code, '基金简称': '未知基金'})
    except Exception as e:
        return pd.Series({'基金代码': fund_code, '基金简称': f'获取失败: {str(e)[:30]}'})

def get_fund_holding(fund_code):
    """获取基金持仓数据"""
    cache_file = f'data/cache/holding_{fund_code}.json'
    cache_time = 3600  # 缓存1小时
    
    # 检查缓存
    if os.path.exists(cache_file):
        file_time = os.path.getmtime(cache_file)
        if time.time() - file_time < cache_time:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    
    try:
        # 获取持仓数据
        holding_df = ak.fund_portfolio_hold_em(symbol=fund_code, date="2024")
        
        if not holding_df.empty:
            # 清理数据
            holding_df = holding_df.copy()
            holding_df = holding_df[holding_df['占净值比例'] != '---']
            holding_df['占净值比例'] = pd.to_numeric(holding_df['占净值比例'], errors='coerce')
            holding_df = holding_df.dropna(subset=['占净值比例'])
            
            # 获取前十大持仓
            top10 = holding_df.nlargest(10, '占净值比例')
            
            result = {
                'fund_code': fund_code,
                'update_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'holdings': top10[['股票代码', '股票名称', '占净值比例', '持股数']].to_dict('records'),
                'total_weight': top10['占净值比例'].sum()
            }
            
            # 缓存结果
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            return result
    except Exception as e:
        st.error(f"获取持仓数据失败: {str(e)}")
    
    return None

def get_stock_real_time_data(stock_codes):
    """批量获取股票实时数据"""
    if not stock_codes:
        return {}
    
    try:
        # 获取A股实时数据
        stock_data = ak.stock_zh_a_spot_em()
        
        # 创建股票代码映射（去除前缀）
        code_mapping = {}
        for code in stock_codes:
            # 标准化股票代码格式
            if code.startswith('sh') or code.startswith('sz'):
                clean_code = code[2:]  # 去掉sh/sz前缀
            else:
                clean_code = code
            
            # 尝试匹配多种格式
            for stock_code in stock_data['代码'].unique():
                if stock_code.endswith(clean_code) or stock_code == clean_code:
                    code_mapping[code] = stock_code
                    break
        
        result = {}
        for original_code, matched_code in code_mapping.items():
            stock_info = stock_data[stock_data['代码'] == matched_code]
            if not stock_info.empty:
                info = stock_info.iloc[0]
                result[original_code] = {
                    'name': info['名称'],
                    'current': info['最新价'],
                    'change_percent': info['涨跌幅'],
                    'change_amount': info['涨跌额'],
                    'volume': info['成交量'],
                    'amount': info['成交额']
                }
        
        return result
    except Exception as e:
        st.error(f"获取股票数据失败: {str(e)}")
        return {}

def calculate_fund_estimated_change(fund_code):
    """计算基金估算涨跌幅"""
    # 获取持仓数据
    holding_data = get_fund_holding(fund_code)
    
    if not holding_data or 'holdings' not in holding_data:
        return None, None
    
    holdings = holding_data['holdings']
    if not holdings:
        return None, None
    
    # 提取股票代码
    stock_codes = [h['股票代码'] for h in holdings if h.get('股票代码')]
    
    # 获取股票实时数据
    stock_data = get_stock_real_time_data(stock_codes)
    
    if not stock_data:
        return None, None
    
    # 计算加权涨跌幅
    total_change = 0
    valid_count = 0
    
    for holding in holdings:
        stock_code = holding.get('股票代码')
        weight = holding.get('占净值比例', 0)
        
        if stock_code and stock_code in stock_data and weight > 0:
            stock_info = stock_data[stock_code]
            change_percent = stock_info.get('change_percent', 0)
            
            # 计算贡献度
            contribution = weight * change_percent / 100
            total_change += contribution
            valid_count += 1
    
    if valid_count == 0:
        return None, None
    
    # 估算总涨跌幅（假设其他持仓涨跌幅为0或市场平均）
    estimated_change = total_change
    
    return {
        'estimated_change': round(estimated_change, 4),
        'holding_data': holding_data,
        'stock_data': stock_data,
        'calculation_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

def search_fund(keyword):
    """搜索基金"""
    try:
        # 如果是纯数字，按代码搜索
        if keyword.isdigit():
            # 直接尝试获取该基金信息
            fund_info = get_fund_basic_info(keyword)
            if not fund_info.empty:
                return pd.DataFrame([{
                    '基金代码': keyword,
                    '基金简称': fund_info.get('基金简称', '未知'),
                    '类型': fund_info.get('基金类型', '未知'),
                    '成立日期': fund_info.get('成立日期', '未知'),
                    '规模(亿元)': fund_info.get('最新规模', '未知')
                }])
        
        # 按名称搜索
        try:
            search_result = ak.fund_name_em()
            if not search_result.empty:
                filtered = search_result[search_result['基金简称'].str.contains(keyword, case=False, na=False)]
                return filtered.head(20)
        except:
            pass
        
        return pd.DataFrame()
    except Exception as e:
        st.error(f"搜索失败: {str(e)}")
        return pd.DataFrame()

# 侧边栏
with st.sidebar:
    st.title("📊 基金跟踪系统")
    st.markdown("---")
    
    # 当前时间
    current_time = datetime.now()
    st.caption(f"🕐 更新时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if is_trading_day(current_time):
        st.success("✅ 当前为交易日")
    else:
        st.info("📅 当前为非交易日")
    
    st.markdown("---")
    
    # 添加基金
    st.subheader("添加基金")
    add_option = st.radio("添加方式", ["按代码添加", "搜索添加"], horizontal=True)
    
    if add_option == "按代码添加":
        new_code = st.text_input("输入基金代码（6位数字）", max_chars=6, key="add_by_code")
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
        search_keyword = st.text_input("搜索基金名称或代码", key="search_add")
        if search_keyword:
            with st.spinner("搜索中..."):
                search_results = search_fund(search_keyword)
                if not search_results.empty:
                    for idx, row in search_results.iterrows():
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.write(f"{row['基金简称']}")
                        with col2:
                            if st.button("添加", key=f"add_{row['基金代码']}"):
                                if row['基金代码'] not in st.session_state.fund_list:
                                    st.session_state.fund_list.append(row['基金代码'])
                                    with open('data/fund_list.json', 'w', encoding='utf-8') as f:
                                        json.dump(st.session_state.fund_list, f, ensure_ascii=False, indent=2)
                                    st.success(f"✅ 已添加: {row['基金简称']}")
                                    st.rerun()
    
    st.markdown("---")
    
    # 管理基金列表
    st.subheader("我的基金列表")
    
    if st.session_state.fund_list:
        for i, fund_code in enumerate(st.session_state.fund_list):
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.write(f"`{fund_code}`")
            with col2:
                if st.button("🔍", key=f"view_{i}"):
                    st.session_state.search_results = fund_code
            with col3:
                if st.button("🗑️", key=f"del_{i}"):
                    st.session_state.fund_list.pop(i)
                    with open('data/fund_list.json', 'w', encoding='utf-8') as f:
                        json.dump(st.session_state.fund_list, f, ensure_ascii=False, indent=2)
                    st.rerun()
    else:
        st.info("暂无基金，请先添加")
    
    st.markdown("---")
    
    # 导入导出功能
    st.subheader("数据管理")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("导出数据", use_container_width=True):
            if st.session_state.fund_list:
                # 导出为JSON
                json_str = json.dumps(st.session_state.fund_list, ensure_ascii=False, indent=2)
                st.download_button(
                    label="下载JSON文件",
                    data=json_str,
                    file_name=f"fund_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                    use_container_width=True
                )
            else:
                st.warning("暂无数据可导出")
    
    with col2:
        uploaded_file = st.file_uploader("导入数据", type=['json'], key="import_file")
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
    
    st.markdown("---")
    st.caption("💡 提示：基金数据有15分钟延迟")

# 主界面
st.title("📈 基金持仓跟踪与估算系统")

# 搜索功能
search_col1, search_col2 = st.columns([4, 1])
with search_col1:
    search_input = st.text_input(
        "搜索基金（代码或名称）",
        value=st.session_state.search_results if isinstance(st.session_state.search_results, str) else "",
        placeholder="输入基金代码或名称..."
    )
with search_col2:
    search_btn = st.button("搜索", type="primary", use_container_width=True)

if search_btn and search_input:
    with st.spinner("搜索中..."):
        st.session_state.search_results = search_fund(search_input)
elif st.session_state.search_results is not None and isinstance(st.session_state.search_results, pd.DataFrame):
    if not st.session_state.search_results.empty:
        st.write("### 搜索结果")
        st.dataframe(
            st.session_state.search_results,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("未找到相关基金")

# 显示基金详情
if st.session_state.search_results and isinstance(st.session_state.search_results, str):
    fund_code = st.session_state.search_results
    st.write(f"### 基金详情: `{fund_code}`")
    
    # 获取基金基本信息
    with st.spinner("获取基金信息中..."):
        fund_info = get_fund_basic_info(fund_code)
    
    if not fund_info.empty:
        # 基本信息卡片
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("基金代码", fund_code)
        with col2:
            st.metric("基金简称", fund_info.get('基金简称', '未知'))
        with col3:
            st.metric("基金类型", fund_info.get('基金类型', '未知'))
        with col4:
            st.metric("成立日期", str(fund_info.get('成立日期', '未知')))
    
    # 计算估算涨跌幅
    st.write("### 📊 实时估算")
    
    if is_trading_day():
        with st.spinner("计算实时估算涨跌幅中..."):
            calc_result = calculate_fund_estimated_change(fund_code)
        
        if calc_result:
            estimated_change = calc_result['estimated_change']
            holding_data = calc_result['holding_data']
            stock_data = calc_result['stock_data']
            
            # 显示估算结果
            delta_color = "normal"
            if estimated_change > 0:
                delta_color = "normal"
                change_icon = "📈"
            elif estimated_change < 0:
                delta_color = "inverse"
                change_icon = "📉"
            else:
                change_icon = "➡️"
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(
                    "估算涨跌幅",
                    f"{estimated_change:.2%}",
                    delta=f"{estimated_change:.2%}",
                    delta_color=delta_color
                )
            with col2:
                st.metric("计算时间", calc_result['calculation_time'])
            with col3:
                st.metric("持仓股票数", len(holding_data.get('holdings', [])))
            
            # 显示持仓详情
            st.write("### 🏦 前十大重仓股")
            if holding_data and 'holdings' in holding_data:
                holdings_df = pd.DataFrame(holding_data['holdings'])
                
                # 添加实时数据
                holdings_display = holdings_df.copy()
                holdings_display['实时涨跌幅'] = holdings_display['股票代码'].apply(
                    lambda x: f"{stock_data.get(x, {}).get('change_percent', 0):.2f}%" 
                    if x in stock_data else "N/A"
                )
                holdings_display['当前价'] = holdings_display['股票代码'].apply(
                    lambda x: stock_data.get(x, {}).get('current', 'N/A')
                )
                
                # 格式化显示
                holdings_display = holdings_display[[
                    '股票代码', '股票名称', '占净值比例', '持股数', '当前价', '实时涨跌幅'
                ]]
                holdings_display.columns = ['股票代码', '股票名称', '持仓比例%', '持股数(万股)', '当前价', '实时涨跌幅']
                
                st.dataframe(
                    holdings_display,
                    use_container_width=True,
                    hide_index=True
                )
                
                # 持仓比例饼图
                if not holdings_df.empty:
                    fig = go.Figure(data=[go.Pie(
                        labels=holdings_df['股票名称'] + ' (' + holdings_df['股票代码'] + ')',
                        values=holdings_df['占净值比例'],
                        hole=0.3
                    )])
                    fig.update_layout(
                        title='持仓比例分布',
                        height=400
                    )
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("未获取到持仓数据")
    else:
        st.info("📅 当前为非交易日，显示最新净值信息")
        
        try:
            # 获取最新净值
            nav_df = ak.fund_open_fund_info_em(symbol=fund_code)
            if not nav_df.empty and len(nav_df) > 0:
                latest_nav = nav_df.iloc[0]
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("单位净值", f"{latest_nav.get('单位净值', 0):.4f}")
                with col2:
                    st.metric("累计净值", f"{latest_nav.get('累计净值', 0):.4f}")
                with col3:
                    date_str = latest_nav.get('净值日期', '')
                    st.metric("净值日期", date_str)
                
                # 显示净值走势
                if len(nav_df) > 1:
                    nav_df['净值日期'] = pd.to_datetime(nav_df['净值日期'])
                    nav_df = nav_df.sort_values('净值日期')
                    
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=nav_df['净值日期'],
                        y=nav_df['单位净值'],
                        mode='lines+markers',
                        name='单位净值',
                        line=dict(color='blue')
                    ))
                    fig.update_layout(
                        title='单位净值走势',
                        xaxis_title='日期',
                        yaxis_title='单位净值',
                        height=400
                    )
                    st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"获取净值信息失败: {str(e)}")

# 批量更新自选基金
if st.session_state.fund_list and is_trading_day():
    st.write("### 🚀 批量更新自选基金")
    
    if st.button("一键更新所有基金估算", type="primary"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        results = []
        
        for i, fund_code in enumerate(st.session_state.fund_list):
            status_text.text(f"正在处理: {fund_code} ({i+1}/{len(st.session_state.fund_list)})")
            
            try:
                calc_result = calculate_fund_estimated_change(fund_code)
                if calc_result:
                    results.append({
                        '基金代码': fund_code,
                        '估算涨跌幅': f"{calc_result['estimated_change']:.2%}",
                        '更新时间': calc_result['calculation_time']
                    })
            except Exception as e:
                results.append({
                    '基金代码': fund_code,
                    '估算涨跌幅': f"错误: {str(e)[:20]}",
                    '更新时间': datetime.now().strftime('%H:%M:%S')
                })
            
            progress_bar.progress((i + 1) / len(st.session_state.fund_list))
        
        if results:
            results_df = pd.DataFrame(results)
            st.dataframe(results_df, use_container_width=True, hide_index=True)
            
            # 提供下载
            csv = results_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 下载结果 (CSV)",
                data=csv,
                file_name=f"fund_estimates_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )

# 页脚
st.markdown("---")
st.caption("""
**免责声明**: 本系统数据仅供参考，估算涨跌幅基于前十大重仓股实时数据计算，与实际净值可能存在差异。投资有风险，入市需谨慎。
""")
