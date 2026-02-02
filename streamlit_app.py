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
from dateutil import parser
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

# ====================== 交易日判断函数 ======================
class TradingDayChecker:
    """交易日判断类，解决错误判断问题"""
    
    def __init__(self):
        self.trade_dates = None
        self.last_update = None
        self.cache_file = 'data/cache/trade_dates.json'
        self.holidays_2024 = [
            '2024-01-01',  # 元旦
            '2024-02-10', '2024-02-11', '2024-02-12', '2024-02-13', '2024-02-14', '2024-02-15', '2024-02-16', '2024-02-17',  # 春节
            '2024-04-04', '2024-04-05', '2024-04-06',  # 清明节
            '2024-05-01', '2024-05-02', '2024-05-03', '2024-05-04', '2024-05-05',  # 劳动节
            '2024-06-10',  # 端午节
            '2024-09-15', '2024-09-16', '2024-09-17',  # 中秋节
            '2024-10-01', '2024-10-02', '2024-10-03', '2024-10-04', '2024-10-05', '2024-10-06', '2024-10-07',  # 国庆节
        ]
        
    def _load_trade_dates(self):
        """加载交易日历，从缓存或API获取"""
        # 检查缓存
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    if 'dates' in cache_data and 'update_time' in cache_data:
                        # 检查是否过期（缓存7天）
                        update_time = datetime.strptime(cache_data['update_time'], '%Y-%m-%d %H:%M:%S')
                        if (datetime.now() - update_time).days < 7:
                            self.trade_dates = set(cache_data['dates'])
                            self.last_update = update_time
                            return
            except:
                pass
        
        # 从API获取
        try:
            # 使用akshare获取交易日历
            trade_cal_df = ak.tool_trade_date_hist_sina()
            if not trade_cal_df.empty:
                self.trade_dates = set(trade_cal_df['trade_date'].astype(str).tolist())
                # 保存到缓存
                cache_data = {
                    'dates': list(self.trade_dates),
                    'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump(cache_data, f, ensure_ascii=False, indent=2)
                return
        except Exception as e:
            st.warning(f"获取交易日历失败: {str(e)[:50]}")
        
        # 如果API失败，使用固定节假日+周末判断
        self._generate_fallback_calendar()
    
    def _generate_fallback_calendar(self):
        """生成备用交易日历（周末+节假日为非交易日）"""
        start_date = '2024-01-01'
        end_date = '2024-12-31'
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        
        trade_dates = set()
        for date in dates:
            # 周末
            if date.weekday() >= 5:  # 5=周六, 6=周日
                continue
            
            # 节假日
            date_str = date.strftime('%Y-%m-%d')
            if date_str in self.holidays_2024:
                continue
            
            # 调休判断（简单实现，实际需要更复杂逻辑）
            # 这里简化处理，假设非周末非节假日都是交易日
            trade_dates.add(date.strftime('%Y%m%d'))
        
        self.trade_dates = trade_dates
        # 保存到缓存
        cache_data = {
            'dates': list(self.trade_dates),
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    
    def is_trading_day(self, date_str=None):
        """判断是否为交易日"""
        if date_str is None:
            date = datetime.now()
        else:
            try:
                date = datetime.strptime(date_str, '%Y-%m-%d')
            except:
                date = datetime.now()
        
        # 加载交易日历
        if self.trade_dates is None:
            self._load_trade_dates()
        
        # 判断
        date_key = date.strftime('%Y%m%d')
        return date_key in self.trade_dates if self.trade_dates else date.weekday() < 5

# 初始化交易日检查器
trade_checker = TradingDayChecker()

def is_trading_day(date=None):
    """对外接口：判断是否为交易日"""
    if date is None:
        date_str = None
    elif isinstance(date, datetime):
        date_str = date.strftime('%Y-%m-%d')
    elif isinstance(date, str):
        date_str = date
    else:
        date_str = None
    
    return trade_checker.is_trading_day(date_str)

# ====================== 数据获取函数 ======================
def safe_request(func, *args, max_retries=3, **kwargs):
    """安全的API请求，带重试机制"""
    for i in range(max_retries):
        try:
            result = func(*args, **kwargs)
            if result is not None and (not hasattr(result, 'empty') or not result.empty):
                return result
        except Exception as e:
            if i == max_retries - 1:
                st.warning(f"请求失败 ({func.__name__}): {str(e)[:100]}")
            time.sleep(1)  # 等待1秒
    return None

def get_fund_basic_info(fund_code):
    """获取基金基本信息（改进版）"""
    try:
        # 使用多个接口获取
        fund_info_dict = {
            '基金代码': fund_code,
            '基金简称': f'基金{fund_code}',
            '基金类型': '未知',
            '成立日期': '',
            '最新规模': '',
            '基金经理': ''
        }
        
        # 方法1: 使用基金基本信息接口
        try:
            info_df = safe_request(ak.fund_em_fund_info, fund=fund_code, indicator="单位净值走势")
            if info_df is not None and not info_df.empty:
                # 尝试从不同列获取信息
                for col in ['基金简称', '基金名称', 'name']:
                    if col in info_df.columns:
                        fund_info_dict['基金简称'] = str(info_df.iloc[0][col])
                        break
                
                for col in ['基金类型', 'type']:
                    if col in info_df.columns:
                        fund_info_dict['基金类型'] = str(info_df.iloc[0][col])
                        break
        except:
            pass
        
        # 方法2: 使用基金档案接口
        try:
            profile_df = safe_request(ak.fund_em_fund_info, fund=fund_code, indicator="档案")
            if profile_df is not None and not profile_df.empty:
                for col in ['基金经理', '基金经理人']:
                    if col in profile_df.columns:
                        fund_info_dict['基金经理'] = str(profile_df.iloc[0][col])
                        break
        except:
            pass
        
        return fund_info_dict
        
    except Exception as e:
        st.warning(f"获取基金{fund_code}信息失败: {str(e)[:50]}")
        return {
            '基金代码': fund_code,
            '基金简称': f'基金{fund_code}',
            '基金类型': '未知',
            '成立日期': '',
            '最新规模': '',
            '基金经理': ''
        }

def get_fund_holding(fund_code):
    """获取基金持仓数据（改进版）"""
    cache_file = f'data/cache/holding_{fund_code}.json'
    cache_time = 3600 * 6  # 缓存6小时
    
    # 检查缓存
    if os.path.exists(cache_file):
        try:
            file_time = os.path.getmtime(cache_file)
            if time.time() - file_time < cache_time:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except:
            pass
    
    try:
        # 尝试多种接口获取持仓
        holding_df = None
        
        # 方法1: 获取基金持仓
        try:
            holding_df = safe_request(ak.fund_em_portfolio_hold, fund=fund_code)
        except:
            pass
        
        # 方法2: 备用接口
        if holding_df is None or holding_df.empty:
            try:
                # 尝试其他接口
                holding_df = safe_request(ak.fund_portfolio_hold_em, symbol=fund_code)
            except:
                pass
        
        if holding_df is not None and not holding_df.empty:
            # 清理和标准化数据
            holdings = []
            
            for _, row in holding_df.iterrows():
                holding_item = {}
                
                # 股票代码
                for code_col in ['股票代码', '股票代码', 'code', 'symbol']:
                    if code_col in row and pd.notna(row[code_col]):
                        holding_item['股票代码'] = str(row[code_col]).replace(' ', '')
                        break
                
                # 股票名称
                for name_col in ['股票名称', '名称', '股票简称', 'name']:
                    if name_col in row and pd.notna(row[name_col]):
                        holding_item['股票名称'] = str(row[name_col])
                        break
                
                # 占净值比例
                for weight_col in ['占净值比例', '占净值比例%', 'weight', '持股占净值比']:
                    if weight_col in row and pd.notna(row[weight_col]):
                        weight_str = str(row[weight_col])
                        # 清理百分比符号
                        weight_str = weight_str.replace('%', '').strip()
                        try:
                            holding_item['占净值比例'] = float(weight_str)
                        except:
                            holding_item['占净值比例'] = 0.0
                        break
                else:
                    holding_item['占净值比例'] = 0.0
                
                # 持股数
                for share_col in ['持股数', '持股数(万股)', '持股数量', 'share']:
                    if share_col in row and pd.notna(row[share_col]):
                        holding_item['持股数'] = str(row[share_col])
                        break
                
                # 只添加有效数据
                if holding_item.get('股票代码') and holding_item.get('股票名称'):
                    holdings.append(holding_item)
            
            # 按持仓比例排序，取前10
            holdings.sort(key=lambda x: x.get('占净值比例', 0), reverse=True)
            top_10 = holdings[:10]
            
            result = {
                'fund_code': fund_code,
                'update_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'holdings': top_10,
                'total_weight': sum(h.get('占净值比例', 0) for h in top_10)
            }
            
            # 保存缓存
            try:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
            except:
                pass
            
            return result
            
    except Exception as e:
        st.warning(f"获取基金{fund_code}持仓失败: {str(e)[:50]}")
    
    return None

def get_stock_real_time_data(stock_codes):
    """获取股票实时数据（改进版）"""
    if not stock_codes:
        return {}
    
    result = {}
    
    try:
        # 批量获取股票数据
        all_stocks = []
        
        # 尝试多个接口
        try:
            # 接口1: 东财实时数据
            stock_df = safe_request(ak.stock_zh_a_spot_em)
            if stock_df is not None and not stock_df.empty:
                all_stocks.append(stock_df)
        except:
            pass
        
        try:
            # 接口2: 新浪实时数据
            stock_df = safe_request(ak.stock_zh_a_spot)
            if stock_df is not None and not stock_df.empty:
                all_stocks.append(stock_df)
        except:
            pass
        
        if not all_stocks:
            return {}
        
        # 合并数据
        combined_df = pd.concat(all_stocks, ignore_index=True)
        
        # 处理每个股票代码
        for stock_code in stock_codes:
            if not stock_code or not isinstance(stock_code, str):
                continue
            
            # 标准化股票代码
            clean_code = str(stock_code).strip()
            
            # 去除可能的交易所前缀
            if clean_code.startswith('sh') or clean_code.startswith('sz'):
                clean_code = clean_code[2:]
            
            # 匹配股票
            matched = False
            for _, row in combined_df.iterrows():
                # 检查代码列
                for code_col in ['代码', 'symbol', '股票代码']:
                    if code_col in row and pd.notna(row[code_col]):
                        compare_code = str(row[code_col]).strip()
                        
                        # 多种匹配方式
                        if (clean_code == compare_code or 
                            clean_code == compare_code[2:] or  # 去掉交易所前缀
                            f"sh{clean_code}" == compare_code or
                            f"sz{clean_code}" == compare_code or
                            compare_code.endswith(clean_code)):
                            
                            # 提取信息
                            stock_info = {}
                            
                            # 名称
                            for name_col in ['名称', 'name', '股票简称']:
                                if name_col in row and pd.notna(row[name_col]):
                                    stock_info['name'] = str(row[name_col])
                                    break
                            
                            # 最新价
                            for price_col in ['最新价', '最新', 'price', 'trade']:
                                if price_col in row and pd.notna(row[price_col]):
                                    try:
                                        stock_info['current'] = float(row[price_col])
                                    except:
                                        stock_info['current'] = 0.0
                                    break
                            
                            # 涨跌幅
                            for change_col in ['涨跌幅', '涨跌(%)', 'changepercent', 'pctChg']:
                                if change_col in row and pd.notna(row[change_col]):
                                    try:
                                        stock_info['change_percent'] = float(row[change_col])
                                    except:
                                        stock_info['change_percent'] = 0.0
                                    break
                            
                            # 涨跌额
                            for amount_col in ['涨跌额', '涨跌', 'change', 'price_change']:
                                if amount_col in row and pd.notna(row[amount_col]):
                                    try:
                                        stock_info['change_amount'] = float(row[amount_col])
                                    except:
                                        stock_info['change_amount'] = 0.0
                                    break
                            
                            result[stock_code] = stock_info
                            matched = True
                            break
                
                if matched:
                    break
            
            # 如果没匹配到，返回空信息
            if not matched:
                result[stock_code] = {
                    'name': f'股票{clean_code}',
                    'current': 0.0,
                    'change_percent': 0.0,
                    'change_amount': 0.0
                }
        
        return result
        
    except Exception as e:
        st.warning(f"获取股票数据时出错: {str(e)[:50]}")
        return {}

def get_fund_nav(fund_code):
    """获取基金净值（用于非交易日）"""
    try:
        # 获取基金净值
        nav_df = safe_request(ak.fund_em_open_fund_info, fund=fund_code)
        
        if nav_df is not None and not nav_df.empty:
            # 获取最新净值
            latest_nav = nav_df.iloc[0]
            
            return {
                '净值日期': latest_nav.get('净值日期', ''),
                '单位净值': latest_nav.get('单位净值', 0),
                '累计净值': latest_nav.get('累计净值', 0),
                '日增长率': latest_nav.get('日增长率', 0)
            }
        
        # 备用接口
        nav_df = safe_request(ak.fund_open_fund_info_em, symbol=fund_code)
        if nav_df is not None and not nav_df.empty:
            latest_nav = nav_df.iloc[0]
            return {
                '净值日期': latest_nav.get('净值日期', ''),
                '单位净值': latest_nav.get('单位净值', 0),
                '累计净值': latest_nav.get('累计净值', 0),
                '日增长率': latest_nav.get('日增长率', 0)
            }
            
    except Exception as e:
        st.warning(f"获取基金{fund_code}净值失败: {str(e)[:50]}")
    
    return None

def calculate_fund_estimated_change(fund_code):
    """计算基金估算涨跌幅（改进版）"""
    try:
        # 获取持仓数据
        holding_data = get_fund_holding(fund_code)
        
        if not holding_data or 'holdings' not in holding_data:
            return None
        
        holdings = holding_data['holdings']
        if not holdings:
            return None
        
        # 提取股票代码
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
        
        # 估算总涨跌幅（按前十大重仓比例缩放）
        estimated_change = total_change * 100  # 直接使用总和，因为权重已经是百分比
        
        return {
            'estimated_change': round(estimated_change, 4),
            'holding_data': holding_data,
            'stock_data': stock_data,
            'calculation_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'valid_stocks': valid_count,
            'total_weight': total_weight
        }
        
    except Exception as e:
        st.warning(f"计算基金{fund_code}估算失败: {str(e)[:50]}")
        return None

def search_fund(keyword):
    """搜索基金（改进版）"""
    try:
        # 如果输入的是纯数字，先按代码搜索
        if keyword.isdigit():
            try:
                # 直接尝试获取该基金
                search_df = safe_request(ak.fund_em_fund_name)
                if search_df is not None and not search_df.empty:
                    result = search_df[search_df['基金代码'].astype(str).str.contains(keyword, na=False)]
                    if not result.empty:
                        return result.head(20)
            except:
                pass
        
        # 按名称搜索
        try:
            search_df = safe_request(ak.fund_em_fund_name)
            if search_df is not None and not search_df.empty:
                result = search_df[search_df['基金简称'].str.contains(keyword, case=False, na=False)]
                if not result.empty:
                    return result.head(20)
        except:
            pass
        
        return pd.DataFrame()
        
    except Exception as e:
        st.warning(f"搜索基金失败: {str(e)[:50]}")
        return pd.DataFrame()

# ====================== 界面保持不变 ======================
# 侧边栏
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
    
    # 正确显示交易日状态
    is_trading = is_trading_day()
    if is_trading:
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
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("文件格式错误")
            except Exception as e:
                st.error(f"导入失败: {str(e)}")
    
    # 导出面板
    if st.session_state.get('show_export'):
        if st.session_state.fund_list:
            json_str = json.dump(st.session_state.fund_list, ensure_ascii=False, indent=2)
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
                    time.sleep(1)
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
                if search_results is not None and not search_results.empty:
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
                                    time.sleep(1)
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
                    time.sleep(1)
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
        search_result = search_fund(search_input)
        if search_result is not None and not search_result.empty:
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
                
                # 根据是否为交易日显示不同内容
                if is_trading:
                    # 交易日：显示估算涨跌幅
                    with st.spinner(f"计算{fund_code}..."):
                        calc_result = calculate_fund_estimated_change(fund_code)
                    
                    if calc_result:
                        change = calc_result['estimated_change']
                        # 根据涨跌设置卡片样式
                        card_class = "up" if change > 0 else ("down" if change < 0 else "flat")
                        change_color = "#4CAF50" if change > 0 else ("#F44336" if change < 0 else "#2196F3")
                        change_display = f"{'+' if change > 0 else ''}{change:.2f}%"
                        
                        st.markdown(f"""
                        <div class="fund-card {card_class}">
                            <h4 style="margin:0;">{fund_info['基金简称']}</h4>
                            <p style="color:#666; font-size:0.9em; margin:5px 0;">{fund_code}</p>
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <span style="font-size:1.2em; font-weight:bold;">{fund_info['基金类型']}</span>
                                <span style="font-size:1.5em; font-weight:bold; color:{change_color}">
                                    {change_display}
                                </span>
                            </div>
                            <p style="font-size:0.8em; color:#888; margin-top:5px;">
                                估算时间: {calc_result['calculation_time'][-8:] if 'calculation_time' in calc_result else 'N/A'}
                            </p>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div class="fund-card flat">
                            <h4 style="margin:0;">{fund_info['基金简称']}</h4>
                            <p style="color:#666; font-size:0.9em; margin:5px 0;">{fund_code}</p>
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <span style="font-size:1.2em; font-weight:bold;">{fund_info['基金类型']}</span>
                                <span style="font-size:1.2em; font-weight:bold; color:#FF9800;">
                                    计算中...
                                </span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    # 非交易日：显示最新净值
                    nav_data = get_fund_nav(fund_code)
                    if nav_data and nav_data.get('单位净值'):
                        nav_date = nav_data.get('净值日期', '未知日期')
                        nav_value = nav_data.get('单位净值', 0)
                        
                        st.markdown(f"""
                        <div class="fund-card flat">
                            <h4 style="margin:0;">{fund_info['基金简称']}</h4>
                            <p style="color:#666; font-size:0.9em; margin:5px 0;">{fund_code}</p>
                            <div style="display:flex; justify-content:space-between; align-items:center; margin:10px 0;">
                                <span style="font-size:1.1em; font-weight:bold;">单位净值</span>
                                <span style="font-size:1.3em; font-weight:bold; color:#2196F3;">
                                    {nav_value:.4f}
                                </span>
                            </div>
                            <p style="font-size:0.8em; color:#888; margin:0;">
                                {nav_date}
                            </p>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div class="fund-card flat">
                            <h4 style="margin:0;">{fund_info['基金简称']}</h4>
                            <p style="color:#666; font-size:0.9em; margin:5px 0;">{fund_code}</p>
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <span style="font-size:1.2em; font-weight:bold;">{fund_info['基金类型']}</span>
                                <span style="font-size:1.2em; font-weight:bold; color:#9E9E9E;">
                                    非交易日
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
                        # 清除缓存
                        cache_file = f'data/cache/holding_{fund_code}.json'
                        if os.path.exists(cache_file):
                            os.remove(cache_file)
                        st.rerun()
    
    with view_tab2:
        # 列表视图
        list_data = []
        for fund_code in st.session_state.fund_list:
            fund_info = get_fund_basic_info(fund_code)
            
            if is_trading:
                calc_result = calculate_fund_estimated_change(fund_code)
                estimate = f"{calc_result['estimated_change']:.2f}%" if calc_result else "计算失败"
            else:
                nav_data = get_fund_nav(fund_code)
                if nav_data and nav_data.get('单位净值'):
                    estimate = f"{nav_data['单位净值']:.4f}"
                else:
                    estimate = "非交易日"
            
            list_data.append({
                "基金代码": fund_code,
                "基金简称": fund_info['基金简称'],
                "基金类型": fund_info['基金类型'],
                "估算/净值": estimate
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
                    "估算/净值": st.column_config.TextColumn("估算/净值", width="small")
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
                            try:
                                os.remove(f'data/cache/{file}')
                            except:
                                pass
                    st.success("缓存已清除，正在重新计算...")
                    time.sleep(1)
                    st.rerun()

# 基金详情展示
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
            trading_status = "交易日" if is_trading else "非交易日"
            st.metric("当前状态", trading_status)
        
        if is_trading:
            # 交易日：显示估算涨跌幅
            with st.spinner("计算实时估算中..."):
                calc_result = calculate_fund_estimated_change(fund_code)
            
            if calc_result:
                delta_color = "normal" if calc_result['estimated_change'] >= 0 else "inverse"
                delta_symbol = "+" if calc_result['estimated_change'] >= 0 else ""
                
                st.metric(
                    "估算涨跌幅",
                    f"{calc_result['estimated_change']:.2f}%",
                    delta=f"{delta_symbol}{calc_result['estimated_change']:.2f}%",
                    delta_color=delta_color
                )
                st.caption(f"基于 {calc_result['valid_stocks']} 只重仓股计算 • 更新时间: {calc_result['calculation_time']}")
                
                # 显示前三大持仓
                if calc_result.get('holding_data') and calc_result['holding_data'].get('holdings'):
                    st.write("**前三大重仓股:**")
                    holdings = calc_result['holding_data']['holdings'][:3]
                    for i, holding in enumerate(holdings, 1):
                        stock_code = holding.get('股票代码', '')
                        stock_name = holding.get('股票名称', '')
                        weight = holding.get('占净值比例', 0)
                        stock_info = calc_result.get('stock_data', {}).get(stock_code, {})
                        change = stock_info.get('change_percent', 0)
                        
                        col_stock1, col_stock2, col_stock3 = st.columns(3)
                        with col_stock1:
                            st.write(f"{i}. {stock_name}")
                        with col_stock2:
                            st.write(f"{weight:.2f}%")
                        with col_stock3:
                            change_color = "green" if change >= 0 else "red"
                            st.markdown(f"<span style='color:{change_color}'>{change:.2f}%</span>", unsafe_allow_html=True)
            else:
                st.warning("无法计算实时估算")
        else:
            # 非交易日：显示最新净值
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
                    growth_rate = float(str(nav_data['日增长率']).replace('%', ''))
                    delta_color = "normal" if growth_rate >= 0 else "inverse"
                    st.metric(
                        "日增长率",
                        f"{growth_rate:.2f}%",
                        delta=f"{growth_rate:.2f}%",
                        delta_color=delta_color
                    )
            else:
                st.info("无法获取净值信息")
    
    with detail_tab2:
        if is_trading:
            # 交易日：显示持仓详情
            with st.spinner("获取持仓数据中..."):
                holding_data = get_fund_holding(fund_code)
            
            if holding_data and holding_data.get('holdings'):
                holdings = holding_data['holdings']
                
                # 获取股票实时数据
                stock_codes = [h.get('股票代码') for h in holdings if h.get('股票代码')]
                stock_data = get_stock_real_time_data(stock_codes)
                
                # 显示持仓表格
                holdings_display = []
                for h in holdings:
                    stock_code = h.get('股票代码', '')
                    stock_info = stock_data.get(stock_code, {})
                    
                    holdings_display.append({
                        '股票代码': stock_code,
                        '股票名称': h.get('股票名称', ''),
                        '持仓比例%': f"{h.get('占净值比例', 0):.2f}",
                        '当前价格': f"{stock_info.get('current', 0):.2f}" if stock_info.get('current') else 'N/A',
                        '涨跌幅%': f"{stock_info.get('change_percent', 0):.2f}" if stock_info.get('change_percent') is not None else 'N/A'
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
            # 非交易日：显示历史净值
            st.info("非交易日不显示持仓详情，请在交易日查看实时数据。")

# 批量更新功能区
if st.session_state.fund_list and is_trading:
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
                        '有效股票数': calc_result.get('valid_stocks', 0),
                        '更新时间': calc_result.get('calculation_time', '')[11:19]  # 只显示时间
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
                results.append({
                    '基金代码': fund_code,
                    '基金简称': get_fund_basic_info(fund_code)['基金简称'],
                    '估算涨跌幅': f"错误: {str(e)[:30]}",
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

# 页脚
st.markdown("---")
st.caption("""
**免责声明**: 本系统数据仅供参考，估算涨跌幅基于前十大重仓股实时数据计算，与实际净值可能存在差异。投资有风险，入市需谨慎。
**数据来源**: 东方财富、新浪财经等公开数据接口
**更新时间**: 数据有15分钟延迟
**交易日状态**: 基于中国A股交易日历判断
""")

# 初始化session_state变量
if 'show_import' not in st.session_state:
    st.session_state.show_import = False
if 'show_export' not in st.session_state:
    st.session_state.show_export = False
if 'selected_fund' not in st.session_state:
    st.session_state.selected_fund = None
