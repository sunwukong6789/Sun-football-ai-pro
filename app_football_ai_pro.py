import math
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Football AI Pro", page_icon="🏈", layout="wide")

# -----------------------------
# Helpers
# -----------------------------
def clamp(x, lo=0, hi=100):
    return max(lo, min(hi, x))

def american_to_decimal(odds):
    if odds > 0:
        return 1 + odds / 100
    return 1 + 100 / abs(odds)

def implied_prob(odds):
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)

def kelly_fraction(p, decimal_odds):
    b = decimal_odds - 1
    if b <= 0:
        return 0
    q = 1 - p
    return max(0, (b*p - q) / b)

def label(score):
    if score >= 88:
        return "🔥 ELITE"
    if score >= 80:
        return "✅ STRONG"
    if score >= 70:
        return "🟡 PLAYABLE"
    return "⛔ PASS"

def football_score(
    market, side, model_edge, qb_edge, trench_edge, explosive_edge,
    pace_edge, defense_edge, injury_edge, weather_under,
    sharp_signal, line_value, game_script, second_half_adjustment=0
):
    # 50 = neutral. Inputs are 0-100, with 50 neutral.
    weights = {
        "model": .22, "qb": .12, "trench": .10, "explosive": .09,
        "pace": .08, "defense": .10, "injury": .07, "weather": .05,
        "sharp": .09, "line": .08
    }
    factors = {
        "model": model_edge, "qb": qb_edge, "trench": trench_edge,
        "explosive": explosive_edge, "pace": pace_edge,
        "defense": defense_edge, "injury": injury_edge,
        "weather": weather_under, "sharp": sharp_signal, "line": line_value
    }

    raw = 50 + sum((factors[k]-50) * w for k, w in weights.items())

    # Market-specific adjustments
    if market == "1H":
        raw += (game_script - 50) * .08
    elif market == "2H":
        raw += (game_script - 50) * .05 + second_half_adjustment
    else:
        raw += (game_script - 50) * .04

    # Total-specific interpretation
    if side == "Over":
        raw += (pace_edge - 50) * .08 + (explosive_edge - 50) * .06
        raw -= (weather_under - 50) * .08
        raw -= (defense_edge - 50) * .04
    elif side == "Under":
        raw += (defense_edge - 50) * .07 + (weather_under - 50) * .07
        raw -= (pace_edge - 50) * .05
        raw -= (explosive_edge - 50) * .04

    return round(clamp(raw), 1)

def fair_probability(score):
    # Conservative mapping: score 50 -> 50%; 90 -> ~62%
    return clamp(50 + (score - 50) * .30, 45, 65) / 100

def build_pick(league, matchup, market, bet_type, side, line, odds, score, bankroll, kelly_cap):
    dec = american_to_decimal(odds)
    p = fair_probability(score)
    imp = implied_prob(odds)
    edge = p - imp
    ev = p*(dec-1) - (1-p)
    k = min(kelly_fraction(p, dec), kelly_cap/100)
    stake = bankroll * k if score >= 80 and ev > 0 else 0
    return {
        "League": league,
        "Game": matchup,
        "Market": market,
        "Type": bet_type,
        "Pick": f"{side} {line:g}" if line != 0 else side,
        "Odds": int(odds),
        "AI Score": score,
        "Grade": label(score),
        "Win Prob": f"{p*100:.1f}%",
        "Edge": f"{edge*100:+.1f}%",
        "EV": f"{ev*100:+.1f}%",
        "Kelly Stake": f"${stake:,.0f}",
    }

# -----------------------------
# UI
# -----------------------------
st.title("🏈 Football AI Pro — NFL + NCAAF")
st.caption("1H • 2H • Whole Game • Spread • Total • Moneyline • Sharp Money • Kelly • Best Bets")

with st.sidebar:
    st.header("⚙️ Bankroll")
    bankroll = st.number_input("Bankroll ($)", 50.0, 1_000_000.0, 1000.0, 50.0)
    kelly_cap = st.slider("Kelly cap tối đa (%)", .25, 5.0, 2.0, .25)
    min_score = st.slider("Chỉ chơi từ AI Score", 65, 95, 80)
    st.divider()
    st.caption("88+ ELITE • 80–87 STRONG • 70–79 PLAYABLE • <70 PASS")
    st.warning("Bot là công cụ phân tích, không bảo đảm thắng. Không chase loss / không all-in.")

tabs = st.tabs(["⭐ Best Bet", "🏈 Analyzer", "🔥 2H Live", "📈 Sharp Money", "🧾 Tracker"])

# Persist analyzed picks
if "football_picks" not in st.session_state:
    st.session_state.football_picks = []
if "tracker" not in st.session_state:
    st.session_state.tracker = []

with tabs[1]:
    st.subheader("🏈 NFL / NCAAF Analyzer")
    a,b,c,d = st.columns(4)
    league = a.selectbox("League", ["NFL", "NCAAF"])
    matchup = b.text_input("Matchup", "SEA vs ARI")
    market = c.selectbox("Market", ["1H", "2H", "Whole Game"])
    bet_type = d.selectbox("Bet type", ["Spread", "Total", "Moneyline"])

    a,b,c = st.columns(3)
    if bet_type == "Total":
        side = a.selectbox("Side", ["Under", "Over"])
        line = b.number_input("Total line", 0.5, 100.0, 44.5, .5)
    elif bet_type == "Spread":
        side = a.text_input("Team / Side", "SEA")
        line = b.number_input("Spread", -40.0, 40.0, -2.5, .5)
    else:
        side = a.text_input("Team", "SEA")
        line = 0.0
        b.write("")
    odds = c.number_input("American odds", -500, 500, -110, 5)

    st.markdown("#### Model inputs")
    st.caption("50 = neutral. >50 = càng ủng hộ pick đang phân tích.")
    c1,c2,c3,c4 = st.columns(4)
    model_edge = c1.slider("Power/model edge", 0, 100, 70)
    qb_edge = c2.slider("QB edge", 0, 100, 65)
    trench_edge = c3.slider("OL/DL edge", 0, 100, 65)
    explosive_edge = c4.slider("Explosive-play edge", 0, 100, 60)

    c5,c6,c7,c8 = st.columns(4)
    pace_edge = c5.slider("Pace / possessions", 0, 100, 50)
    defense_edge = c6.slider("Defense matchup", 0, 100, 65)
    injury_edge = c7.slider("Injury / depth edge", 0, 100, 55)
    weather_under = c8.slider("Weather favors UNDER", 0, 100, 50)

    c9,c10,c11 = st.columns(3)
    sharp_signal = c9.slider("Sharp money signal", 0, 100, 60)
    line_value = c10.slider("Current line value", 0, 100, 65)
    game_script = c11.slider("Expected game-script fit", 0, 100, 60)

    if st.button("🚀 ANALYZE", type="primary", use_container_width=True):
        score = football_score(
            market, side, model_edge, qb_edge, trench_edge, explosive_edge,
            pace_edge, defense_edge, injury_edge, weather_under,
            sharp_signal, line_value, game_script
        )
        row = build_pick(league, matchup, market, bet_type, side, line, odds, score, bankroll, kelly_cap)
        st.session_state.football_picks.append(row)
        st.success(f"{row['Grade']} — AI Score {score}/100")
        st.dataframe(pd.DataFrame([row]), use_container_width=True, hide_index=True)

with tabs[2]:
    st.subheader("🔥 2H Live Analyzer")
    st.caption("Dùng lúc halftime: nhập dữ liệu 1H + line 2H hiện tại.")
    a,b,c,d = st.columns(4)
    l_league = a.selectbox("League ", ["NFL", "NCAAF"], key="live_league")
    l_match = b.text_input("Matchup ", "SEA vs ARI", key="live_match")
    l_type = c.selectbox("2H Bet", ["Spread", "Total"], key="live_type")
    l_odds = d.number_input("Odds ", -500, 500, -110, 5, key="live_odds")

    a,b,c,d = st.columns(4)
    halftime_total = a.number_input("1H points scored", 0, 100, 20)
    possessions = b.number_input("Est. 1H possessions/team", 1, 20, 6)
    yards_play = c.number_input("Combined yards/play", 0.0, 15.0, 5.4, .1)
    turnovers = d.number_input("Turnovers", 0, 10, 1)

    a,b,c,d = st.columns(4)
    redzone = a.number_input("Combined red-zone trips", 0, 15, 3)
    explosive = b.number_input("Explosive plays (20+ yd)", 0, 30, 4)
    sacks = c.number_input("Combined sacks", 0, 20, 3)
    injuries_live = d.slider("Live injury impact", 0, 100, 50)

    if l_type == "Total":
        a,b,c = st.columns(3)
        l_side = a.selectbox("2H Side", ["Under", "Over"], key="live_side")
        l_line = b.number_input("2H total", 0.5, 70.0, 23.5, .5)
        weather = c.slider("Weather favors UNDER ", 0, 100, 50)
    else:
        a,b,c = st.columns(3)
        l_side = a.text_input("2H team", "SEA")
        l_line = b.number_input("2H spread", -30.0, 30.0, -1.5, .5)
        weather = c.slider("Weather impact", 0, 100, 50)

    a,b,c = st.columns(3)
    sharp = a.slider("2H sharp signal", 0, 100, 60)
    value = b.slider("2H line value", 0, 100, 65)
    script = c.slider("2H game-script fit", 0, 100, 65)

    # Live adjustment: efficiency + possessions + explosives; turnovers can be noisy.
    tempo = clamp(50 + (possessions-6)*6)
    explosive_edge_live = clamp(50 + (explosive-4)*4 + (yards_play-5.5)*7)
    defense_live = clamp(55 + sacks*2 - max(redzone-3, 0)*3)
    regression = clamp(50 + turnovers*4)
    live_adj = (regression-50)*.04 + (injuries_live-50)*.03

    if st.button("🔥 ANALYZE 2H", type="primary", use_container_width=True):
        score = football_score(
            "2H", l_side, 65, 55, 55, explosive_edge_live,
            tempo, defense_live, injuries_live, weather,
            sharp, value, script, live_adj
        )
        row = build_pick(l_league, l_match, "2H", l_type, l_side, l_line, l_odds, score, bankroll, kelly_cap)
        st.session_state.football_picks.append(row)
        st.success(f"{row['Grade']} — 2H AI Score {score}/100")
        st.dataframe(pd.DataFrame([row]), use_container_width=True, hide_index=True)

with tabs[3]:
    st.subheader("📈 Sharp Money / Line Movement")
    a,b,c,d = st.columns(4)
    open_line = a.number_input("Opening line", -100.0, 100.0, 44.5, .5)
    current_line = b.number_input("Current line", -100.0, 100.0, 43.5, .5)
    public = c.slider("Public tickets %", 0, 100, 65)
    handle = d.slider("Money/handle %", 0, 100, 78)

    move = current_line - open_line
    gap = handle - public
    sharp_score = clamp(50 + abs(move)*8 + max(gap,0)*.8)
    if abs(move) >= 1 and gap >= 10:
        note = "🔥 Strong sharp/steam signal"
    elif abs(move) >= .5 or gap >= 8:
        note = "✅ Sharp lean"
    else:
        note = "🟡 Signal chưa rõ"

    st.metric("Sharp Score", f"{sharp_score:.0f}/100", f"Line move {move:+.1f}")
    st.info(f"{note} • Handle - tickets: {gap:+d}%")

with tabs[0]:
    st.subheader("⭐ Best Bets")
    if st.session_state.football_picks:
        df = pd.DataFrame(st.session_state.football_picks)
        df = df.sort_values("AI Score", ascending=False)
        show = df[df["AI Score"] >= min_score]
        if show.empty:
            st.warning(f"Chưa có kèo nào đạt {min_score}+.")
        else:
            st.dataframe(show, use_container_width=True, hide_index=True)
            best = show.iloc[0]
            st.success(f"BEST BET: {best['Game']} — {best['Market']} — {best['Pick']} • {best['AI Score']}/100")
        if st.button("Clear analyzed picks"):
            st.session_state.football_picks = []
            st.rerun()
    else:
        st.info("Vào Analyzer hoặc 2H Live để phân tích. Bot sẽ tự xếp hạng kèo ở đây.")

with tabs[4]:
    st.subheader("🧾 Bet Tracker")
    a,b,c,d = st.columns(4)
    t_game = a.text_input("Game", "SEA vs ARI", key="tgame")
    t_pick = b.text_input("Pick", "Under 44.5", key="tpick")
    t_stake = c.number_input("Stake $", 0.0, 100000.0, 20.0, 5.0)
    t_result = d.selectbox("Result", ["Pending", "Win", "Loss", "Push"])
    if st.button("Add to tracker"):
        profit = t_stake if t_result == "Win" else (-t_stake if t_result == "Loss" else 0)
        st.session_state.tracker.append({
            "Game": t_game, "Pick": t_pick, "Stake": t_stake,
            "Result": t_result, "Profit": profit
        })
    if st.session_state.tracker:
        tdf = pd.DataFrame(st.session_state.tracker)
        st.dataframe(tdf, use_container_width=True, hide_index=True)
        st.metric("Tracked Profit", f"${tdf['Profit'].sum():,.0f}")
