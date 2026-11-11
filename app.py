import streamlit as st
from zhipuai import ZhipuAI
import json
from supabase import create_client, Client

# ================= 配置区 =================
st.set_page_config(page_title="青盾防诈系统", page_icon="🛡️")

# 从 Streamlit Secrets 读取密钥 (确保你在云端后台配置了这三个)
api_key = st.secrets["ZHIPU_API_KEY"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

client = ZhipuAI(api_key=api_key)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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
                # 写入云端数据库
                supabase.table("messages").insert({"old_text": input_text, "status": "pending"}).execute()
                st.success("✅ 已发送！请等待子女的回复...")
            except Exception as e:
                st.error(f"发送失败：{e}")
        else:
            st.warning("请先输入可疑内容哦！")

    st.markdown("---")
    st.subheader("📬 子女的回复：")
    
    # 手机端每次刷新，都去云端找最近一条已回复的数据
    try:
        res = supabase.table("messages").select("*").eq("status", "replied").order("id", desc=True).limit(1).execute()
        if res.data:
            st.success(f"子女回复：{res.data[0]['ai_reply']}")
        else:
            st.info("等待回复中... (如果刚刚发送，请稍等几秒钟)")
    except Exception as e:
        pass # 忽略读取错误

# ---------------- 青年研判端（电脑） ----------------
with tab2:
    st.header("待处理的求助")
    
    # 电脑端每次刷新，都去云端找最近一条待处理的数据
    latest_msg = None
    try:
        res = supabase.table("messages").select("*").eq("status", "pending").order("id", desc=True).limit(1).execute()
        if res.data:
            latest_msg = res.data[0]
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
                    
                    # 更新数据库状态
                    supabase.table("messages").update({"status": "replied", "ai_reply": result_json['reply']}).eq("id", latest_msg['id']).execute()
                    st.success("✅ 已发送给长辈！")
                    
                except Exception as e:
                    st.error(f"分析失败：{e}")
                    
    else:
        st.write("当前暂无待处理求助。")
