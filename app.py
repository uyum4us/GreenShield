import streamlit as st
import json
from zhipuai import ZhipuAI

# ================= 配置区 =================
st.set_page_config(page_title="青盾防诈系统", page_icon="🛡️")

api_key = st.secrets["ZHIPU_API_KEY"]
client = ZhipuAI(api_key=api_key)

st.title("🛡️ 青盾 - 代际协同防诈系统")
st.write("数智赋能 · 青春力行")

tab1, tab2 = st.tabs(["👴 长辈求助端", "💻 青年研判端"])

# 模拟本地缓存
if 'current_help' not in st.session_state:
    st.session_state['current_help'] = ""
if 'ai_reply' not in st.session_state:
    st.session_state['ai_reply'] = ""

# ---------------- 长辈求助端（手机） ----------------
with tab1:
    st.header("遇到可疑信息？发给子女看看")
    input_text = st.text_area("请将可疑短信或链接粘贴到这里：", height=150)
    
    if st.button("发送给子女研判", type="primary", use_container_width=True):
        if input_text:
            st.session_state['current_help'] = input_text
            st.session_state['ai_reply'] = "" # 清空旧回复
            st.success("✅ 已发送！请等待子女的回复...")
        else:
            st.warning("请先输入可疑内容哦！")
            
    # 手机端如果收到了回复，就显示出来
    if st.session_state['ai_reply']:
        st.markdown("---")
        st.subheader("📬 子女的回复：")
        st.success(f"子女回复：{st.session_state['ai_reply']}")

# ---------------- 青年研判端（电脑） ----------------
with tab2:
    st.header("待处理的求助")
    
    if st.session_state['current_help']:
        st.info(f"📩 收到长辈求助：\n\n**{st.session_state['current_help']}**")
        
        if st.button("🤖 启动 AI 分析"):
            with st.spinner("AI 正在分析中..."):
                try:
                    response = client.chat.completions.create(
                        model="glm-4-flash-250414",
                        messages=[
                            {"role": "system", "content": "你是一个反诈专家。只返回JSON格式，不要其他文字：{\"risk_level\":\"高风险/中/低\",\"reply\":\"大白话防骗回复\"}"},
                            {"role": "user", "content": st.session_state['current_help']}
                        ],
                        temperature=0.1
                    )
                    result_str = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
                    result_json = json.loads(result_str)
                    
                    st.error(f"🚨 风险等级：{result_json['risk_level']}")
                    st.write("👇 **建议回复长辈的话：**")
                    st.code(result_json['reply'], language="text")
                    
                    # 关键：这里把 AI 的回复存在本地缓存里
                    st.session_state['ai_reply'] = result_json['reply']
                    
                    if st.button("📤 确认并发送给长辈"):
                        st.success("✅ 已成功发送至长辈手机端！")
                    
                except Exception as e:
                    st.error(f"分析失败：{e}")
                    
    else:
        st.write("当前暂无待处理求助。")
