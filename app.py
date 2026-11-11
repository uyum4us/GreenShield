import streamlit as st
from zhipuai import ZhipuAI
import json

# ⚠️ 换成你新生成的 API Key
# 把原来的 api_key = "sk-..." 替换成下面这行
api_key = st.secrets["ZHIPU_API_KEY"]
client = ZhipuAI(api_key=api_key)

st.set_page_config(page_title="青盾防诈系统", page_icon="🛡️")

st.title("🛡️ 青盾 - 代际协同防诈系统")
st.write("数智赋能 · 青春力行")

# 设置两个标签页
tab1, tab2 = st.tabs(["👴 长辈求助端", "💻 青年研判端"])

with tab1:
    st.header("遇到可疑信息？发给子女看看")
    # 老人输入框
    input_text = st.text_area("请将可疑短信或链接粘贴到这里：", height=150)
    
    if st.button("发送给子女研判", type="primary", use_container_width=True):
        if input_text:
            st.session_state['old_text'] = input_text
            st.success("✅ 已发送！请等待子女的回复...")
        else:
            st.warning("请先输入可疑内容哦！")

with tab2:
    st.header("待处理的求助")
    if 'old_text' in st.session_state:
        st.info(f"📩 收到长辈求助：\n\n**{st.session_state['old_text']}**")
        
        if st.button("🤖 启动 AI 分析"):
            with st.spinner("AI 正在分析中..."):
                # 这里就是刚才跑通的逻辑
                try:
                    response = client.chat.completions.create(
                        model="glm-4-flash-250414",
                        messages=[
                            {"role": "system", "content": "你是一个反诈专家。只返回JSON格式，不要其他文字：{\"risk_level\":\"高风险/中/低\",\"reply\":\"大白话防骗回复\"}"},
                            {"role": "user", "content": st.session_state['old_text']}
                        ],
                        temperature=0.1
                    )
                    result_str = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
                    result_json = json.loads(result_str)
                    
                    # 展示结果
                    st.error(f"🚨 风险等级：{result_json['risk_level']}")
                    st.write("👇 **建议回复长辈的话：**")
                    st.code(result_json['reply'], language="text")
                    
                except Exception as e:
                    st.error(f"分析失败：{e}")
    else:
        st.write("当前暂无求助记录。")