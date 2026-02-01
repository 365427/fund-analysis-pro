import streamlit as st
import pandas as pd
import os
import time
import requests
import akshare as ak
import inspect
import datetime
import io # 用于处理上传的文件流

# --- 1. 页面配置 ---
st.set_page_config(page_title="基金持仓分析 Pro (AkShare+DeepSeek)", layout="wide")
st.title("📈 基金持仓实时深度分析")

# --- 2. 辅助函数：判断是否为交易日 ---
def is_trading_day(date_to_check):
    if date_to_check.weekday() > 4:
        return False
    return True

# --- 3. 核心抓取函数 ---
@st.cache_data(ttl=3600)
def get_detail_data(fund_code):
    try:
        df = ak.fund_portfolio_hold_em(symbol=fund_code)
        if df.empty:
            return None, "未找到持仓数据", None
        date_cols = [col for col in df.columns if '时间' in col or '日期' in col or 'quarter' in col.lower() or 'date' in col.lower()]
        if not date_cols:
            latest_df = df.copy()
            report_date = "最新一期"
        else:
            date_col = date_cols[0]
            latest_date = df[date_col].max()
            latest_df = df[df[date_col] == latest_date].copy()
            report_date = str(latest_date)
        required_cols = ['股票代码', '股票名称', '占净值比例']
        if not all(col in latest_df.columns for col in required_cols):
            missing = [col for col in required_cols if col not in latest_df.columns]
            return None, f"数据格式不匹配，缺少字段: {missing}", None
        latest_df = latest_df[required_cols].copy()
        latest_df.rename(columns={'占净值比例': 'curr_weight'}, inplace=True)
        latest_df['curr_weight'] = pd.to_numeric(latest_df['curr_weight'], errors='coerce').fillna(0)
        return latest_df, report_date, None
    except Exception as e:
        error_msg = f"AkShare 获取失败: {str(e)}"
        return None, error_msg, None

# --- 4. 获取实时净值估算或历史涨跌幅 ---
def get_fund_realtime_info(fund_code, is_today_trading_day):
    try:
        sig = inspect.signature(ak.fund_open_fund_info_em)
        params = list(sig.parameters.keys())
        fund_param_name = None
        for name in ['symbol', 'code', 'fund_code', 'fund']:
            if name in params:
                fund_param_name = name
                break
        if not fund_param_name:
            print(f"DEBUG: 未找到基金代码对应的参数名。可用参数: {params}")
            return "N/A", "N/A"
        call_kwargs = {fund_param_name: fund_code, 'indicator': '单位净值走势'}
        hist_df = ak.fund_open_fund_info_em(**call_kwargs)
        if hist_df.empty:
            print(f"DEBUG: 基金 {fund_code} 的历史数据为空。")
            return "N/A", "N/A"
        date_col_candidates = [col for col in hist_df.columns if '净值日期' in col or 'date' in col.lower() or '日期' in col]
        if not date_col_candidates:
            print(f"DEBUG: 基金 {fund_code} 未找到日期列。列名为: {list(hist_df.columns)}")
            return "N/A", "N/A"
        date_col = date_col_candidates[0]
        nav_col_candidates = [col for col in hist_df.columns if '单位净值' in col or '估算' in col]
        if not nav_col_candidates:
             print(f"DEBUG: 基金 {fund_code} 未找到净值列。列名为: {list(hist_df.columns)}")
             return "N/A", "N/A"
        nav_col = nav_col_candidates[0]
        hist_df.sort_values(by=date_col, ascending=False, inplace=True)
        hist_df.reset_index(drop=True, inplace=True)
        nav_series = hist_df[nav_col].dropna()
        if len(nav_series) < 2:
            print(f"DEBUG: 基金 {fund_code} 数据不足，无法计算涨跌幅。")
            return "N/A", "N/A"
        current_nav = nav_series.iloc[0]
        prev_nav = nav_series.iloc[1]
        if prev_nav == 0:
            daily_growth = 0
        else:
            daily_growth = ((current_nav - prev_nav) / prev_nav) * 100
        formatted_nav = f"{current_nav:.4f}"
        formatted_growth = f"{daily_growth:+.2f}%"
        return formatted_nav, formatted_growth
    except KeyError as e:
        print(f"DEBUG: 基金 {fund_code} 发生 KeyError: {e}.")
        return "N/A", "N/A"
    except IndexError as e:
        print(f"DEBUG: 基金 {fund_code} 发生 IndexError: {e}.")
        return "N/A", "N/A"
    except Exception as e:
        print(f"DEBUG: 基金 {fund_code} 发生未知错误: {e}")
        return "N/A", "N/A"

# --- 5. DeepSeek 兜底 ---
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
def call_deepseek_for_fund_info(fund_code, fund_name):
    if not DEEPSEEK_API_KEY:
        return "未配置或无效的 DeepSeek API Key，请检查环境变量设置。"
    try:
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "你是一个专业的金融数据助手。请根据用户提供的基金名称和代码，简要说明该基金的最新持仓概况（如主要行业、重仓股等）。回答请简洁、专业，不超过100字。"},
                {"role": "user", "content": f"基金名称：{fund_name}，基金代码：{fund_code}。请提供其最新持仓概况。"}
            ],
            "temperature": 0.3,
            "max_tokens": 200
        }
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        if response.status_code == 401:
            return "API 认证失败 (401)，请检查您的 API Key 是否正确有效。"
        elif response.status_code == 429:
            return "请求过于频繁或超出配额 (429)。"
        elif response.status_code != 200:
            return f"DeepSeek 调用失败: {response.status_code}, {response.text}"
        response_json = response.json()
        if 'choices' in response_json and len(response_json['choices']) > 0:
            return response_json['choices'][0]['message']['content'].strip()
        else:
            return f"API 返回了意外的响应格式: {response_json}"
    except requests.exceptions.Timeout:
        return "调用 DeepSeek 时请求超时。"
    except requests.exceptions.RequestException as e:
        return f"网络请求错误: {str(e)}"
    except Exception as e:
        return f"调用 DeepSeek 出错: {str(e)}"

# --- 6. 搜索与收藏逻辑 ---
@st.cache_data(ttl=3600)
def get_all_funds():
    try:
        return ak.fund_name_em()[['基金代码', '基金简称']]
    except Exception as e:
        st.warning(f"无法获取基金列表: {e}")
        return pd.DataFrame(columns=['基金代码', '基金简称'])

CSV_FILE = 'fund_favs.csv'

def load_favs(): 
    if os.path.exists(CSV_FILE):
        df = pd.read_csv(CSV_FILE, dtype={'代码': str})
        if '涨跌幅' not in df.columns:
            df['涨跌幅'] = 'N/A'
        return df[['代码', '名称', '涨跌幅']]
    else:
        return pd.DataFrame(columns=['代码', '名称', '涨跌幅'])

def save_favs(df): 
    df.to_csv(CSV_FILE, index=False)

# --- 7. 云端备份与恢复功能 (Gist) ---
GIST_TOKEN = os.getenv('GITHUB_GIST_TOKEN')
GIST_ID = os.getenv('FUND_FAVS_GIST_ID')

def backup_to_gist():
    if not GIST_TOKEN or not GIST_ID:
        return "❌ 失败: 未设置 GITHUB_GIST_TOKEN 或 FUND_FAVS_GIST_ID 环境变量。"
    try:
        if not os.path.exists(CSV_FILE):
            return "⚠️ 警告: 本地收藏列表为空，无法备份。"
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        url = f"https://api.github.com/gists/{GIST_ID}"
        headers = {
            "Authorization": f"token {GIST_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        data = {
            "files": {
                "fund_favs.csv": {
                    "content": content
                }
            }
        }
        response = requests.patch(url, headers=headers, json=data)
        if response.status_code == 200:
            return "✅ 成功: 数据已备份到云端 Gist。"
        else:
            return f"❌ 失败: Gist API 响应错误 {response.status_code}: {response.text}"
    except Exception as e:
        return f"❌ 失败: 备份过程中发生错误: {str(e)}"

def restore_from_gist():
    if not GIST_TOKEN or not GIST_ID:
        return "❌ 失败: 未设置 GITHUB_GIST_TOKEN 或 FUND_FAVS_GIST_ID 环境变量。"
    try:
        url = f"https://api.github.com/gists/{GIST_ID}"
        headers = {
            "Authorization": f"token {GIST_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            gist_data = response.json()
            file_content = gist_data['files'].get('fund_favs.csv', {}).get('content', '')
            if not file_content:
                return "❌ 失败: Gist 中未找到 fund_favs.csv 文件或文件为空。"
            with open(CSV_FILE, 'w', encoding='utf-8') as f:
                f.write(file_content)
            st.rerun()
            return "✅ 成功: 数据已从云端 Gist 恢复。页面已刷新。"
        else:
            return f"❌ 失败: Gist API 响应错误 {response.status_code}: {response.text}"
    except Exception as e:
        return f"❌ 失败: 恢复过程中发生错误: {str(e)}"

# --- 8. 本地文件导入功能 ---
def restore_from_local_file(uploaded_file):
    try:
        # 使用 pandas 读取上传的 CSV 文件
        # 注意：uploaded_file 是一个 BytesIO 对象
        uploaded_df = pd.read_csv(uploaded_file, dtype={'代码': str})

        # 检查必要的列是否存在
        required_columns = {'代码', '名称', '涨跌幅'}
        if not required_columns.issubset(uploaded_df.columns.tolist()):
            missing_cols = required_columns - set(uploaded_df.columns.tolist())
            return f"❌ 失败: 上传的文件缺少必要列: {missing_cols}"

        # 与现有数据合并，去重
        current_df = load_favs()
        combined_df = pd.concat([current_df, uploaded_df], ignore_index=True)
        unique_df = combined_df.drop_duplicates(subset=['代码'], keep='last')

        # 保存合并后的数据
        save_favs(unique_df)

        # 刷新页面以显示新数据
        st.rerun()
        return "✅ 成功: 数据已从本地文件导入。页面已刷新。"

    except pd.errors.EmptyDataError:
        return "❌ 失败: 上传的文件是空的。"
    except Exception as e:
        return f"❌ 失败: 解析上传文件时出错: {str(e)}"


# --- 9. 侧边栏交互 ---
st.sidebar.header("⭐ 基金搜索")
all_funds = get_all_funds()
fav_df = load_favs()

search = st.sidebar.text_input("🔍 输入名称或代码 (如: 161725)")
f_code, f_name = "", ""
if search:
    res = all_funds[(all_funds['基金代码'].str.contains(search)) | (all_funds['基金简称'].str.contains(search))]
    if not res.empty:
        f_code, f_name = res.iloc[0]['基金代码'], res.iloc[0]['基金简称']
        st.sidebar.success(f"已选: {f_name}")

# --- 10. 云端 & 本地备份导入按钮 (放在侧边栏) ---
st.sidebar.header("☁️ 数据同步")
backup_col, restore_col = st.sidebar.columns(2)
with backup_col:
    if st.button("📤 云端备份"):
        message = backup_to_gist()
        st.sidebar.info(message)
with restore_col:
    if st.button("📥 云端导入"):
        message = restore_from_gist()
        st.sidebar.info(message)

st.sidebar.header("📱 本地导入")
uploaded_file = st.sidebar.file_uploader(
    "选择本地CSV文件 (fund_favs.csv)",
    type=["csv"],
    accept_multiple_files=False,
    key="local_upload_widget"
)

if uploaded_file is not None:
    message = restore_from_local_file(uploaded_file)
    st.sidebar.info(message)
    # 清空上传组件的状态，防止重复处理
    # 这可以通过重新渲染页面来间接实现，或者使用 session_state 控制
    # 这里我们直接在处理完后显示消息，实际的清空发生在页面刷新后

# --- 11. 主界面：显示收藏列表 ---
st.subheader("我的自选基金列表")
today = datetime.date.today()
is_today_a_trading_day = is_trading_day(today)

if not fav_df.empty:
    display_df = fav_df.copy()
    for i, row in display_df.iterrows():
        code = row['代码']
        _, growth = get_fund_realtime_info(code, is_today_a_trading_day)
        display_df.loc[i, '涨跌幅'] = growth
    
    # 🔧 添加样式：红涨绿跌
    def color_growth(val):
        if pd.isna(val) or val == 'N/A':
            return 'color: gray;'
        elif isinstance(val, str) and val.startswith('+'):
            return 'color: red;'
        elif isinstance(val, str) and val.startswith('-'):
            return 'color: green;'
        else:
            # 针对数值型涨跌幅（虽然目前是字符串格式）
            if val > 0:
                return 'color: red;'
            elif val < 0:
                return 'color: green;'
            else:
                return 'color: gray;'

    styled_df = display_df.style.applymap(color_growth, subset=['涨跌幅'])
    st.dataframe(styled_df, width='stretch')
    status_text = "📊 **当前为交易日，显示实时估算涨跌幅**" if is_today_a_trading_day else "📊 **当前为非交易日，显示上一交易日收盘涨跌幅**"
    st.caption(status_text)
else:
    st.info("您的自选基金列表为空。请在左侧搜索并添加基金。")

# --- 12. 查询单个基金详情 ---
if f_code:
    st.divider()
    st.subheader(f"🔍 单独分析: {f_name} ({f_code})")
    current_nav, daily_growth = get_fund_realtime_info(f_code, is_today_a_trading_day)
    if daily_growth != "N/A":
        # 为单独查询的涨跌幅也应用红涨绿跌样式 (通过 delta_color)
        # delta_color='inverse' 会让正值显示为绿色，负值显示为红色，与标准相反
        # 我们需要反向逻辑，所以对于正值(上涨)用'reverse'让它变红，对于负值(下跌)用'normal'让它变绿
        # 或者，我们直接用 st.markdown 来显示带颜色的文本，更灵活
        # 为了保持 st.metric 的结构，我们暂时只用 label 显示颜色，value 不用 delta
        growth_delta_color = "inverse" if daily_growth.startswith('+') else "normal"
        st.metric(label="实时估算涨跌幅", value=daily_growth, delta=None, delta_color=growth_delta_color)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("➕ 加入自选"):
            new_entry = pd.DataFrame([{'代码': f_code, '名称': f_name, '涨跌幅': daily_growth}])
            updated_fav_df = pd.concat([fav_df, new_entry], ignore_index=True).drop_duplicates(subset=['代码'], keep='first')
            save_favs(updated_fav_df)
            st.rerun()
    with col2:
        if st.button("➖ 移出自选"):
            updated_fav_df = fav_df[fav_df['代码'] != f_code].reset_index(drop=True)
            save_favs(updated_fav_df)
            st.rerun()
    
    h, msg_or_date, _ = get_detail_data(f_code)
    if h is not None:
        st.caption(f"📅 持仓季度: {msg_or_date}")
        display_data = []
        for _, r in h.iterrows():
            display_data.append({
                "股票": f"{r['股票名称']} ({r['股票代码']})",
                "仓位": f"{r['curr_weight']:.2f}%",
                "变动": "-" 
            })
        st.dataframe(pd.DataFrame(display_data), width='stretch')
    else:
        st.error(msg_or_date)
        with st.spinner("正在调用 DeepSeek 获取基金信息..."):
            deepseek_response = call_deepseek_for_fund_info(f_code, f_name or "未知基金")
        st.info("💡 DeepSeek 提供的信息：")
        st.write(deepseek_response)
else:
    st.info("💡 请在左侧输入你想查询的基金名称或代码")

# --- 13. 部署提示 ---
st.sidebar.divider()
st.sidebar.markdown("**📱 手机部署提示:**")
st.sidebar.markdown("- 在手机浏览器中打开此应用。")
st.sidebar.markdown("- 使用侧边栏的备份/导入功能同步数据。")
st.sidebar.markdown("- **手机本地导入**: 点击“选择本地CSV文件”按钮，从手机相册、文件管理器或微信等渠道选择 `fund_favs.csv` 文件导入。")
st.sidebar.markdown("- **首次部署前请设置环境变量。**")

