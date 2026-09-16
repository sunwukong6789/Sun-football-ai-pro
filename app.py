import os, math, json, hashlib, requests
from datetime import datetime, timezone
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Football AI Pro v21 ELITE", page_icon="🏈", layout="wide")

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

SPORTS = {"NFL": "americanfootball_nfl", "NCAAF": "americanfootball_ncaaf"}

def clamp(x, lo=0, hi=100): return max(lo, min(hi, x))

def american_to_decimal(odds):
    if not odds: return 1.0
    return 1 + odds / 100 if odds > 0 else 1 + 100 / abs(odds)

def implied_prob(odds):
    if odds is None: return 0.5
    return 100/(odds+100) if odds > 0 else abs(odds)/(abs(odds)+100)

def no_vig_two_way(p1, p2):
    s=p1+p2
    return (p1/s, p2/s) if s else (.5,.5)

def kelly_fraction(p, dec):
    b=dec-1
    return max(0, (b*p-(1-p))/b) if b > 0 else 0

def grade(score):
    if score >= 88: return "💎 ELITE"
    if score >= 82: return "🔥 STRONG"
    if score >= 76: return "✅ PLAYABLE"
    return "⛔ PASS"

def pick_key(row):
    return hashlib.sha1(f"{row.get('Game')}|{row.get('Market')}|{row.get('Pick')}".encode()).hexdigest()[:16]

def telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False, "Thiếu TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID."
    try:
        r=requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id":TELEGRAM_CHAT_ID,"text":text},
            timeout=15
        )
        return r.ok, r.text[:250]
    except Exception as e:
        return False, str(e)

def alert_text(row):
    return (
        "🏈 FOOTBALL AI PRO v21 ELITE\n"
        f"{row['League']} • {row['Market']}\n"
        f"{row['Game']}\n\n"
        f"💎 PICK: {row['Pick']} ({row['Odds']:+d})\n"
        f"⭐ Edge Score: {row['AI Score']:.1f}/100 • {row['Grade']}\n"
        f"📊 Market edge: {row['Edge']}\n"
        f"💰 Suggested stake: {row['Kelly Stake']}\n\n"
        f"Why: {row.get('Reason','Market consensus + price/line value')}"
    )

@st.cache_data(ttl=60)
def get_odds(league):
    if not ODDS_API_KEY: return []
    url=f"https://api.the-odds-api.com/v4/sports/{SPORTS[league]}/odds/"
    params={
        "apiKey":ODDS_API_KEY, "regions":"us",
        "markets":"h2h,spreads,totals",
        "oddsFormat":"american","dateFormat":"iso"
    }
    r=requests.get(url,params=params,timeout=20)
    r.raise_for_status()
    return r.json()

def median(vals):
    vals=[v for v in vals if v is not None]
    return float(pd.Series(vals).median()) if vals else None

def market_rows(raw, league):
    rows=[]
    for g in raw:
        home,away=g.get("home_team",""),g.get("away_team","")
        totals={"Over":[],"Under":[]}
        spreads={home:[],away:[]}
        h2h={home:[],away:[]}
        for book in g.get("bookmakers",[]):
            title=book.get("title","")
            for m in book.get("markets",[]):
                for o in m.get("outcomes",[]):
                    name=o.get("name")
                    if m.get("key")=="totals" and name in totals:
                        totals[name].append((o.get("point"),o.get("price"),title))
                    elif m.get("key")=="spreads" and name in spreads:
                        spreads[name].append((o.get("point"),o.get("price"),title))
                    elif m.get("key")=="h2h" and name in h2h:
                        h2h[name].append((o.get("price"),title))
        tline=median([x[0] for x in totals["Under"]])
        under=median([x[1] for x in totals["Under"]])
        over=median([x[1] for x in totals["Over"]])
        hs=median([x[0] for x in spreads[home]])
        asp=median([x[0] for x in spreads[away]])
        hso=median([x[1] for x in spreads[home]])
        aso=median([x[1] for x in spreads[away]])
        hml=median([x[0] for x in h2h[home]])
        aml=median([x[0] for x in h2h[away]])
        rows.append({
            "League":league,"Game":f"{away} @ {home}","Start":g.get("commence_time",""),
            "Home":home,"Away":away,"Total":tline,
            "Under Odds":round(under) if under is not None else None,
            "Over Odds":round(over) if over is not None else None,
            "Home Spread":hs,"Away Spread":asp,
            "Home Spread Odds":round(hso) if hso is not None else None,
            "Away Spread Odds":round(aso) if aso is not None else None,
            "Home ML":round(hml) if hml is not None else None,
            "Away ML":round(aml) if aml is not None else None,
            "Books":max(len(totals["Under"]),len(spreads[home]),len(h2h[home]))
        })
    return rows

def market_score(odds, books=1, bias=0):
    # Conservative market-quality score. It is NOT a historical win probability.
    price=implied_prob(odds)
    price_quality=clamp(100-abs(price-.5)*150)
    depth=clamp(45+books*4,45,85)
    return clamp(.55*price_quality+.45*depth+bias)

def make_pick(league,game,market,kind,side,line,odds,score,bankroll,cap,reason):
    dec=american_to_decimal(odds)
    imp=implied_prob(odds)
    # Conservative estimated p: only small adjustment from market probability.
    p=clamp(imp*100+(score-75)*0.12, 45, 65)/100
    ev=p*(dec-1)-(1-p)
    k=min(kelly_fraction(p,dec),cap/100)
    stake=bankroll*k if score>=82 and ev>0 else 0
    pick=f"{side} {line:g}" if line not in (None,0) else side
    return {
        "League":league,"Game":game,"Market":market,"Type":kind,"Pick":pick,
        "Odds":int(odds),"AI Score":round(score,1),"Grade":grade(score),
        "Est. Prob":f"{p*100:.1f}%","Market Prob":f"{imp*100:.1f}%",
        "Edge":f"{(p-imp)*100:+.1f}%","EV":f"{ev*100:+.1f}%",
        "Kelly Stake":f"${stake:,.0f}","Reason":reason
    }

def auto_candidates(g, under_priority=4):
    out=[]
    books=g["Books"]
    if g["Total"] is not None:
        for side,key,bias in [("Under","Under Odds",under_priority),("Over","Over Odds",0)]:
            odds=g.get(key)
            if odds is not None:
                score=market_score(odds,books,bias)
                # Avoid manufacturing a strong signal from market price alone.
                reason=("UNDER priority + sportsbook consensus depth" if side=="Under"
                        else "Sportsbook consensus depth; OVER included only when its score clears filter")
                out.append(make_pick(g["League"],g["Game"],"Whole Game","Total",
                                     side,g["Total"],odds,score,bankroll,kelly_cap,reason))
    for team,line,odds in [
        (g["Home"],g["Home Spread"],g["Home Spread Odds"]),
        (g["Away"],g["Away Spread"],g["Away Spread Odds"])
    ]:
        if line is not None and odds is not None:
            score=market_score(odds,books,-2)
            out.append(make_pick(g["League"],g["Game"],"Whole Game","Spread",
                                 team,line,odds,score,bankroll,kelly_cap,
                                 "Spread consensus + price quality"))
    for team,odds in [(g["Home"],g["Home ML"]),(g["Away"],g["Away ML"])]:
        if odds is not None:
            score=market_score(odds,books,-4)
            out.append(make_pick(g["League"],g["Game"],"Whole Game","Moneyline",
                                 team,None,odds,score,bankroll,kelly_cap,
                                 "Moneyline consensus + price quality"))
    return out

st.title("🏈 Football AI Pro v21 ELITE — NFL + NCAAF")
st.caption("Pregame • selective Best Bets • UNDER priority • sides/OVER when stronger • Telegram")

with st.sidebar:
    st.header("⚙️ Control Center")
    bankroll=st.number_input("Bankroll ($)",50.0,1_000_000.0,1000.0,50.0)
    kelly_cap=st.slider("Max Kelly stake (%)",.25,3.0,1.0,.25)
    min_score=st.slider("Elite alert threshold",70,95,82)
    max_picks=st.slider("Max picks shown",1,5,3)
    under_priority=st.slider("UNDER priority",0,8,4)
    st.write("Odds API", "🟢 Connected" if ODDS_API_KEY else "🟠 Manual")
    st.write("Telegram", "🟢 Ready" if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID else "🟠 Not configured")
    st.info("Edge Score = ranking signal, không phải xác suất thắng. Bot chỉ alert ít kèo vượt threshold.")

if "best" not in st.session_state: st.session_state.best=[]
if "sent" not in st.session_state: st.session_state.sent=set()
if "history" not in st.session_state: st.session_state.history=[]

tabs=st.tabs(["⚡ Auto Scanner","💎 Best Bets","🏈 Manual","🔥 Live / 2H","📈 Line Move","📨 Telegram"])

with tabs[0]:
    c1,c2,c3=st.columns([1,1,1])
    league=c1.selectbox("League",["NFL","NCAAF"])
    scan=c2.button("🔎 Scan market",use_container_width=True,type="primary")
    refresh=c3.button("🔄 Refresh API",use_container_width=True)
    if refresh: st.cache_data.clear()

    if not ODDS_API_KEY:
        st.warning("Add ODDS_API_KEY in Render Environment.")
    else:
        try:
            games=market_rows(get_odds(league),league)
            if games:
                df=pd.DataFrame(games)
                st.dataframe(df[["Game","Start","Total","Under Odds","Over Odds","Home Spread","Home ML","Books"]],
                             use_container_width=True,hide_index=True)
                if scan:
                    candidates=[]
                    for g in games:
                        candidates += auto_candidates(g,under_priority)
                    # one candidate per game first, then rank globally
                    candidates=sorted(candidates,key=lambda x:x["AI Score"],reverse=True)
                    unique=[]
                    used=set()
                    for p in candidates:
                        if p["Game"] in used: continue
                        if p["AI Score"] >= min_score:
                            unique.append(p); used.add(p["Game"])
                        if len(unique)>=max_picks: break
                    st.session_state.best=unique
                    if unique:
                        st.success(f"Found {len(unique)} selective pick(s).")
                    else:
                        st.info("Không có kèo nào vượt threshold. PASS cũng là một kết quả hợp lệ.")
            else:
                st.info("API chưa trả game.")
        except Exception as e:
            st.error(f"Odds API error: {e}")

with tabs[1]:
    picks=st.session_state.best
    if not picks:
        st.info("Chưa có Elite pick. Qua Auto Scanner → Scan market.")
    else:
        df=pd.DataFrame(picks)
        st.dataframe(df[["League","Game","Pick","Odds","AI Score","Grade","Edge","EV","Kelly Stake"]],
                     use_container_width=True,hide_index=True)
        for i,p in enumerate(picks):
            with st.container(border=True):
                st.subheader(f"{p['Grade']}  {p['Game']}")
                a,b,c=st.columns(3)
                a.metric("Pick",p["Pick"])
                b.metric("Edge Score",f"{p['AI Score']}/100")
                c.metric("Stake",p["Kelly Stake"])
                st.caption(p["Reason"])
                if st.button("📨 Send this pick",key=f"send_{i}"):
                    key=pick_key(p)
                    if key in st.session_state.sent:
                        st.warning("Pick này đã gửi Telegram rồi.")
                    else:
                        ok,detail=telegram(alert_text(p))
                        if ok:
                            st.session_state.sent.add(key); st.success("Sent.")
                        else: st.error(detail)

with tabs[2]:
    st.subheader("🏈 Manual Analyzer")
    c1,c2,c3,c4=st.columns(4)
    ml=c1.selectbox("League ",["NFL","NCAAF"])
    matchup=c2.text_input("Matchup","SEA vs ARI")
    market=c3.selectbox("Market",["1H","2H","Whole Game"])
    kind=c4.selectbox("Bet type",["Total","Spread","Moneyline"])
    c1,c2,c3=st.columns(3)
    if kind=="Total":
        side=c1.selectbox("Side",["Under","Over"])
        line=c2.number_input("Line",.5,100.0,44.5,.5)
    elif kind=="Spread":
        side=c1.text_input("Team","SEA")
        line=c2.number_input("Spread",-50.0,50.0,-2.5,.5)
    else:
        side=c1.text_input("Team ","SEA"); line=None
    odds=c3.number_input("American odds",-1000,1000,-110,5)

    st.caption("Manual inputs are your scouting inputs; they are not fetched automatically.")
    labels=["Model","QB","Trenches","Explosive","Pace","Defense","Injury/depth",
            "Weather UNDER","Market/sharp","Line value","Game script"]
    defaults=[60,55,55,50,50,60,50,50,50,55,55]
    vals=[]
    cols=st.columns(4)
    for i,(label,d) in enumerate(zip(labels,defaults)):
        vals.append(cols[i%4].slider(label,0,100,d,key=f"v21_{i}"))

    if st.button("🚀 Analyze manual",type="primary"):
        model,qb,trench,expl,pace,defense,injury,weather,sharp,linevalue,script=vals
        score=50+(model-50)*.20+(qb-50)*.10+(trench-50)*.10+(sharp-50)*.12+(linevalue-50)*.12
        score+=(script-50)*.06+(injury-50)*.06
        if side=="Under":
            score+=(defense-50)*.10+(weather-50)*.08-(pace-50)*.04-(expl-50)*.04+under_priority
        elif side=="Over":
            score+=(pace-50)*.08+(expl-50)*.08-(weather-50)*.06-(defense-50)*.04
        else:
            score+=(qb-50)*.06+(trench-50)*.06
        score=clamp(score)
        p=make_pick(ml,matchup,market,kind,side,line,odds,score,bankroll,kelly_cap,
                    "Manual scouting model")
        st.dataframe(pd.DataFrame([p]),use_container_width=True,hide_index=True)
        if p["AI Score"]>=min_score:
            if st.button("💎 Add to Best Bets"):
                st.session_state.best.append(p); st.success("Added.")

with tabs[3]:
    st.subheader("🔥 Live / 2H Analyzer")
    st.warning("The Odds API feed used here is not play-by-play. Enter live game state manually unless you add a live-data provider.")
    c1,c2,c3,c4=st.columns(4)
    lg=c1.text_input("Game ","SEA vs ARI")
    ls=c2.selectbox("Live total",["Under","Over"])
    ll=c3.number_input("Live line",.5,100.0,23.5,.5)
    lo=c4.number_input("Live odds",-1000,1000,-110,5)
    c1,c2,c3,c4=st.columns(4)
    points=c1.number_input("Points scored",0,150,20)
    possessions=c2.number_input("Possessions/team",1,30,6)
    ypp=c3.number_input("Yards/play",0.0,15.0,5.4,.1)
    turnovers=c4.number_input("Turnovers",0,10,1)
    c1,c2,c3,c4=st.columns(4)
    rz=c1.number_input("Red-zone trips",0,20,3)
    explosive=c2.number_input("Explosive plays",0,40,4)
    sacks=c3.number_input("Sacks",0,20,3)
    live_weather=c4.slider("Weather favors UNDER",0,100,50,key="live_weather")

    if st.button("🔥 Analyze live",type="primary"):
        tempo=clamp(50+(possessions-6)*7)
        exp=clamp(50+(explosive-4)*4+(ypp-5.5)*8)
        defense=clamp(50+sacks*3-max(rz-3,0)*4)
        score=50
        if ls=="Under":
            score+=(defense-50)*.18+(live_weather-50)*.12-(tempo-50)*.12-(exp-50)*.10+under_priority
            if turnovers>=3: score-=4
        else:
            score+=(tempo-50)*.16+(exp-50)*.14-(live_weather-50)*.10-(defense-50)*.08
        score=clamp(score)
        p=make_pick("LIVE",lg,"2H/Live","Total",ls,ll,lo,score,bankroll,kelly_cap,
                    "Live game-state inputs")
        st.dataframe(pd.DataFrame([p]),use_container_width=True,hide_index=True)

with tabs[4]:
    st.subheader("📈 Line Movement / RLM")
    st.caption("Enter real opening/current lines and ticket/handle data only if your provider supplies them.")
    c1,c2,c3,c4=st.columns(4)
    opening=c1.number_input("Opening",-100.0,100.0,44.5,.5)
    current=c2.number_input("Current",-100.0,100.0,43.5,.5)
    tickets=c3.slider("Tickets %",0,100,50)
    handle=c4.slider("Handle %",0,100,50)
    move=current-opening; gap=handle-tickets
    signal=clamp(50+abs(move)*7+max(gap,0)*.6)
    st.metric("Market Signal",f"{signal:.0f}/100",f"Line {move:+.1f}")
    if abs(move)>=1 and gap>=10: st.success("Strong market-move pattern")
    elif abs(move)>=.5 or gap>=8: st.info("Moderate market signal")
    else: st.warning("No clear signal")

with tabs[5]:
    st.subheader("📨 Telegram")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        st.success("Telegram ready.")
        msg=st.text_area("Test message","🏈 Football AI Pro v21 ELITE — Telegram test ✅")
        if st.button("Send test"):
            ok,detail=telegram(msg)
            st.success("Sent!") if ok else st.error(detail)
        st.caption("Best Bets has per-pick send buttons + duplicate protection for the current app session.")
    else:
        st.warning("Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to Render Environment.")

st.divider()
st.caption("v21 ELITE • Selective ranking, not guaranteed outcomes. Market-only scores are not historical win probabilities.")
