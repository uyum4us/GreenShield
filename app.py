import streamlit as st
import json
import requests
from supabase import create_client
from zhipuai import ZhipuAI

# ================= 配置区（Secrets） =================
st.set_page_config(page_title="青盾防诈系统", page_icon="🛡️")
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_ANON_KEY"]
ZHIPU_API_KEY = st.secrets.get("ZHIPU_API_KEY", "")
PUSHPLUS_TOKEN = st.secrets.get("PUSHPLUS_TOKEN", "")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
client = ZhipuAI(api_key=ZHIPU_API_KEY) if ZHIPU_API_KEY else None

# ================= AI 研判（沿用你初版风格） =================
def ai_analyze(content: str) -> tuple[str, str]:
    """返回 (风险等级, 建议回复)。AI 不可用时自动降级为关键词规则，永不停摆。"""
    if client:
        try:
            resp = client.chat.completions.create(
                model="glm-4-flash-250414",
                messages=[
                    {"role": "system", "content": "你是一个反诈专家。只返回JSON格式，不要其他文字：{\"risk_level\":\"高风险/中/低\",\"reply\":\"大白话防骗回复，60字以内，带明确行动指令，语气像子女\"}"},
                    {"role": "user", "content": content},
                ],
                temperature=0.1,
            )
            s = resp.choices[0].message.content.replace("```json", "").replace("```", "").strip()
            j = json.loads(s)
            return j.get("risk_level", "中"), (j.get("reply") or FALLBACK_REPLY).strip()
        except Exception:
            pass  # 网络/额度问题 → 走关键词兜底
    hits = [w for w in ["转账", "汇款", "打钱", "安全账户", "验证码", "公检法",
                        "刷单", "解冻", "屏幕共享", "中奖", "退款", "银行卡"] if w in content]
    if hits:
        return "高风险", f"这条提到了{'、'.join(hits[:3])}，八成是骗子。先别转账、别报验证码，把电话挂了等我。"
    return "中", "先别点这个链接、别扫码。截图发给我，我确认完你再操作。"

def push_wechat(elder_name: str):
    if PUSHPLUS_TOKEN:
        try:
            requests.post("https://www.pushplus.plus/send", json={
                "token": PUSHPLUS_TOKEN, "title": f"🛡️ {elder_name}发来求助",
                "content": "打开子女工作台查看回复"}, timeout=10)
        except Exception:
            pass

# ================= 长辈求助端 =================
def render_elder():
    st.title("🛡️ 青盾 · 一键求助")
    st.write("遇到可疑信息？发给子女看看")
    if "elder_uid" not in st.session_state:
        res = supabase.auth.sign_in_anonymously()
        st.session_state.elder_uid = res.user.id

    input_text = st.text_area("请将可疑短信或链接粘贴到这里：", height=150)
    if st.button("发送给子女研判", type="primary", use_container_width=True):
        if input_text.strip():
            supabase.table("requests").insert({
                "elder_uid": st.session_state.elder_uid,
                "elder_name": st.session_state.get("elder_name", "家人"),
                "content": input_text,
            }).execute()
            push_wechat(st.session_state.get("elder_name", "家人"))
            st.success("✅ 已发送！请等待子女的回复... 在那之前：先别转账、别报验证码。")
        else:
            st.warning("请先输入可疑内容哦！")

    st.markdown("---")
    st.subheader("📬 子女的回复：")
    rows = supabase.table("requests").select("*, replies(*)") \
        .eq("elder_uid", st.session_state.elder_uid) \
        .order("created_at", desc=True).limit(20).execute().data
    for r in rows:
        st.write(f"**我问：** {r['content']}")
        for rep in r.get("replies") or []:
            st.success(f"子女回复：{rep['content']}")
        st.divider()
    if rows:
        st.button("🔄 看看子女回了没", use_container_width=True)

# ================= 青年研判端（只有你能进） =================
def render_desk():
    if not st.session_state.get("desk_uid"):
        st.title("🛡️ 子女端登录")
        with st.form("login"):
            email = st.text_input("邮箱")
            pw = st.text_input("密码", type="password")
            if st.form_submit_button("登录", use_container_width=True, type="primary"):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": pw})
                    st.session_state.desk_uid = res.user.id
                    st.rerun()
                except Exception:
                    st.error("账号或密码不对")
        st.stop()

    st.title("🛡️ 青盾 · 子女工作台")
    st.write("数智赋能 · 青春力行")
    if st.button("🔄 刷新待处理队列", type="primary"):
        st.rerun()

    if "drafts" not in st.session_state:
        st.session_state.drafts = {}

    rows = supabase.table("requests").select("*, replies(*)") \
        .neq("status", "closed").order("created_at", desc=True).execute().data
    for r in rows:
        st.markdown(f"### 📩 {r['elder_name']}　`{r['status']}`　{r['created_at'][:19]}")
        st.info(r["content"])

        if r["id"] not in st.session_state.drafts:      # 每条只分析一次
            st.session_state.drafts[r["id"]] = ai_analyze(r["content"])
        risk, draft = st.session_state.drafts[r["id"]]
        (st.error if risk == "高风险" else st.warning)(f"🚨 风险等级：{risk}")
        st.write("👇 **建议回复长辈的话（可修改）：**")
        st.code(draft, language="text")

        for rep in r.get("replies") or []:
            st.write(f"↩️ 已回复：{rep['content']}")
        final = st.text_input("最终回复内容", key=f"in{r['id']}", value=draft)
        c1, c2 = st.columns(2)
        if c1.button("📤 确认并发送给长辈", key=f"s{r['id']}") and final.strip():
            supabase.table("replies").insert({
                "request_id": r["id"], "author_uid": st.session_state.desk_uid,
                "role": "desk", "content": final}).execute()
            supabase.table("requests").update({"status": "responded"}).eq("id", r["id"]).execute()
            st.rerun()
        if c2.button("✔️ 标记已解决", key=f"c{r['id']}"):
            supabase.table("requests").update({"status": "closed"}).eq("id", r["id"]).execute()
            st.rerun()
        st.divider()

# ================= 入口分流 =================
mode = st.query_params.get("mode", "elder")
if mode == "desk":
    render_desk()
else:
    render_elder()
