import json
from datetime import datetime, timedelta, timezone

import requests
import streamlit as st
import extra_streamlit_components as stx
from supabase import create_client

# 智谱包出问题也不拖垮应用（自动降级为关键词兜底）
try:
    from zhipuai import ZhipuAI
except Exception:
    ZhipuAI = None

# ================= 基础配置 =================
st.set_page_config(page_title="青盾防诈系统", page_icon="🛡️")
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_ANON_KEY"]
ZHIPU_API_KEY = st.secrets.get("ZHIPU_API_KEY", "")
PUSHPLUS_TOKEN = st.secrets.get("PUSHPLUS_TOKEN", "")
ELDER_EMAIL = st.secrets.get("ELDER_EMAIL", "")
ELDER_PASSWORD = st.secrets.get("ELDER_PASSWORD", "")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
client = ZhipuAI(api_key=ZHIPU_API_KEY) if (ZHIPU_API_KEY and ZhipuAI) else None

cookies = stx.CookieManager(key="qs_cookies")
COOKIE_DAYS = 365

# Cookie 组件第一次运行时还没回传数据，先空跑一轮再判断
if not st.session_state.get("ck_settled"):
    st.session_state.ck_settled = True
    st.rerun()


def save_cookie(name: str, value: str) -> None:
    try:
        cookies.set(name, value, path="/",
                    expires_at=datetime.now(timezone.utc) + timedelta(days=COOKIE_DAYS))
    except Exception:
        pass


def remember(res) -> str:
    st.session_state.access_token = res.session.access_token
    st.session_state.refresh_token = res.session.refresh_token
    st.session_state.auth_uid = res.user.id
    return res.user.id


def auth_elder() -> str:
    """长辈端身份：固定家庭账号。Cookie 只是加速，失效了就用账号密码重登，身份永远不变。"""
    role = "elder"
    if st.session_state.get("access_token") and st.session_state.get("auth_role") == role:
        try:
            supabase.auth.set_session(st.session_state["access_token"],
                                      st.session_state["refresh_token"])
            return st.session_state["auth_uid"]
        except Exception:
            st.session_state.pop("access_token", None)

    raw = cookies.get("qs_elder")
    if raw and "|" in raw:
        try:
            res = supabase.auth.refresh_session(raw.split("|")[1])
            st.session_state.auth_role = role
            return remember(res)
        except Exception:
            pass

    # 关键兜底：固定家庭账号重新登录，不依赖任何会过期的令牌
    if ELDER_EMAIL and ELDER_PASSWORD:
        try:
            res = supabase.auth.sign_in_with_password(
                {"email": ELDER_EMAIL, "password": ELDER_PASSWORD})
            st.session_state.auth_role = role
            uid = remember(res)
            save_cookie("qs_elder", f"{uid}|{res.session.refresh_token}")
            return uid
        except Exception as e:
            st.error(f"长辈端登录失败，请检查 Secrets 里的 ELDER_EMAIL / ELDER_PASSWORD（{e}）")
            st.stop()

    # 没配家庭账号时退回匿名身份（临时可用，但刷新后历史会丢）
    try:
        res = supabase.auth.sign_in_anonymously()
        st.session_state.auth_role = role
        return remember(res)
    except Exception as e:
        st.error(f"暂时连不上服务器，请稍后重试（{e}）")
        st.stop()


def auth_desk():
    """子女端身份：你自己的账号，必须有密码才能进。"""
    role = "desk"
    if st.session_state.get("access_token") and st.session_state.get("auth_role") == role:
        try:
            supabase.auth.set_session(st.session_state["access_token"],
                                      st.session_state["refresh_token"])
            return st.session_state["auth_uid"]
        except Exception:
            st.session_state.pop("access_token", None)

    raw = cookies.get("qs_desk")
    if raw and "|" in raw:
        try:
            res = supabase.auth.refresh_session(raw.split("|")[1])
            st.session_state.auth_role = role
            return remember(res)
        except Exception:
            pass
    return None


# ================= AI 研判 =================
def ai_analyze(content: str) -> tuple[str, str]:
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
            return j.get("risk_level", "中"), (j.get("reply") or "先别操作，等我确认。").strip()
        except Exception:
            pass
    hits = [w for w in ["转账", "汇款", "打钱", "安全账户", "验证码", "公检法",
                        "刷单", "解冻", "屏幕共享", "中奖", "退款", "银行卡", "卡号", "领奖"] if w in content]
    if hits:
        return "高风险", f"这条提到了{'、'.join(hits[:3])}，八成是骗子。先别转账、别给卡号和验证码，把电话挂了等我。"
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

    auth_elder()

    saved_name = cookies.get("qs_name") or ""
    me = st.text_input("怎么称呼你（填一次，以后自动记住）", value=saved_name).strip()
    if me and me != saved_name:
        save_cookie("qs_name", me)
    me = me or "家人"
    st.caption(f"这里是「{me}」的求助记录，退出再进来也能看到")

    input_text = st.text_area("请将可疑短信或链接粘贴到这里：", height=150)
    if st.button("发送给子女研判", type="primary", use_container_width=True):
        if input_text.strip():
            try:
                supabase.table("requests").insert({
                    "elder_uid": st.session_state.auth_uid,
                    "elder_name": me,
                    "content": input_text,
                }).execute()
                save_cookie("qs_name", me)
                push_wechat(me)
                st.success("✅ 已发送！请等待子女的回复... 在那之前：先别转账、别报验证码。")
            except Exception as e:
                st.error(f"发送失败：{e}")
        else:
            st.warning("请先输入可疑内容哦！")

    st.markdown("---")
    st.subheader("📬 我的求助和子女的回复")
    try:
        rows = supabase.table("requests").select("*, replies(*)") \
            .eq("elder_name", me).order("created_at", desc=True).limit(30).execute().data
    except Exception as e:
        st.error(f"读取记录失败：{e}")
        rows = []

    if not rows:
        st.caption("还没有求助记录，发第一条试试")
    for r in rows:
        st.markdown(f"**🙋 我问：** {r['content']}")
        reps = r.get("replies") or []
        if reps:
            for rep in reps:
                st.success(f"子女回复：{rep['content']}")
        else:
            st.caption("⏳ 等子女回复中…")
        st.caption(f"发送时间：{r['created_at'][:19].replace('T', ' ')}")
        st.divider()

    if rows:
        st.button("🔄 看看有没有新回复", use_container_width=True)


# ================= 青年研判端 =================
def render_desk():
    uid = auth_desk()
    if not uid:
        st.title("🛡️ 子女端登录")
        with st.form("login"):
            email = st.text_input("邮箱")
            pw = st.text_input("密码", type="password")
            if st.form_submit_button("登录", use_container_width=True, type="primary"):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": pw})
                    st.session_state.auth_role = "desk"
                    uid = remember(res)
                    save_cookie("qs_desk", f"{uid}|{res.session.refresh_token}")
                    st.rerun()
                except Exception:
                    st.error("账号或密码不对")
        st.stop()

    st.title("🛡️ 青盾 · 子女工作台")
    st.write("数智赋能 · 青春力行")

    c1, c2 = st.columns([3, 1])
    if c2.button("退出登录"):
        for k in ("access_token", "refresh_token", "auth_uid", "auth_role", "drafts"):
            st.session_state.pop(k, None)
        try:
            cookies.delete("qs_desk")
        except Exception:
            pass
        st.rerun()
    if c1.button("🔄 刷新待处理队列", type="primary"):
        st.rerun()

    if "drafts" not in st.session_state:
        st.session_state.drafts = {}

    try:
        rows = supabase.table("requests").select("*, replies(*)") \
            .neq("status", "closed").order("created_at", desc=True).execute().data
    except Exception as e:
        st.error(f"读取队列失败：{e}")
        rows = []

    if not rows:
        st.info("当前暂无待处理求助。")

    for r in rows:
        st.markdown(f"### 📩 {r['elder_name']}　`{r['status']}`　{r['created_at'][:19].replace('T', ' ')}")
        st.info(r["content"])

        if r["id"] not in st.session_state.drafts:
            st.session_state.drafts[r["id"]] = ai_analyze(r["content"])
        risk, draft = st.session_state.drafts[r["id"]]
        (st.error if risk == "高风险" else st.warning)(f"🚨 风险等级：{risk}")

        for rep in r.get("replies") or []:
            st.write(f"↩️ 已回复：{rep['content']}")

        st.write("👇 **给长辈的话（AI 草稿，可随意修改）：**")
        in_key = f"in{r['id']}"
        if in_key not in st.session_state:
            st.session_state[in_key] = draft
        final = st.text_input("回复内容", key=in_key, label_visibility="collapsed")

        b1, b2 = st.columns(2)
        if b1.button("📤 确认并发送给长辈", key=f"s{r['id']}", type="primary"):
            if final.strip():
                try:
                    supabase.table("replies").insert({
                        "request_id": r["id"], "author_uid": uid,
                        "role": "desk", "content": final.strip()}).execute()
                    supabase.table("requests").update({"status": "responded"}) \
                        .eq("id", r["id"]).execute()
                    st.session_state.drafts.pop(r["id"], None)
                    st.session_state.pop(in_key, None)
                    st.rerun()
                except Exception as e:
                    st.error(f"发送失败：{e}")
            else:
                st.warning("回复内容不能为空")
        if b2.button("✔️ 标记已解决", key=f"c{r['id']}"):
            try:
                supabase.table("requests").update({"status": "closed"}).eq("id", r["id"]).execute()
                st.session_state.drafts.pop(r["id"], None)
                st.session_state.pop(in_key, None)
                st.rerun()
            except Exception as e:
                st.error(f"操作失败：{e}")
        st.divider()


# ================= 入口分流 =================
mode = st.query_params.get("mode", "elder")
if mode == "desk":
    render_desk()
else:
    render_elder()
