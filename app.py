import os, math, requests
from datetime import datetime, timezone
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Football AI Pro", page_icon="🏈", layout="wide")

def secret(name, default=""):
    v = os.getenv(name)
    if v:
        return v
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

ODDS_API_KEY = secret("ODDS_API_KEY")
TELEGRAM_BOT_TOKEN = secret("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = secret("TELEGRAM_CHAT_ID")

SPORTS = {
    "NFL": "americanfootball_nfl",
    "NCAAF": "americanfootball_ncaaf",
}

def clamp(x, lo=0, hi=100):
    return max(lo, min(hi, x))

def american_to_decimal(odds):
    return 1 + odds / 100 if odds > 0 else 1 + 100 / abs(odds)

def implied_prob(odds):
    return 100 / (odds + 100) if odds > 0 else abs(odds) / (abs(odds) + 100)

def fair_probability(score):
    return clamp(50 + (score - 50) * .30, 45, 65) / 100

def kelly_fraction(p, decimal_odds):
    b = decimal_odds - 1
    if b <= 0: return 0
    return max(0, (b*p - (1-p))/b)

def grade(score):
    if score >= 88: return "🔥 ELITE"
    if score >= 80: return "✅ STRONG"
    if score >= 70: return "🟡 PLAYABLE"
    return "⛔ PASS"

def football_score(side, model, qb, trench, explosive, pace, defense,
                   injury, weather_under, sharp, line_value, script, market="Whole Game"):
    weights = {"model":.22,"qb":.12,"trench":.10,"explosive":.09,"pace":.08,
               "defense":.10,"injury":.07,"weather":.05,"sharp":.09,"line":.08}
    f = {"model":model,"qb":qb,"trench":trench,"explosive":explosive,"pace":pace,
         "defense":defense,"injury":injury,"weather":weather_under,"sharp":sharp,"line":line_value}
    raw = 50 + sum((f[k]-50)*w for k,w in weights.items())
    raw += (script-50) * (.08 if market=="1H" else .05 if market=="2H" else .04)
    if side == "Under":
        raw += (defense-50)*.07 + (weather_under-50)*.07
        raw -= (pace-50)*.05 + (explosive-50)*.04
    elif side == "Over":
        raw += (pace-50)*.08 + (explosive-50)*.06
        raw -= (weather_under-50)*.08 + (defense-50)*.04
    return round(clamp(raw),1)

@st.cache_data(ttl=90)
def get_odds(league):
    if not ODDS_API_KEY:
        return []
    url = f"https://api.the-odds-api.com/v4/sports/{SPORTS[league]}/odds/"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "h2h,spreads,totals",
        "oddsFormat": "american",
        "dateFormat": "iso",
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def consensus_games(raw):
    rows = []
    for g in raw:
        home, away = g.get("home_team",""), g.get("away_team","")
        spreads, totals, h2h = [], [], []
        for book in g.get("bookmakers",[]):
            for m in book.get("markets",[]):
                if m["key"] == "totals":
                    for o in m["outcomes"]:
                        if o["name"] == "Under":
                            totals.append((o.get("point"), o.get("price"), book.get("title")))
                elif m["key"] == "spreads":
                    for o in m["outcomes"]:
                        if o["name"] == home:
                            spreads.append((o.get("point"), o.get("price"), book.get("title")))
                elif m["key"] == "h2h":
                    for o in m["outcomes"]:
                        if o["name"] == home:
                            h2h.append((o.get("price"), book.get("title")))
        def median_num(items, idx=0):
            vals=[x[idx] for x in items if x[idx] is not None]
            return float(pd.Series(vals).median()) if vals else None
        rows.append({
            "Game": f"{away} @ {home}",
            "Start": g.get("commence_time",""),
            "Home": home, "Away": away,
            "Total": median_num(totals,0),
            "Under Odds": int(round(median_num(totals,1))) if median_num(totals,1) is not None else None,
            "Home Spread": median_num(spreads,0),
            "Home Spread Odds": int(round(median_num(spreads,1))) if median_num(spreads,1) is not None else None,
            "Home ML": int(round(median_num(h2h,0))) if median_num(h2h,0) is not None else None,
            "Books": max(len(totals), len(spreads), len(h2h)),
        })
    return rows

def build_pick(game, market, bet_type, side, line, odds, score, bankroll, cap):
    dec=american_to_decimal(odds); p=fair_probability(score); imp=implied_prob(odds)
    ev=p*(dec-1)-(1-p); k=min(kelly_fraction(p,dec),cap/100)
    stake=bankroll*k if score>=80 and ev>0 else 0
    return {"Game":game,"Market":market,"Type":bet_type,"Pick":f"{side} {line:g}" if line else side,
            "Odds":odds,"AI Score":score,"Grade":grade(score),"Win Prob":f"{p*100:.1f}%",
            "Edge":f"{(p-imp)*100:+.1f}%","EV":f"{ev*100:+.1f}%","Kelly Stake":f"${stake:,.0f}"}

def telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False, "Thiếu TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID."
    url=f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    r=requests.post(url,json={"chat_id":TELEGRAM_CHAT_ID,"text":text},timeout=15)
    return r.ok, r.text[:200]

st.title("🏈 Football AI Pro — NFL + NCAAF")
st.caption("Live odds board • Best Bets • Manual Analyzer • Kelly/EV • Telegram")

with st.sidebar:
    st.header("⚙️ Settings")
    bankroll=st.number_input("Bankroll ($)",50.0,1_000_000.0,1000.0,50.0)
    kelly_cap=st.slider("Kelly cap (%)",.25,5.0,2.0,.25)
    min_score=st.slider("Minimum AI Score",65,95,80)
    st.caption("API: " + ("✅ connected" if ODDS_API_KEY else "⚠️ manual mode"))
    st.warning("AI Score là mô hình chấm điểm, không bảo đảm kết quả. Không chase loss / không all-in.")

if "picks" not in st.session_state: st.session_state.picks=[]

tabs=st.tabs(["⚡ Auto Board","⭐ Best Bets","🏈 Manual Analyzer","🔥 2H Live","📈 Sharp/RLM","📨 Telegram"])

with tabs[0]:
    a,b=st.columns([1,1])
    league=a.selectbox("League",["NFL","NCAAF"])
    refresh=b.button("🔄 Refresh odds",use_container_width=True)
    if refresh: st.cache_data.clear()
    if not ODDS_API_KEY:
        st.info("Thêm ODDS_API_KEY vào Render Environment để bật lịch + odds tự động.")
    else:
        try:
            games=consensus_games(get_odds(league))
            if not games:
                st.warning("API chưa trả về trận nào cho league này.")
            else:
                df=pd.DataFrame(games)
                st.dataframe(df[["Game","Start","Total","Under Odds","Home Spread","Home ML","Books"]],
                             use_container_width=True,hide_index=True)
                st.caption("Consensus = median từ các sportsbook API trả về; không phải 'sharp money'.")
                options=[x["Game"] for x in games]
                game_name=st.selectbox("Analyze game",options)
                g=next(x for x in games if x["Game"]==game_name)
                if g["Total"] is not None and g["Under Odds"] is not None:
                    c1,c2,c3,c4=st.columns(4)
                    defense=c1.slider("Defense edge",0,100,60,key="auto_def")
                    pace=c2.slider("Slow pace edge",0,100,60,key="auto_pace")
                    weather=c3.slider("Weather favors UNDER",0,100,50,key="auto_weather")
                    sharp=c4.slider("Market signal",0,100,50,key="auto_sharp")
                    # Invert pace input into the existing pace convention: higher = more possessions.
                    pace_model=100-pace
                    score=football_score("Under",65,50,55,45,pace_model,defense,50,weather,sharp,60,55)
                    st.metric("UNDER Score",f"{score}/100",grade(score))
                    if st.button("➕ Add UNDER to Best Bets",type="primary"):
                        row=build_pick(g["Game"],"Whole Game","Total","Under",g["Total"],g["Under Odds"],
                                       score,bankroll,kelly_cap)
                        st.session_state.picks.append(row); st.success("Đã thêm.")
                else:
                    st.warning("Không có total/Under odds để phân tích.")
        except Exception as e:
            st.error(f"Odds API error: {e}")

with tabs[1]:
    if not st.session_state.picks:
        st.info("Chưa có pick. Dùng Auto Board hoặc Manual Analyzer.")
    else:
        df=pd.DataFrame(st.session_state.picks).sort_values("AI Score",ascending=False)
        show=df[df["AI Score"]>=min_score]
        st.dataframe(show,use_container_width=True,hide_index=True)
        if not show.empty:
            b=show.iloc[0]
            st.success(f"BEST BET: {b['Game']} — {b['Pick']} • {b['AI Score']}/100")
        if st.button("Clear picks"):
            st.session_state.picks=[]; st.rerun()

with tabs[2]:
    c1,c2,c3,c4=st.columns(4)
    m_league=c1.selectbox("League ",["NFL","NCAAF"])
    matchup=c2.text_input("Matchup","SEA vs ARI")
    market=c3.selectbox("Market",["1H","2H","Whole Game"])
    bet_type=c4.selectbox("Bet type",["Spread","Total","Moneyline"])
    c1,c2,c3=st.columns(3)
    if bet_type=="Total":
        side=c1.selectbox("Side",["Under","Over"]); line=c2.number_input("Line",.5,100.0,44.5,.5)
    elif bet_type=="Spread":
        side=c1.text_input("Team / Side","SEA"); line=c2.number_input("Spread",-40.0,40.0,-2.5,.5)
    else:
        side=c1.text_input("Team","SEA"); line=0.0
    odds=c3.number_input("American odds",-500,500,-110,5)
    vals=[]
    names=["Power/model","QB","OL/DL","Explosive","Pace","Defense","Injury/depth","Weather favors UNDER","Sharp signal","Line value","Game script"]
    defaults=[70,65,65,60,50,65,55,50,60,65,60]
    cols=st.columns(4)
    for i,(n,d) in enumerate(zip(names,defaults)):
        vals.append(cols[i%4].slider(n,0,100,d,key=f"manual_{i}"))
    if st.button("🚀 ANALYZE",type="primary",use_container_width=True):
        score=football_score(side,*vals,market=market)
        row=build_pick(matchup,market,bet_type,side,line,odds,score,bankroll,kelly_cap)
        st.session_state.picks.append(row)
        st.success(f"{grade(score)} — {score}/100")
        st.dataframe(pd.DataFrame([row]),hide_index=True,use_container_width=True)

with tabs[3]:
    st.subheader("🔥 2H Live")
    st.caption("Nhập dữ liệu halftime + line 2H hiện tại. Bản này giữ manual live vì nguồn play-by-play/live odds cần API riêng.")
    c1,c2,c3,c4=st.columns(4)
    lgame=c1.text_input("Game ","SEA vs ARI")
    lside=c2.selectbox("2H Total",["Under","Over"])
    lline=c3.number_input("2H line",.5,70.0,23.5,.5)
    lodds=c4.number_input("2H odds",-500,500,-110,5)
    c1,c2,c3,c4=st.columns(4)
    pts=c1.number_input("1H points",0,100,20)
    poss=c2.number_input("Possessions/team",1,20,6)
    ypp=c3.number_input("Combined yards/play",0.0,15.0,5.4,.1)
    turnovers=c4.number_input("Turnovers",0,10,1)
    c1,c2,c3,c4=st.columns(4)
    rz=c1.number_input("Red-zone trips",0,15,3)
    expl=c2.number_input("Explosive plays",0,30,4)
    sacks=c3.number_input("Sacks",0,20,3)
    weather=c4.slider("2H weather UNDER",0,100,50)
    tempo=clamp(50+(poss-6)*6)
    expedge=clamp(50+(expl-4)*4+(ypp-5.5)*7)
    defense=clamp(55+sacks*2-max(rz-3,0)*3)
    if st.button("🔥 ANALYZE 2H",type="primary"):
        score=football_score(lside,65,50,55,expedge,tempo,defense,50,weather,60,60,60,market="2H")
        row=build_pick(lgame,"2H","Total",lside,lline,lodds,score,bankroll,kelly_cap)
        st.session_state.picks.append(row)
        st.dataframe(pd.DataFrame([row]),hide_index=True,use_container_width=True)

with tabs[4]:
    st.subheader("📈 Sharp / Reverse Line Movement")
    c1,c2,c3,c4=st.columns(4)
    opening=c1.number_input("Opening line",-100.0,100.0,44.5,.5)
    current=c2.number_input("Current line",-100.0,100.0,43.5,.5)
    tickets=c3.slider("Tickets %",0,100,65)
    handle=c4.slider("Handle %",0,100,78)
    move=current-opening; gap=handle-tickets
    score=clamp(50+abs(move)*8+max(gap,0)*.8)
    st.metric("Market Signal",f"{score:.0f}/100",f"Move {move:+.1f}")
    if abs(move)>=1 and gap>=10: st.success("🔥 Strong steam/sharp-style signal")
    elif abs(move)>=.5 or gap>=8: st.info("✅ Market lean")
    else: st.warning("🟡 Signal chưa rõ")
    st.caption("Tickets/handle phải đến từ nguồn dữ liệu thật; app không tự gọi dữ liệu này nếu chưa cấu hình provider.")

with tabs[5]:
    st.subheader("📨 Telegram")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        st.success("Telegram configured.")
        msg=st.text_area("Message","🏈 Football AI Pro test alert")
        if st.button("Send test"):
            ok,detail=telegram(msg)
            st.success("Sent!") if ok else st.error(detail)
    else:
        st.info("Thêm TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID vào Render Environment.")
