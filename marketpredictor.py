import requests
import pandas as pd
from datetime import datetime

# Binance Futures API URLs for long/short data, kline data
LSR_URL = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
KLINE_URL = "https://fapi.binance.com/fapi/v1/klines"
EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"

# Parameters for API requests
interval = "4h"  # Set to 4 hours
limit = 14  # Changed limit to 14

# Function to convert timestamps to local system time
def convert_to_local_time(timestamp):
    local_time = datetime.fromtimestamp(timestamp / 1000)  # Convert timestamp to local time
    return local_time.strftime('%H:%M:%S')  # Return time as HH:MM:SS

# Function to calculate CND Rating
def calculate_cnd_rating(long_percent, short_percent):
    return (long_percent / (long_percent + short_percent)) * 10  # Scale to 10

# Function to calculate RSI
def calculate_rsi(prices, period=14):
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gain = sum(x for x in deltas if x > 0) / period
    loss = abs(sum(x for x in deltas if x < 0)) / period

    if loss == 0:  # No loss means RS is effectively infinite, so RSI should be 100
        return 100
    else:
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

    return rsi

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

    return score_code_d

# Function to calculate Signal Quality
def calculate_signal_quality(cnd_rating, rsi):
    if cnd_rating >= 7 and rsi < 30:
        return "4CR"
    elif cnd_rating >= 5 and rsi < 50:
        return "3CR"
    elif cnd_rating >= 3 and rsi < 70:
        return "2CR"
    else:
        return "1CR"

# Function to calculate EMA
def calculate_ema(prices, period):
    ema = [sum(prices[:period]) / period]  # Starting EMA as simple average of first 'period' prices
    multiplier = 2 / (period + 1)

    for price in prices[period:]:
        new_ema = (price - ema[-1]) * multiplier + ema[-1]
        ema.append(new_ema)

    return ema[-1]  # Return the latest EMA value

# Function to forecast prices using EMA
def forecast_price_ema(closing_prices, period_4h, period_8h, period_12h):
    if len(closing_prices) < max(period_4h, period_8h, period_12h):
        return None, None, None

    ema_4h = calculate_ema(closing_prices, period_4h)
    ema_8h = calculate_ema(closing_prices, period_8h)
    ema_12h = calculate_ema(closing_prices, period_12h)

    return ema_4h, ema_8h, ema_12h

# Function to determine the Prediction Status
def calculate_prediction_status(signal_status, signal_quality, rsi, cnd_rating, score_code_d):
    if signal_status == "Hold" and signal_quality == "1CR" and 70 < rsi < 73 and 4.0 < cnd_rating < 4.9 and score_code_d > -50:
        return "Long_1CR_7%"
    elif signal_status == "Hold" and signal_quality == "2CR" and rsi < 66 and cnd_rating < 7.00 and score_code_d > -25:
        return "Short_2CR"
    elif signal_status == "Hold" and signal_quality == "2CR" and rsi < 66 and cnd_rating < 7.00 and score_code_d < -25:
        return "Long_2CR"
    elif signal_status == "Buy" and signal_quality == "2CR" and 47 < rsi < 70 and 7.00 < cnd_rating < 7.838 and -18 < score_code_d < -12:
        return "Long_2CR_3%"
    elif signal_status == "Hold" and signal_quality == "3CR" and rsi < 66 and cnd_rating < 7.00 and score_code_d > -18:
        return "Short_3CR"
    else:
        return "Placeholder"

# Function to determine the Likely Coins to change 5%
def determine_high_change(signal_status, signal_quality, rsi, cnd_rating, score_code_d):
    if 62 < rsi < 66 and 5.5 < cnd_rating < 5.7 and -27.5 < score_code_d < -24:
        return "Long_5%"
    else:
        return "NA"

# Get all futures symbols
exchange_info_response = requests.get(EXCHANGE_INFO_URL)
exchange_info_data = exchange_info_response.json()
symbols = [symbol['symbol'] for symbol in exchange_info_data['symbols']]

# List to hold results for all symbols
all_results = []

# Iterate over each symbol
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
        volumes = [float(kline_entry[5]) for kline_entry in kline_data]

        rsi = calculate_rsi(closing_prices)

        score_code_d = calculate_score_code_d(long_short_ratio, rsi, cnd_rating)

        timestamp = kline_data[-1][0]
        current_price = closing_prices[-1]

        # EMA Forecasts
        ema_4h, ema_8h, ema_12h = forecast_price_ema(closing_prices, period_4h=4, period_8h=8, period_12h=12)

        # Calculate price changes and signal quality
        price_change_percentage = ((current_price - ema_4h) / ema_4h) * 100 if ema_4h else None
        volume_change_percentage = ((volumes[-1] - volumes[-2]) / volumes[-2]) * 100 if len(volumes) > 1 else None
        signal_quality = calculate_signal_quality(cnd_rating, rsi)

        if rsi < 30:
            signal_status = "Long"
        elif rsi > 70:
            signal_status = "Short"
        else:
            signal_status = "Hold"

        prediction_status = calculate_prediction_status(signal_status, signal_quality, rsi, cnd_rating, score_code_d)
        likely_change = determine_high_change(signal_status, signal_quality, rsi, cnd_rating, score_code_d)

        result = {
            "Symbol": symbol,
            "Timestamp": convert_to_local_time(timestamp),
            "Current Price": current_price,
            "EMA 4H": ema_4h,
            "EMA 8H": ema_8h,
            "EMA 12H": ema_12h,
            "RSI 4H": rsi,
            "Long/Short Ratio": long_short_ratio,
            "CND Rating": cnd_rating,
            "Signal Quality": signal_quality,
            "Score Code D": score_code_d,
            "Signal Status": signal_status,
            "Prediction Status": prediction_status,
            "Likely 5% Change": likely_change,
            "Price Change 4H-8H": price_change_percentage,
            "Volume Change %": volume_change_percentage,
        }

        all_results.append(result)

# Convert results to DataFrame
df = pd.DataFrame(all_results)

# Create a Pandas Excel writer object using XlsxWriter as the engine
output_file = "signals.xlsx"
writer = pd.ExcelWriter(output_file, engine='xlsxwriter')

# Get unique Signal Quality values
signal_statuses = df["Signal Quality"].unique()

# Summarise data per Signal Quality
summary_data = df.groupby("Signal Quality").agg(
    Num_Coins=("Symbol", "count"),
    Avg_RSI=("RSI 4H", "mean"),
    Avg_CND_Rating=("CND Rating", "mean"),
    Avg_Score_Code_D=("Score Code D", "mean")
).reset_index()

# Write the summary data to a new sheet in the Excel file
summary_data.to_excel(writer, sheet_name="Summary", index=False)

# Add the individual Signal Quality sheets
for status in signal_statuses:
    df_status = df[df["Signal Quality"] == status]
    df_status.to_excel(writer, sheet_name=status, index=False)
    
# Save the Excel file
writer.close()

print(f"Data saved to {output_file} with EMA forecasts and sheets for each Signal Status")
