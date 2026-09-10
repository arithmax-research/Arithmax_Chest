"""
Download data for new crypto pairs: SOL, BNB, XRP, ADA, DOGE
Downloads:
  1. OHLC data (spot {pair}USDC + perp {pair}USDT) at hourly and daily resolution
  2. Funding rate data for perpetual contracts
  3. Follows same format as existing BTC/ETH data
"""

import os
import sys
import csv
import time
import pytz
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# Add parent dir to path
sys.path.insert(0, os.path.dirname(__file__))

from binance.client import Client as BinanceClient
from config import (
    BINANCE_API_KEY, BINANCE_SECRET_KEY,
    LEAN_TIME_FORMAT,
    BINANCE_RATE_LIMIT
)
from utils import (
    setup_logging, ensure_directory_exists, create_lean_crypto_csv,
    write_lean_zip_file, DataValidator
)

logger = setup_logging()

# New pairs to add
NEW_PAIRS = {
    "SOL": {"name": "Solana", "decimals": 2},
    "BNB": {"name": "Binance Coin", "decimals": 2},
    "XRP": {"name": "Ripple", "decimals": 4},
    "ADA": {"name": "Cardano", "decimals": 4},
    "DOGE": {"name": "Dogecoin", "decimals": 5},
}

# Data paths
DATA_ROOT = os.path.join(os.path.dirname(__file__), '..', 'data')
CRYPTO_PATH = os.path.join(DATA_ROOT, 'crypto', 'binance')
FUNDING_PATH = os.path.join(CRYPTO_PATH, 'funding')

# Date range for historical funding data
FUNDING_START_DATE = datetime(2020, 1, 1)
FUNDING_END_DATE = datetime.now()

class NewCryptoDataDownloader:
    def __init__(self):
        self.client = BinanceClient(
            api_key=BINANCE_API_KEY if BINANCE_API_KEY else None,
            api_secret=BINANCE_SECRET_KEY if BINANCE_SECRET_KEY else None
        )
        self.rate_limit_delay = 60 / BINANCE_RATE_LIMIT

    def download_ohlcv(self, symbol: str, resolution: str, start_date: datetime, end_date: datetime):
        """Download OHLCV data from Binance and save in Lean format"""
        logger.info(f"Downloading {symbol} OHLCV at {resolution} resolution...")
        
        interval_map = {'minute': '1m', 'hour': '1h', 'daily': '1d'}
        binance_interval = interval_map.get(resolution, '1h')
        
        try:
            # Convert to timestamps
            start_ts = int(start_date.timestamp() * 1000)
            end_ts = int(end_date.timestamp() * 1000)
            
            klines = self.client.get_historical_klines(
                symbol, binance_interval, start_ts, end_ts
            )
            
            if not klines:
                logger.warning(f"No kline data for {symbol}")
                return
            
            # Convert to our format
            data = []
            for kline in klines:
                timestamp = datetime.fromtimestamp(kline[0] / 1000.0, tz=pytz.UTC)
                data.append({
                    'timestamp': timestamp,
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5])
                })
            
            # Clean data
            cleaned_data = DataValidator.clean_ohlcv_data(data)
            if not cleaned_data:
                logger.warning(f"No valid data after cleaning for {symbol}")
                return
            
            output_dir = os.path.join(CRYPTO_PATH, resolution)
            ensure_directory_exists(output_dir)
            symbol_lower = symbol.lower()
            
            # Group by date for processing
            daily_data = {}
            for bar in cleaned_data:
                date_key = bar['timestamp'].strftime(LEAN_TIME_FORMAT)
                if date_key not in daily_data:
                    daily_data[date_key] = []
                daily_data[date_key].append(bar)
            
            # Generate trade content
            all_trade_content = []
            all_quote_content = []
            for date_key in sorted(daily_data.keys()):
                date_bars = daily_data[date_key]
                trade_content = create_lean_crypto_csv(date_bars, symbol, date_bars[0]['timestamp'], resolution)
                # For quote files, we approximate bid/ask from OHLC
                quote_content = []
                for bar in date_bars:
                    # Approximate: bid = close * 0.999, ask = close * 1.001 (spread approx 0.2%)
                    bid = bar['close'] * 0.999
                    ask = bar['close'] * 1.001
                    time_str = bar['timestamp'].strftime("%Y%m%d %H:%M")
                    quote_content.append([
                        time_str,
                        bid, bid, bid, bid, float(bar['volume']),
                        ask, ask, ask, ask, float(bar['volume'])
                    ])
                all_trade_content.extend(trade_content)
                all_quote_content.extend(quote_content)
            
            # Write trade zip
            trade_path = os.path.join(output_dir, f"{symbol_lower}_trade.zip")
            trade_csv_name = f"{symbol_lower}_{resolution}_trade.csv"
            write_lean_zip_file(all_trade_content, trade_path, trade_csv_name)
            logger.info(f"Saved {len(all_trade_content)} trade bars to {trade_path}")
            
            # Write quote zip
            quote_path = os.path.join(output_dir, f"{symbol_lower}_quote.zip")
            quote_csv_name = f"{symbol_lower}_{resolution}_quote.csv"
            write_lean_zip_file(all_quote_content, quote_path, quote_csv_name)
            logger.info(f"Saved {len(all_quote_content)} quote bars to {quote_path}")
            
            time.sleep(self.rate_limit_delay)
            
        except Exception as e:
            logger.error(f"Error downloading OHLCV for {symbol}: {str(e)}")

    def download_funding_rate(self, symbol: str, start_date: datetime, end_date: datetime):
        """Download funding rate data from Binance for perpetual futures"""
        logger.info(f"Downloading funding rates for {symbol}...")
        
        try:
            # Binance funding rate API uses the perp symbol (e.g., SOLUSDT)
            funding_data = []
            
            # Binance's funding rate history - get all available data
            start_ts = int(start_date.timestamp() * 1000)
            end_ts = int(end_date.timestamp() * 1000)
            
            # Use the funding rate API
            current_start = start_ts
            while current_start < end_ts:
                try:
                    response = self.client.futures_funding_rate(
                        symbol=symbol,
                        startTime=current_start,
                        endTime=end_ts,
                        limit=1000
                    )
                    
                    if not response:
                        break
                    
                    for entry in response:
                        funding_time = int(entry['fundingTime'])
                        funding_rate = float(entry['fundingRate'])
                        mark_price_str = entry.get('markPrice', '')
                        mark_price = float(mark_price_str) if mark_price_str and mark_price_str.strip() else 0.0
                        
                        # Convert funding time to ISO timestamp
                        timestamp = datetime.fromtimestamp(funding_time / 1000.0, tz=pytz.UTC)
                        
                        funding_data.append({
                            'timestamp': timestamp.isoformat(),
                            'funding_time': funding_time,
                            'funding_rate': funding_rate,
                            'mark_price': mark_price
                        })
                    
                    if len(response) < 1000:
                        break
                    
                    # Move to next batch
                    current_start = int(response[-1]['fundingTime']) + 1
                    time.sleep(self.rate_limit_delay)
                    
                except Exception as e:
                    logger.error(f"Error fetching funding batch for {symbol}: {str(e)}")
                    break
            
            if not funding_data:
                logger.warning(f"No funding data for {symbol}")
                return
            
            # Sort by timestamp
            funding_data.sort(key=lambda x: x['funding_time'])
            
            # Write CSV file
            symbol_lower = symbol.lower()
            output_path = os.path.join(FUNDING_PATH, f"{symbol_lower}_funding.csv")
            ensure_directory_exists(FUNDING_PATH)
            
            with open(output_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'funding_time', 'funding_rate', 'mark_price'])
                for entry in funding_data:
                    mark_price_str = f"{entry['mark_price']:.8f}" if entry['mark_price'] else ''
                    writer.writerow([
                        entry['timestamp'],
                        entry['funding_time'],
                        f"{entry['funding_rate']:.8f}",
                        mark_price_str
                    ])
            
            logger.info(f"Saved {len(funding_data)} funding records to {output_path}")
            
        except Exception as e:
            logger.error(f"Error downloading funding rates for {symbol}: {str(e)}")

    def run_all(self):
        """Download all data for new pairs"""
        
        # For each base asset, we need:
        # 1. {ASSET}USDC - spot pair (for spot leg of arbitrage)
        # 2. {ASSET}USDT - perpetual pair (for perp leg of arbitrage)
        # 3. Funding rates for {ASSET}USDT
        
        bases = ["SOL", "BNB", "XRP", "ADA", "DOGE"]
        
        # Date range for OHLC data (match existing BTC/ETH range)
        ohlcv_start = datetime(2020, 1, 1)
        ohlcv_end = datetime(2026, 6, 15)
        
        # First, check which symbols exist on Binance
        try:
            exchange_info = self.client.get_exchange_info()
            available_symbols = {s['symbol'] for s in exchange_info['symbols'] if s['status'] == 'TRADING'}
            logger.info(f"Available trading pairs on Binance: {len(available_symbols)}")
        except Exception as e:
            logger.error(f"Could not get exchange info: {e}")
            available_symbols = set()
        
        for base in bases:
            print(f"\n{'='*60}")
            print(f"Processing {base} ({NEW_PAIRS[base]['name']})")
            print(f"{'='*60}")
            
            # Spot pair: {BASE}USDC
            spot_symbol = f"{base}USDC"
            # Perp pair: {BASE}USDT
            perp_symbol = f"{base}USDT"
            
            # Check availability
            if perp_symbol not in available_symbols:
                logger.warning(f"{perp_symbol} not available on Binance, checking alternate...")
                # Try USDC perp
                if f"{base}USDC" in available_symbols:
                    logger.info(f"Using {base}USDC as the perp pair")
                    perp_symbol = f"{base}USDC"
            
            # Step 1: Download spot USDC pair OHLCV at hourly and daily
            print(f"\n--- Downloading {spot_symbol} spot OHLCV ---")
            self.download_ohlcv(spot_symbol, 'hour', ohlcv_start, ohlcv_end)
            self.download_ohlcv(spot_symbol, 'daily', ohlcv_start, ohlcv_end)
            
            # Step 2: Download perp USDT pair OHLCV at hourly and daily
            print(f"\n--- Downloading {perp_symbol} perp OHLCV ---")
            self.download_ohlcv(perp_symbol, 'hour', ohlcv_start, ohlcv_end)
            self.download_ohlcv(perp_symbol, 'daily', ohlcv_start, ohlcv_end)
            
            # Step 3: Download funding rates for the perp
            print(f"\n--- Downloading funding rates for {perp_symbol} ---")
            self.download_funding_rate(perp_symbol, FUNDING_START_DATE, FUNDING_END_DATE)
            
            print(f"\n✅ Completed {base}")

        print(f"\n{'='*60}")
        print("ALL DOWNLOADS COMPLETE!")
        print(f"{'='*60}")
        print(f"\nFiles saved to:")
        print(f"  OHLC: {CRYPTO_PATH}/hour/ and {CRYPTO_PATH}/daily/")
        print(f"  Funding: {FUNDING_PATH}/")
        print(f"\nFiles created:")
        
        # List created files
        for base in bases:
            for ext in ['_trade.zip', '_quote.zip']:
                for res in ['hour', 'daily']:
                    path = os.path.join(CRYPTO_PATH, res, f"{base.lower()}usdc{ext}")
                    if os.path.exists(path):
                        print(f"  ✓ {path}")
                    path = os.path.join(CRYPTO_PATH, res, f"{base.lower()}usdt{ext}")
                    if os.path.exists(path):
                        print(f"  ✓ {path}")
            funding_path = os.path.join(FUNDING_PATH, f"{base.lower()}usdt_funding.csv")
            if os.path.exists(funding_path):
                print(f"  ✓ {funding_path}")


if __name__ == "__main__":
    downloader = NewCryptoDataDownloader()
    downloader.run_all()
