import streamlit as st
import requests
import json
from zhipuai import ZhipuAI

# ================= 配置区 =================
st.set_page_config(page_title="青盾防诈系统", page_icon="🛡️")

api_key = st.secrets["ZHIPU_API_KEY"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

client = ZhipuAI(api_key=api_key)

# 统一构造请求头，确保编码为 utf-8
headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json; charset=utf-8",
    "Accept": "application/json"
}

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
                # 手动构造 POST 请求，明确使用 UTF-8 编码
                url = f"{SUPABASE_URL}/rest/v1/messages"
                data = {"old_text": input_text, "status": "pending"}
                
                # 关键：使用 json.dumps 并指定 ensure_ascii=False，再编码为 utf-8
                body = json.dumps(data, ensure_ascii=False).encode('utf-8')
                
                resp = requests.post(url, data=body, headers=headers)
                if resp.status_code == 201:
                    st.success("✅ 已发送！请等待子女的回复...")
                else:
                    st.error(f"发送失败：{resp.text}")
            except Exception as e:
                st.error(f"发送失败：{e}")
        else:
            st.warning("请先输入可疑内容哦！")

    st.markdown("---")
    st.subheader("📬 子女的回复：")
    
    try:
        url = f"{SUPABASE_URL}/rest/v1/messages?status=eq.replied&order=id.desc&limit=1"
        resp = requests.get(url, headers=headers)
        data = resp.json()
        
        if data:
            # 手动解码，确保中文正常显示
            reply_text = data[0]['ai_reply'].encode('utf-8').decode('utf-8')
            st.success(f"子女回复：{reply_text}")
        else:
            st.info("等待回复中... (如果刚刚发送，请稍等几秒钟)")
    except Exception as e:
        pass # 忽略读取错误

# ---------------- 青年研判端（电脑） ----------------
with tab2:
    st.header("待处理的求助")
    
    latest_msg = None
    try:
        url = f"{SUPABASE_URL}/rest/v1/messages?status=eq.pending&order=id.desc&limit=1"
        resp = requests.get(url, headers=headers)
        data = resp.json()
        
        if data:
            # 手动解码，确保中文正常显示
            latest_msg = data[0]
            latest_msg['old_text'] = latest_msg['old_text'].encode('utf-8').decode('utf-8')
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
                    
                    # 手动构造 PATCH 请求更新数据库
                    url = f"{SUPABASE_URL}/rest/v1/messages?id=eq.{latest_msg['id']}"
                    data = {"status": "replied", "ai_reply": result_json['reply']}
                    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
                    
                    resp = requests.patch(url, data=body, headers=headers)
                    st.success("✅ 已发送给长辈！")
                    
                except Exception as e:
                    st.error(f"分析失败：{e}")
                    
    else:
        st.write("当前暂无待处理求助。")
