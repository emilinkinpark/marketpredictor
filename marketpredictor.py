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
def calculate_rsi(prices, period=limit):
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gain = sum(x for x in deltas if x > 0) / period
    loss = abs(sum(x for x in deltas if x < 0)) / period
    rs = gain / loss if loss != 0 else float('inf')
    rsi = 100 - (100 / (1 + rs))
    return rsi

# Function to calculate Score Code D with dynamic weighting
def calculate_score_code_d(long_short_ratio, rsi, cnd_rating):
    # Dynamic weighting based on RSI and long/short ratio conditions
    if rsi > 70:  # RSI indicates overbought
        rsi_weight = 0.7
        long_short_weight = 0.3
    elif rsi < 30:  # RSI indicates oversold
        rsi_weight = 0.3
        long_short_weight = 0.7
    else:  # Neutral market conditions
        rsi_weight = 0.5
        long_short_weight = 0.5

    # Adjust weight based on long/short ratio
    if long_short_ratio > 1.5:  # Market is heavily long
        long_short_weight += 0.1
        rsi_weight -= 0.1
    elif long_short_ratio < 0.5:  # Market is heavily short
        long_short_weight -= 0.1
        rsi_weight += 0.1

    # Final dynamic weighting adjustment based on CND rating
    if cnd_rating > 7:  # Strong trend
        long_short_weight += 0.05
        rsi_weight -= 0.05
    elif cnd_rating < 3:  # Weak trend
        long_short_weight -= 0.05
        rsi_weight += 0.05

    # Calculate Score Code D with dynamic weights
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

# Function to forecast price for the next 4, 8, and 12 hours
def forecast_price(closing_prices, multiplier=2):
    if len(closing_prices) < 2:
        return None
    # Calculate percentage change between the last two closing prices
    price_change = closing_prices[-1] - closing_prices[-2]
    forecasted_price = closing_prices[-1] + price_change * multiplier  # Predicting for the next intervals
    return forecasted_price


# Function to determine the Prediction Status
def calculate_prediction_status(signal_status, signal_quality, rsi, cnd_rating, score_code_d):
    #1CR
    if (signal_status == "Hold" and signal_quality == "1CR" and (rsi < 73 and rsi > 70) and (cnd_rating > 4.0 and cnd_rating < 4.9) and score_code_d > -50):
        return "Long_1CR_7%"
    #2CR
    elif (signal_status == "Hold" and signal_quality == "2CR" and rsi < 66 and cnd_rating < 7.00 and score_code_d > -25):
        return "Short_2CR"
    elif (signal_status == "Hold" and signal_quality == "2CR" and rsi < 66 and cnd_rating < 7.00 and score_code_d < -25):
        return "Long_2CR"
    elif (signal_status == "Buy" and signal_quality == "2CR" and (rsi > 47 and rsi < 70) and (cnd_rating > 7.00 and cnd_rating < 7.838) and (score_code_d < -12 and score_code_d > -18)):
        return "Long_2CR_3%"
    #3CR
    elif (signal_status == "Hold" and signal_quality == "3CR" and rsi < 66 and cnd_rating < 7.00 and score_code_d > -18):
        return "Short_3CR"
    else:
        return "Placeholder"

# Function to determine the Likely Coins to change 5%
def determine_high_change(signal_status, signal_quality, rsi, cnd_rating, score_code_d):
    if ((rsi > 62 and rsi < 66) and (cnd_rating > 5.5 and cnd_rating < 5.7) and (score_code_d > -27.5 and score_code_d < -24)):
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
    # Request parameters for long/short data
    lsr_params = {
        "symbol": symbol,
        "period": interval,
        "limit": limit
    }

    # Request parameters for kline data
    kline_params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }

    # Send request for long/short account data
    lsr_response = requests.get(LSR_URL, params=lsr_params)
    lsr_data = lsr_response.json()

    # Send request for kline (candlestick) data
    kline_response = requests.get(KLINE_URL, params=kline_params)
    kline_data = kline_response.json()

    # Ensure we have enough data in both responses
    if len(lsr_data) >= limit and len(kline_data) >= limit:
        long_account_percent = float(lsr_data[-1]['longAccount'])
        short_account_percent = float(lsr_data[-1]['shortAccount'])
        long_short_ratio = float(lsr_data[-1]['longShortRatio'])

        cnd_rating = calculate_cnd_rating(long_account_percent, short_account_percent)

        closing_prices = [float(kline_entry[4]) for kline_entry in kline_data]  # Closing prices
        volumes = [float(kline_entry[5]) for kline_entry in kline_data]  # Extract volumes

        rsi = calculate_rsi(closing_prices)

        score_code_d = calculate_score_code_d(long_short_ratio, rsi, cnd_rating)

        # Get the latest timestamp and latest price from the kline data
        timestamp = kline_data[-1][0]
        current_price = closing_prices[-1]  # Current closing price

        # Calculate forecasted prices
        forecasted_price_4h = forecast_price(closing_prices, multiplier=2)
        forecasted_price_8h = forecast_price(closing_prices, multiplier=4)
        forecasted_price_12h = forecast_price(closing_prices, multiplier=6)

        # Calculate the Price Change as the difference between forecasted prices
        price_change = forecasted_price_8h - forecasted_price_4h

        # Calculate Price Change Percentage
        if forecasted_price_4h != 0:  # Avoid division by zero
            price_change_percentage = (price_change / forecasted_price_4h) * 100
        else:
            price_change_percentage = 0.0  # Default value if forecasted_price_4h is zero

        # Calculate Volume 4hr before and after
        volume_4hr_before = volumes[-2]  # Volume from the second-to-last candle (4 hours before)
        volume_4hr_after = volumes[-1]  # Volume from the last candle (current 4-hour period)

        # Calculate Change in Volume
        volume_change = volume_4hr_after - volume_4hr_before

        # Calculate Percentage of Change in Volume
        if volume_4hr_before != 0:
            volume_change_percentage = (volume_change / volume_4hr_before) * 100
        else:
            volume_change_percentage = 0.0

        # Revised Signal Status Logic
        if cnd_rating > 7 and rsi < 70:
            signal_status = "Buy"
        elif cnd_rating < 3 and rsi > 30:
            signal_status = "Sell"
        else:
            signal_status = "Hold"

        # Calculate Signal Quality
        signal_quality = calculate_signal_quality(cnd_rating, rsi)

        # Calculate Prediction Status
        prediction_status = calculate_prediction_status(signal_status, signal_quality, rsi, cnd_rating, score_code_d)

        # Determine High Chance
        high_change = determine_high_change(signal_status, signal_quality, rsi, cnd_rating, score_code_d)

        # Append the combined data
        all_results.append({
            "Symbol": symbol,
            "Time": convert_to_local_time(timestamp),
            "Signal Status": signal_status,
            "CND Rating": cnd_rating,
            "RSI 4H": rsi,
            "Score Code D": score_code_d,
            "Signal Quality": signal_quality,
            "Current Price": current_price,
            #"Forecasted Price (Next 4H)": forecasted_price_4h,
            #"Forecasted Price (Next 8H)": forecasted_price_8h,
            #"Forecasted Price (Next 12H)": forecasted_price_12h,
            "Price Change": price_change,
            "Price Change Percentage": price_change_percentage,
            "Volume 4hr Before": volume_4hr_before,
            "Volume 4hr After": volume_4hr_after,
            "Change in Volume": volume_change,
            "Percentage Change in Volume": volume_change_percentage,
            "Prediction Status": prediction_status,
            "High Chance": high_change  # Added High Chance parameter
        })

# Convert results to DataFrame
df = pd.DataFrame(all_results)

# Save DataFrame to an Excel file
output_file = "signal.xlsx"
df.to_excel(output_file, index=False)

print(f"Data saved to {output_file}")
