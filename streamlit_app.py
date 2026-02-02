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
warnings.filterwarnings('ignore')

# 设置时区为北京时间
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# 页面配置
st.set_page_config(
    page_title="基金持仓跟踪与估算系统",
    page_icon="📈",
    layout="wide"
)

# 设置中文字体
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&display=swap');
* {
    font-family: 'Noto Sans SC', sans-serif;
}
</style>
""", unsafe_allow_html=True)

# 获取北京时间
def get_beijing_time():
    return datetime.now(BEIJING_TZ)

# 初始化session_state
if 'fund_list' not in st.session_state:
    st.session_state.fund_list = []

# 创建数据目录
os.makedirs('data', exist_ok=True)

# ====================== 核心数据获取函数 ======================
def get_fund_basic_info(fund_code):
    """获取基金基本信息"""
    try:
        # 方法1：使用基金列表接口
        fund_list = ak.fund_name_em()
        if not fund_list.empty:
            fund_info = fund_list[fund_list['基金代码'] == fund_code]
            if not fund_info.empty:
                return {
                    'code': fund_code,
                    'name': fund_info.iloc[0]['基金简称'],
                    'type': fund_info.iloc[0]['基金类型']
                }
        
        # 方法2：使用基金基本信息接口
        try:
            basic_info = ak.fund_open_fund_info_em(symbol=fund_code, indicator="基本信息")
            if not basic_info.empty:
                return {
                    'code': fund_code,
                    'name': basic_info.iloc[0]['基金简称'] if '基金简称' in basic_info else f"基金{fund_code}",
                    'type': basic_info.iloc[0]['基金类型'] if '基金类型' in basic_info else '未知'
                }
        except:
            pass
        
        return {
            'code': fund_code,
            'name': f"基金{fund_code}",
            'type': '未知'
        }
    except Exception as e:
        return {
            'code': fund_code,
            'name': f"基金{fund_code}",
            'type': '未知'
        }

def get_fund_holdings_simple(fund_code):
    """获取基金持仓数据 - 简化版本"""
    try:
        # 使用正确的接口获取持仓
        holdings = ak.fund_portfolio_hold_em(symbol=fund_code)
        
        if holdings.empty:
            return []
        
        # 获取最新季度的数据
        if '季度' in holdings.columns:
            latest_quarter = holdings['季度'].max()
            holdings = holdings[holdings['季度'] == latest_quarter]
        
        # 只取前十大持仓
        holdings = holdings.head(10)
        
        # 清理数据
        clean_data = []
        for _, row in holdings.iterrows():
            stock_code = str(row.get('股票代码', '')).strip()
            stock_name = str(row.get('股票名称', '')).strip()
            
            # 提取持仓比例
            weight_str = str(row.get('占净值比例', '0')).replace('%', '').strip()
            try:
                weight = float(weight_str)
            except:
                weight = 0.0
            
            if stock_code and stock_code != 'nan' and weight > 0:
                clean_data.append({
                    '股票代码': stock_code,
                    '股票名称': stock_name,
                    '占净值比例': weight
                })
        
        return clean_data
    except Exception as e:
        return []

def get_stock_real_time_data(stock_code):
    """获取股票实时数据"""
    try:
        # 标准化股票代码
        code_str = str(stock_code).strip()
        
        # 获取A股实时数据
        all_stocks = ak.stock_zh_a_spot_em()
        
        if all_stocks.empty:
            return None
        
        # 查找股票
        for _, row in all_stocks.iterrows():
            current_code = str(row['代码']).strip()
            
            # 匹配逻辑：直接匹配或去掉市场前缀匹配
            if (current_code == code_str or 
                current_code.endswith(code_str) or
                current_code.replace('sh', '').replace('sz', '') == code_str):
                
                # 提取涨跌幅
                change_str = str(row.get('涨跌幅', '0')).replace('%', '').strip()
                try:
                    change = float(change_str)
                except:
                    change = 0.0
                
                # 提取最新价
                price_str = str(row.get('最新价', '0')).strip()
                try:
                    price = float(price_str)
                except:
                    price = 0.0
                
                return {
                    '代码': code_str,
                    '名称': row.get('名称', ''),
                    '涨跌幅': change,
                    '最新价': price,
                    '更新时间': get_beijing_time().strftime('%H:%M:%S')
                }
        
        return None
    except Exception as e:
        return None

def get_fund_latest_nav(fund_code):
    """获取基金最新净值"""
    try:
        nav_data = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
        
        if nav_data.empty or len(nav_data) == 0:
            return None
        
        # 获取最新净值
        latest = nav_data.iloc[0]
        
        # 提取净值
        nav_value = None
        nav_date = None
        
        for col in ['单位净值', '净值']:
            if col in latest and latest[col] not in [None, '', np.nan]:
                try:
                    nav_value = float(latest[col])
                    break
                except:
                    continue
        
        # 提取日期
        for col in ['净值日期', '日期']:
            if col in latest and latest[col] not in [None, '', np.nan]:
                nav_date = str(latest[col])
                break
        
        if nav_value is not None:
            return {
                'value': nav_value,
                'date': nav_date,
                'type': 'nav'
            }
        
        return None
    except Exception as e:
        return None

def calculate_fund_estimation(fund_code):
    """通过持仓计算基金估算净值"""
    try:
        # 1. 获取持仓
        holdings = get_fund_holdings_simple(fund_code)
        if not holdings:
            return None
        
        # 2. 获取最新净值作为基数
        nav_data = get_fund_latest_nav(fund_code)
        if not nav_data:
            return None
        
        base_value = nav_data['value']
        base_date = nav_data.get('date', '')
        
        # 3. 获取股票实时涨跌幅
        stock_changes = []
        total_weight = 0
        
        for holding in holdings:
            stock_code = holding['股票代码']
            weight = holding['占净值比例']
            
            stock_data = get_stock_real_time_data(stock_code)
            if stock_data and '涨跌幅' in stock_data:
                stock_changes.append({
                    '代码': stock_code,
                    '名称': holding['股票名称'],
                    '权重': weight,
                    '涨跌幅': stock_data['涨跌幅']
                })
                total_weight += weight
        
        if not stock_changes or total_weight == 0:
            return None
        
        # 4. 计算加权平均涨跌幅
        weighted_change = sum(item['涨跌幅'] * item['权重'] for item in stock_changes) / total_weight
        
        # 5. 计算估算净值
        estimated_value = base_value * (1 + weighted_change / 100)
        
        return {
            '估算净值': estimated_value,
            '涨跌幅': weighted_change,
            '基准净值': base_value,
            '基准日期': base_date,
            '持仓数量': len(stock_changes),
            '总权重': total_weight,
            '更新时间': get_beijing_time().strftime('%Y-%m-%d %H:%M:%S'),
            '数据来源': '持仓加权计算'
        }
        
    except Exception as e:
        return None

# ====================== 界面部分 ======================
st.title("📈 基金持仓跟踪与估算系统")

# 显示系统时间
beijing_time = get_beijing_time()
st.caption(f"🕐 系统时间: {beijing_time.strftime('%Y-%m-%d %H:%M:%S')}")

# 添加基金
st.subheader("➕ 添加基金")
col1, col2 = st.columns([3, 1])
with col1:
    new_code = st.text_input("输入基金代码（6位数字）", placeholder="如：005827", max_chars=6)
with col2:
    if st.button("添加", type="primary", use_container_width=True):
        if new_code and len(new_code) == 6 and new_code.isdigit():
            if new_code not in st.session_state.fund_list:
                st.session_state.fund_list.append(new_code)
                st.success(f"✅ 已添加基金: {new_code}")
                st.rerun()
            else:
                st.warning("基金已在列表中")
        else:
            st.error("请输入6位数字基金代码")

# 基金列表
st.subheader(f"📊 基金列表 ({len(st.session_state.fund_list)}个)")

if st.session_state.fund_list:
    # 刷新按钮
    if st.button("🔄 刷新所有数据", type="secondary"):
        st.rerun()
    
    # 显示基金数据
    for fund_code in st.session_state.fund_list:
        with st.container():
            st.markdown("---")
            
            # 获取基本信息
            fund_info = get_fund_basic_info(fund_code)
            
            # 获取估算数据
            with st.spinner(f"计算 {fund_code} 估算值..."):
                estimation = calculate_fund_estimation(fund_code)
            
            col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
            
            with col1:
                st.markdown(f"**{fund_info['name']}**")
                st.caption(f"代码: `{fund_code}` | 类型: {fund_info['type']}")
            
            with col2:
                if estimation:
                    value = estimation['估算净值']
                    change = estimation['涨跌幅']
                    
                    # 显示数值
                    st.metric(
                        label="估算净值",
                        value=f"{value:.4f}",
                        delta=f"{change:+.2f}%" if change != 0 else None,
                        delta_color="normal" if change == 0 else ("inverse" if change < 0 else "normal")
                    )
                else:
                    st.metric(label="估算净值", value="计算失败", delta=None)
            
            with col3:
                if estimation:
                    st.caption(f"**基准净值**: {estimation['基准净值']:.4f}")
                    st.caption(f"**基准日期**: {estimation['基准日期']}")
                    st.caption(f"**持仓数量**: {estimation['持仓数量']}只")
                    st.caption(f"**更新时间**: {estimation['更新时间']}")
                else:
                    st.caption("数据获取失败")
            
            with col4:
                if st.button("🗑️", key=f"del_{fund_code}"):
                    st.session_state.fund_list.remove(fund_code)
                    st.success(f"已删除基金: {fund_code}")
                    st.rerun()
            
            # 显示持仓详情
            if estimation and estimation.get('持仓数量', 0) > 0:
                with st.expander("查看持仓详情"):
                    # 获取持仓数据
                    holdings = get_fund_holdings_simple(fund_code)
                    if holdings:
                        # 获取实时数据
                        holdings_with_data = []
                        for holding in holdings:
                            stock_data = get_stock_real_time_data(holding['股票代码'])
                            if stock_data:
                                holdings_with_data.append({
                                    '股票代码': holding['股票代码'],
                                    '股票名称': holding['股票名称'],
                                    '持仓比例': holding['占净值比例'],
                                    '实时涨跌幅': stock_data['涨跌幅'],
                                    '最新价': stock_data['最新价']
                                })
                        
                        if holdings_with_data:
                            df = pd.DataFrame(holdings_with_data)
                            st.dataframe(df, use_container_width=True)
                            
                            # 显示计算说明
                            st.caption(f"**计算说明**: 基于{len(holdings_with_data)}只持仓股票，总权重{estimation['总权重']:.1f}%，加权计算得出估算净值")
                    else:
                        st.info("暂无持仓数据")
else:
    st.info("暂无基金，请先添加基金代码")

# 数据管理
st.subheader("📁 数据管理")
col_import, col_export = st.columns(2)

with col_import:
    if st.button("导入数据", use_container_width=True):
        uploaded_file = st.file_uploader("选择JSON文件", type=['json'], key="import_file")
        if uploaded_file is not None:
            try:
                import_data = json.load(uploaded_file)
                if isinstance(import_data, list):
                    st.session_state.fund_list = import_data
                    st.success("✅ 数据导入成功")
                    st.rerun()
            except:
                st.error("导入失败")

with col_export:
    if st.session_state.fund_list:
        json_str = json.dumps(st.session_state.fund_list, ensure_ascii=False, indent=2)
        st.download_button(
            label="导出数据",
            data=json_str,
            file_name=f"fund_list_{beijing_time.strftime('%Y%m%d')}.json",
            mime="application/json",
            use_container_width=True
        )
    else:
        st.button("导出数据", disabled=True, use_container_width=True)

# 调试信息
with st.expander("调试信息"):
    st.write("当前基金列表:", st.session_state.fund_list)
    st.write("系统时间:", beijing_time.strftime('%Y-%m-%d %H:%M:%S'))
    
    # 测试接口
    if st.button("测试接口"):
        test_code = "005827"  # 易方达蓝筹精选
        st.write("测试基金代码:", test_code)
        
        # 测试持仓接口
        st.write("测试持仓接口...")
        holdings = get_fund_holdings_simple(test_code)
        st.write("持仓数据:", holdings)
        
        # 测试股票实时数据
        if holdings:
            stock_code = holdings[0]['股票代码']
            st.write(f"测试股票 {stock_code} 实时数据...")
            stock_data = get_stock_real_time_data(stock_code)
            st.write("股票实时数据:", stock_data)
        
        # 测试净值接口
        st.write("测试净值接口...")
        nav_data = get_fund_latest_nav(test_code)
        st.write("净值数据:", nav_data)
