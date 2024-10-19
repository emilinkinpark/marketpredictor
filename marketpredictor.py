import requests
import pandas as pd
from datetime import datetime

# Binance Futures API URLs for long/short data, kline data
LSR_URL = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
KLINE_URL = "https://fapi.binance.com/fapi/v1/klines"
EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"

# Parameters for API requests
interval = "1h"  # Set to 1 hour
limit = 14  # Changed limit to 14

# Function to calculate RSI
def calculate_rsi(prices):
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gain = sum(x for x in deltas if x > 0) / limit
    loss = abs(sum(x for x in deltas if x < 0)) / limit

    if loss == 0:  # No loss means RS is effectively infinite, so RSI should be 100
        return 100
    else:
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

    return rsi

# Function to calculate moving averages
def calculate_moving_average(prices, period):
    return sum(prices[-period:]) / period

# Function to calculate MACD
def calculate_macd(prices, short_period=12, long_period=26, signal_period=9):
    short_ema = calculate_ema(prices, short_period)
    long_ema = calculate_ema(prices, long_period)
    macd_line = short_ema - long_ema
    signal_line = calculate_ema([macd_line] * signal_period, signal_period)
    return macd_line, signal_line

# Function to calculate EMA
def calculate_ema(prices, period):
    ema = [sum(prices[:period]) / period]  # Starting EMA as simple average of first 'period' prices
    multiplier = 2 / (period + 1)

    for price in prices[period:]:
        new_ema = (price - ema[-1]) * multiplier + ema[-1]
        ema.append(new_ema)

    return ema[-1]  # Return the latest EMA value

# Function to calculate CND Rating
def calculate_cnd_rating(long_percent, short_percent):
    return (long_percent / (long_percent + short_percent)) * 10  # Scale to 10

# Function to calculate Score Code D with dynamic weighting
def calculate_score_code_d(long_short_ratio, rsi, cnd_rating):
    if rsi > 70:
        rsi_weight = 0.7
        long_short_weight = 0.3
    elif rsi < 30:
        rsi_weight = 0.3
        long_short_weight = 0.7
    else:
        rsi_weight = 0.5
        long_short_weight = 0.5

    if long_short_ratio > 1.5:
        long_short_weight += 0.1
        rsi_weight -= 0.1
    elif long_short_ratio < 0.5:
        long_short_weight -= 0.1
        rsi_weight += 0.1

    if cnd_rating > 7:
        long_short_weight += 0.05
        rsi_weight -= 0.05
    elif cnd_rating < 3:
        long_short_weight -= 0.05
        rsi_weight += 0.05

    score_code_d = (long_short_ratio * long_short_weight) + ((10 - rsi) * rsi_weight)

    return abs(score_code_d)

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

# Function to determine the Prediction Status and set Profit Target
# Function to determine the Prediction Status and set Profit Target in percentage
def calculate_prediction_status_and_profit_target(entry_price, signal_quality, rsi, long_short_ratio, cnd_rating, macd_line, signal_line, current_price, stop_loss, risk_reward_ratio=2):
    # Set Profit Target based on risk-reward ratio
    risk = abs(entry_price - stop_loss)
    profit_target = entry_price + (risk * risk_reward_ratio) if signal_quality in ["4CR", "3CR"] else entry_price - (risk * risk_reward_ratio)

    # Calculate the percentage change between entry price and profit target
    if profit_target > entry_price:
        percentage_change = ((profit_target - entry_price) / entry_price) * 100
    else:
        percentage_change = ((entry_price - profit_target) / entry_price) * 100

    # Classification based on percentage price change thresholds
    if signal_quality == "4CR" and percentage_change > 5 and rsi < 30:
        return f"Strong Long (>5%)", profit_target
    elif signal_quality == "3CR" and 2 < percentage_change <= 5 and macd_line > signal_line:
        return f"Moderate Long (2% - 5%)", profit_target
    elif signal_quality == "2CR" and 0 < percentage_change <= 2:
        return f"Weak Long (0% - 2%)", profit_target
    elif signal_quality == "1CR":
        return f"Hold", None
    elif signal_quality == "4CR" and percentage_change > 5 and rsi > 70:
        return f"Strong Short (>5%)", profit_target
    elif signal_quality == "3CR" and 2 < percentage_change <= 5 and macd_line < signal_line:
        return f"Moderate Short (2% - 5%)", profit_target
    elif signal_quality == "2CR" and 0 < percentage_change <= 2:
        return f"Weak Short (0% - 2%)", profit_target
    else:
        return "Placeholder", None

# Function to set Trailing Stop Loss
def set_trailing_stop(current_price, trail_percentage):
    """
    Set a trailing stop based on the current price and a trailing percentage.
    """
    stop_price = current_price * (1 - trail_percentage / 100)
    return stop_price

# Function to process symbols and calculate all indicators
def process_symbols(): 

    # Get all futures symbols
    exchange_info_response = requests.get(EXCHANGE_INFO_URL)
    exchange_info_data = exchange_info_response.json()
    symbols = [symbol['symbol'] for symbol in exchange_info_data['symbols']]

    # List to hold results for all symbols
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
            rsi = calculate_rsi(closing_prices)

            current_price = closing_prices[-1]
            stop_loss = current_price * 0.95

            score_code_d = calculate_score_code_d(long_short_ratio, rsi, cnd_rating)
            macd_line, signal_line = calculate_macd(closing_prices)
            signal_quality = calculate_signal_quality(cnd_rating, rsi, macd_line, signal_line)

            prediction_status, profit_target = calculate_prediction_status_and_profit_target(
                entry_price=current_price,
                signal_quality=signal_quality,
                rsi=rsi,
                long_short_ratio=long_short_ratio,
                cnd_rating=cnd_rating,
                macd_line=macd_line,
                signal_line=signal_line,
                current_price=current_price,
                stop_loss=stop_loss
            )

            trailing_stop = set_trailing_stop(current_price, trail_percentage=5)

            result = {
                "Symbol": symbol,
                "Current Price": current_price,
                "RSI": rsi,
                "Long/Short Ratio": long_short_ratio,
                "CND Rating": cnd_rating,
                "Signal Quality": signal_quality,
                "Score Code D": score_code_d,
                "Prediction Status": prediction_status,
                "Profit Target": profit_target,
                "Trailing Stop": trailing_stop,
                "MACD Line": macd_line,
                "Signal Line": signal_line
            }

            all_results.append(result)

    df = pd.DataFrame(all_results)
    return df

# Function to save the grouped data by Signal Quality into an Excel file
def save_grouped_by_signal_quality(df):
    current_time = datetime.now().strftime("%d%m%Y_%H%M")
    output_file = f"Signals_{current_time}.xlsx"
    writer = pd.ExcelWriter(output_file, engine='xlsxwriter')

    signal_qualities = df["Signal Quality"].unique()

    for quality in signal_qualities:
        df_quality = df[df["Signal Quality"] == quality]
        df_quality.to_excel(writer, sheet_name=str(quality), index=False)

    writer.close()
    return output_file

# Execute the symbol processing and save the results
processed_data = process_symbols()
output_file = save_grouped_by_signal_quality(processed_data)
print(f"Data saved to {output_file}")
