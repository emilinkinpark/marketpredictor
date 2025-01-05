import requests
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk
from tkinter import filedialog
import time
import threading
import itertools
import tkinter.font as tkfont

# Binance Futures API URLs for long/short data, kline data
LSR_URL = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
KLINE_URL = "https://fapi.binance.com/fapi/v1/klines"
EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"

# Parameters for API requests
interval = "30m"
limit = 30

print("Starting Market Predictor")

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

    response = requests.get(TOP_TRADER_RATIO_URL, params=params)
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
                #"Signal Line": signal_line,
                #"MACD Histogram": macd_histogram,
                "ATR": atr,
                "DI+": di_plus,
                "DI-": di_minus,
                "ADX": adx
            }

            all_results.append(result)

    df = pd.DataFrame(all_results)
    return df

# Function to save the grouped data by Signal Quality into an Excel file
def save_grouped_by_signal_quality(df):
    current_time = datetime.now().strftime("%d%m%Y_%H%M")
    output_file = f"{current_time}.xlsx"
    writer = pd.ExcelWriter(output_file, engine='xlsxwriter')

    # Create a summary per Signal Quality
    summary = df.groupby("Signal Quality").agg(
        Total_Symbols=("Symbol", "nunique"),
        Avg_RSI=("RSI", "mean"),
        Avg_ATR=("ATR", "mean"),
        Avg_ADX=("ADX", "mean"),
        Avg_DIplus=("DI+", "mean"),
        Avg_DImin=("DI-", "mean"),
        Total_Trades=("Symbol", "count"),
    ).reset_index()

    # Write the Signal Quality summary to the leftmost sheet named "Summary"
    summary.to_excel(writer, sheet_name="Summary", index=False, startrow=0)

    # Find the top 6 coins by DI+ and DI-
    top_di_plus = df.nlargest(6, "DI+")[["Symbol", "DI+"]].reset_index(drop=True)
    top_di_minus = df.nlargest(6, "DI-")[["Symbol", "DI-"]].reset_index(drop=True)

    # Write the top 6 DI+ coins below the summary
    top_di_plus_startrow = len(summary) + 3  # Leave some space below the summary
    top_di_plus.to_excel(
        writer,
        sheet_name="Summary",
        index=False,
        startrow=top_di_plus_startrow,
        startcol=0,
    )
    worksheet = writer.sheets["Summary"]
    worksheet.write(top_di_plus_startrow - 1, 0, "Top 6 Coins by DI+")

    # Write the top 6 DI- coins below the top DI+ table
    top_di_minus_startrow = top_di_plus_startrow + len(top_di_plus) + 3
    top_di_minus.to_excel(
        writer,
        sheet_name="Summary",
        index=False,
        startrow=top_di_minus_startrow,
        startcol=0,
    )
    worksheet.write(top_di_minus_startrow - 1, 0, "Top 6 Coins by DI-")

    ## Create Individual Coin data per Signal Quality
    signal_qualities = df["Signal Quality"].unique()

    for quality in signal_qualities:
        df_quality = df[df["Signal Quality"] == quality]
        df_quality.to_excel(writer, sheet_name=str(quality), index=False)

    # Save the Excel file
    writer.close()
    return output_file

# Function to update data and refresh the GUI
def update_data():
    global new_df, top_15_stats, next_update_time

    # Fetch new data
    df = process_symbols()

    #Save the grouped data by Signal Quality into an Excel file
    save_grouped_by_signal_quality(df)
    # Top 6 coins by DI+ and DI-
    top_di_plus = df.nlargest(6, "DI+")[["Symbol", "DI+"]]
    top_di_minus = df.nlargest(6, "DI-")[["Symbol", "DI-"]]

    # Update GUI for Top 6 Coins
    for i, (symbol, di) in enumerate(top_di_plus.values):
        top_di_plus_labels[i]["text"] = f"{symbol}: DI+ {di:.2f}"
    for i, (symbol, di) in enumerate(top_di_minus.values):
        top_di_minus_labels[i]["text"] = f"{symbol}: DI- {di:.2f}"

    # Calculate grouped statistics
    grouped_stats_new = df.groupby("Signal Quality").agg({
        "DI+": "mean",
        "DI-": "mean",
        "RSI": "mean"
    }).rename(columns={"DI+": "Avg_DI+", "DI-": "Avg_DI-", "RSI": "Avg_RSI"})

    # Prepare new stats string
    current_time = datetime.now().strftime("%H:%M:%S")
    stats_label_new = f"{current_time} | " + " | ".join([
        f"{quality}: DI+ {row['Avg_DI+']:.2f} DI- {row['Avg_DI-']:.2f} RSI {row['Avg_RSI']:.2f}"
        for quality, row in grouped_stats_new.iterrows()
    ])

    # Maintain only the top 15 stats
    if len(top_15_stats) >= 15:
        top_15_stats.pop(0)
    top_15_stats.append(stats_label_new)

    # Update GUI for Grouped Stats
    stats_listbox.delete(0, tk.END)
    for stat in top_15_stats:
        stats_listbox.insert(tk.END, stat)

    # Update the next update time
    next_update_time = datetime.now() + timedelta(minutes=30)
    update_timer()
    # Schedule the next update
    root.after(30 * 60 * 1000, update_data)  # 30 minutes

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

# Top 6 Coins by DI+
tk.Label(root, text="Top 6 Coins by DI+:", font=("Arial", 12, "bold")).grid(row=0, column=0, padx=10, pady=5)
top_di_plus_labels = [tk.Label(root, text="", font=("Arial", 10)) for _ in range(6)]
for i, label in enumerate(top_di_plus_labels):
    label.grid(row=i + 1, column=0, sticky="w", padx=10)

# Top 6 Coins by DI-
tk.Label(root, text="Top 6 Coins by DI-:", font=("Arial", 12, "bold")).grid(row=0, column=1, padx=10, pady=5)
top_di_minus_labels = [tk.Label(root, text="", font=("Arial", 10)) for _ in range(6)]
for i, label in enumerate(top_di_minus_labels):
    label.grid(row=i + 1, column=1, sticky="w", padx=10)

# Grouped Statistics
tk.Label(root, text="Recent Grouped Statistics (Last 15):", font=("Arial", 12, "bold")).grid(row=7, column=0, columnspan=2, pady=10)
stats_listbox = tk.Listbox(root, width=125, height=15, font=("Courier", 10))
stats_listbox.grid(row=8, column=0, columnspan=2, padx=10, pady=5)

# Countdown Timer for Next Update
timer_label = tk.Label(root, text="Next update in: 30m 0s", font=("Arial", 12, "bold"), fg="blue")
timer_label.grid(row=9, column=0, columnspan=2, pady=10)

# Initialize variables
new_df = pd.DataFrame()
top_15_stats = []
next_update_time = None

# Start data update
update_data()

# Run the GUI event loop
root.mainloop()