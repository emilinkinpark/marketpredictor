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

print("Starting Market Predictor")
# Function to convert timestamps to local system time
timestamp = datetime.now().strftime("%H:%M:%S")

# Function to calculate CND Rating
def calculate_cnd_rating(long_percent, short_percent):
    return (long_percent / (long_percent + short_percent)) * 10  # Scale to 10

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
def calculate_prediction_status(signal_quality, rsi, long_short_ratio, cnd_rating, price_change_percentage, score_code_d):
    if signal_quality == "1CR" and (84.00 < rsi < 93.12130178) and (0.5891 < long_short_ratio < 1.9121) and (43.95245958 < score_code_d < 57.81318124):
        return "Long_5.0%"
    elif signal_quality == "1CR" and (70.25641026 < rsi < 80.25) and (0.634 < long_short_ratio < 1.9533) and (37.30031265 < score_code_d < 46.11983113):
        return "Long_3.0%"
    elif signal_quality == "1CR" and (74.00611621 < rsi < 82.89940828) and (0.6661 < long_short_ratio < 1.5681) and (37.90060504 < score_code_d < 48.56233495):
        return "Short_5.00%"
    elif signal_quality == "1CR" and (72.54901961 < rsi < 73.8700565) and (0.8396 < long_short_ratio < 2.126) and (36.67901176 < score_code_d < 44.44683795):
        return "Short_3.00%"
    else:
        return "Placeholder"


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

        #timestamp = kline_data[-1][0]
        current_price = closing_prices[-1]

        # EMA Forecasts
        ema_4h, ema_8h, ema_12h = forecast_price_ema(closing_prices, period_4h=4, period_8h=8, period_12h=12)

        # Calculate price changes and signal quality
        price_change_percentage = ((current_price - ema_4h) / ema_4h) * 100 if ema_4h else None
        volume_change_percentage = ((volumes[-1] - volumes[-2]) / volumes[-2]) * 100 if len(volumes) > 1 else None
        signal_quality = calculate_signal_quality(cnd_rating, rsi)

        if rsi < 30:
            signal_status = "Buy"
        elif rsi > 70:
            signal_status = "Sell"
        else:
            signal_status = "Hold"

        prediction_status = calculate_prediction_status(signal_quality, rsi, long_short_ratio, cnd_rating, price_change_percentage, score_code_d)

        result = {
            "Symbol": symbol,
            "Timestamp": timestamp,
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
            "Price Change 4H-8H": price_change_percentage,
            "Volume Change %": volume_change_percentage,
        }

        all_results.append(result)

# Convert results to DataFrame
df = pd.DataFrame(all_results)

timestamp_output_file = datetime.now().strftime("%d%m%Y_%H%M")

# Create a Pandas Excel writer object using XlsxWriter as the engine
output_file = f"signals_{timestamp_output_file}.xlsx"
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
