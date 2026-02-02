import streamlit as st
import pandas as pd
import numpy as np
import akshare as ak
import json
import os
import time
from datetime import datetime
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

def get_fund_latest_nav(fund_code):
    """获取基金最新净值（不判断时间）"""
    try:
        # 方法1：获取基金历史净值
        nav_data = ak.fund_open_fund_info_em(symbol=fund_code)
        if not nav_data.empty and len(nav_data) > 0:
            # 获取最新净值（第一行）
            latest = nav_data.iloc[0]
            
            # 提取净值
            nav_value = None
            nav_date = None
            
            # 净值
            for nav_col in ['单位净值', '净值', 'value']:
                if nav_col in latest and latest[nav_col] not in [None, '', np.nan, '']:
                    try:
                        nav_value = float(latest[nav_col])
                        if nav_value != 1.0:  # 排除默认值
                            break
                    except:
                        continue
            
            # 日期
            for date_col in ['净值日期', '日期', 'date']:
                if date_col in latest and latest[date_col] not in [None, '', np.nan, '']:
                    nav_date = str(latest[date_col])
                    break
            
            if nav_value is not None:
                return {
                    'type': 'nav',
                    'value': nav_value,
                    'date': nav_date if nav_date else '',
                    'update_time': get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')
                }
        
        return None
    except Exception as e:
        return None

def get_fund_holdings(fund_code):
    """获取基金持仓数据"""
    try:
        # 方法1：获取基金持仓
        holdings = ak.fund_em_portfolio_hold(fund=fund_code)
        if not holdings.empty:
            # 只取前十大持仓
            holdings = holdings.head(10)
            
            # 清理数据
            clean_holdings = []
            for _, row in holdings.iterrows():
                # 提取股票代码
                stock_code = str(row.get('股票代码', '')).strip()
                if not stock_code or stock_code == 'nan':
                    continue
                
                # 提取持仓比例
                weight_str = str(row.get('占净值比例', '0')).replace('%', '').strip()
                try:
                    weight = float(weight_str)
                except:
                    weight = 0.0
                
                # 提取股票名称
                stock_name = str(row.get('股票名称', '')).strip()
                
                if stock_code and stock_name and weight > 0:
                    clean_holdings.append({
                        '股票代码': stock_code,
                        '股票名称': stock_name,
                        '占净值比例': weight
                    })
            
            return clean_holdings
        return []
    except Exception as e:
        return []

def get_stock_real_time_change(stock_code):
    """获取股票实时涨跌幅"""
    try:
        # 标准化股票代码
        clean_code = str(stock_code).strip()
        
        # 判断是沪市还是深市
        if clean_code.startswith('6'):
            market_code = f"sh{clean_code}"
        elif clean_code.startswith('0') or clean_code.startswith('3'):
            market_code = f"sz{clean_code}"
        else:
            market_code = clean_code
        
        # 方法1：获取A股实时数据
        try:
            stock_data = ak.stock_zh_a_spot_em()
            if not stock_data.empty:
                # 查找股票
                for _, row in stock_data.iterrows():
                    market_code_str = str(row['代码']).strip()
                    if market_code_str == market_code or market_code_str.endswith(clean_code):
                        # 获取涨跌幅
                        change_str = str(row.get('涨跌幅', '0')).replace('%', '').strip()
                        try:
                            change = float(change_str)
                            return {
                                'change': change,
                                'price': float(row.get('最新价', 0)),
                                'name': row.get('名称', '')
                            }
                        except:
                            pass
        except:
            pass
        
        # 方法2：备用接口
        try:
            stock_data = ak.stock_zh_a_spot(symbol=market_code)
            if not stock_data.empty and len(stock_data) > 0:
                row = stock_data.iloc[0]
                change_str = str(row.get('涨跌幅', '0')).replace('%', '').strip()
                try:
                    change = float(change_str)
                    return {
                        'change': change,
                        'price': float(row.get('最新价', 0)),
                        'name': row.get('名称', '')
                    }
                except:
                    pass
        except:
            pass
        
        return None
    except Exception as e:
        return None

def calculate_fund_estimated_value(fund_code):
    """通过持仓计算基金估算净值"""
    try:
        # 1. 获取基金持仓
        holdings = get_fund_holdings(fund_code)
        if not holdings:
            return None
        
        # 2. 获取基金最新净值作为基数
        nav_data = get_fund_latest_nav(fund_code)
        if not nav_data:
            return None
        
        base_value = nav_data['value']
        base_date = nav_data.get('date', '')
        
        # 3. 获取持仓股票的实时涨跌幅
        stock_changes = []
        total_weight = 0
        
        for holding in holdings:
            stock_code = holding.get('股票代码')
            weight = holding.get('占净值比例', 0)
            
            if stock_code and weight > 0:
                stock_data = get_stock_real_time_change(stock_code)
                if stock_data and 'change' in stock_data:
                    stock_changes.append({
                        'code': stock_code,
                        'name': holding.get('股票名称', ''),
                        'weight': weight,
                        'change': stock_data['change']
                    })
                    total_weight += weight
        
        if not stock_changes:
            return None
        
        # 4. 计算加权平均涨跌幅
        weighted_change = sum(item['change'] * item['weight'] for item in stock_changes) / total_weight
        
        # 5. 计算估算净值
        estimated_value = base_value * (1 + weighted_change / 100)
        
        return {
            'type': 'calculated',
            'value': estimated_value,
            'change': weighted_change,
            'base_value': base_value,
            'base_date': base_date,
            'stock_count': len(stock_changes),
            'total_weight': total_weight,
            'update_time': get_beijing_time().strftime('%Y-%m-%d %H:%M:%S'),
            'source': '持仓计算'
        }
        
    except Exception as e:
        return None

def get_fund_real_time_estimation(fund_code):
    """获取基金实时估算数据"""
    try:
        # 方法1：尝试获取基金实时估算数据
        try:
            est_data = ak.fund_value_estimation_em(symbol=fund_code)
            if not est_data.empty and len(est_data) > 0:
                # 找到最新的估算数据
                for _, row in est_data.iterrows():
                    # 检查是否有估算数据
                    estimated_value = None
                    estimated_change = None
                    
                    # 提取估算净值
                    for val_col in ['估算净值', '估算值', 'estimated_value']:
                        if val_col in row and row[val_col] not in [None, '', np.nan, '']:
                            try:
                                estimated_value = float(row[val_col])
                                if estimated_value != 1.0:  # 排除默认值
                                    break
                            except:
                                continue
                    
                    # 提取涨跌幅
                    for chg_col in ['估算涨跌幅', '涨跌幅', 'change_percent']:
                        if chg_col in row and row[chg_col] not in [None, '', np.nan, '']:
                            chg_str = str(row[chg_col])
                            chg_str = chg_str.replace('%', '').replace(' ', '').strip()
                            try:
                                estimated_change = float(chg_str)
                            except:
                                pass
                            break
                    
                    if estimated_value is not None and estimated_value != 1.0:
                        return {
                            'type': 'real_time',
                            'value': estimated_value,
                            'change': estimated_change if estimated_change is not None else 0,
                            'update_time': get_beijing_time().strftime('%Y-%m-%d %H:%M:%S'),
                            'source': '实时估算'
                        }
        except:
            pass
        
        # 方法2：通过持仓计算估算值
        calculated_data = calculate_fund_estimated_value(fund_code)
        if calculated_data:
            return calculated_data
        
        # 方法3：返回最新净值
        nav_data = get_fund_latest_nav(fund_code)
        if nav_data:
            nav_data['source'] = '最新净值'
            return nav_data
        
        return None
    except Exception as e:
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
    st.caption("💡 实时数据，系统时间: " + beijing_time.strftime('%Y-%m-%d %H:%M:%S'))

# 主界面
st.title("📈 基金持仓跟踪与估算系统")

# 搜索功能区
st.subheader("🔍 搜索基金")
search_col1, search_col2 = st.columns([3, 1])
with search_col1:
    search_keyword = st.text_input("输入基金名称或代码", key="search_main", placeholder="如：招商中证白酒指数")
with search_col2:
    search_btn = st.button("搜索", type="primary", use_container_width=True)

if search_btn and search_keyword:
    with st.spinner("搜索中..."):
        search_results = search_funds(search_keyword)
        if not search_results.empty:
            st.subheader(f"搜索结果 ({len(search_results)}个)")
            for idx, row in search_results.iterrows():
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.write(f"**{row['基金简称']}**")
                    st.caption(f"代码: `{row['基金代码']}` | 类型: {row['基金类型']}")
                with col2:
                    if st.button("➕ 添加", key=f"add_{row['基金代码']}_main"):
                        if row['基金代码'] not in st.session_state.fund_list:
                            st.session_state.fund_list.append(row['基金代码'])
                            with open('data/fund_list.json', 'w', encoding='utf-8') as f:
                                json.dump(st.session_state.fund_list, f, ensure_ascii=False, indent=2)
                            st.success(f"✅ 已添加: {row['基金简称']}")
                            st.rerun()
                with col3:
                    if st.button("📊 查看", key=f"view_{row['基金代码']}_main"):
                        st.session_state.selected_fund = row['基金代码']
        else:
            st.info("未找到相关基金")

# 基金列表展示
st.subheader(f"📊 基金实时数据 ({len(st.session_state.fund_list)}个)")

if st.session_state.fund_list:
    # 刷新按钮
    col_refresh, col_clear = st.columns([1, 1])
    with col_refresh:
        if st.button("🔄 刷新数据", type="primary", use_container_width=True):
            st.rerun()
    with col_clear:
        if st.button("🗑️ 清空列表", type="secondary", use_container_width=True):
            st.session_state.fund_list = []
            with open('data/fund_list.json', 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            st.rerun()
    
    # 显示基金数据
    for fund_code in st.session_state.fund_list:
        with st.container():
            st.markdown("---")
            
            # 获取基金基本信息
            fund_info = get_fund_basic_info(fund_code)
            
            # 获取实时数据
            with st.spinner(f"获取 {fund_code} 数据中..."):
                real_time_data = get_fund_real_time_estimation(fund_code)
            
            col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
            
            with col1:
                st.markdown(f"### {fund_info['name']}")
                st.caption(f"代码: `{fund_code}` | 类型: {fund_info['type']}")
            
            with col2:
                if real_time_data:
                    value = real_time_data.get('value', 0)
                    change = real_time_data.get('change', 0)
                    
                    # 显示数值
                    st.metric(
                        label="估算净值" if real_time_data.get('type') in ['real_time', 'calculated'] else "单位净值",
                        value=f"{value:.4f}",
                        delta=f"{change:+.2f}%" if change != 0 else None,
                        delta_color="normal" if change == 0 else ("inverse" if change < 0 else "normal")
                    )
                else:
                    st.metric(label="数据", value="获取失败", delta=None)
            
            with col3:
                if real_time_data:
                    source = real_time_data.get('source', '未知')
                    update_time = real_time_data.get('update_time', '')
                    
                    st.caption(f"**数据来源**: {source}")
                    st.caption(f"**更新时间**: {update_time}")
                    
                    if real_time_data.get('type') == 'calculated':
                        stock_count = real_time_data.get('stock_count', 0)
                        total_weight = real_time_data.get('total_weight', 0)
                        base_date = real_time_data.get('base_date', '')
                        
                        st.caption(f"**计算依据**: {stock_count}只股票，权重{total_weight:.1f}%")
                        if base_date:
                            st.caption(f"**基准净值日期**: {base_date}")
                else:
                    st.caption("**状态**: 数据获取失败")
            
            with col4:
                if st.button("🗑️", key=f"del_{fund_code}_main"):
                    if fund_code in st.session_state.fund_list:
                        st.session_state.fund_list.remove(fund_code)
                        with open('data/fund_list.json', 'w', encoding='utf-8') as f:
                            json.dump(st.session_state.fund_list, f, ensure_ascii=False, indent=2)
                        st.success(f"已删除基金: {fund_code}")
                        st.rerun()
    
    # 显示选中的基金详情
    if st.session_state.get('selected_fund'):
        st.markdown("---")
        st.subheader(f"📋 {st.session_state.selected_fund} 详情")
        
        selected_fund = st.session_state.selected_fund
        fund_info = get_fund_basic_info(selected_fund)
        
        # 获取持仓数据
        holdings = get_fund_holdings(selected_fund)
        
        if holdings:
            st.write(f"**前十大持仓 ({len(holdings)}只)**")
            
            # 创建持仓表格
            holdings_df = pd.DataFrame(holdings)
            
            # 获取股票实时数据
            stock_data_list = []
            for holding in holdings:
                stock_code = holding.get('股票代码')
                stock_name = holding.get('股票名称')
                weight = holding.get('占净值比例', 0)
                
                stock_data = get_stock_real_time_change(stock_code)
                if stock_data:
                    stock_data_list.append({
                        '股票代码': stock_code,
                        '股票名称': stock_name,
                        '持仓比例': f"{weight:.2f}%",
                        '实时涨跌幅': f"{stock_data.get('change', 0):+.2f}%",
                        '最新价': stock_data.get('price', 0)
                    })
                else:
                    stock_data_list.append({
                        '股票代码': stock_code,
                        '股票名称': stock_name,
                        '持仓比例': f"{weight:.2f}%",
                        '实时涨跌幅': "获取失败",
                        '最新价': "-"
                    })
            
            if stock_data_list:
                stock_df = pd.DataFrame(stock_data_list)
                st.dataframe(stock_df, use_container_width=True)
                
                # 计算加权平均涨跌幅
                total_weight = sum(float(item['持仓比例'].replace('%', '')) for item in stock_data_list if item['实时涨跌幅'] != '获取失败')
                if total_weight > 0:
                    weighted_change = sum(
                        float(item['持仓比例'].replace('%', '')) * float(item['实时涨跌幅'].replace('%', '').replace('+', '')) 
                        for item in stock_data_list if item['实时涨跌幅'] not in ['获取失败', '-']
                    ) / total_weight
                    
                    st.info(f"**持仓加权平均涨跌幅**: {weighted_change:+.2f}% (基于{len([x for x in stock_data_list if x['实时涨跌幅'] != '获取失败'])}只股票)")
        else:
            st.info("暂无持仓数据")
        
        # 关闭详情按钮
        if st.button("关闭详情", key="close_detail"):
            st.session_state.selected_fund = None
            st.rerun()
else:
    st.info("暂无基金数据，请在侧边栏添加基金")

# 底部信息
st.markdown("---")
st.caption("💡 **系统说明**: 本系统直接获取实时数据，不进行交易日判断。数据来源包括实时估算接口和持仓计算。")
st.caption(f"🕐 **当前系统时间**: {get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')}")
