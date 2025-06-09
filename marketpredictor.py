import requests
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk
from tkinter import filedialog
import time

import itertools
import tkinter.font as tkfont
from ftplib import FTP

import asyncio
import threading
from telegram import Bot
from telegram.error import TelegramError
from telegram.request import HTTPXRequest
import logging
import httpx

# Add these configuration variables near your other constants
TELEGRAM_BOT_TOKEN = "7313019255:AAHLX7402sOnleA6G8X4zOd81T3ANZD1I8M"  # Replace with your bot token
TELEGRAM_CHAT_IDS = ["1467753798", "7067223564"]  # Replace with your chat ID

DataInterval = 30

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    filename="binance_api.log",
    filemode="a",  # Append mode
    format="%(asctime)s - %(levelname)s - %(message)s"
)


# Telegram Related Class
import asyncio
import threading
from telegram import Bot
from telegram.error import TelegramError
from telegram.request import HTTPXRequest
import logging
import httpx

class TelegramBot:
    def __init__(self, token, chat_ids):
        self.token = token
        self.chat_ids = chat_ids
        # Create a single client instance with larger connection pool
        self.client = httpx.AsyncClient(
            timeout=30.0,  # Increased timeout
            limits=httpx.Limits(
                max_connections=10,  # Increased connection pool
                max_keepalive_connections=5
            )
        )
        # Initialize the request object without passing client directly
        self.request = HTTPXRequest()
        self.request._client = self.client  # Manually set the client

    async def _send_message_async(self, text):
        bot = Bot(token=self.token, request=self.request)
        for chat_id in self.chat_ids:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    read_timeout=30,  # Increased read timeout
                    write_timeout=30,  # Increased write timeout
                    connect_timeout=30  # Increased connect timeout
                )
                await asyncio.sleep(1)  # Small delay between messages
            except TelegramError as e:
                logging.error(f"Telegram send message error to {chat_id}: {e}")
                continue  # Continue with next chat ID if one fails

    def send_message_sync(self, text):
        def _run():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._send_message_async(text))
            except Exception as e:
                logging.error(f"Error sending Telegram message: {e}")
            finally:
                loop.close()
        
        # Run in a separate thread to avoid blocking
        threading.Thread(target=_run, daemon=True).start()

    def __del__(self):
        # Clean up the client when the bot is destroyed
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.client.aclose())
        except Exception as e:
            logging.error(f"Error closing Telegram client: {e}")


# Initialize the Telegram bot at the start of your script (before process_symbols())
telegram_bot = TelegramBot(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS)

# Binance API URLs
LSR_URL = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
KLINE_URL = "https://fapi.binance.com/fapi/v1/klines"
EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
OPEN_INTEREST_URL = "https://fapi.binance.com/fapi/v1/openInterest"  # Open Interest endpoint
FUNDING_RATE_URL = "https://fapi.binance.com/fapi/v1/fundingRate"


# Funding Rate function
def fetch_funding_rate(symbol, limit=1):
    """
    Fetch the most recent funding rate for a given symbol.
    Returns the funding rate (as percentage) and mark price.
    """
    params = {"symbol": symbol, "limit": limit}
    try:
        response = requests.get(FUNDING_RATE_URL, params=params, timeout=10)
        response.raise_for_status()
        funding_data = response.json()
        if funding_data:
            latest_funding = funding_data[-1]  # Get the most recent entry
            return {
                "fundingRate": float(latest_funding["fundingRate"]) * 100,  # Convert to percentage
                "markPrice": float(latest_funding["markPrice"]),
                "fundingTime": latest_funding["fundingTime"]
            }
        return {"fundingRate": 0.0, "markPrice": 0.0, "fundingTime": 0}
    except Exception as e:
        logging.error(f"Error fetching funding rate for {symbol}: {e}")
        return {"fundingRate": 0.0, "markPrice": 0.0, "fundingTime": 0}

# Retry mechanism with exponential backoff
def fetch_data(url, params=None, retries=100):
    for attempt in range(retries):
        try:
            #logging.info(f"Fetching data from {url} with params: {params}")
            response = requests.get(url, params=params, timeout=10)  # 10 seconds timeout
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx, 5xx)
            logging.info(f"Successful response from {url}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching data from {url}: {e}")
            if attempt < retries - 1:
                sleep_time = 2 ** attempt  # Exponential backoff
                logging.warning(f"Retrying in {sleep_time} seconds... (Attempt {attempt + 1}/{retries})")
                time.sleep(sleep_time)
            else:
                logging.critical(f"Max retries reached. Could not fetch data from {url}")
                raise

# Test all three URLs
try:
    # Fetch Long/Short Ratio data
    params_lsr = {"symbol": "BTCUSDT", "period": "5m", "limit": 30}
    lsr_data = fetch_data(LSR_URL, params=params_lsr)
    logging.info(f"Long/Short Ratio Data: {lsr_data}")

    # Fetch Kline data
    params_kline = {"symbol": "BTCUSDT", "interval": "30m", "limit": 30}
    kline_data = fetch_data(KLINE_URL, params=params_kline)
    logging.info(f"Kline Data: {kline_data}")

    # Fetch Exchange Info
    exchange_info_data = fetch_data(EXCHANGE_INFO_URL)
    logging.info(f"Exchange Info Data: {exchange_info_data}")

except Exception as e:
    logging.critical(f"Failed to fetch data: {e}")

# Parameters for API requests
interval = "30m"
limit = 30

print("Starting Market Predictor")

# Function to calculate VWAP
def calculate_vwap(klines):
    """
    VWAP is a popular indicator that combines price and volume to give an average price a security has traded at throughout the day. 
    It's often used to identify trends and potential entry/exit points.
    """
    total_volume = 0
    total_price_volume = 0

    for kline in klines:
        high = float(kline[2])
        low = float(kline[3])
        close = float(kline[4])
        volume = float(kline[5])

        typical_price = (high + low + close) / 3  # Typical price for the period
        total_price_volume += typical_price * volume
        total_volume += volume

    if total_volume == 0:
        return 0  # Avoid division by zero
    return total_price_volume / total_volume

# Function to fetch Open Interest (OI)

def fetch_open_interest(symbol):
    """
    This represents the total number of outstanding futures contracts. 
    Increasing OI can indicate new money entering the market, while decreasing OI may suggest that traders are closing positions.
    """
    params = {"symbol": symbol}
    try:
        response = requests.get(OPEN_INTEREST_URL, params=params, timeout=10)
        response.raise_for_status()
        oi_data = response.json()
        return float(oi_data["openInterest"])
    except Exception as e:
        logging.error(f"Error fetching Open Interest for {symbol}: {e}")
        return 0.0  # Default value if no data is available


# Function to calculate RSI
def calculate_rsi(prices):
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gain = sum(x for x in deltas if x > 0) / limit
    loss = abs(sum(x for x in deltas if x < 0)) / limit
    if loss == 0:
        return 100
    else:
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
    return rsi

# Function to calculate EMA
def calculate_ema(prices, period):
    ema = [sum(prices[:period]) / period]
    multiplier = 2 / (period + 1)
    for price in prices[period:]:
        new_ema = (price - ema[-1]) * multiplier + ema[-1]
        ema.append(new_ema)
    return ema[-1]

# Function to calculate MACD
def calculate_macd(prices, short_period=12, long_period=26, signal_period=9):
    short_ema = calculate_ema(prices, short_period)
    long_ema = calculate_ema(prices, long_period)
    macd_line = short_ema - long_ema
    signal_line = calculate_ema([macd_line] * signal_period, signal_period)
    #macd_histogram = macd_line - signal_line
    return macd_line, signal_line

# Function to calculate ATR
def calculate_atr(highs, lows, closes, period=limit):
    tr = [max(high - low, abs(high - closes[i - 1]), abs(low - closes[i - 1])) for i, (high, low) in enumerate(zip(highs[1:], lows[1:]), 1)]
    return sum(tr[-period:]) / period

# Function to calculate CND Rating
def calculate_cnd_rating(long_percent, short_percent):
    return (long_percent / (long_percent + short_percent)) * 10

# Function to calculate DMI and ADX with EMA smoothing
def calculate_dmi_and_adx(highs, lows, closes, period=limit):
    plus_dm = [max(highs[i] - highs[i - 1], 0) if (highs[i] - highs[i - 1]) > (lows[i - 1] - lows[i]) else 0 for i in range(1, len(highs))]
    minus_dm = [max(lows[i - 1] - lows[i], 0) if (lows[i - 1] - lows[i]) > (highs[i] - highs[i - 1]) else 0 for i in range(1, len(lows))]
    
    tr = [max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])) for i in range(1, len(highs))]
    
    tr_sum = sum(tr[-period:])
    
    if tr_sum == 0:
        # If tr_sum is zero, set default values to avoid division by zero
        plus_di = 0
        minus_di = 0
        adx = 0
    else:
        plus_di = (sum(plus_dm[-period:]) / tr_sum) * 100
        minus_di = (sum(minus_dm[-period:]) / tr_sum) * 100
        dx = [(abs(plus_di - minus_di) / (plus_di + minus_di)) * 100 if (plus_di + minus_di) != 0 else 0 for _ in range(period)]
        
        # Apply an EMA for ADX calculation (smoothing)
        multiplier = 2 / (period + 1)
        adx = dx[0]  # Initial ADX value
        for i in range(1, period):
            adx = ((dx[i] - adx) * multiplier) + adx  # EMA formula for smoothing
    
    return plus_di, minus_di, adx

# Function to calculate Signal Quality
def calculate_signal_quality(cnd_rating, rsi, macd_line, signal_line):
    if cnd_rating >= 7 and rsi < 30:
        return "4CR"
    elif cnd_rating >= 5 and rsi < 50 and macd_line > signal_line:
        return "3CR"
    elif cnd_rating >= 3 and rsi < 70:
        return "2CR"
    else:
        return "1CR"

# Function to fetch top_trader_ratio
def fetch_top_trader_ratio(symbol):
    """
    Fetch the top trader long/short ratio (positions) for the given symbol.

    Args:
        symbol (str): The trading pair symbol (e.g., BTCUSDT).

    Returns:
        float: The latest top trader long/short ratio.
    """
    TOP_TRADER_RATIO_URL = "https://fapi.binance.com/futures/data/topLongShortPositionRatio"
    params = {"symbol": symbol, "period": "30m", "limit": 1}  # 30-minute interval, latest data only

    try:
        response = requests.get(TOP_TRADER_RATIO_URL, params=params, timeout=10)
        response.raise_for_status()
        trader_data = response.json()
        if trader_data:
            return float(trader_data[-1]["longShortRatio"])
        return 0.0
    except Exception as e:
        logging.error(f"Error fetching top trader ratio for {symbol}: {e}")
        return 0.0

    if response.status_code == 200:
        trader_data = response.json()
        if len(trader_data) > 0:
            return float(trader_data[-1]["longShortRatio"])
        else:
            return 0.0  # Default value if no data is available
    else:
        print(f"Error fetching top trader ratio for {symbol}: {response.status_code}")
        return 0.0

# Main symbol processing function
def process_symbols():
    # Get all futures symbols
    exchange_info_response = requests.get(EXCHANGE_INFO_URL)
    exchange_info_data = exchange_info_response.json()
    symbols = [symbol['symbol'] for symbol in exchange_info_data['symbols']]
    
    all_results = []

    for symbol in symbols:
        lsr_params = {"symbol": symbol, "period": interval, "limit": limit}
        kline_params = {"symbol": symbol, "interval": interval, "limit": limit}

        lsr_response = requests.get(LSR_URL, params=lsr_params)
        lsr_data = lsr_response.json()

        kline_response = requests.get(KLINE_URL, params=kline_params)
        kline_data = kline_response.json()

        if len(lsr_data) >= limit and len(kline_data) >= limit:
            long_account_percent = float(lsr_data[-1]['longAccount'])
            short_account_percent = float(lsr_data[-1]['shortAccount'])
            long_short_ratio = float(lsr_data[-1]['longShortRatio'])

            cnd_rating = calculate_cnd_rating(long_account_percent, short_account_percent)

            closing_prices = [float(kline_entry[4]) for kline_entry in kline_data]
            highs = [float(kline_entry[2]) for kline_entry in kline_data]
            lows = [float(kline_entry[3]) for kline_entry in kline_data]
            rsi = calculate_rsi(closing_prices)

            current_price = closing_prices[-1]

            macd_line, signal_line = calculate_macd(closing_prices)
            atr = calculate_atr(highs, lows, closing_prices)

            di_plus, di_minus, adx = calculate_dmi_and_adx(highs, lows, closing_prices)

            signal_quality = calculate_signal_quality(cnd_rating, rsi, macd_line, signal_line)

            # Fetch top trader ratio
            top_trader_ratio = fetch_top_trader_ratio(symbol)

            # Calculate VWAP
            vwap = calculate_vwap(kline_data)

            # Fetch Open Interest
            open_interest = fetch_open_interest(symbol)

            # Fetch Funding Rate Data
            funding_data = fetch_funding_rate(symbol)
            funding_rate = funding_data["fundingRate"]
            funding_mark_price = funding_data["markPrice"]
            funding_time = datetime.fromtimestamp(funding_data["fundingTime"]/1000).strftime("%Y-%m-%d %H:%M:%S")

            # Adding a timestamp for the data collected
            timestamp = datetime.now().strftime("%H:%M:%S")

            result = {
                "Timestamp": timestamp,
                "Symbol": symbol,
                "RSI": rsi,
                "Long/Short Ratio": long_short_ratio,
                "Top Trader Ratio": top_trader_ratio,
                "CND Rating": cnd_rating,
                "Signal Quality": signal_quality,
                "Current Price": current_price,
                "MACD Line": macd_line,
                "ATR": atr,
                "DI+": di_plus,
                "DI-": di_minus,
                "ADX": adx,
                "VWAP": vwap,
                "Open Interest": open_interest,
                "Funding Rate": funding_rate,
                "Funding Mark Price": funding_mark_price,
                "Last Funding Time": funding_time,
            }

            all_results.append(result)
    
    df = pd.DataFrame(all_results)
    return df

# Function to save the grouped data by Signal Quality into an Excel file
def save_grouped_by_signal_quality(df):
    current_time = datetime.now().strftime("%d%m%Y_%H%M")
    output_file = f"{current_time}.xlsx"
    writer = pd.ExcelWriter(output_file, engine='xlsxwriter')

    # Define the columns to include (now with funding rate data)
    columns_to_include = [
        "Timestamp", "Symbol", "RSI", "Long/Short Ratio", "Top Trader Ratio",
        "CND Rating", "Signal Quality", "Current Price", "MACD Line", "ATR",
        "DI+", "DI-", "ADX", "VWAP", "Open Interest","Funding Rate", 
        "Funding Mark Price", "Last Funding Time"
    ]

    # Create a summary per Signal Quality with additional funding metrics
    summary = df.groupby("Signal Quality").agg(
        Total_Symbols=("Symbol", "nunique"),
        Avg_RSI=("RSI", "mean"),
        Avg_ATR=("ATR", "mean"),
        Avg_ADX=("ADX", "mean"),
        Avg_DIplus=("DI+", "mean"),
        Avg_DImin=("DI-", "mean"),
        Avg_VWAP=("VWAP", "mean"),
        Avg_Open_Interest=("Open Interest", "mean"),
        Avg_Funding_Rate=("Funding Rate", "mean"),
        Total_Trades=("Symbol", "count"),
    ).reset_index()

    # Write the Signal Quality summary to the leftmost sheet named "Summary"
    summary.to_excel(writer, sheet_name="Summary", index=False, startrow=0)

    # Find the top coins by DI+ and DI- with all columns including funding data
    top_di_plus = df.nlargest(10, "DI+")[columns_to_include].reset_index(drop=True)
    top_di_minus = df.nlargest(10, "DI-")[columns_to_include].reset_index(drop=True)

    # Write the top 10 DI+ coins below the summary
    top_di_plus_startrow = len(summary) + 3  # Leave some space below the summary
    top_di_plus.to_excel(
        writer,
        sheet_name="Summary",
        index=False,
        startrow=top_di_plus_startrow,
        startcol=0,
    )
    worksheet = writer.sheets["Summary"]
    worksheet.write(top_di_plus_startrow - 1, 0, "Top 10 Coins by DI+ with Details")

    # Write the top 10 DI- coins below the top DI+ table
    top_di_minus_startrow = top_di_plus_startrow + len(top_di_plus) + 3
    top_di_minus.to_excel(
        writer,
        sheet_name="Summary",
        index=False,
        startrow=top_di_minus_startrow,
        startcol=0,
    )
    worksheet.write(top_di_minus_startrow - 1, 0, "Top 10 Coins by DI- with Details")

    # Create Individual Coin data per Signal Quality
    signal_qualities = df["Signal Quality"].unique()

    for quality in signal_qualities:
        df_quality = df[df["Signal Quality"] == quality]
        # Include all columns including funding data for individual sheets
        df_quality[columns_to_include].to_excel(writer, sheet_name=str(quality), index=False)

        # Auto-adjust column widths for better readability
        worksheet = writer.sheets[str(quality)]
        for idx, col in enumerate(df_quality[columns_to_include].columns):
            max_len = max(
                df_quality[col].astype(str).map(len).max(),  # Max length in data
                len(str(col))  # Length of column header
            ) + 1  # Add a little extra space
            worksheet.set_column(idx, idx, max_len)

    # Auto-adjust column widths for the Summary sheet
    worksheet = writer.sheets["Summary"]
    for idx, col in enumerate(summary.columns):
        max_len = max((
            summary[col].astype(str).map(len).max(),
            len(str(col))
        )) + 1
        worksheet.set_column(idx, idx, max_len)

    # Add conditional formatting for Funding Rate (negative values in red)
    for sheet_name in writer.sheets:
        worksheet = writer.sheets[sheet_name]
        # Find the column index for Funding Rate
        if "Funding Rate" in columns_to_include:
            col_idx = columns_to_include.index("Funding Rate")
            # Format negative funding rates in red
            worksheet.conditional_format(
                1, col_idx, len(df), col_idx,
                {
                    'type': 'cell',
                    'criteria': '<',
                    'value': 0,
                    'format': writer.book.add_format({'font_color': 'red'})
                }
            )

    # Save the Excel file locally
    writer.close()

    # Upload the file to the FTP server
    ftp_host = "192.168.1.1"
    ftp_user = "admin"  # Replace with your FTP username
    ftp_pass = "admin"  # Replace with your FTP password
    ftp_path = "/volume(sda2)/Data/"

    try:
        with FTP(ftp_host) as ftp:
            ftp.login(user=ftp_user, passwd=ftp_pass)
            ftp.cwd(ftp_path)  # Change to the target directory
            with open(output_file, "rb") as file:
                ftp.storbinary(f"STOR {output_file}", file)  # Upload the file
            print(f"File {output_file} uploaded successfully to {ftp_path}")
    except Exception as e:
        print(f"FTP upload failed: {e}")

    return output_file

# Function to update data and refresh the GUI
def update_data():
    global new_df, top_30_stats, next_update_time

    # Fetch new data
    df = process_symbols()

    # Save the grouped data by Signal Quality into an Excel file
    save_grouped_by_signal_quality(df)
    
    # Filter for Funding Rate < -0.2500 and RSI > 60
    negative_funding_df = df[(df["Funding Rate"] < -0.2500) & (df["RSI"] > 60)]
    top_negative_funding = negative_funding_df.nsmallest(10, "Funding Rate")

    # Prepare Telegram message for filtered results
    if not top_negative_funding.empty:
        message_lines = ["🔴 Top Coins with RSI > 60 and High Negative Funding Rates (< -0.2500%):"]
        for i, (_, row) in enumerate(top_negative_funding.iterrows(), 1):
            price = row['Current Price']
            message_lines.append(
                f"{i}. {row['Symbol']}: "
                f"Funding {row['Funding Rate']:.5f}% | RSI {row['RSI']:.1f} | DI- {row['DI-']:.2f} | "
                f"VWAP {row['VWAP']:.5f} | Price+5%: {price * 1.05:.5f} | Price-5%: {price * 0.95:.5f} | "
                f"Last Funding: {row['Last Funding Time']}"
            )
        message = "\n".join(message_lines)
        telegram_bot.send_message_sync(message)
        # Print formatted time and message
        print("Current Time:", datetime.now().strftime("%H:%M:%S"), "- Sending Telegram Message..")
    """else:
        telegram_bot.send_message_sync("ℹ️ No coins with funding rate < -0.2500% found in this interval.")"""

    # Update GUI for Top 10 Coins by DI+
    top_di_plus = df.nlargest(10, "DI+")

    for i in range(10):
        if i < len(top_di_plus):
            row = top_di_plus.iloc[i]
            top_di_plus_labels[i]["text"] = (
                f"{row['Symbol']}: DI+ {row['DI+']:.2f} | "
                f"RSI {row['RSI']:.1f} | "
                f"Funding {row['Funding Rate']:.5f}%"
            )
        else:
            top_di_plus_labels[i]["text"] = ""

        if i < len(top_negative_funding):
            row = top_negative_funding.iloc[i]
            negative_funding_labels[i]["text"] = (
                f"{row['Symbol']}: Funding {row['Funding Rate']:.5f}% | "
                f"RSI {row['RSI']:.1f} | "
                f"DI- {row['DI-']:.2f}"
            )
        else:
            negative_funding_labels[i]["text"] = ""

    # Calculate grouped statistics including funding rate
    grouped_stats_new = df.groupby("Signal Quality").agg({
        "DI+": "mean",
        "DI-": "mean",
        "RSI": "mean",
        "Funding Rate": "mean"
    }).rename(columns={
        "DI+": "Avg_DI+",
        "DI-": "Avg_DI-",
        "RSI": "Avg_RSI",
        "Funding Rate": "Avg_Funding"
    })

    # Prepare new stats string with funding rate as percentage
    current_time = datetime.now().strftime("%H:%M:%S")
    stats_label_new = f"{current_time} | " + " | ".join([
        f"{quality}: DI+ {row['Avg_DI+']:.2f} DI- {row['Avg_DI-']:.2f} "
        f"RSI {row['Avg_RSI']:.2f} "
        f"Funding {row['Avg_Funding']:.5f}%"
        for quality, row in grouped_stats_new.iterrows()
    ])

    # Maintain only the top 30 stats
    if len(top_30_stats) >= 30:
        top_30_stats.pop(0)
    top_30_stats.append(stats_label_new)

    # Update GUI for Grouped Stats
    stats_listbox.delete(0, tk.END)
    for stat in top_30_stats:
        stats_listbox.insert(tk.END, stat)

    # Update the next update time
    next_update_time = datetime.now() + timedelta(minutes=DataInterval)
    update_timer()

    # Schedule the next update
    root.after(DataInterval * 60 * 1000, update_data)

# Function to update the countdown timer for the next update
def update_timer():
    global next_update_time

    if next_update_time:
        remaining_time = next_update_time - datetime.now()
        if remaining_time.total_seconds() > 0:
            timer_label["text"] = f"Next update in: {remaining_time.seconds // 60}m {remaining_time.seconds % 60}s"
            root.after(1000, update_timer)  # Update every second
        else:
            timer_label["text"] = "Updating now..."

# Create GUI
root = tk.Tk()
root.title("Market Predictor")

# Make the window wider to accommodate the additional information
root.geometry("1200x800")

# Use a monospace font for better alignment
mono_font = tkfont.Font(family="Courier", size=10)

# Top 10 Coins by DI+ Frame
di_plus_frame = tk.Frame(root)
di_plus_frame.grid(row=0, column=0, padx=10, pady=5, sticky="nsew")
tk.Label(di_plus_frame, text="Top 10 Coins by DI+:", font=("Arial", 12, "bold")).pack()

# Top 10 Coins by DI+ Labels - now with funding rate
top_di_plus_labels = [tk.Label(di_plus_frame, text="", font=mono_font) for _ in range(10)]
for label in top_di_plus_labels:
    label.pack(anchor="w")

""" # Top 10 Coins by DI- Frame
di_minus_frame = tk.Frame(root)
di_minus_frame.grid(row=0, column=1, padx=10, pady=5, sticky="nsew")
tk.Label(di_minus_frame, text="Top 10 Coins by DI-:", font=("Arial", 12, "bold")).pack() """

""" # Top 10 Coins by DI- Labels - now with funding rate
top_di_minus_labels = [tk.Label(di_minus_frame, text="", font=mono_font) for _ in range(10)]
for label in top_di_minus_labels:
    label.pack(anchor="w") """
# Top 10 Coins with Funding Rate < -0.2500 Frame
negative_funding_frame = tk.Frame(root)
negative_funding_frame.grid(row=0, column=1, padx=10, pady=5, sticky="nsew")
tk.Label(negative_funding_frame, text="Top 10 Coins with Funding Rate < -0.2500%:", font=("Arial", 12, "bold")).pack()

# Labels for Top 10 Negative Funding Rate Coins
negative_funding_labels = [tk.Label(negative_funding_frame, text="", font=mono_font) for _ in range(10)]
for label in negative_funding_labels:
    label.pack(anchor="w")

# Grouped Statistics Frame
stats_frame = tk.Frame(root)
stats_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")
tk.Label(stats_frame, text="Recent Grouped Statistics (Last 30):", 
         font=("Arial", 12, "bold")).pack()

# Use a wider Listbox with scrollbar
stats_listbox = tk.Listbox(stats_frame, width=140, height=20, font=mono_font)
scrollbar = tk.Scrollbar(stats_frame, orient="vertical")
scrollbar.pack(side="right", fill="y")
stats_listbox.pack(side="left", fill="both", expand=True)
stats_listbox.config(yscrollcommand=scrollbar.set)
scrollbar.config(command=stats_listbox.yview)

# Countdown Timer for Next Update
timer_frame = tk.Frame(root)
timer_frame.grid(row=2, column=0, columnspan=2, pady=10)
timer_label = tk.Label(timer_frame, text="Next update in: --:--", 
                      font=("Arial", 12, "bold"), fg="blue")
timer_label.pack()

# Configure grid weights for proper resizing
root.grid_rowconfigure(1, weight=1)
root.grid_columnconfigure(0, weight=1)
root.grid_columnconfigure(1, weight=1)

# Initialize variables
new_df = pd.DataFrame()
top_30_stats = []
next_update_time = None
columns_to_include = [
    "Timestamp", "Symbol", "RSI", "Long/Short Ratio", "Top Trader Ratio",
    "CND Rating", "Signal Quality", "Current Price", "MACD Line", "ATR",
    "DI+", "DI-", "ADX", "VWAP", "Open Interest",
    "Funding Rate", "Funding Mark Price", "Last Funding Time"
]

# Start data update
update_data()

# Run the GUI event loop
root.mainloop()