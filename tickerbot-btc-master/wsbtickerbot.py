import multiprocessing
import re
import sys
from collections import defaultdict
from copy import deepcopy
import pandas_market_calendars as mcal
import pandas
import praw
import time
import json
import operator
import datetime
from pandas.tseries.offsets import *

from joblib import Parallel, delayed
from praw.models import MoreComments
from iexfinance.stocks import Stock as IEXStock
from iexfinance.refdata import get_iex_symbols
import os
import stopwords

from datetime import date, datetime, timedelta

# to add the path for Python to search for files to use my edited version of vaderSentiment
sys.path.insert(0, 'vaderSentiment/vaderSentiment')
from vaderSentiment import SentimentIntensityAnalyzer


def extract_ticker(body, start_index):
    """
   Given a starting index and text, this will extract the ticker, return None if it is incorrectly formatted.
   """
    count = 0
    ticker = ""

    for char in body[start_index:]:
        # if it should return
        if not char.isalpha():
            # if there aren't any letters following the $
            if (count == 0):
                return None

            return ticker.upper()
        else:
            ticker += char
            count += 1

    return ticker.upper()


def get_date():
    now = datetime.datetime.now()
    return now.strftime("%b %d, %Y")


def setup(sub):
    if sub == "":
        sub = "bitcoin"

    with open("config.json") as json_data_file:
        data = json.load(json_data_file)

    # create a reddit instance
    reddit = praw.Reddit(client_id=data["login"]["client_id"], client_secret=data["login"]["client_secret"],
                         username=data["login"]["username"], password=data["login"]["password"],
                         user_agent=data["login"]["user_agent"])
    # create an instance of the subreddit
    subreddit = reddit.subreddit(sub)
    return subreddit


def convert_to_datestring(date):
    month = date.strftime("%B")
    # print(''.join((2 - len(str(date.day))) * ['0']))
    day_of_month = ''.join((2 - len(str(date.day))) * ['0']) + str(date.day)

    year = date.year
    wsb_reddit_date_string = month + ' ' + str(day_of_month) + ', ' + str(year)
    if '0' == str(day_of_month)[0]:
        wsb_reddit_date_string2 = month + ' ' + str(day_of_month)[1:] + ', ' + str(year)
    else:
        wsb_reddit_date_string2 = wsb_reddit_date_string
    # print(wsb_reddit_date_string)
    return wsb_reddit_date_string, wsb_reddit_date_string2


def current_or_last_business_day_btc():
    today = datetime.today()
    weekno = today.weekday()
    if today.hour <= 4:
        return today - timedelta(days=1)
    return today


def run(sub, num_submissions, buy_signals, sell_signals, hold_signals):
    # print(get_iex_symbols()[:2])
    # exit(0)
    ticker_dict = {}
    text = ""
    total_count = 0
    within24_hrs = False
    count = 0
    subreddit = setup(sub)
    new_posts = subreddit.new(limit=num_submissions)
    link = 'www.reddit.com'
    discussion_submissions = []
    # print([sub.title for sub in list(subreddit.search("Discussion Thread", limit=10))])
    today_date_string = convert_to_datestring(current_or_last_business_day_btc())

    today = datetime.now()
    # print(today_date_string, today.hour, today.weekday())
    for submission in subreddit.search("Daily Discussion,", limit=20):
        # print(submission.title)
        # print(submission.title)
        for datestring in today_date_string:
            if datestring in submission.title:
                discussion_submissions.append(submission)
            try:
                submission.comment_sort = "new"
            except:
                raise Exception
    # print(discussion_submissions)
    print([subm.title for subm in discussion_submissions])
    for discussion_submission in discussion_submissions:
        for top_level_comment in discussion_submission.comments:

            # search through all comments and replies to comments

            # without this, would throw AttributeError since the instance in this represents the "load more comments" option
            if isinstance(top_level_comment, MoreComments):
                continue
            count += 1
            # print(top_level_comment.body)
            # print('comment', comment.body)
            buy, sell, hold = analyze_sentiment(top_level_comment.body, buy_signals, sell_signals, hold_signals)
            buy_signals += buy
            sell_signals += sell
            hold_signals += hold
            # if len(ticker_dict):
            #     print(ticker_dict)
            # generate_sentiment_report(ticker_dict)
            # update the progress count
            sys.stdout.write(
                "\rProgress: {0} / {1} posts\n".format(count + 1, len(discussion_submissions) * num_submissions))
            sys.stdout.flush()

            if count == num_submissions:
                break
            generate_sentiment_report(buy_signals, sell_signals, hold_signals)
    # ticker_df.to_csv('existing_tickers.csv', mode='w+')
    return buy_signals, sell_signals, hold_signals
    # ticker_df.to_csv('existing_tickers.csv.csv')


def generate_sentiment_report(buy_signals, sell_signals, hold_signals):
    text = "\n\nTicker | Buy Signals (%) | Hold Signals (%) | Sell Signals (%)"

    total_signals = buy_signals + sell_signals + hold_signals
    # url = get_url(ticker.ticker, ticker.count, total_mentions)
    # setting up formatting for table
    text += "\n{} | {} | {} | {}".format('btc',
                                         str(buy_signals),
                                         str(sell_signals),
                                         str(hold_signals))

    print(text)


def analyze_sentiment(text, buy_signals, sell_signals, hold_signals):
    buy_triggers = ["MOON", "BUY", "BOUGHT", "PUMP", "ELON", 'MUSK', "LOAD"]
    hold_triggers = ["HOLD", "HODL"]
    sell_triggers = ["DUMP", "SELL"]

    ws_split = [word.lower() for word in text.split()]
    print(ws_split)
    for trigger in buy_triggers:
        for word in ws_split:
            if trigger.lower() in word:
                buy_signals += 1

    for trigger in sell_triggers:
        for word in ws_split:
            if trigger.lower() in word:
                sell_signals += 1
    for trigger in hold_triggers:
        for word in ws_split:
            if trigger.lower() in word:
                hold_signals += 1
    return buy_signals, sell_signals, hold_signals


if __name__ == "__main__":
    # USAGE: wsbtickerbot.py [ subreddit ] [ num_submissions ]
    wsb_ticker_dict = {}
    current = None
    crypto_ticker_dict = defaultdict(list)
    crypto_ticker_dict['btc'].append('btc')
    crypto_ticker_dict['btc'].append('bitcoin')
    buy_signal_count = 0
    sell_signal_count = 0
    hold_signal_count = 0
    while True:
        num_submissions = 10
        sub = "bitcoin"
        # os.environ["IEX_TOKEN"] = "pk_c9d60275d7934039a4e73d2bceafca71"
        ticker_df_csv = pandas.read_csv("existing_tickers.csv")
        existing_ticker_data = crypto_ticker_dict['btc']
        # try:
        buy_signals, sell_signals, hold_signals = run(sub, num_submissions, 0, 0, 0)
        buy_signal_count += buy_signals
        sell_signal_count += sell_signals
        hold_signals += hold_signals
        # except Exception:
        #     continue

        generate_sentiment_report(buy_signal_count, sell_signal_count, hold_signal_count)
