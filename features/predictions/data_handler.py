from kickbase_api.player import (
    get_all_players,
    get_player_info,
    get_player_market_value,
    get_player_performance,
)
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import concurrent.futures
import pandas as pd
import sqlite3

def create_player_data_table():
    """Create the player_data_1d table in the SQLite database if it doesn't exist"""

    conn = sqlite3.connect("player_data_total.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS player_data_1d (
        player_id INTEGER,
        team_id INTEGER,
        team_name TEXT,
        first_name TEXT,
        last_name TEXT,
        position TEXT,
        md DATE,
        date DATE,
        p REAL,
        mp INTEGER,
        ppm REAL,
        t1 INTEGER,
        t2 INTEGER,
        t1g INTEGER,
        t2g INTEGER,
        won INTEGER,
        k TEXT,
        mv REAL
    );
    """)

    conn.commit()

def check_if_data_reload_needed():
    """Check if data reload is needed based on the last entry with null market value"""

    print("\nData reload needed, this takes a few minutes...")
    return True # Due to some issues with the data, we always reload for now, until fixed

    now = datetime.now(ZoneInfo("Europe/Berlin"))
    today_date = now.date()

    # Get nearest entry to today where mv is null
    with sqlite3.connect("player_data_total.db") as conn:
        cursor = conn.cursor()

        # Get the most recent date where mv is NULL
        cursor.execute("SELECT date FROM player_data_1d WHERE mv IS NULL ORDER BY date ASC LIMIT 1;")
        last_null_entry = cursor.fetchone()

        # convert last_null_entry (timestamp) to date
        if last_null_entry is not None:
            last_null_entry = datetime.fromisoformat(last_null_entry[0]).date()

        # Get the most recent date where mv is NOT NULL and at least 100 rows have this date
        # Hardcoded 100, bc if a player transfers on day x, he immediately has a mv value on day x and we dont want that
        cursor.execute("""
            SELECT date
            FROM player_data_1d
            WHERE mv IS NOT NULL
            GROUP BY date
            HAVING COUNT(*) >= 100
            ORDER BY date DESC
            LIMIT 1;
        """)
        last_non_null_entry = cursor.fetchone()

        # convert last_non_null_entry (timestamp) to date
        if last_non_null_entry is not None:
            last_non_null_entry = datetime.fromisoformat(last_non_null_entry[0]).date()

        # If there are no entries with null mv or no entries with non-null mv, we need to reload
        if last_null_entry is None or last_non_null_entry is None:
            return True

        # Cutoff-Time: 22:15 Uhr
        cutoff = now.replace(hour=22, minute=15, second=0, microsecond=0)

        # If it is before 22:15 then yesterday should exist in the database with a mv value or today should exist with a null mv value
        if now < cutoff and (last_non_null_entry == today_date - timedelta(days=1) or last_null_entry == today_date):
            return False

        # If it is after 22:15 today should exist in the database with a mv value
        elif now >= cutoff and last_non_null_entry == today_date:
            return False
        
        # Any other case we need to reload
        else:
            print("\nData reload needed, this takes a few minutes...")
            return True


def save_player_data_to_db(token, competition_ids, last_mv_values, last_pfm_values, reload_data):
    """Fetch player data and save to SQLite database if reload_data is needed"""

    if reload_data:
        all_competitions_dfs = []

        for competition_id in competition_ids:
            players = get_all_players(token, competition_id)

            def process_player(player_id):
                player_info = get_player_info(token, competition_id, player_id)
                player_team_id = player_info["team_id"]
                player_df = pd.DataFrame([player_info])

                # Market Value
                mv_df = pd.DataFrame(get_player_market_value(token, competition_id, player_id, last_mv_values))
                if not mv_df.empty:
                    mv_df["date"] = pd.to_datetime(mv_df["date"])
                    mv_df = mv_df.sort_values("date")

                # Special case for players with 500k market value and no change, manually add them
                #if (mv_df["date"].max() < pd.Timestamp(datetime.now(ZoneInfo("Europe/Berlin")).date())) and mv_df["mv"].iloc[-1] == 500_000:
                #    print("Testing special case")
                #    last_row = mv_df.iloc[-1].copy()
                #    last_row["date"] = pd.Timestamp(datetime.now(ZoneInfo("Europe/Berlin")).date())
                #    mv_df = pd.concat([mv_df, pd.DataFrame([last_row])], ignore_index=True)

                # Performance
                p_df = pd.DataFrame(get_player_performance(token, competition_id, player_id, last_pfm_values, player_team_id))
                if not p_df.empty:
                    p_df["date"] = pd.to_datetime(p_df["date"])
                    p_df = p_df.sort_values("date")
                else:
                    p_df = pd.DataFrame({"date": pd.to_datetime([])})

                # Ensure date columns are in datetime64[us] format, see problem #6
                p_df["date"] = p_df["date"].astype("datetime64[us]")

                # Merge DataFrames
                merged_df = (
                    pd.merge_asof(mv_df, p_df, on="date", direction="backward")
                    if not mv_df.empty else pd.DataFrame()
                )

                # Get p_df values where p_df.date > max(mv_df.date) and append to merged_df
                if not p_df.empty and not mv_df.empty:
                    max_mv_date = mv_df["date"].max()
                    additional_p_df = p_df[p_df["date"] > max_mv_date]
                    merged_df = pd.concat([merged_df, additional_p_df], ignore_index=True) 

                if not merged_df.empty:
                    merged_df = player_df.merge(merged_df, how="cross")
                    merged_df["competition_id"] = competition_id

                return merged_df

            # Use ThreadPoolExecutor to parallelize player fetching
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
                comp_dfs = list(executor.map(process_player, players))
            
            comp_final_df = pd.concat(
                [df.dropna(how="all", axis=1) for df in comp_dfs if df is not None and not df.empty],
                ignore_index=True
            )

            all_competitions_dfs.append(comp_final_df)

        # Combine all competitions
        final_df = pd.concat(all_competitions_dfs, ignore_index=True)

        # Convert k column to string
        final_df["k"] = final_df["k"].apply(
            lambda x: ",".join(map(str, x)) if isinstance(x, list) else (None if x is None else str(x))
        )

        # Save to SQLite
        with sqlite3.connect("player_data_total.db") as conn:
            final_df.to_sql("player_data_1d", conn, if_exists="replace", index=False)

def load_player_data_from_db():
    """Load player data from SQLite database into a dataframe"""
    
    conn = sqlite3.connect("player_data_total.db")
    df = pd.read_sql("SELECT * FROM player_data_1d", conn)
    conn.close()

    return df