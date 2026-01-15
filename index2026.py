import streamlit as st
import datetime
import pytz
import requests
import xml.etree.ElementTree as ET
from streamlit_autorefresh import st_autorefresh

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Northeast Astro-Scalp", layout="wide", page_icon="🕉️")

# --- LOADING DATA ---
with st.spinner('Initializing Kamrupi Astro Algorithms...'):
    from skyfield import almanac
    from skyfield.api import load, wgs84

# --- AUTO REFRESH (60s) ---
count = st_autorefresh(interval=60000, key="datarefresh")

# --- CUSTOM CSS (Advanced Planner Style) ---
st.markdown("""
    <style>
    .stApp { background-color: #0E1117; color: #E0E0E0; }
    
    /* Header Cards */
    .prediction-box {
        background-color: #1A1C24; border: 1px solid #333; border-radius: 8px;
        padding: 15px; height: 100%; display: flex; flex-direction: column;
        justify-content: space-between; border-left: 4px solid #00FFA3;
    }
    .index-title { font-size: 1.1rem; font-weight: bold; color: #FFF; margin-bottom: 10px; border-bottom: 1px solid #444; padding-bottom: 5px;}
    
    /* Schedule Table */
    .trade-row { border-left: 4px solid #444; padding: 12px; margin-bottom: 8px; background: #16181e; display: flex; align-items: center; border-radius: 4px;}
    .trade-row.active { border-left: 4px solid #00FFA3; background: #1f2937; border: 1px solid #00FFA3; }
    .trade-row.rahu { border-left: 4px solid #FF453A; background: #2d1b1b; }
    
    /* Advanced Planner Styles */
    .planner-row {
        background-color: #1A1C24;
        padding: 12px 15px;
        margin-bottom: 8px;
        border-radius: 6px;
        display: flex;
        align-items: center;
        transition: all 0.2s;
    }
    .planner-row:hover { background-color: #252830; }
    
    .border-green { border-left: 4px solid #00FFA3; }
    .border-red { border-left: 4px solid #FF453A; }
    .border-gray { border-left: 4px solid #555; }
    
    /* Badges & Buttons */
    .badge { padding: 4px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: bold; text-transform: uppercase; display: inline-block; min-width: 100px; text-align: center;}
    .badge-high { background-color: rgba(0, 255, 163, 0.15); color: #00FFA3; border: 1px solid #00FFA3; }
    .badge-danger { background-color: rgba(255, 69, 58, 0.15); color: #FF453A; border: 1px solid #FF453A; }
    .badge-neutral { background-color: rgba(100, 100, 100, 0.2); color: #AAA; border: 1px solid #555; }
    
    .btn-green { background-color: #00FFA3; color: #000; padding: 4px 12px; border-radius: 4px; font-weight: bold; font-size: 0.8rem; border: none; }
    .btn-red { background-color: transparent; color: #FF453A; padding: 4px 12px; border-radius: 4px; font-weight: bold; font-size: 0.8rem; border: 1px solid #FF453A; }
    
    .time-font { font-family: 'Courier New', monospace; font-size: 0.95rem; font-weight: 600; color: #FFF; }
    .planet-font { font-weight: bold; color: #FFF; font-size: 0.95rem; }
    
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- CONFIGURATION: NORTHEAST INDIA ---
TZ_IST = pytz.timezone('Asia/Kolkata')

# Precise Coordinates for Northeast
LOCATIONS = {
    "Silapathar, Dhemaji": (27.6100, 94.7300), # User Requested
    "North Lakhimpur": (27.2360, 94.1028),
    "Dibrugarh": (27.4728, 94.9120),
    "Guwahati": (26.1445, 91.7362),
    "Jorhat": (26.7509, 94.2037),
    "Tezpur": (26.6528, 92.7926)
}

# --- ASTRONOMY ENGINE ---
@st.cache_resource
def load_ephemeris():
    return load('de421.bsp')

eph = load_ephemeris()
sun, moon, earth = eph['sun'], eph['moon'], eph['earth']
ts = load.timescale()

def get_sidereal_pos(body, t, observer_loc):
    observer = earth + observer_loc
    astrometric = observer.at(t).observe(body)
    _, lon_ecl, _ = astrometric.apparent().ecliptic_latlon()
    # Lahiri Ayanamsa (Standard in Assam/Kamrup)
    days_since_j2000 = t.tt - 2451545.0
    ayanamsa = 23.855 + ((50.29 * (days_since_j2000 / 365.25)) / 3600.0)
    return (lon_ecl.degrees - ayanamsa) % 360

def get_tithi(t, loc_obj):
    moon_lon = get_sidereal_pos(moon, t, loc_obj)
    sun_lon = get_sidereal_pos(sun, t, loc_obj)
    diff = (moon_lon - sun_lon) % 360
    tithi_idx = int(diff / 12) + 1
    paksha = "Shukla" if tithi_idx <= 15 else "Krishna"
    name = f"Tithi {tithi_idx}" if tithi_idx <= 15 else f"Tithi {tithi_idx-15}"
    if tithi_idx == 30: name = "Amavasya"
    if tithi_idx == 15: name = "Purnima"
    return f"{name} ({paksha})"

def calculate_rahu_kaal(weekday_idx, sunrise, sunset):
    # Kamrupi/Vedic Standard: Mon=2, Tue=7, Wed=5, Thu=6, Fri=4, Sat=3, Sun=8
    rk_map = {0: 2, 1: 7, 2: 5, 3: 6, 4: 4, 5: 3, 6: 8} 
    duration = (sunset - sunrise).total_seconds()
    part = duration / 8.0
    start_sec = (rk_map[weekday_idx] - 1) * part 
    start = sunrise + datetime.timedelta(seconds=start_sec)
    return start, start + datetime.timedelta(seconds=part)

@st.cache_data(ttl=3600)
def calculate_market_schedule(date_obj_py, lat, lon):
    # KAMRUPI SYSTEM: Use LOCAL Sunrise (Assam) for Hora Calculation
    # This aligns the planetary hours with the user's local energy/time.
    loc_obj = wgs84.latlon(lat, lon)
    
    midnight = date_obj_py.replace(hour=0, minute=0, second=0, microsecond=0)
    t0, t1 = ts.from_datetime(midnight), ts.from_datetime(midnight + datetime.timedelta(days=1))
    t_rise, y_rise = almanac.find_discrete(t0, t1, almanac.sunrise_sunset(eph, loc_obj))
    
    sunrise_t, sunset_t = None, None
    for t, event in zip(t_rise, y_rise):
        if event == 1 and sunrise_t is None: sunrise_t = t
        elif event == 0 and sunset_t is None: sunset_t = t
    
    if sunrise_t is None: return [], "Unknown", None, None

    sunrise_dt = sunrise_t.astimezone(TZ_IST)
    sunset_dt = sunset_t.astimezone(TZ_IST)
    rk_start, rk_end = calculate_rahu_kaal(date_obj_py.weekday(), sunrise_dt, sunset_dt)
    
    hora_len = (sunset_dt - sunrise_dt).total_seconds() / 12.0
    lords = ["Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Sun"]
    day_lord = lords[date_obj_py.weekday()]
    
    hora_order = ["Sun", "Venus", "Mercury", "Moon", "Saturn", "Jupiter", "Mars"]
    start_idx = hora_order.index(day_lord)
    
    schedule = []
    curr = sunrise_dt
    
    # Market Open/Close (IST Fixed)
    mkt_open = date_obj_py.replace(hour=9, minute=15)
    mkt_close = date_obj_py.replace(hour=15, minute=30)
    
    for i in range(16): # Calculate extra hours to cover full market day
        end = curr + datetime.timedelta(seconds=hora_len)
        planet = hora_order[(start_idx + i) % 7]
        
        # Check overlaps with Market Hours
        latest_start = max(curr, mkt_open)
        earliest_end = min(end, mkt_close)
        
        if latest_start < earliest_end:
            is_rahu = (latest_start < rk_end) and (earliest_end > rk_start)
            # Clip the display time to market hours for cleaner UI
            display_start = latest_start
            display_end = earliest_end
            
            schedule.append({
                "start": display_start, 
                "end": display_end, 
                "planet": planet, 
                "is_rahu": is_rahu,
                "time_str": f"{display_start.strftime('%I:%M %p')} - {display_end.strftime('%I:%M %p')}"
            })
        curr = end
        
    return schedule, day_lord, rk_start, rk_end

@st.cache_data(ttl=300)
def fetch_real_news():
    news_items = []
    headers = {"User-Agent": "Mozilla/5.0"}
    sources = [
        ("Economic Times", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
        ("MoneyControl", "https://www.moneycontrol.com/rss/marketreports.xml")
    ]
    for source_name, url in sources:
        try:
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                count = 0
                for item in root.findall('./channel/item'):
                    if count >= 2: break
                    news_items.append({"title": item.find('title').text, "link": item.find('link').text, "source": source_name})
                    count += 1
        except: continue
    if not news_items: return [{"title": "News Unavailable", "link": "#", "source": "System"}]
    return news_items

# --- INDEX PREFERENCES ---
INDEX_CONFIG = {
    "NIFTY 50": {"Best": ["Jupiter", "Sun"], "Worst": ["Saturn", "Rahu"], "Strategy": "BUY CALL"},
    "BANK NIFTY": {"Best": ["Mercury", "Mars", "Jupiter"], "Worst": ["Saturn", "Venus"], "Strategy": "BUY CALL"},
    "SENSEX": {"Best": ["Sun", "Jupiter"], "Worst": ["Ketu", "Saturn"], "Strategy": "BUY CALL"},
    "MIDCAP SEL": {"Best": ["Mars", "Mercury"], "Worst": ["Saturn"], "Strategy": "SCALP"}
}

# --- UI EXECUTION ---
with st.sidebar:
    st.header("⚙️ Configuration")
    user_dob = st.date_input("Date of Birth", datetime.date(1984, 9, 6))
    user_tob = st.time_input("Time of Birth", datetime.time(0, 37))
    
    # Defaults to Silapathar (Northeast)
    pob_name = st.selectbox("Location (Sunrise Basis)", list(LOCATIONS.keys()), index=0)
    target_date = st.date_input("Trading Date", datetime.date.today())
    
    st.markdown("---")
    st.info(f"**System:** Kamrupi/Northeast\n**Sunrise:** Local ({pob_name})\n**Logic:** Hora calculated from Local Sunrise.")

# --- CALCULATION PHASE ---
is_today = (target_date == datetime.date.today())
now_ist = datetime.datetime.now(TZ_IST)
calc_dt = now_ist if is_today else TZ_IST.localize(datetime.datetime.combine(target_date, datetime.time(9, 15)))

lat, lon = LOCATIONS[pob_name]
schedule, day_lord, rk_start, rk_end = calculate_market_schedule(calc_dt, lat, lon)

loc_obj = wgs84.latlon(lat, lon)
tithi_str = get_tithi(ts.from_datetime(calc_dt), loc_obj)

# --- DASHBOARD HEADER ---
st.title(f"🔮 Northeast Astro-Scalping: {target_date.strftime('%d %b %Y')}")
st.caption(f"Day Lord: **{day_lord}** | Tithi: **{tithi_str}** | Zone: **{pob_name}**")

# --- SECTION 1: TOP CARDS ---
cols = st.columns(4)
for i, (name, config) in enumerate(INDEX_CONFIG.items()):
    best_time = "None"
    for s in schedule:
        if s['planet'] in config["Best"] and not s['is_rahu']:
            best_time = s['start'].strftime('%H:%M')
            break
            
    with cols[i]:
        st.markdown(f"""
        <div class='prediction-box'>
            <div class='index-title'>{name}</div>
            <div style='display:flex; justify-content:space-between; font-size:0.8rem; color:#888'>
                <span>Best Entry:</span> <span style='color:#00FFA3; font-weight:bold'>{best_time}</span>
            </div>
            <div style='margin-top:10px; background:rgba(0,255,163,0.1); color:#00FFA3; padding:4px; text-align:center; border-radius:4px; font-weight:bold; font-size:0.8rem; border:1px solid #00FFA3'>
                {config['Strategy'] if best_time != 'None' else 'WAIT'}
            </div>
        </div>
        """, unsafe_allow_html=True)

# --- SECTION 2: NEWS ---
st.markdown("---")
st.subheader("📰 Real-Time Headlines")
news = fetch_real_news()
n1, n2 = st.columns(2)
for i, item in enumerate(news):
    col = n1 if i % 2 == 0 else n2
    col.markdown(f"**[{item['source']}]** [{item['title']}]({item['link']})")

# --- SECTION 3: SCHEDULE TABLE ---
st.markdown("---")
st.subheader(f"📜 Schedule (Local Sunrise: {pob_name})")

st.markdown("""
<div style="display:flex; color:#888; font-weight:bold; margin-bottom:10px; padding-left:10px; font-size:0.9rem">
    <div style="width:25%">Time (IST)</div>
    <div style="width:15%">Hora</div>
    <div style="width:15%">Rahu?</div>
    <div style="width:20%">Status</div>
    <div style="width:25%">Explanation</div>
</div>
""", unsafe_allow_html=True)

for s in schedule:
    is_active = s['start'] <= now_ist < s['end'] if is_today else False
    
    status_txt = "🟢 OPEN"
    status_col = "#00FFA3"
    expl = "Scalping Zone"
    
    if s['is_rahu']:
        status_txt = "⛔ RAHU"
        status_col = "#FF453A"
        expl = "Trap Zone / High Risk"
    elif s['planet'] == "Saturn":
        status_txt = "🟠 SLOW"
        status_col = "#FFD700"
        expl = "Low Momentum"
        
    row_class = "trade-row" + (" active" if is_active else "") + (" rahu" if s['is_rahu'] else "")
    rahu_txt = "💀 YES" if s['is_rahu'] else "-"
    
    st.markdown(f"""
    <div class='{row_class}'>
        <div style='width:25%; font-family:monospace; color:#EEE'>{s['time_str']}</div>
        <div style='width:15%; font-weight:bold; color:#FFF'>{s['planet']}</div>
        <div style='width:15%; color:{'#FF453A' if s['is_rahu'] else '#555'}; font-weight:bold'>{rahu_txt}</div>
        <div style='width:20%; font-weight:bold; color:{status_col}'>{status_txt}</div>
        <div style='width:25%; color:#AAA; font-size:0.9rem'>{expl}</div>
    </div>
    """, unsafe_allow_html=True)

# --- SECTION 4: ADVANCED PLANNER (YOUR REQUESTED STYLE) ---
st.markdown("---")
st.title("🚀 Advanced Index Scalping Planner")
st.caption("Filters specific trade setups based on Planetary Friendships & Market Timings.")

tabs = st.tabs(list(INDEX_CONFIG.keys()))

for i, index_name in enumerate(INDEX_CONFIG.keys()):
    with tabs[i]:
        if not schedule:
            st.error("Market Closed")
            continue
            
        config = INDEX_CONFIG[index_name]
        
        st.markdown(f"""
        <div style="display:flex; color:#888; font-weight:bold; margin-bottom:10px; padding-left:15px; margin-top:15px;">
            <div style="width:30%">Time</div>
            <div style="width:20%">Hora</div>
            <div style="width:30%">Signal</div>
            <div style="width:20%">Action</div>
        </div>
        """, unsafe_allow_html=True)
        
        for slot in schedule:
            planet = slot['planet']
            is_rahu = slot['is_rahu']
            
            if is_rahu:
                status_class = "border-red"
                signal_html = "<span class='badge badge-danger'>💀 DANGER ZONE</span>"
                action_html = "<span class='btn-red'>⛔ NO TRADING</span>"
            elif planet in config["Best"]:
                status_class = "border-green"
                signal_html = "<span class='badge badge-high'>☀️ HIGH PROBABILITY</span>"
                action_html = f"<span class='btn-green'>✅ {config['Strategy']}</span>"
            elif planet in config["Worst"]:
                status_class = "border-red"
                signal_html = "<span class='badge badge-danger'>🛑 DANGER ZONE</span>"
                action_html = "<span class='btn-red'>⛔ NO TRADING</span>"
            else:
                status_class = "border-gray"
                signal_html = "<span class='badge badge-neutral'>⚪ NEUTRAL</span>"
                action_html = "<span style='color:#777; font-size:0.8rem; font-weight:bold'>Wait for Setup</span>"

            st.markdown(f"""
            <div class='planner-row {status_class}'>
                <div style="width:30%" class="time-font">{slot['time_str']}</div>
                <div style="width:20%" class="planet-font">{planet}</div>
                <div style="width:30%">{signal_html}</div>
                <div style="width:20%">{action_html}</div>
            </div>
            """, unsafe_allow_html=True)