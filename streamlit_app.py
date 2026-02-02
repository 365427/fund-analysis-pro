import streamlit as st
import pandas as pd
import numpy as np
import akshare as ak
import json
import os
import time
from datetime import datetime, timedelta
import plotly.graph_objects as go
import requests
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
/* 美化卡片样式 */
.stMetric {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 10px;
    padding: 15px;
    color: white !important;
}
/* 侧边栏按钮美化 */
.stButton > button {
    width: 100%;
    border-radius: 8px;
    height: 40px;
    font-weight: 500;
}
/* 基金卡片样式 */
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

if 'fund_data_cache' not in st.session_state:
    st.session_state.fund_data_cache = {}

if 'search_results' not in st.session_state:
    st.session_state.search_results = None

# 创建必要的目录
os.makedirs('data/cache', exist_ok=True)

# 交易日判断函数
def is_trading_day(date=None):
    """判断是否为交易日"""
    if date is None:
        date = datetime.now()
    
    # 判断是否为周末
    if date.weekday() >= 5:
        return False
    
    # 获取交易日历
    try:
        trade_date = ak.tool_trade_date_hist_sina()
        if not trade_date.empty:
            trade_dates = trade_date['trade_date'].astype(str).tolist()
            return date.strftime('%Y%m%d') in trade_dates
    except:
        pass
    
    return True

def get_fund_basic_info(fund_code):
    """获取基金基本信息"""
    try:
        # 使用多个接口获取基金信息
        fund_name = "未知基金"
        fund_type = "未知"
        
        try:
            fund_info = ak.fund_em_info(fund=fund_code)
            if not fund_info.empty:
                fund_name = fund_info.iloc[0]['基金简称'] if '基金简称' in fund_info.columns else fund_name
                fund_type = fund_info.iloc[0]['基金类型'] if '基金类型' in fund_info.columns else fund_type
        except Exception as e:
            pass
        
        return {
            '基金代码': fund_code,
            '基金简称': fund_name,
            '基金类型': fund_type
        }
    except Exception as e:
        return {
            '基金代码': fund_code,
            '基金简称': f'基金{fund_code}',
            '基金类型': '未知'
        }

def safe_akshare_request(func, *args, **kwargs):
    """安全执行akshare请求，增加重试机制"""
    max_retries = 2
    for attempt in range(max_retries):
        try:
            result = func(*args, **kwargs)
            if result is not None and (isinstance(result, pd.DataFrame) and not result.empty):
                return result
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            time.sleep(1)  # 等待1秒后重试
    return None

def get_fund_holding(fund_code):
    """获取基金持仓数据"""
    cache_file = f'data/cache/holding_{fund_code}.json'
    cache_time = 3600  # 缓存1小时
    
    # 检查缓存
    if os.path.exists(cache_file):
        file_time = os.path.getmtime(cache_file)
        if time.time() - file_time < cache_time:
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
    
    try:
        # 尝试多种方式获取持仓数据
        holding_df = None
        
        # 方式1: 获取最新季报持仓
        try:
            holding_df = safe_akshare_request(ak.fund_portfolio_hold_em, symbol=fund_code)
        except:
            pass
        
        # 方式2: 备用接口
        if holding_df is None or holding_df.empty:
            try:
                holding_df = safe_akshare_request(ak.fund_em_portfolio_hold, fund=fund_code)
            except:
                pass
        
        if holding_df is not None and not holding_df.empty:
            # 清理数据
            holding_df = holding_df.copy()
            
            # 统一列名
            column_mapping = {
                '股票代码': ['股票代码', 'code'],
                '股票名称': ['股票名称', 'name'],
                '占净值比例': ['占净值比例', '占净值比例%', 'weight'],
                '持股数': ['持股数', '持股数(万股)']
            }
            
            for target_col, possible_cols in column_mapping.items():
                for col in possible_cols:
                    if col in holding_df.columns:
                        holding_df[target_col] = holding_df[col]
                        break
            
            # 确保有必要的列
            required_cols = ['股票代码', '股票名称', '占净值比例']
            for col in required_cols:
                if col not in holding_df.columns:
                    holding_df[col] = None
            
            # 清理比例数据
            if '占净值比例' in holding_df.columns:
                holding_df['占净值比例'] = holding_df['占净值比例'].astype(str).str.replace('%', '', regex=False)
                holding_df['占净值比例'] = pd.to_numeric(holding_df['占净值比例'], errors='coerce')
                holding_df = holding_df.dropna(subset=['占净值比例'])
            
            # 获取前十大持仓
            top10 = holding_df.nlargest(10, '占净值比例')
            
            result = {
                'fund_code': fund_code,
                'update_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'holdings': top10[['股票代码', '股票名称', '占净值比例']].to_dict('records'),
                'total_weight': top10['占净值比例'].sum()
            }
            
            # 缓存结果
            try:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
            except:
                pass
            
            return result
    except Exception as e:
        st.warning(f"获取持仓数据失败: {str(e)[:50]}")
    
    return None

def get_stock_real_time_data(stock_codes):
    """批量获取股票实时数据（优化版）"""
    if not stock_codes:
        return {}
    
    result = {}
    
    try:
        # 方法1: 使用东方财富接口
        try:
            stock_data = ak.stock_zh_a_spot_em()
            if not stock_data.empty:
                for code in stock_codes:
                    # 标准化股票代码
                    clean_code = str(code).replace('sh', '').replace('sz', '')
                    
                    # 尝试多种匹配方式
                    for _, row in stock_data.iterrows():
                        stock_code = str(row['代码'])
                        if (clean_code == stock_code or 
                            stock_code.endswith(clean_code) or 
                            f"sh{clean_code}" == stock_code or 
                            f"sz{clean_code}" == stock_code):
                            
                            result[code] = {
                                'name': row.get('名称', ''),
                                'current': float(row.get('最新价', 0)),
                                'change_percent': float(row.get('涨跌幅', 0)),
                                'change_amount': float(row.get('涨跌额', 0))
                            }
                            break
        except Exception as e:
            st.warning(f"股票接口1失败: {str(e)[:30]}")
        
        # 如果数据不足，尝试备用接口
        if len(result) < len(stock_codes) * 0.5:  # 获取不到一半的数据
            try:
                # 使用新浪接口
                for code in stock_codes:
                    if code not in result:
                        try:
                            stock_df = ak.stock_zh_a_spot(symbol=f"sh{code}" if code.startswith('6') else f"sz{code}")
                            if not stock_df.empty:
                                result[code] = {
                                    'name': stock_df.iloc[0]['name'],
                                    'current': float(stock_df.iloc[0]['price']),
                                    'change_percent': float(stock_df.iloc[0]['changepercent']),
                                    'change_amount': float(stock_df.iloc[0]['change'])
                                }
                        except:
                            continue
            except Exception as e:
                st.warning(f"股票接口2失败: {str(e)[:30]}")
    
    except Exception as e:
        st.error(f"获取股票数据失败，请检查网络连接: {str(e)[:100]}")
    
    return result

def calculate_fund_estimated_change(fund_code):
    """计算基金估算涨跌幅（优化版）"""
    try:
        # 获取持仓数据
        holding_data = get_fund_holding(fund_code)
        
        if not holding_data or 'holdings' not in holding_data:
            return None
        
        holdings = holding_data['holdings']
        if not holdings:
            return None
        
        # 提取股票代码（去重）
        stock_codes = []
        for h in holdings:
            stock_code = h.get('股票代码')
            if stock_code and stock_code not in stock_codes:
                stock_codes.append(stock_code)
        
        # 获取股票实时数据
        stock_data = get_stock_real_time_data(stock_codes)
        
        if not stock_data:
            return None
        
        # 计算加权涨跌幅
        total_change = 0
        total_weight = 0
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
                total_weight += weight
                valid_count += 1
        
        if valid_count == 0 or total_weight == 0:
            return None
        
        # 估算总涨跌幅（按实际持仓比例缩放）
        if total_weight > 0:
            estimated_change = total_change / total_weight * 100
        else:
            estimated_change = total_change
        
        return {
            'estimated_change': round(estimated_change, 4),
            'holding_data': holding_data,
            'stock_data': stock_data,
            'calculation_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'valid_stocks': valid_count,
            'total_weight': total_weight
        }
    except Exception as e:
        st.error(f"计算基金{fund_code}时出错: {str(e)}")
        return None

def search_fund(keyword):
    """搜索基金"""
    try:
        # 如果是纯数字，按代码搜索
        if keyword.isdigit():
            try:
                # 直接搜索基金
                search_df = ak.fund_em_fund_name()
                if not search_df.empty:
                    result = search_df[search_df['基金代码'].astype(str).str.contains(keyword, na=False)]
                    if not result.empty:
                        return result.head(10)
            except:
                pass
        
        # 按名称搜索
        try:
            search_df = ak.fund_em_fund_name()
            if not search_df.empty:
                result = search_df[search_df['基金简称'].str.contains(keyword, case=False, na=False)]
                return result.head(10)
        except:
            pass
        
        return pd.DataFrame()
    except Exception as e:
        st.error(f"搜索失败: {str(e)[:100]}")
        return pd.DataFrame()

# 侧边栏 - 重新设计布局
with st.sidebar:
    st.title("📊 基金跟踪系统")
    st.markdown("---")
    
    # 当前时间
    current_time = datetime.now()
    time_col1, time_col2 = st.columns(2)
    with time_col1:
        st.caption(f"🕐 更新时间")
    with time_col2:
        st.caption(f"{current_time.strftime('%H:%M:%S')}")
    
    if is_trading_day(current_time):
        st.success("✅ 当前为交易日")
    else:
        st.info("📅 当前为非交易日")
    
    st.markdown("---")
    
    # 数据管理 - 移到上部
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
                file_name=f"fund_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
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
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.warning("基金已在列表中")
            else:
                st.error("请输入6位数字基金代码")
    else:
        search_keyword = st.text_input("搜索基金名称或代码", key="search_add_sidebar")
        if search_keyword:
            with st.spinner("搜索中..."):
                search_results = search_fund(search_keyword)
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
                                    time.sleep(0.5)
                                    st.rerun()
    
    st.markdown("---")
    
    # 我的基金列表 - 优化显示
    st.subheader(f"📋 我的基金 ({len(st.session_state.fund_list)})")
    
    if st.session_state.fund_list:
        for i, fund_code in enumerate(st.session_state.fund_list):
            fund_info = get_fund_basic_info(fund_code)
            col1, col2, col3 = st.columns([4, 1, 1])
            with col1:
                st.write(f"**{fund_info['基金简称']}**")
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
                    time.sleep(0.5)
                    st.rerun()
    else:
        st.info("暂无基金，请先添加")
    
    st.markdown("---")
    st.caption("💡 基金数据有15分钟延迟")

# 主界面
st.title("📈 基金持仓跟踪与估算系统")

# 1. 搜索功能区
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
        search_result = search_fund(search_input)
        if not search_result.empty:
            st.session_state.search_results = search_result

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

# 2. 我的基金收藏展示区
if st.session_state.fund_list:
    st.markdown("---")
    st.subheader(f"⭐ 我的基金收藏 ({len(st.session_state.fund_list)})")
    
    # 创建选项卡：列表视图和卡片视图
    view_tab1, view_tab2 = st.tabs(["📊 卡片视图", "📋 列表视图"])
    
    with view_tab1:
        # 卡片视图
        cols = st.columns(3)
        fund_estimates = {}
        
        with st.spinner("正在计算估算涨跌幅..."):
            for idx, fund_code in enumerate(st.session_state.fund_list):
                col_idx = idx % 3
                with cols[col_idx]:
                    # 创建卡片
                    fund_info = get_fund_basic_info(fund_code)
                    
                    # 计算估算涨跌幅
                    if is_trading_day():
                        calc_result = calculate_fund_estimated_change(fund_code)
                        if calc_result:
                            change = calc_result['estimated_change']
                            fund_estimates[fund_code] = change
                            
                            # 根据涨跌设置卡片样式
                            card_class = "up" if change > 0 else ("down" if change < 0 else "flat")
                            
                            st.markdown(f"""
                            <div class="fund-card {card_class}">
                                <h4 style="margin:0;">{fund_info['基金简称']}</h4>
                                <p style="color:#666; font-size:0.9em; margin:5px 0;">{fund_code}</p>
                                <div style="display:flex; justify-content:space-between; align-items:center;">
                                    <span style="font-size:1.2em; font-weight:bold;">{fund_info['基金类型']}</span>
                                    <span style="font-size:1.5em; font-weight:bold; color:{"#4CAF50" if change > 0 else ("#F44336" if change < 0 else "#2196F3")}">
                                        {f"+{change:.2f}" if change > 0 else f"{change:.2f}"}%
                                    </span>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # 添加操作按钮
                            col_btn1, col_btn2 = st.columns(2)
                            with col_btn1:
                                if st.button("查看详情", key=f"detail_{fund_code}", use_container_width=True):
                                    st.session_state.selected_fund = fund_code
                            with col_btn2:
                                if st.button("刷新", key=f"refresh_{fund_code}", use_container_width=True):
                                    # 清除缓存
                                    cache_file = f'data/cache/holding_{fund_code}.json'
                                    if os.path.exists(cache_file):
                                        os.remove(cache_file)
                                    st.rerun()
                        else:
                            st.info(f"无法计算 {fund_code} 的估算值")
                    else:
                        st.info(f"{fund_code} - 非交易日")
    
    with view_tab2:
        # 列表视图
        list_data = []
        for fund_code in st.session_state.fund_list:
            fund_info = get_fund_basic_info(fund_code)
            if is_trading_day():
                calc_result = calculate_fund_estimated_change(fund_code)
                estimate = f"{calc_result['estimated_change']:.2f}%" if calc_result else "计算失败"
            else:
                estimate = "非交易日"
            
            list_data.append({
                "基金代码": fund_code,
                "基金简称": fund_info['基金简称'],
                "基金类型": fund_info['基金类型'],
                "估算涨跌幅": estimate
            })
        
        if list_data:
            list_df = pd.DataFrame(list_data)
            st.dataframe(
                list_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "基金代码": st.column_config.TextColumn("代码", width="small"),
                    "基金简称": st.column_config.TextColumn("名称"),
                    "基金类型": st.column_config.TextColumn("类型", width="small"),
                    "估算涨跌幅": st.column_config.TextColumn("估算", width="small")
                }
            )
            
            # 添加批量操作
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📥 导出列表为CSV", use_container_width=True):
                    csv = list_df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="点击下载",
                        data=csv,
                        file_name=f"my_funds_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        key="download_list_csv"
                    )
            with col2:
                if st.button("🔄 刷新所有数据", use_container_width=True):
                    # 清除所有缓存
                    for file in os.listdir('data/cache'):
                        if file.endswith('.json'):
                            os.remove(f'data/cache/{file}')
                    st.success("缓存已清除，正在重新计算...")
                    st.rerun()

# 3. 批量更新功能区
if st.session_state.fund_list and is_trading_day():
    st.markdown("---")
    st.subheader("🚀 批量更新")
    
    if st.button("🔄 一键更新所有基金估算", type="primary", use_container_width=True):
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
                        '基金简称': get_fund_basic_info(fund_code)['基金简称'],
                        '估算涨跌幅': f"{calc_result['estimated_change']:.2f}%",
                        '有效股票数': calc_result['valid_stocks'],
                        '更新时间': calc_result['calculation_time'][-8:]  # 只显示时间
                    })
                else:
                    results.append({
                        '基金代码': fund_code,
                        '基金简称': get_fund_basic_info(fund_code)['基金简称'],
                        '估算涨跌幅': "计算失败",
                        '有效股票数': 0,
                        '更新时间': datetime.now().strftime('%H:%M:%S')
                    })
            except Exception as e:
                error_msg = str(e)
                if "tuple" in error_msg and "indices" in error_msg:
                    error_msg = "数据处理错误，请稍后重试"
                elif "Connection" in error_msg:
                    error_msg = "网络连接失败，请检查网络"
                
                results.append({
                    '基金代码': fund_code,
                    '基金简称': get_fund_basic_info(fund_code)['基金简称'],
                    '估算涨跌幅': f"错误: {error_msg[:30]}",
                    '有效股票数': 0,
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
                mime="text/csv",
                use_container_width=True
            )

# 4. 基金详情展示
if st.session_state.get('selected_fund'):
    st.markdown("---")
    fund_code = st.session_state.selected_fund
    fund_info = get_fund_basic_info(fund_code)
    
    st.write(f"### 📊 基金详情: **{fund_info['基金简称']}** ({fund_code})")
    
    # 创建选项卡
    detail_tab1, detail_tab2 = st.tabs(["概览", "持仓详情"])
    
    with detail_tab1:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("基金代码", fund_code)
        with col2:
            st.metric("基金简称", fund_info['基金简称'])
        with col3:
            st.metric("基金类型", fund_info['基金类型'])
        with col4:
            st.metric("当前状态", "交易日" if is_trading_day() else "非交易日")
        
        # 计算并显示估算
        if is_trading_day():
            with st.spinner("计算中..."):
                calc_result = calculate_fund_estimated_change(fund_code)
            
            if calc_result:
                st.metric(
                    "估算涨跌幅",
                    f"{calc_result['estimated_change']:.2f}%",
                    delta=f"{calc_result['estimated_change']:.2f}%",
                    delta_color="normal" if calc_result['estimated_change'] >= 0 else "inverse"
                )
                st.caption(f"基于 {calc_result['valid_stocks']} 只重仓股计算 • 更新时间: {calc_result['calculation_time']}")
            else:
                st.warning("无法计算估算值")
        else:
            st.info("当前为非交易日，无法计算实时估算")
    
    with detail_tab2:
        if is_trading_day():
            calc_result = calculate_fund_estimated_change(fund_code)
            if calc_result and 'holding_data' in calc_result:
                holdings = calc_result['holding_data']['holdings']
                stock_data = calc_result['stock_data']
                
                if holdings:
                    # 显示持仓表格
                    holdings_display = []
                    for h in holdings:
                        stock_code = h.get('股票代码')
                        stock_info = stock_data.get(stock_code, {})
                        
                        holdings_display.append({
                            '股票代码': stock_code,
                            '股票名称': h.get('股票名称'),
                            '持仓比例%': f"{h.get('占净值比例', 0):.2f}",
                            '当前价格': stock_info.get('current', 'N/A'),
                            '涨跌幅%': f"{stock_info.get('change_percent', 0):.2f}" if stock_info else 'N/A',
                            '涨跌额': stock_info.get('change_amount', 'N/A') if stock_info else 'N/A'
                        })
                    
                    holdings_df = pd.DataFrame(holdings_display)
                    st.dataframe(holdings_df, use_container_width=True, hide_index=True)
                    
                    # 显示饼图
                    if len(holdings) > 0:
                        fig = go.Figure(data=[go.Pie(
                            labels=[f"{h['股票名称']}\n({h.get('占净值比例', 0):.1f}%)" for h in holdings],
                            values=[h.get('占净值比例', 0) for h in holdings],
                            hole=0.3
                        )])
                        fig.update_layout(
                            title='持仓比例分布',
                            height=400
                        )
                        st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("暂无持仓数据")
            else:
                st.warning("无法获取持仓详情")
        else:
            st.info("非交易日不显示持仓详情")

# 页脚
st.markdown("---")
st.caption("""
**免责声明**: 本系统数据仅供参考，估算涨跌幅基于前十大重仓股实时数据计算，与实际净值可能存在差异。投资有风险，入市需谨慎。
**数据来源**: 东方财富、新浪财经等公开数据接口
**更新时间**: 数据有15分钟延迟
""")

# 初始化session_state变量
if 'show_import' not in st.session_state:
    st.session_state.show_import = False
if 'show_export' not in st.session_state:
    st.session_state.show_export = False
if 'selected_fund' not in st.session_state:
    st.session_state.selected_fund = None
