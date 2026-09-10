"""
Fix Binance crypto quote archives to match the Lean QuoteBar schema.

Lean's QuoteBar.Reader() -> ParseForex() -> ParseQuote() expects:
  yyyyMMdd HH:mm, bidOpen, bidHigh, bidLow, bidClose, bidSize, askOpen, askHigh, askLow, askClose, askSize

Problems found:
1. Daily quote files (*USDT_quote.zip) contained 6-column trade-shaped data (no bid/ask columns)
2. Daily quote files (*USDC_quote.zip) had correct 11 columns but contained CSVs named *_hour_trade.csv (wrong name)
3. Hourly quote files (*USDT_quote.zip) had 10 columns - missing bidSize as a separate column
   They used: time, bidO, bidH, bidL, bidC, askO, askH, askL, askC, volume
   But Lean expects: time, bidO, bidH, bidL, bidC, bidSize, askO, askH, askL, askC, askSize
   (The 10th column was volume being used as askSize, so adding a bidSize column fixes it)
4. Hourly quote files (*USDC_quote.zip) had 10 columns - same bidSize issue
"""

import os
import zipfile
import shutil
from collections import OrderedDict

DATA_ROOT = os.path.join(os.path.dirname(__file__), '..', 'data')
CRYPTO_DIR = os.path.join(DATA_ROOT, 'crypto', 'binance')

# Symbols that need fixing
SYMBOLS = ['btcusdt', 'btcusdc', 'ethusdt', 'ethusdc']


def get_csv_name(symbol: str) -> str:
    """Return the csv name that Lean expects for a quote zip file."""
    # Lean's crypto reader looks for {symbol}_{resolution}_quote.csv
    # But with different logic depending on the resolution. For simplicity,
    # we'll use what Lean's reader expects.
    return f"{symbol}_quote.csv"


def get_hour_csv_name(symbol: str) -> str:
    """Return the CSV name Lean expects for hourly quote data."""
    return f"{symbol}_hour_quote.csv"


def get_daily_csv_name(symbol: str) -> str:
    """Return the CSV name Lean expects for daily quote data."""
    return f"{symbol}_daily_quote.csv"


def fix_hourly_quote_file(filepath: str, symbol: str):
    """
    Fix hourly quote files.
    
    Current hourly quote rows have 10 columns:
      time, bidO, bidH, bidL, bidC, askO, askH, askL, askC, volume
    
    Lean expects 11 columns:
      time, bidO, bidH, bidL, bidC, bidSize, askO, askH, askL, askC, askSize
    
    Since our Binance klines don't have bid/ask size, we use the volume as both
    bidSize and askSize (or 0 if no volume available). Actually, since these are
    derived from trade klines, we use the existing volume as askSize and insert
    the same volume as bidSize to match the 11-column schema.
    """
    print(f"  Fixing hourly quote: {os.path.basename(filepath)}")
    
    # Read existing content
    with zipfile.ZipFile(filepath, 'r') as z_in:
        # Find the CSV file inside
        names = z_in.namelist()
        if not names:
            print(f"    WARNING: Empty zip file!")
            return
        csv_name = names[0]
        content = z_in.read(csv_name).decode()
    
    lines = content.strip().split('\n')
    new_lines = []
    
    for line in lines:
        cols = line.split(',')
        if len(cols) < 10:
            print(f"    WARNING: Line has {len(cols)} columns instead of 10+: {cols}")
            new_lines.append(line)
            continue
        
        # Current cols (10): time, bidO, bidH, bidL, bidC, askO, askH, askL, askC, askSize-like
        # We need to insert bidSize between bidClose and askOpen
        
        time = cols[0]
        bid_open = cols[1]
        bid_high = cols[2]
        bid_low = cols[3]
        bid_close = cols[4]
        ask_open = cols[5]
        ask_high = cols[6]
        ask_low = cols[7]
        ask_close = cols[8]
        ask_size = cols[9]
        
        # Insert bidSize (copy ask_size as bid_size since we don't have separate bid/ask volumes from klines)
        bid_size = ask_size
        
        new_row = [time, bid_open, bid_high, bid_low, bid_close, bid_size,
                   ask_open, ask_high, ask_low, ask_close, ask_size]
        new_lines.append(','.join(new_row))
    
    # Write back with proper CSV name
    new_csv_name = get_hour_csv_name(symbol)
    temp_path = filepath + '.tmp'
    with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as z_out:
        z_out.writestr(new_csv_name, '\n'.join(new_lines) + '\n')
    
    shutil.move(temp_path, filepath)
    print(f"    Rewrote with {len(new_lines)} rows, CSV name: {new_csv_name}")


def fix_daily_quote_file(filepath: str, symbol: str):
    """
    Fix daily quote files.
    
    Two sub-problems:
    1. USDT pairs (btcusdt, ethusdt): had only 6 trade-shaped columns
       -> Need to derive quote data from available trade data (bid=ask=price)
    2. USDC pairs (btcusdc, ethusdc): had 11 columns but wrong CSV filename
       -> Just need to rename the CSV inside the zip to the correct name
    
    For USDT pairs that only have trade data, we'll convert the 6-col trade data
    to 11-col quote data by using the trade price as both bid and ask.
    """
    print(f"  Fixing daily quote: {os.path.basename(filepath)}")
    
    with zipfile.ZipFile(filepath, 'r') as z_in:
        names = z_in.namelist()
        if not names:
            print(f"    WARNING: Empty zip file!")
            return
        csv_name = names[0]
        content = z_in.read(csv_name).decode()
    
    lines = content.strip().split('\n')
    new_lines = []
    
    for line in lines:
        cols = line.split(',')
        
        if len(cols) >= 11:
            # Already has 11+ cols (like USDC files that had correct data but wrong name)
            # Just use as-is
            new_lines.append(','.join(cols[:11]))
            
        elif len(cols) == 6:
            # Trade-shaped data: time, open, high, low, close, volume
            # Convert to quote data: bid = ask = trade price
            time, open_p, high_p, low_p, close_p, volume = cols
            bid_size = volume
            ask_size = volume
            new_row = [time, open_p, high_p, low_p, close_p, bid_size,
                       open_p, high_p, low_p, close_p, ask_size]
            new_lines.append(','.join(new_row))
            
        else:
            print(f"    WARNING: Line has {len(cols)} columns, unexpected: {cols}")
            new_lines.append(line)
    
    # Write back with proper daily CSV name
    new_csv_name = get_daily_csv_name(symbol)
    temp_path = filepath + '.tmp'
    with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as z_out:
        z_out.writestr(new_csv_name, '\n'.join(new_lines) + '\n')
    
    shutil.move(temp_path, filepath)
    print(f"    Rewrote with {len(new_lines)} rows, CSV name: {new_csv_name}")


def fix_hourly_also_missing_ask_size():
    """
    Some hourly files from older downloads may also have the issue where the 
    CSV inside is named *_hour_trade.csv instead of *_hour_quote.csv,
    or have 10 cols with the wrong layout.
    Let's check all hourly files.
    """
    hour_dir = os.path.join(CRYPTO_DIR, 'hour')
    print(f"\nChecking hourly quote files in {hour_dir}")
    
    for root, dirs, files in os.walk(hour_dir):
        for f in sorted(files):
            if f.endswith('_quote.zip'):
                symbol = f.replace('_quote.zip', '')
                filepath = os.path.join(root, f)
                
                with zipfile.ZipFile(filepath, 'r') as z:
                    names = z.namelist()
                    content = z.read(names[0]).decode()
                    lines = content.strip().split('\n')
                    first_line_cols = len(lines[0].split(',')) if lines else 0
                
                print(f"  {f}: CSV='{names[0]}', cols={first_line_cols}")
                
                if first_line_cols == 10:
                    fix_hourly_quote_file(filepath, symbol)
                elif first_line_cols == 11:
                    # Check if the CSV name is correct
                    expected_name = get_hour_csv_name(symbol)
                    if names[0] != expected_name:
                        print(f"    Renaming CSV inside zip: {names[0]} -> {expected_name}")
                        # Just rename the internal file
                        with zipfile.ZipFile(filepath, 'r') as z_in:
                            data = z_in.read(names[0])
                        temp_path = filepath + '.tmp'
                        with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as z_out:
                            z_out.writestr(expected_name, data)
                        shutil.move(temp_path, filepath)
                        print(f"    Done.")
                    else:
                        print(f"    OK - correct format.")
                else:
                    print(f"    UNEXPECTED column count!")


def main():
    print("=" * 70)
    print("FIXING BINANCE CRYPTO QUOTE ARCHIVES FOR LEAN COMPATIBILITY")
    print("=" * 70)
    
    # 1. Fix daily quote files
    daily_dir = os.path.join(CRYPTO_DIR, 'daily')
    print(f"\n[1] Processing daily quote files in: {daily_dir}")
    
    for symbol in SYMBOLS:
        filepath = os.path.join(daily_dir, f"{symbol}_quote.zip")
        if os.path.exists(filepath):
            fix_daily_quote_file(filepath, symbol)
        else:
            print(f"  {symbol}_quote.zip not found, skipping.")
    
    # 2. Fix hourly quote files
    hour_dir = os.path.join(CRYPTO_DIR, 'hour')
    print(f"\n[2] Processing hourly quote files in: {hour_dir}")
    
    for symbol in SYMBOLS:
        filepath = os.path.join(hour_dir, f"{symbol}_quote.zip")
        if os.path.exists(filepath):
            fix_hourly_quote_file(filepath, symbol)
        else:
            print(f"  {symbol}_quote.zip not found, skipping.")
    
    print("\n" + "=" * 70)
    print("VERIFICATION")
    print("=" * 70)
    
    # Verify daily
    print("\nDaily quote files after fix:")
    for symbol in SYMBOLS:
        filepath = os.path.join(daily_dir, f"{symbol}_quote.zip")
        if os.path.exists(filepath):
            with zipfile.ZipFile(filepath) as z:
                for name in z.namelist():
                    content = z.read(name).decode()
                    lines = content.strip().split('\n')
                    cols = len(lines[0].split(',')) if lines else 0
                    print(f"  {symbol}_quote.zip: CSV='{name}', cols={cols}, rows={len(lines)}")
                    if lines:
                        print(f"    Sample: {lines[0]}")
    
    # Verify hourly
    print("\nHourly quote files after fix:")
    for symbol in SYMBOLS:
        filepath = os.path.join(hour_dir, f"{symbol}_quote.zip")
        if os.path.exists(filepath):
            with zipfile.ZipFile(filepath) as z:
                for name in z.namelist():
                    content = z.read(name).decode()
                    lines = content.strip().split('\n')
                    cols = len(lines[0].split(',')) if lines else 0
                    print(f"  {symbol}_quote.zip: CSV='{name}', cols={cols}, rows={len(lines)}")
                    if lines:
                        print(f"    Sample: {lines[0]}")
    
    print("\nDone! All quote archives should now be in proper Lean QuoteBar format.")


if __name__ == '__main__':
    main()
