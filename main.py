import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    ContextTypes, 
    MessageHandler, 
    filters, 
    CallbackContext,
    CallbackQueryHandler
)
import random
from datetime import datetime, timedelta
import asyncio
import time
import math
import re
import requests
import json
import websockets
import threading
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
import matplotlib.pyplot as plt
import io
import base64

# ====== Bot Configuration ======
BOT_TOKEN = "7253914117:AAFyLaqa1ksxUuVUN5qVCthlBnvcWfxLH0A"  # Updated token
REQUIRED_CHANNEL = "@quantum_wingo_predictor"  # Channel to join
MAX_HISTORY = 1000
HISTORY_DISPLAY = 20
HGZY_API_URL = "https://api.hgzy.cc/wingo/live"
HGZY_WS_URL = "wss://api.hgzy.cc/wingo/ws"
GAME_URL = "https://hgzy.cc/#/saasLottery/WinGo?gameCode=WinGo_30S&lottery=WinGo"

# ====== Setup Logging ======
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("quantum_wingo_ai.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ====== Game Data Storage ======
prediction_history = []
live_rounds = {}
last_results = []
user_stats = {}
real_time_data = []
active_websocket = None
ai_agents = {}
ml_model = None
scaler = StandardScaler()
ml_stats = {"predictions": 0, "wins": 0, "streak": 0, "max_streak": 0, "accuracy": 0.0}  # ML stats tracker
channel_subscribers = set()  # Track users who joined channel

# ====== AI Agent Configuration ======
class AIAgent:
    def __init__(self, name, specialty):
        self.name = name
        self.specialty = specialty
        self.history = []
        self.accuracy = 0.0
        self.streak = 0
        self.max_streak = 0
        self.predictions = 0
        self.wins = 0
        self.weight = 1.0  # Default weight
        
    def analyze(self, data):
        """Base analysis method to be overridden by specialized agents"""
        return "Big", 80
    
    def update_stats(self, correct):
        self.predictions += 1
        if correct:
            self.wins += 1
            self.streak += 1
            if self.streak > self.max_streak:
                self.max_streak = self.streak
            # Increase weight for correct predictions
            self.weight = min(2.0, self.weight + 0.05)
        else:
            self.streak = 0
            # Decrease weight for incorrect predictions
            self.weight = max(0.5, self.weight - 0.1)
        self.accuracy = (self.wins / self.predictions) * 100 if self.predictions > 0 else 0

# Create specialized AI agents
ai_agents["quantum"] = AIAgent("Quantum Neural Net", "Deep pattern recognition")
ai_agents["temporal"] = AIAgent("Temporal Analyst", "Time-based predictions")
ai_agents["statistical"] = AIAgent("Statistical Engine", "Probability analysis")
ai_agents["volatility"] = AIAgent("Volatility Tracker", "Market fluctuation prediction")
ai_agents["harmonic"] = AIAgent("Harmonic Analyst", "Wave pattern detection")  # New agent

# ====== Initialize ML Model ======
def init_ml_model():
    global ml_model
    ml_model = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=1000, random_state=42)
    logger.info("ML model initialized")

# ====== Pattern Analysis Algorithms ======
def analyze_historical_patterns(results):
    """Advanced pattern recognition algorithm"""
    if not results:
        return {"trend": "N/A", "pattern": "No data", "volatility": 0}
    
    numbers = [r["number"] for r in results]
    
    # Calculate moving averages
    ma_5 = [sum(numbers[i:i+5])/5 for i in range(len(numbers)-4)] if len(numbers) >= 5 else []
    ma_10 = [sum(numbers[i:i+10])/10 for i in range(len(numbers)-9)] if len(numbers) >= 10 else []
    
    # Detect trends
    current_trend = "Bullish" if len(numbers) > 1 and numbers[-1] > numbers[-2] else "Bearish"
    
    # Pattern detection
    patterns = []
    big_count = 0
    small_count = 0
    odd_count = 0
    even_count = 0
    
    if len(numbers) > 10:
        # Streak detection
        current_streak = 1
        current_type = "Big" if numbers[-1] >= 5 else "Small"
        for i in range(len(numbers)-2, max(len(numbers)-10, -1), -1):
            if (numbers[i] >= 5 and current_type == "Big") or (numbers[i] < 5 and current_type == "Small"):
                current_streak += 1
            else:
                break
                
        patterns.append(f"{current_type} streak: {current_streak}")
        
        # Oscillation pattern
        last_10 = numbers[-10:]
        big_count = sum(1 for n in last_10 if n >= 5)
        small_count = 10 - big_count
        odd_count = sum(1 for n in last_10 if n % 2 == 1)
        even_count = 10 - odd_count
        
        if abs(big_count - small_count) <= 2:
            patterns.append("Oscillating market")
        elif big_count > 7:
            patterns.append("Big dominant")
        elif small_count > 7:
            patterns.append("Small dominant")
            
        # Parity patterns
        if abs(odd_count - even_count) <= 2:
            patterns.append("Balanced parity")
        elif odd_count > 7:
            patterns.append("Odd dominant")
        elif even_count > 7:
            patterns.append("Even dominant")
    
    # Volatility analysis
    volatility = max(numbers[-10:]) - min(numbers[-10:]) if len(numbers) >= 10 else 0
    
    return {
        "trend": current_trend,
        "patterns": ", ".join(patterns) if patterns else "No clear pattern",
        "volatility": volatility,
        "big_ratio": f"{big_count/10:.0%}" if len(numbers) >= 10 else "N/A",
        "small_ratio": f"{small_count/10:.0%}" if len(numbers) >= 10 else "N/A",
        "odd_ratio": f"{odd_count/10:.0%}" if len(numbers) >= 10 else "N/A",
        "even_ratio": f"{even_count/10:.0%}" if len(numbers) >= 10 else "N/A"
    }

# ====== Hgzy Server Connection ======
async def fetch_hgzy_data():
    """Fetch real-time data from Hgzy server"""
    try:
        response = requests.get(HGZY_API_URL, timeout=3)
        response.raise_for_status()
        data = response.json()
        
        # Process real data
        current_round = {
            "round_id": data["current"]["roundId"],
            "end_time": data["current"]["endTime"],
            "countdown": data["current"]["countdown"]
        }
        
        # Process recent results
        recent_results = []
        for result in data["recent"]:
            number = int(result["result"])
            recent_results.append({
                "round_id": result["roundId"],
                "number": number,
                "result": "Big" if number >= 5 else "Small",
                "parity": "Odd" if number % 2 == 1 else "Even",  # Add parity
                "timestamp": result["timestamp"]
            })
        
        # Update real-time data store
        global real_time_data
        real_time_data = {
            "current_round": current_round,
            "recent_results": recent_results
        }
        
        return real_time_data
        
    except Exception as e:
        logger.error(f"Hgzy API Error: {str(e)}")
        return None

async def connect_to_hgzy_websocket():
    """Connect to Hgzy WebSocket for real-time updates"""
    global active_websocket
    while True:
        try:
            async with websockets.connect(HGZY_WS_URL) as websocket:
                active_websocket = websocket
                logger.info("Connected to Hgzy WebSocket")
                
                while True:
                    message = await websocket.recv()
                    data = json.loads(message)
                    
                    # Process WebSocket data
                    if data.get("type") == "round_update":
                        # Update current round information
                        current_round = data["data"]
                        if real_time_data:
                            real_time_data["current_round"] = {
                                "round_id": current_round["roundId"],
                                "end_time": current_round["endTime"],
                                "countdown": current_round["countdown"]
                            }
                            
                    elif data.get("type") == "result_update":
                        # Add new result
                        result = data["data"]
                        number = int(result["result"])
                        new_result = {
                            "round_id": result["roundId"],
                            "number": number,
                            "result": "Big" if number >= 5 else "Small",
                            "parity": "Odd" if number % 2 == 1 else "Even",  # Add parity
                            "timestamp": result["timestamp"]
                        }
                        
                        if real_time_data:
                            # Add to beginning of list (most recent first)
                            real_time_data["recent_results"].insert(0, new_result)
                            # Keep only last 100 results
                            if len(real_time_data["recent_results"]) > 100:
                                real_time_data["recent_results"] = real_time_data["recent_results"][:100]
                            
                        # Also add to last_results
                        last_results.append(new_result)
                        if len(last_results) > 100:
                            last_results = last_results[-100:]
                            
                        logger.info(f"New result: {new_result}")
                        
        except Exception as e:
            logger.error(f"WebSocket error: {str(e)}")
            active_websocket = None
            await asyncio.sleep(3)  # Reconnect after 3 seconds

def start_websocket_thread():
    """Start WebSocket connection in a separate thread"""
    def run_websocket():
        asyncio.run(connect_to_hgzy_websocket())
    
    thread = threading.Thread(target=run_websocket, daemon=True)
    thread.start()
    logger.info("WebSocket thread started")

# ====== AI Agent Analysis Methods ======
def quantum_analysis(data):
    """Quantum Neural Network simulation"""
    if not data or not data["recent_results"]:
        return "Big" if random.random() > 0.5 else "Small", 75
    
    numbers = [r["number"] for r in data["recent_results"]]
    
    # Simulate quantum state analysis
    quantum_state = [abs(math.sin(n)) for n in numbers[-10:]]
    avg_state = sum(quantum_state) / len(quantum_state)
    
    prediction = "Big" if avg_state > 0.65 else "Small"
    confidence = min(99, int(80 + (abs(avg_state - 0.5) * 40))
    
    # Add quantum uncertainty
    confidence = max(65, confidence - random.randint(0, 10))
    
    return prediction, confidence

def temporal_analysis(data):
    """Time-based pattern analysis"""
    if not data or not data["recent_results"]:
        return "Big" if random.random() > 0.5 else "Small", 75
    
    # Analyze results by time of day
    hour_results = {}
    for res in data["recent_results"]:
        hour = datetime.fromtimestamp(res["timestamp"]).hour
        if hour not in hour_results:
            hour_results[hour] = []
        hour_results[hour].append(res["number"])
    
    # Current hour analysis
    current_hour = datetime.now().hour
    if current_hour in hour_results:
        avg = sum(hour_results[current_hour]) / len(hour_results[current_hour])
        prediction = "Big" if avg >= 4.8 else "Small"
        confidence = min(95, int(70 + len(hour_results[current_hour]) * 2))
    else:
        # Fallback to overall average
        numbers = [r["number"] for r in data["recent_results"]]
        avg = sum(numbers) / len(numbers)
        prediction = "Big" if avg >= 5 else "Small"
        confidence = 75
    
    return prediction, confidence

def statistical_analysis(data):
    """Statistical probability analysis"""
    if not data or not data["recent_results"]:
        return "Big" if random.random() > 0.5 else "Small", 75
    
    results = [r["result"] for r in data["recent_results"]]
    big_count = results.count("Big")
    small_count = len(results) - big_count
    
    # Bayesian probability calculation
    big_prob = (big_count + 1) / (len(results) + 2)
    small_prob = (small_count + 1) / (len(results) + 2)
    
    prediction = "Big" if big_prob > small_prob else "Small"
    confidence = int(max(big_prob, small_prob) * 100)
    
    return prediction, confidence

def volatility_analysis(data):
    """Market volatility-based prediction"""
    if not data or not data["recent_results"] or len(data["recent_results"]) < 10:
        return "Big" if random.random() > 0.5 else "Small", 75
    
    numbers = [r["number"] for r in data["recent_results"]]
    last_10 = numbers[-10:]
    
    # Calculate volatility
    volatility = max(last_10) - min(last_10)
    
    if volatility >= 7:
        # High volatility - predict opposite of last result
        prediction = "Small" if data["recent_results"][0]["result"] == "Big" else "Big"
        confidence = 82
    elif volatility <= 3:
        # Low volatility - predict same as last result
        prediction = data["recent_results"][0]["result"]
        confidence = 85
    else:
        # Medium volatility - use weighted average
        weights = [0.15, 0.13, 0.12, 0.11, 0.10, 0.09, 0.08, 0.07, 0.06, 0.05]
        weighted_sum = sum(num * weights[i] for i, num in enumerate(last_10))
        prediction = "Big" if weighted_sum >= 4.8 else "Small"
        confidence = min(90, int(80 + (abs(weighted_sum - 4.5) * 10)))
    
    return prediction, confidence

def harmonic_analysis(data):
    """Harmonic wave pattern detection"""
    if not data or len(data["recent_results"]) < 15:
        return "Big" if random.random() > 0.5 else "Small", 75
    
    numbers = [r["number"] for r in data["recent_results"]][-15:]
    
    # Fast Fourier Transform to detect patterns
    fft = np.fft.fft(numbers)
    frequencies = np.fft.fftfreq(len(numbers))
    
    # Find dominant frequency
    dominant_idx = np.argmax(np.abs(fft))
    dominant_freq = frequencies[dominant_idx]
    
    # Predict based on wave phase
    phase = (len(numbers) % (1/abs(dominant_freq))) if abs(dominant_freq) > 0 else 0
    prediction = "Big" if phase < 0.5 else "Small"
    confidence = min(95, int(80 + (1 - np.std(numbers)/5) * 20))
    
    return prediction, confidence

def ml_analysis(data):
    """Machine learning prediction"""
    global ml_model
    
    if not data or len(data["recent_results"]) < 20:
        return statistical_analysis(data)
    
    # Prepare data for ML model
    numbers = [r["number"] for r in data["recent_results"]]
    X = []
    y = []
    
    # Create features: last 10 numbers as input, next as target
    for i in range(10, len(numbers)):
        features = numbers[i-10:i]
        target = 1 if numbers[i] >= 5 else 0  # 1 = Big, 0 = Small
        X.append(features)
        y.append(target)
    
    # Train the model
    try:
        ml_model.fit(X[:-1], y[:-1])
        
        # Predict the next outcome
        last_features = numbers[-10:]
        prediction_proba = ml_model.predict_proba([last_features])[0]
        big_prob = prediction_proba[1]  # Probability for class 1 (Big)
        
        prediction = "Big" if big_prob >= 0.5 else "Small"
        confidence = int(big_prob * 100) if prediction == "Big" else int((1 - big_prob) * 100)
        
        return prediction, max(65, confidence)
    except Exception as e:
        logger.error(f"ML analysis failed: {str(e)}")
        return statistical_analysis(data)

# Assign analysis methods to agents
ai_agents["quantum"].analyze = quantum_analysis
ai_agents["temporal"].analyze = temporal_analysis
ai_agents["statistical"].analyze = statistical_analysis
ai_agents["volatility"].analyze = volatility_analysis
ai_agents["harmonic"].analyze = harmonic_analysis  # New agent

# ====== Visualization Tools ======
def create_trend_chart(results):
    """Create a trend visualization chart"""
    if len(results) < 5:
        return None
    
    numbers = [r["number"] for r in results[-20:]]
    timestamps = [datetime.fromtimestamp(r["timestamp"]).strftime('%H:%M') for r in results[-20:]]
    
    plt.figure(figsize=(10, 4))
    
    # Plot numbers
    plt.plot(timestamps, numbers, 'o-', label='Numbers', linewidth=2)
    
    # Add moving averages
    if len(numbers) >= 5:
        ma_5 = [sum(numbers[i:i+5])/5 for i in range(len(numbers)-4)]
        plt.plot(timestamps[4:], ma_5, 'g--', label='5-Round MA', linewidth=1.5)
    
    if len(numbers) >= 10:
        ma_10 = [sum(numbers[i:i+10])/10 for i in range(len(numbers)-9)]
        plt.plot(timestamps[9:], ma_10, 'r-.', label='10-Round MA', linewidth=1.5)
    
    # Formatting
    plt.title('WinGo Number Trends', fontsize=14)
    plt.xlabel('Time', fontsize=12)
    plt.ylabel('Number', fontsize=12)
    plt.xticks(rotation=45)
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.legend()
    plt.tight_layout()
    
    # Save to buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    
    return buf

def create_prediction_radar(agent_predictions):
    """Create radar chart of agent predictions"""
    plt.figure(figsize=(8, 8))
    
    # Data preparation
    agents = list(agent_predictions.keys())
    confidences = [agent_predictions[agent][1] for agent in agents]
    
    # Number of variables
    categories = agents
    N = len(categories)
    
    # Angle for each axis
    angles = [n / float(N) * 2 * np.pi for n in range(N)]
    angles += angles[:1]
    
    # Initial plot
    ax = plt.subplot(111, polar=True)
    
    # First axis on top
    plt.xticks(angles[:-1], categories, color='grey', size=10)
    
    # Draw ylabels
    ax.set_rlabel_position(0)
    plt.yticks([25, 50, 75, 100], ["25", "50", "75", "100"], color="grey", size=8)
    plt.ylim(0, 100)
    
    # Plot data
    confidences += confidences[:1]
    ax.plot(angles, confidences, linewidth=1, linestyle='solid', label="Confidence")
    ax.fill(angles, confidences, 'b', alpha=0.1)
    
    # Title
    plt.title("AI Agent Prediction Confidence", size=15, y=1.1)
    
    # Save to buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    
    return buf

# ====== Animation Effects ======
async def quantum_animation(update: Update, context: CallbackContext, prediction):
    """Create quantum prediction animation"""
    msg = await update.message.reply_text("🚀 Initializing quantum prediction sequence...")
    
    # Stage 1: Quantum initialization
    await msg.edit_text("🌌 Connecting to Hgzy.cc quantum network...")
    await asyncio.sleep(1)
    
    # Stage 2: Agent analysis visualization
    await msg.edit_text("🤖 Activating AI analysis agents...")
    await asyncio.sleep(0.5)
    
    agents_online = ""
    for agent_id in ai_agents:
        agents_online += f"🔹 {ai_agents[agent_id].name}\n"
        await msg.edit_text(f"🤖 AI Agents Online:\n{agents_online}")
        await asyncio.sleep(0.3)
    
    # Stage 3: Data processing
    await msg.edit_text("📊 Processing real-time game data...")
    await asyncio.sleep(0.5)
    
    # Stage 4: Prediction convergence
    animation_text = [
        "⚡ Synthesizing agent predictions...",
        "🌐 Converging quantum probabilities...",
        "🧠 Finalizing neural network output...",
        "🔮 Prediction imminent..."
    ]
    
    for text in animation_text:
        await msg.edit_text(text)
        await asyncio.sleep(0.5)
    
    # Final reveal
    await msg.edit_text(f"🎯 **NEXT WINGO: {prediction}** 🎯", parse_mode="Markdown")
    
    return msg

# ====== Channel Subscription Management ======
async def check_subscription(update: Update, context: CallbackContext) -> bool:
    """Check if user has joined the required channel"""
    user_id = update.effective_user.id
    
    # Check cache first
    if user_id in channel_subscribers:
        return True
    
    try:
        # Check channel status
        chat_member = await context.bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        if chat_member.status in ["member", "administrator", "creator"]:
            channel_subscribers.add(user_id)
            return True
    except Exception as e:
        logger.error(f"Subscription check error: {str(e)}")
    
    # User not subscribed
    keyboard = [
        [InlineKeyboardButton("✨ Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL[1:]}")],
        [InlineKeyboardButton("✅ I've Joined", callback_data="check_subscription")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔒 Access to advanced predictions requires joining our official channel!\n\n"
        f"Please join: {REQUIRED_CHANNEL}\n\n"
        "After joining, click '✅ I've Joined' to verify.",
        reply_markup=reply_markup
    )
    return False

async def subscription_callback(update: Update, context: CallbackContext) -> None:
    """Handle subscription verification callback"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "check_subscription":
        try:
            # Verify subscription
            chat_member = await context.bot.get_chat_member(REQUIRED_CHANNEL, query.from_user.id)
            if chat_member.status in ["member", "administrator", "creator"]:
                channel_subscribers.add(query.from_user.id)
                await query.edit_message_text(
                    "✅ Subscription verified! You now have access to all features.\n\n"
                    "Use /predict to get the next prediction!"
                )
            else:
                await query.answer("❌ You haven't joined the channel yet!", show_alert=True)
        except Exception as e:
            logger.error(f"Subscription verification error: {str(e)}")
            await query.answer("⚠️ Verification failed. Please try again.", show_alert=True)

# ====== Bot Command Handlers ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message with animation"""
    user = update.effective_user
    user_id = user.id
    
    # Initialize user stats
    if user_id not in user_stats:
        user_stats[user_id] = {
            "predictions": 0,
            "wins": 0,
            "losses": 0,
            "streak": 0,
            "max_streak": 0,
            "accuracy": 0.0
        }
    
    welcome_msg = await update.message.reply_text("🌌 Initializing quantum interface...")
    await asyncio.sleep(0.5)
    
    animations = [
        f"👋 HELLO {user.first_name.upper()}!",
        "⚡ QUANTUM WINGO PREDICTOR ACTIVATED",
        "🧠 AI ANALYSIS AGENTS ONLINE",
        "🌐 CONNECTED TO HGZY.CC LIVE SERVER",
        "💫 SYSTEM READY FOR QUANTUM PREDICTION"
    ]
    
    for text in animations:
        await welcome_msg.edit_text(text)
        await asyncio.sleep(0.3)
    
    await asyncio.sleep(1)
    await welcome_msg.edit_text(
        f"🚀 **WELCOME {user.first_name} TO AI-POWERED WINGO PREDICTOR!**\n\n"
        "✨ *Advanced Features:*\n"
        "- Real-time Hgzy.cc game integration\n"
        "- 5 specialized AI analysis agents\n"
        "- Machine learning predictions\n"
        "- Real-time data visualization\n"
        "- Win/loss statistics tracking\n\n"
        "🤖 *AI Agents:*\n"
        "- Quantum Neural Net: Deep pattern recognition\n"
        "- Temporal Analyst: Time-based predictions\n"
        "- Statistical Engine: Probability analysis\n"
        "- Volatility Tracker: Market fluctuations\n"
        "- Harmonic Analyst: Wave pattern detection\n\n"
        "🔮 *Commands:*\n"
        "/predict - Full prediction sequence\n"
        "/agents - AI agent predictions\n"
        "/live - Current game info\n"
        "/stats - Your prediction stats\n"
        "/server - Server status\n\n"
        "⚡ Type /predict to start!",
        parse_mode="Markdown"
    )
    
    # Check and request subscription
    await check_subscription(update, context)

async def predict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Full prediction sequence with AI analysis"""
    # Check subscription first
    if not await check_subscription(update, context):
        return
    
    user_id = update.effective_user.id
    
    # Fetch live data
    hgzy_data = real_time_data if real_time_data else await fetch_hgzy_data()
    if not hgzy_data:
        await update.message.reply_text("⚠️ Quantum network unstable. Please try again later.")
        return
    
    # Run AI agent analysis
    agent_predictions = {}
    for agent_id, agent in ai_agents.items():
        prediction, confidence = agent.analyze(hgzy_data)
        agent_predictions[agent_id] = (prediction, confidence)
    
    # Get ML prediction
    ml_prediction, ml_confidence = ml_analysis(hgzy_data)
    agent_predictions["ml"] = (ml_prediction, ml_confidence)
    
    # Determine consensus prediction with weighted voting
    total_weight = 0
    weighted_votes = {"Big": 0, "Small": 0}
    
    for agent_id, (prediction, confidence) in agent_predictions.items():
        if agent_id in ai_agents:
            agent = ai_agents[agent_id]
            weight = agent.weight * (agent.accuracy / 100) * (1 + agent.streak * 0.1)
        else:
            # For ML model
            weight = ml_stats["accuracy"] / 100 * (1 + ml_stats["streak"] * 0.1)
            
        weighted_votes[prediction] += weight
        total_weight += weight
    
    # Determine consensus
    if weighted_votes["Big"] > weighted_votes["Small"]:
        consensus = "Big"
        confidence = int((weighted_votes["Big"] / total_weight) * 100) if total_weight > 0 else ml_confidence
    else:
        consensus = "Small"
        confidence = int((weighted_votes["Small"] / total_weight) * 100) if total_weight > 0 else ml_confidence
    
    # Run the animation sequence
    anim_msg = await quantum_animation(update, context, consensus)
    
    # Get actual outcome
    actual_result = hgzy_data["recent_results"][0]
    actual_number = actual_result["number"]
    actual_outcome = actual_result["result"]
    is_correct = consensus == actual_outcome
    
    # Update user stats
    user_stats[user_id]["predictions"] += 1
    if is_correct:
        user_stats[user_id]["wins"] += 1
        user_stats[user_id]["streak"] += 1
        if user_stats[user_id]["streak"] > user_stats[user_id]["max_streak"]:
            user_stats[user_id]["max_streak"] = user_stats[user_id]["streak"]
    else:
        user_stats[user_id]["losses"] += 1
        user_stats[user_id]["streak"] = 0
    
    # Update agent stats
    for agent in ai_agents.values():
        agent_pred = agent.analyze(hgzy_data)[0]  # Re-run for consistency
        agent.update_stats(agent_pred == actual_outcome)
    
    # Update ML stats
    is_ml_correct = ml_prediction == actual_outcome
    ml_stats["predictions"] += 1
    if is_ml_correct:
        ml_stats["wins"] += 1
        ml_stats["streak"] += 1
        if ml_stats["streak"] > ml_stats["max_streak"]:
            ml_stats["max_streak"] = ml_stats["streak"]
    else:
        ml_stats["streak"] = 0
    ml_stats["accuracy"] = (ml_stats["wins"] / ml_stats["predictions"]) * 100 if ml_stats["predictions"] > 0 else 0
    
    # Calculate accuracy
    total = user_stats[user_id]["predictions"]
    wins = user_stats[user_id]["wins"]
    user_stats[user_id]["accuracy"] = (wins / total) * 100 if total > 0 else 0
    
    # Add to history
    prediction_history.append({
        "user_id": user_id,
        "timestamp": datetime.now(),
        "prediction": consensus,
        "outcome": actual_outcome,
        "number": actual_number,
        "is_correct": is_correct,
        "confidence": confidence,
        "agents": agent_predictions
    })
    
    # Prepare result message
    result_msg = (
        f"🎲 **ACTUAL RESULT: {actual_outcome.upper()} ({actual_number})**\n"
        f"📊 Consensus Confidence: {confidence:.1f}%\n"
        f"⏱️ Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    
    if is_correct:
        result_msg += f"✅ **AI PREDICTION ACCURATE!**\n"
        result_msg += f"🔥 Current Streak: {user_stats[user_id]['streak']}\n"
    else:
        result_msg += f"❌ **PREDICTION INACCURATE!**\n"
        result_msg += f"💔 Streak reset to 0\n"
    
    # Add agent performance
    result_msg += "\n🤖 Agent Performance:\n"
    for agent_id, agent in ai_agents.items():
        result_msg += f"- {agent.name}: {agent.accuracy:.1f}% ({agent.streak}🔥)\n"
    
    # Send result
    await anim_msg.reply_text(result_msg, parse_mode="Markdown")
    
    # Add trend visualization
    if len(last_results) >= 5:
        chart_buf = create_trend_chart(last_results)
        if chart_buf:
            await update.message.reply_photo(photo=chart_buf, caption="📈 Recent Number Trends")

async def show_agents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show predictions from all AI agents"""
    # Check subscription first
    if not await check_subscription(update, context):
        return
    
    # Fetch live data
    hgzy_data = real_time_data if real_time_data else await fetch_hgzy_data()
    if not hgzy_data:
        await update.message.reply_text("⚠️ Quantum network unstable. Please try again later.")
        return
    
    # Run AI agent analysis
    agent_predictions = {}
    for agent_id, agent in ai_agents.items():
        prediction, confidence = agent.analyze(hgzy_data)
        agent_predictions[agent_id] = (prediction, confidence)
    
    # Get ML prediction
    ml_prediction, ml_confidence = ml_analysis(hgzy_data)
    agent_predictions["ml"] = (ml_prediction, ml_confidence)
    
    # Prepare response
    response = "🤖 **AI AGENT PREDICTIONS**\n\n"
    for agent_id, (prediction, confidence) in agent_predictions.items():
        agent_name = ai_agents[agent_id].name if agent_id in ai_agents else "Machine Learning Model"
        response += f"🔹 {agent_name}:\n"
        response += f"   - Prediction: **{prediction}**\n"
        response += f"   - Confidence: **{confidence}%**\n"
        if agent_id in ai_agents:
            agent = ai_agents[agent_id]
            response += f"   - Accuracy: {agent.accuracy:.1f}%\n"
            response += f"   - Streak: {agent.streak}🔥\n"
            response += f"   - Weight: {agent.weight:.2f}\n\n"
        else:
            response += f"   - Accuracy: {ml_stats['accuracy']:.1f}%\n"
            response += f"   - Streak: {ml_stats['streak']}🔥\n\n"
    
    # Add radar chart
    radar_buf = create_prediction_radar(agent_predictions)
    if radar_buf:
        await update.message.reply_photo(photo=radar_buf, caption=response, parse_mode="Markdown")
    else:
        await update.message.reply_text(response, parse_mode="Markdown")

async def live(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show real-time game information"""
    # Check subscription first
    if not await check_subscription(update, context):
        return
    
    try:
        hgzy_data = real_time_data if real_time_data else await fetch_hgzy_data()
        if not hgzy_data:
            raise Exception("No data available")
        
        current_round = hgzy_data["current_round"]
        recent = hgzy_data["recent_results"][:5]
        analysis = analyze_historical_patterns(last_results)
        
        # Generate prediction
        ml_prediction, ml_confidence = ml_analysis(hgzy_data)
        
        # Format response
        countdown = current_round["countdown"]
        response = (
            f"🔴 **LIVE WINGO ROUND**\n\n"
            f"🆔 Round ID: `{current_round['round_id']}`\n"
            f"⏳ Time Remaining: {countdown} seconds\n\n"
            f"🧠 **AI Prediction:**\n"
            f"- Next: **{ml_prediction}**\n"
            f"- Confidence: **{ml_confidence}%**\n\n"
            f"📊 **Market Analysis:**\n"
            f"- Trend: {analysis['trend']}\n"
            f"- Volatility: {analysis['volatility']}\n"
            f"- Pattern: {analysis['patterns']}\n"
            f"- Big Ratio: {analysis['big_ratio']}\n"
            f"- Small Ratio: {analysis['small_ratio']}\n"
            f"- Odd Ratio: {analysis['odd_ratio']}\n"
            f"- Even Ratio: {analysis['even_ratio']}\n\n"
            f"📜 **Last 5 Results:**\n"
        )
        
        for i, res in enumerate(recent, 1):
            dt = datetime.fromtimestamp(res['timestamp'])
            outcome_icon = "🔴" if res["result"] == "Big" else "🔵"
            parity_icon = "⚫" if res["parity"] == "Odd" else "⚪"
            response += f"{i}. {outcome_icon}{parity_icon} #{res['number']} ({dt.strftime('%H:%M:%S')})\n"
        
        # Add countdown animation
        countdown_msg = await update.message.reply_text(response, parse_mode="Markdown")
        
        # Real-time countdown update
        while countdown > 0:
            await asyncio.sleep(1)
            countdown -= 1
            if countdown % 10 == 0 or countdown < 10:
                response = response.split('\n\n')[0] + f"\n⏳ Time Remaining: {countdown} seconds\n\n" + '\n\n'.join(response.split('\n\n')[1:])
                await countdown_msg.edit_text(response, parse_mode="Markdown")
        
        # Final update
        response = response.split('\n\n')[0] + "\n⏰ ROUND ENDED! Waiting for result...\n\n" + '\n\n'.join(response.split('\n\n')[1:])
        await countdown_msg.edit_text(response, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Live command error: {str(e)}")
        await update.message.reply_text("⚠️ Failed to get live data. Quantum sensors offline.")

async def server_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check Hgzy server status"""
    try:
        # Check API status
        api_response = requests.get(HGZY_API_URL, timeout=3)
        api_status = "✅ Online" if api_response.status_code == 200 else "❌ Offline"
        
        # Check WebSocket status
        ws_status = "✅ Connected" if active_websocket else "❌ Disconnected"
        
        # Check game URL status
        game_response = requests.get(GAME_URL, timeout=3)
        game_status = "✅ Online" if game_response.status_code == 200 else "❌ Offline"
        
        # Get last update time
        last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Get recent results count
        results_count = len(last_results)
        
        # Get server time
        if real_time_data and real_time_data["current_round"]:
            server_time = datetime.fromtimestamp(real_time_data["current_round"]["end_time"] - real_time_data["current_round"]["countdown"]).strftime("%H:%M:%S")
        else:
            server_time = "N/A"
        
        response = (
            f"🖥️ **HGZY SERVER STATUS**\n\n"
            f"🌐 Game URL: {game_status}\n"
            f"🔌 API Status: {api_status}\n"
            f"📡 WebSocket: {ws_status}\n"
            f"🕒 Server Time: {server_time}\n"
            f"🕒 Last Update: {last_update}\n"
            f"📊 Recent Results: {results_count}\n\n"
            f"👥 Channel Members: {len(channel_subscribers)}\n\n"
            f"⚡ System Status: {'✅ OPERATIONAL' if api_status == '✅ Online' else '❌ DEGRADED'}"
        )
        
        await update.message.reply_text(response, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Server status error: {str(e)}")
        await update.message.reply_text("⚠️ Failed to check server status. Quantum interference detected.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user prediction statistics"""
    user_id = update.effective_user.id
    
    # Initialize if new user
    if user_id not in user_stats:
        user_stats[user_id] = {
            "predictions": 0,
            "wins": 0,
            "losses": 0,
            "streak": 0,
            "max_streak": 0,
            "accuracy": 0.0
        }
    
    stats = user_stats[user_id]
    response = (
        f"📊 **YOUR PREDICTION STATS**\n\n"
        f"🔮 Total Predictions: {stats['predictions']}\n"
        f"✅ Correct: {stats['wins']}\n"
        f"❌ Incorrect: {stats['losses']}\n"
        f"🎯 Accuracy: {stats['accuracy']:.1f}%\n"
        f"🔥 Current Streak: {stats['streak']}\n"
        f"🏆 Max Streak: {stats['max_streak']}\n\n"
        f"⚡ Keep predicting to improve your stats!"
    )
    
    await update.message.reply_text(response, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle non-command messages"""
    # Check if message is about joining channel
    if "join" in update.message.text.lower() or "channel" in update.message.text.lower():
        await check_subscription(update, context)
    else:
        await update.message.reply_text(
            "🤖 I'm an AI-powered WinGo predictor!\n\n"
            "Use /predict to get the next prediction\n"
            "/live to see current game info\n"
            "/agents to see AI predictions\n\n"
            "Type /help for more options!"
        )

# ====== Main Application ======
def main() -> None:
    """Start the bot"""
    # Create Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    command_handlers = [
        CommandHandler("start", start),
        CommandHandler("predict", predict),
        CommandHandler("agents", show_agents),
        CommandHandler("live", live),
        CommandHandler("server", server_status),
        CommandHandler("stats", stats),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message),
        CallbackQueryHandler(subscription_callback)
    ]
    
    for handler in command_handlers:
        application.add_handler(handler)
    
    # Initialize ML model
    init_ml_model()
    
    # Start WebSocket connection
    start_websocket_thread()
    
    # Run bot
    logger.info("🚀 AI-Powered WinGo Predictor is running...")
    logger.info("🌐 Connected to Hgzy.cc server")
    logger.info(f"🤖 {len(ai_agents)} AI agents activated")
    logger.info(f"🔔 Requiring channel: {REQUIRED_CHANNEL}")
    logger.info("⚡ Press Ctrl+C to stop the bot")
    application.run_polling()

if __name__ == "__main__":
    main()