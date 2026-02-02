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
    
    # 2025年A股交易日历（主要节假日，需根据实际情况更新）
    holidays_2025 = [
        '2025-01-01',  # 元旦
        '2025-01-28', '2025-01-29', '2025-01-30',  # 春节示例，需按实际日期更新
        '2025-04-04', '2025-04-05', '2025-04-06',  # 清明节
        '2025-05-01', '2025-05-02', '2025-05-03',  # 劳动节
        '2025-06-10',  # 端午节
        '2025-09-15', '2025-09-16', '2025-09-17',  # 中秋节
        '2025-10-01', '2025-10-02', '2025-10-03', '2025-10-06', '2025-10-07',  # 国庆节
    ]
    
    today_str = now.strftime('%Y-%m-%d')
    if today_str in holidays_2025:
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
        except Exception as e:
            print(f"通过fund_name_em获取基金{fund_code}信息失败: {e}")
        
        # 方法2：尝试通过其他接口获取
        try:
            fund_info = ak.fund_info_em(fund=fund_code)
            if not fund_info.empty and '基金简称' in fund_info.columns:
                return {
                    'code': fund_code,
                    'name': fund_info.iloc[0]['基金简称'],
                    'type': fund_info.iloc[0]['基金类型'] if '基金类型' in fund_info.columns else '未知'
                }
        except Exception as e:
            print(f"通过fund_info_em获取基金{fund_code}信息失败: {e}")
        
        return {
            'code': fund_code,
            'name': f"基金{fund_code}",
            'type': '未知'
        }
    except Exception as e:
        print(f"获取基金{fund_code}基本信息异常: {e}")
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
                for col in ['估算净值', '估算值', '单位净值']:
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
                for val_col in ['估算净值', '估算值', '单位净值']:
                    if val_col in latest and latest[val_col] not in [None, '', np.nan]:
                        try:
                            estimated_value = float(latest[val_col])
                        except:
                            pass
                        break
                
                # 提取涨跌幅
                for chg_col in ['估算涨跌幅', '涨跌幅', '日增长率']:
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
            daily_change = None
            
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
            
            # 提取日增长率
            for change_col in ['日增长率', '涨跌幅']:
                if change_col in latest and latest[change_col] not in [None, '', np.nan]:
                    try:
                        change_str = str(latest[change_col])
                        change_str = change_str.replace('%', '').strip()
                        daily_change = float(change_str)
                    except:
                        pass
                    break
            
            if nav_value is not None and nav_date is not None:
                return {
                    'type': 'nav',
                    'date': nav_date,
                    'value': nav_value,
                    'daily_change': daily_change if daily_change is not None else 0,
                    'source': '基金净值',
                    'update_time': get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')
                }
        
        return None
    except Exception as e:
        print(f"获取基金{fund_code}净值数据失败: {e}")
        return None

def get_fund_data(fund_code):
    """获取基金数据（实时估算或最新净值）"""
    # 首先尝试获取实时估算数据
    if is_trading_day() and is_trading_hours():
        real_time_data = get_fund_estimation_from_api(fund_code)
        if real_time_data:
            return real_time_data
    
    # 如果非交易时间或实时数据获取失败，获取最新净值
    nav_data = get_fund_nav_data(fund_code)
    if nav_data:
        return nav_data
    
    return None

def save_fund_list():
    """保存基金列表到文件"""
    try:
        with open('data/fund_list.json', 'w', encoding='utf-8') as f:
            json.dump(st.session_state.fund_list, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"保存基金列表失败: {e}")

# ====================== 主界面 ======================
def main():
    st.title("📈 基金持仓跟踪系统")
    
    # 侧边栏
    with st.sidebar:
        st.header("基金管理")
        
        # 添加基金
        with st.form("add_fund_form"):
            st.subheader("添加基金")
            fund_code = st.text_input("基金代码", placeholder="例如: 000001")
            fund_amount = st.number_input("持仓金额", min_value=0.0, value=10000.0, step=1000.0)
            fund_cost = st.number_input("持仓成本", min_value=0.0, value=1.0, step=0.01)
            
            if st.form_submit_button("添加基金"):
                if fund_code and fund_amount > 0 and fund_cost > 0:
                    # 检查是否已存在
                    existing = [f for f in st.session_state.fund_list if f['code'] == fund_code]
                    if existing:
                        st.warning(f"基金{fund_code}已在列表中")
                    else:
                        # 获取基金基本信息
                        basic_info = get_fund_basic_info(fund_code)
                        new_fund = {
                            'code': fund_code,
                            'name': basic_info['name'],
                            'type': basic_info['type'],
                            'amount': fund_amount,
                            'cost': fund_cost
                        }
                        st.session_state.fund_list.append(new_fund)
                        save_fund_list()
                        st.success(f"已添加基金: {basic_info['name']}({fund_code})")
                        
                        # 刷新页面
                        st.rerun()
                else:
                    st.error("请填写完整信息")
        
        st.divider()
        
        # 显示当前基金列表
        st.subheader("当前持仓基金")
        if st.session_state.fund_list:
            for i, fund in enumerate(st.session_state.fund_list):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"{fund['name']}({fund['code']})")
                with col2:
                    if st.button("删除", key=f"del_{i}"):
                        st.session_state.fund_list.pop(i)
                        save_fund_list()
                        st.rerun()
        else:
            st.info("暂无持仓基金，请添加")
        
        st.divider()
        
        # 系统状态
        st.subheader("系统状态")
        current_time = get_beijing_time()
        st.write(f"当前时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        if is_trading_day():
            if is_trading_hours():
                st.success("🟢 交易中")
            else:
                st.info("🟡 非交易时间")
        else:
            st.warning("🔴 非交易日")
        
        # 清空缓存按钮
        if st.button("清空缓存并刷新"):
            cache_dir = 'data/cache'
            for file in os.listdir(cache_dir):
                file_path = os.path.join(cache_dir, file)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"删除文件失败: {e}")
            st.success("缓存已清空")
            st.rerun()
    
    # 主内容区
    if st.session_state.fund_list:
        st.header("持仓基金概览")
        
        # 自动刷新选项
        auto_refresh = st.checkbox("自动刷新（每30秒）", value=False)
        if auto_refresh:
            time.sleep(30)
            st.rerun()
        
        # 显示基金数据
        for fund in st.session_state.fund_list:
            with st.container():
                st.subheader(f"{fund['name']} ({fund['code']})")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("基金类型", fund['type'])
                
                with col2:
                    st.metric("持仓金额", f"¥{fund['amount']:,.2f}")
                
                with col3:
                    st.metric("持仓成本", f"{fund['cost']:.4f}")
                
                # 获取基金数据
                fund_data = get_fund_data(fund['code'])
                
                if fund_data:
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        if fund_data['type'] == 'real_time':
                            st.metric("实时估算", f"{fund_data['value']:.4f}")
                        else:
                            st.metric("单位净值", f"{fund_data['value']:.4f}")
                    
                    with col2:
                        change = fund_data.get('change') or fund_data.get('daily_change', 0)
                        change_color = "red-text" if change < 0 else "green-text"
                        st.metric("涨跌幅", f"{change:.2f}%", delta=f"{change:.2f}%")
                    
                    with col3:
                        if fund_data['type'] == 'real_time':
                            st.metric("数据来源", "实时估算")
                        else:
                            st.metric("数据来源", "基金净值")
                    
                    with col4:
                        date_str = fund_data.get('date') or fund_data.get('update_time', '')
                        st.metric("更新时间", date_str)
                    
                    # 计算持仓盈亏
                    if fund_data['value'] and fund['cost']:
                        current_value = fund_data['value']
                        cost = fund['cost']
                        shares = fund['amount'] / cost
                        current_amount = shares * current_value
                        profit = current_amount - fund['amount']
                        profit_rate = (current_value - cost) / cost * 100
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("当前市值", f"¥{current_amount:,.2f}")
                        with col2:
                            st.metric("持仓盈亏", f"¥{profit:,.2f}", 
                                     delta=f"{profit_rate:.2f}%")
                
                st.divider()
    
    else:
        st.info("💡 请在左侧添加您的持仓基金开始跟踪")
        
        # 显示示例
        st.subheader("示例基金")
        example_funds = [
            {"code": "000001", "name": "华夏成长混合", "type": "混合型"},
            {"code": "110022", "name": "易方达消费行业股票", "type": "股票型"},
            {"code": "161725", "name": "招商中证白酒指数", "type": "指数型"}
        ]
        
        for fund in example_funds:
            with st.expander(f"{fund['name']} ({fund['code']})"):
                fund_data = get_fund_data(fund['code'])
                if fund_data:
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("当前净值", f"{fund_data['value']:.4f}")
                    with col2:
                        change = fund_data.get('change') or fund_data.get('daily_change', 0)
                        st.metric("涨跌幅", f"{change:.2f}%")
                    with col3:
                        st.metric("数据来源", fund_data['source'])
                else:
                    st.warning("无法获取该基金数据")

# 运行主程序
if __name__ == "__main__":
    main()
