import streamlit as st
import json
import urllib.request
import urllib.parse
from zhipuai import ZhipuAI

# ================= 配置区 =================
st.set_page_config(page_title="青盾防诈系统", page_icon="🛡️")

api_key = st.secrets["ZHIPU_API_KEY"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

client = ZhipuAI(api_key=api_key)

# 自定义底层网络请求函数
def make_request(url, method="GET", data=None):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "Accept-Charset": "utf-8"
    }
    
    req_data = None
    if data:
        # 强行将其转为 utf-8 字节流
        req_data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as response:
            # 强行用 utf-8 解码读取到的字节流，抛弃系统默认编码
            raw_bytes = response.read()
            if raw_bytes:
                return json.loads(raw_bytes.decode('utf-8'))
            return None
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode('utf-8')
        raise Exception(f"HTTP {e.code}: {error_msg}")

# ================= 页面 =================
st.title("🛡️ 青盾 - 代际协同防诈系统")
st.write("数智赋能 · 青春力行")

tab1, tab2 = st.tabs(["👴 长辈求助端", "💻 青年研判端"])

# ---------------- 长辈求助端（手机） ----------------
with tab1:
    st.header("遇到可疑信息？发给子女看看")
    input_text = st.text_area("请将可疑短信或链接粘贴到这里：", height=150)
    
    if st.button("发送给子女研判", type="primary", use_container_width=True):
        if input_text:
            try:
                url = f"{SUPABASE_URL}/rest/v1/messages"
                data = {"old_text": input_text, "status": "pending"}
                make_request(url, method="POST", data=data)
                st.success("✅ 已发送！请等待子女的回复...")
            except Exception as e:
                st.error(f"发送失败：{e}")
        else:
            st.warning("请先输入可疑内容哦！")

    st.markdown("---")
    st.subheader("📬 子女的回复：")
    try:
        url = f"{SUPABASE_URL}/rest/v1/messages?status=eq.replied&order=id.desc&limit=1"
        data = make_request(url, method="GET")
        if data:
            st.success(f"子女回复：{data[0]['ai_reply']}")
        else:
            st.info("等待回复中... (如果刚刚发送，请稍等几秒钟)")
    except Exception:
        pass

# ---------------- 青年研判端（电脑） ----------------
with tab2:
    st.header("待处理的求助")
    
    latest_msg = None
    try:
        url = f"{SUPABASE_URL}/rest/v1/messages?status=eq.pending&order=id.desc&limit=1"
        data = make_request(url, method="GET")
        if data:
            latest_msg = data[0]
    except Exception as e:
        st.error(f"读取数据失败：{e}")
    
    if latest_msg:
        st.info(f"📩 收到长辈求助：\n\n**{latest_msg['old_text']}**")
        
        if st.button("🤖 启动 AI 分析"):
            with st.spinner("AI 正在分析中..."):
                try:
                    response = client.chat.completions.create(
                        model="glm-4-flash-250414",
                        messages=[
                            {"role": "system", "content": "你是一个反诈专家。只返回JSON格式，不要其他文字：{\"risk_level\":\"高风险/中/低\",\"reply\":\"大白话防骗回复\"}"},
                            {"role": "user", "content": latest_msg['old_text']}
                        ],
                        temperature=0.1
                    )
                    result_str = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
                    result_json = json.loads(result_str)
                    
                    st.error(f"🚨 风险等级：{result_json['risk_level']}")
                    st.write("👇 **建议回复长辈的话：**")
                    st.code(result_json['reply'], language="text")
                    
                    # 更新状态
                    url = f"{SUPABASE_URL}/rest/v1/messages?id=eq.{latest_msg['id']}"
                    update_data = {"status": "replied", "ai_reply": result_json['reply']}
                    make_request(url, method="PATCH", data=update_data)
                    
                    st.success("✅ 已发送给长辈！")
                except Exception as e:
                    st.error(f"分析失败：{e}")
    else:
        st.write("当前暂无待处理求助。")
