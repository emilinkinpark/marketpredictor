import requests
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk
from tkinter import filedialog
import time
import threading
import itertools

# Binance Futures API URLs for long/short data, kline data
LSR_URL = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
KLINE_URL = "https://fapi.binance.com/fapi/v1/klines"
EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"

# Parameters for API requests
interval = "1h"
limit = 24

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

def calculate_dynamic_stop_loss(current_price, atr, adx, entry_price=None, stop_loss=None, use_trailing=False):
    """
    Calculate a dynamic stop-loss based on market volatility, trend strength, and optional trailing logic.

    Args:
        current_price (float): The current market price.
        atr (float): Average True Range (ATR) indicating market volatility.
        adx (float): Average Directional Index (ADX) indicating trend strength.
        entry_price (float): Entry price of the trade, required for trailing stop-loss.
        stop_loss (float): Current stop-loss value, used for trailing stop-loss logic.
        use_trailing (bool): If True, use trailing stop-loss logic.

    Returns:
        float: Calculated dynamic stop-loss price.
    """
    # ATR-based stop-loss adjustment
    if atr > 2 and adx > 25:
        calculated_stop_loss = current_price - (2 * atr)  # Wider stop-loss for volatile and trending markets
    elif atr < 1.5 or adx < 20:
        calculated_stop_loss = current_price - (0.5 * atr)  # Tighter stop-loss for less volatile or non-trending markets
    else:
        calculated_stop_loss = current_price - (1 * atr)  # Standard stop-loss for moderate conditions

    # Implement trailing stop-loss logic if enabled
    if use_trailing and entry_price is not None and stop_loss is not None:
        # Ensure the trailing stop-loss never decreases
        trailing_stop_loss = max(stop_loss, current_price * (1 - 0.05))  # Example of 5% trailing stop-loss
        calculated_stop_loss = max(calculated_stop_loss, trailing_stop_loss)  # Use the higher of the two stop-loss values

    return calculated_stop_loss

# Function to calculate MACD
def calculate_macd(prices, short_period=12, long_period=26, signal_period=9):
    short_ema = calculate_ema(prices, short_period)
    long_ema = calculate_ema(prices, long_period)
    macd_line = short_ema - long_ema
    signal_line = calculate_ema([macd_line] * signal_period, signal_period)
    macd_histogram = macd_line - signal_line
    return macd_line, signal_line, macd_histogram

# Function to calculate ATR
def calculate_atr(highs, lows, closes, period=limit):
    tr = [max(high - low, abs(high - closes[i - 1]), abs(low - closes[i - 1])) for i, (high, low) in enumerate(zip(highs[1:], lows[1:]), 1)]
    return sum(tr[-period:]) / period

# Function to calculate CND Rating
def calculate_cnd_rating(long_percent, short_percent):
    return (long_percent / (long_percent + short_percent)) * 10

# Function to calculate DMI and ADX
def calculate_dmi_and_adx(highs, lows, closes, period=limit):
    plus_dm = [max(highs[i] - highs[i - 1], 0) if (highs[i] - highs[i - 1]) > (lows[i - 1] - lows[i]) else 0 for i in range(1, len(highs))]
    minus_dm = [max(lows[i - 1] - lows[i], 0) if (lows[i - 1] - lows[i]) > (highs[i] - highs[i - 1]) else 0 for i in range(1, len(lows))]
    
    tr = [max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])) for i in range(1, len(highs))]
    
    tr_sum = sum(tr[-period:])
    plus_di = (sum(plus_dm[-period:]) / tr_sum) * 100
    minus_di = (sum(minus_dm[-period:]) / tr_sum) * 100
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100 if (plus_di + minus_di) != 0 else 0
    adx = sum([dx] * period) / period  # Approximation; replace with smoother ADX calculation if needed
    
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

# Function to determine the Prediction Status
def calculate_prediction_status(entry_price, signal_quality, rsi, long_short_ratio, cnd_rating, macd_line, signal_line, macd_histogram, atr, di_plus, di_minus, adx, current_price, stop_loss, risk_reward_ratio=2):
    """
    Determine the prediction status using various indicators including MACD histogram, ATR, DMI, and ADX.
    """
    # Calculate percentage change between entry price and profit target
    risk = abs(entry_price - stop_loss)
    profit_target = entry_price + (risk * risk_reward_ratio) if signal_quality in ["4CR", "3CR"] else entry_price - (risk * risk_reward_ratio)

    # Calculate the percentage change
    if profit_target > entry_price:
        percentage_change = ((profit_target - entry_price) / entry_price) * 100
    else:
        percentage_change = ((entry_price - profit_target) / entry_price) * 100

    # Debugging: Print the key values for inspection
    #print(f"Signal Quality: {signal_quality}, Percentage Change: {percentage_change:.2f}%, RSI: {rsi}, ATR: {atr}, ADX: {adx}, DI+: {di_plus}, DI-: {di_minus}, MACD Line: {macd_line}, Signal Line: {signal_line}")

    # Refine prediction using additional indicators
    if adx > 25:  # Ensure the trend is strong
        if signal_quality == "4CR" and percentage_change > 3 and rsi < 40 and atr > 0.5 and di_plus > di_minus:
            return f"Strong Long (>3%)", profit_target
        elif signal_quality == "3CR" and 1.5 < percentage_change <= 3 and macd_line > signal_line and di_plus > di_minus:
            return f"Moderate Long (1.5% - 3%)", profit_target
        elif signal_quality == "2CR" and 0 < percentage_change <= 1.5 and di_plus > di_minus:
            return f"Weak Long (0% - 1.5%)", profit_target
        elif signal_quality == "4CR" and percentage_change > 3 and rsi > 60 and atr > 0.5 and di_minus > di_plus:
            return f"Strong Short (>3%)", profit_target
        elif signal_quality == "3CR" and 1.5 < percentage_change <= 3 and macd_line < signal_line and di_minus > di_plus:
            return f"Moderate Short (1.5% - 3%)", profit_target
        elif signal_quality == "2CR" and 0 < percentage_change <= 1.5 and di_minus > di_plus:
            return f"Weak Short (0% - 1.5%)", profit_target
        else:
            return "Hold", None
    else:
        return "No Strong Trend", None

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

            macd_line, signal_line, macd_histogram = calculate_macd(closing_prices)
            atr = calculate_atr(highs, lows, closing_prices)

            di_plus, di_minus, adx = calculate_dmi_and_adx(highs, lows, closing_prices)

            signal_quality = calculate_signal_quality(cnd_rating, rsi, macd_line, signal_line)

            # Calculate the dynamic stop-loss using the new function
            stop_loss = calculate_dynamic_stop_loss(
                current_price=current_price,
                atr=atr,
                adx=adx,
                entry_price=current_price,
                stop_loss=None,  # If there is no existing stop-loss, it defaults to a newly calculated stop-loss
                use_trailing=False  # Set to True if you want to use trailing stop-loss logic
            )

            prediction_status, profit_target = calculate_prediction_status(
                entry_price=current_price,
                signal_quality=signal_quality,
                rsi=rsi,
                long_short_ratio=long_short_ratio,
                cnd_rating=cnd_rating,
                macd_line=macd_line,
                signal_line=signal_line,
                macd_histogram=macd_histogram,
                atr=atr,
                di_plus=di_plus,
                di_minus=di_minus,
                adx=adx,
                current_price=current_price,
                stop_loss=stop_loss
            )

            # Adding a timestamp for the data collected
            timestamp = datetime.now().strftime("%H:%M:%S")

            result = {
                "Timestamp": timestamp,
                "Symbol": symbol,
                "Current Price": current_price,
                "RSI": rsi,
                "Long/Short Ratio": long_short_ratio,
                "CND Rating": cnd_rating,
                "Signal Quality": signal_quality,
                "Prediction Status": prediction_status,
                "Profit Target": profit_target,
                "Stop Loss": stop_loss,  # Include the calculated stop-loss in the result
                "MACD Line": macd_line,
                "Signal Line": signal_line,
                "MACD Histogram": macd_histogram,
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
    output_file = f"Signals_{current_time}.xlsx"
    writer = pd.ExcelWriter(output_file, engine='xlsxwriter')

    # Create a summary per Signal Quality
    summary = df.groupby("Signal Quality").agg(
        Total_Symbols=("Symbol", "nunique"),
        Avg_RSI=("RSI", "mean"),
        Avg_ATR=("ATR", "mean"),
        Avg_ADX=("ADX", "mean"),
        Total_Trades=("Symbol", "count"),
        Strong_Long=("Prediction Status", lambda x: (x == "Strong Long (>3%)").sum()),
        Moderate_Long=("Prediction Status", lambda x: (x == "Moderate Long (1.5% - 3%)").sum()),
        Weak_Long=("Prediction Status", lambda x: (x == "Weak Long (0% - 1.5%)").sum()),
        Strong_Short=("Prediction Status", lambda x: (x == "Strong Short (>3%)").sum()),
        Moderate_Short=("Prediction Status", lambda x: (x == "Moderate Short (1.5% - 3%)").sum()),
        Weak_Short=("Prediction Status", lambda x: (x == "Weak Short (0% - 1.5%)").sum()),
        Hold_Count=("Prediction Status", lambda x: (x == "Hold").sum())
    ).reset_index()

    # Write the Signal Quality summary to the leftmost sheet named "Summary"
    summary.to_excel(writer, sheet_name="Summary", index=False)

    ## Create Individual Coin data per Signal Quality
    signal_qualities = df["Signal Quality"].unique()

    for quality in signal_qualities:
        df_quality = df[df["Signal Quality"] == quality]
        df_quality.to_excel(writer, sheet_name=str(quality), index=False)

    # Save the Excel file
    writer.close()
    return output_file

""""""
# Initialize previous data list to hold last 10 data points and their timestamps
previous_data_list = []
previous_timestamps = []

# Colors for the last 10 intervals (cycling through colors)
colors = itertools.cycle(["red", "green", "blue", "orange", "purple", "brown", "pink", "gray", "olive", "cyan"])

# Variable to store the ID of the scheduled "after" call
after_id = None

# Function to plot the prediction status on a canvas and reset after 10 old data points
def visualize_prediction_status(new_df, canvas, ax):
    global previous_data_list, previous_timestamps

    # Clear the previous plot
    ax.clear()

    # Get the counts for new data
    new_status_counts = new_df["Prediction Status"].value_counts()

    # Plot each of the last 10 old data points with the time they were updated
    for i, (old_data, timestamp) in enumerate(zip(previous_data_list, previous_timestamps)):
        old_status_counts = old_data["Prediction Status"].value_counts()
        old_color = next(colors)
        old_status_counts.plot(kind='bar', color=old_color, edgecolor='black', alpha=0.5, ax=ax, label=f"{timestamp}")

    # Plot the new data in default color
    new_status_counts.plot(kind='bar', color='skyblue', edgecolor='black', ax=ax, label="Current Data")
    
    # Customize the plot
    ax.set_title('Prediction Status Count (Last 10 Intervals)')
    ax.set_xlabel('Prediction Status')
    ax.set_ylabel('Count')
    ax.legend()

    # Apply tight layout to prevent cropping
    plt.tight_layout()

    # Refresh the canvas to show the updated plot
    canvas.draw()

    # Append the current data and its timestamp to previous_data_list
    current_time = datetime.now().strftime("%H:%M:%S")
    
    # Reset the old data list after 10 updates
    if len(previous_data_list) == 10:
        previous_data_list.clear()  # Reset the list
        previous_timestamps.clear()  # Reset the timestamps

    # Add the new data and timestamp after reset
    previous_data_list.append(new_df.copy())
    previous_timestamps.append(current_time)

# Function to save the current DataFrame to an Excel file using save_grouped_by_signal_quality
def save_file(df):
    # Open a file dialog to let the user choose the save location
    file_path = filedialog.asksaveasfilename(defaultextension=".xlsx", 
                                             filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")])
    
    if file_path:  # If the user selects a file path
        # Save the DataFrame to the selected location
        output_file = save_grouped_by_signal_quality(df)
        
        # Rename and move the file to the selected location
        import shutil
        shutil.move(output_file, file_path)
        print(f"Data saved to {file_path}")

# Function to update the countdown timer
def update_timer(label, remaining_time, canvas, ax, df):
    global after_id  # Use a global variable to store the ID of the "after" call
    if remaining_time > 0:
        minutes, seconds = divmod(remaining_time, 60)
        label.config(text=f"Next update in: {minutes:02}:{seconds:02}")
        after_id = label.after(1000, update_timer, label, remaining_time - 1, canvas, ax, df)
    else:
        # Time is up; update the plot and reset the timer
        processed_data = process_symbols()  # Get the latest processed data
        visualize_prediction_status(processed_data, canvas, ax)  # Update the plot in the GUI
        update_timer(label, 1800, canvas, ax, df)  # Reset the countdown for another 30 minutes

# Function to cancel pending after() calls when the window is closed
def on_close(root):
    global after_id
    if after_id is not None:
        root.after_cancel(after_id)  # Cancel any pending after() calls
    root.destroy()  # Close the window

# GUI setup with tkinter
def create_gui(df):
    root = tk.Tk()
    root.title("Prediction Status Visualization")
    
    # Create a frame for the "Save" button and canvas
    frame = tk.Frame(root)
    frame.pack(pady=20)

    # Countdown timer label
    timer_label = tk.Label(root, text="Next update in: 30:00", font=("Arial", 14))
    timer_label.pack(pady=10)
    
    # "Save" button to download the current data using the provided save_grouped_by_signal_quality function
    save_button = tk.Button(frame, text="Save Current Data", command=lambda: save_file(df))
    save_button.pack(side=tk.LEFT, padx=10)
    
    # Create a larger figure (12x8) and an axis for the plot
    fig, ax = plt.subplots(figsize=(12, 8))  # Increased figure size

    # Embed the matplotlib figure in the tkinter window using FigureCanvasTkAgg
    canvas = FigureCanvasTkAgg(fig, master=root)
    canvas_widget = canvas.get_tk_widget()
    canvas_widget.pack(pady=20)

    # Visualize the initial plot
    visualize_prediction_status(df, canvas, ax)

    # Start the countdown timer for 30 minutes (1800 seconds)
    update_timer(timer_label, 1800, canvas, ax, df)

    # Set the protocol to handle window close event
    root.protocol("WM_DELETE_WINDOW", lambda: on_close(root))

    # Allow dynamic window resizing
    root.geometry("1024x768")  # Set a minimum size for the window

    # Start the tkinter main loop
    root.mainloop()

# Assuming process_symbols returns the latest processed DataFrame
processed_data = process_symbols()  # Process symbols to get the initial data

# Start the GUI
create_gui(processed_data)
