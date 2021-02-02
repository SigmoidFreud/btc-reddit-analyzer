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


def parse_section(ticker_dict, body, existing_tickers, ticker_df):
    """ Parses the body of each comment/reply """
    ticker_prefixes = ['#', '$']
    for prefix in ticker_prefixes:
        if prefix in body:
            index = body.find('prefix') + 1
            word = extract_ticker(body, index)

            if word and (
                    word.upper() not in stopwords.blacklist_words and word.lower() not in stopwords.blacklist_words):
                try:
                    if word in existing_tickers:
                        if 'btc' in ticker_dict:
                            ticker_dict['btc'].count += 1
                            ticker_dict['btc'].bodies.append(body)
                        else:
                            ticker_dict['btc'] = Ticker(word)
                            ticker_dict['btc'].count = 1
                            ticker_dict['btc'].bodies.append(body)
                            # print(word, ticker_dict[word_upper].count)
                except:
                    pass

    # checks for non-$ formatted comments, splits every body into list of words
    word_list = re.sub("[^\w]", " ", body).split()
    num_cores = multiprocessing.cpu_count()

    for count, word in enumerate(word_list):
        try:
            if word in existing_tickers:
                if 'btc' in ticker_dict:
                    ticker_dict['btc'].count += 1
                    ticker_dict['btc'].bodies.append(body)
                else:
                    ticker_dict['btc'] = Ticker(word)
                    ticker_dict['btc'].count = 1
                    ticker_dict['btc'].bodies.append(body)
                    # print(word, ticker_dict[word_upper].count)
        except:
            pass

    return ticker_dict


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


def run(sub, num_submissions, existing_tickers, ticker_df):
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
    print(today_date_string, today.hour, today.weekday())
    for submission in subreddit.search("Daily Discussion,", limit=20):
        # print(submission.title)
        print(submission.title)
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
            ticker_dict = parse_section(ticker_dict, top_level_comment.body, existing_tickers, ticker_df)

            # if len(ticker_dict):
            #     print(ticker_dict)
            # generate_sentiment_report(ticker_dict)
            # update the progress count
            sys.stdout.write(
                "\rProgress: {0} / {1} posts\n".format(count + 1, len(discussion_submissions) * num_submissions))
            sys.stdout.flush()

            if count == num_submissions:
                break
            generate_sentiment_report(wsb_ticker_dict)
    # ticker_df.to_csv('existing_tickers.csv', mode='w+')
    return ticker_dict
    # ticker_df.to_csv('existing_tickers.csv.csv')


def generate_sentiment_report(ticker_dictionary):
    text = "\n\nTicker | Mentions | Bullish (%) | Neutral (%) | Bearish (%)"

    ticker_list = []
    # print(ticker_dictionary)
    for key in ticker_dictionary:
        temp_count = ticker_dictionary[key].count
        ticker_dictionary[key].count = temp_count
        ticker_list.append(ticker_dictionary[key])
    if not len(ticker_list):
        return
    ticker_list = sorted(ticker_list, key=operator.attrgetter("count"), reverse=True)
    # print(ticker_list)
    for ticker in ticker_list:
        Ticker.analyze_sentiment(ticker)

    # will break as soon as it hits a ticker with fewer than 5 mentions
    for count, ticker in enumerate(ticker_list):
        # if ticker_dictionary[ticker.ticker].count < 3:
        #     continue
        if count == 6:
            break

        # url = get_url(ticker.ticker, ticker.count, total_mentions)
        # setting up formatting for table
        text += "\n{} | {} | {} | {} | {}".format(ticker.ticker, ticker_dictionary[ticker.ticker].count, ticker.bullish,
                                                  ticker.bearish,
                                                  ticker.neutral)
    print(text)


class Ticker:
    def __init__(self, ticker):
        self.ticker = ticker
        self.count = 0
        self.bodies = []
        self.pos_count = 0
        self.neg_count = 0
        self.bullish = 0
        self.bearish = 0
        self.neutral = 0
        self.sentiment = 0  # 0 is neutral

    def analyze_sentiment(self):
        analyzer = SentimentIntensityAnalyzer()
        neutral_count = 0
        buy_triggers = ["MOON", "BUY", "HOLD", "HODL", "BOUGHT", "PUMP"]
        sell_triggers = ["DUMP", "SELL"]
        for text in self.bodies:
            sentiment = analyzer.polarity_scores(text)
            for trigger in buy_triggers:
                if trigger in text or trigger.lower() in text:
                    self.pos_count += 1
            for trigger in sell_triggers:
                if trigger in text or trigger.lower() in text:
                    self.neg_count += 1
            if (sentiment["compound"] > .005) or (sentiment["pos"] > abs(sentiment["neg"])):
                self.pos_count += 1
            elif (sentiment["compound"] < -.005) or (abs(sentiment["neg"]) > sentiment["pos"]):
                self.neg_count += 1
            else:
                neutral_count += 1

        self.bullish = int(self.pos_count / len(self.bodies) * 100)
        self.bearish = int(self.neg_count / len(self.bodies) * 100)
        self.neutral = int(neutral_count / len(self.bodies) * 100)


if __name__ == "__main__":
    # USAGE: wsbtickerbot.py [ subreddit ] [ num_submissions ]
    wsb_ticker_dict = {}
    current = None
    crypto_ticker_dict = defaultdict(list)
    crypto_ticker_dict['btc'].append('btc')
    crypto_ticker_dict['btc'].append('bitcoin')
    while True:
        num_submissions = 10
        sub = "bitcoin"
        # os.environ["IEX_TOKEN"] = "pk_c9d60275d7934039a4e73d2bceafca71"
        ticker_df_csv = pandas.read_csv("existing_tickers.csv")
        existing_ticker_data = crypto_ticker_dict['btc']
        # try:
        wsb_tick_data = run(sub, num_submissions, existing_ticker_data, ticker_df_csv)
        # except Exception:
        #     continue
        print(wsb_tick_data)
        for ticker, tick_obj in deepcopy(wsb_tick_data).items():
            if ticker not in wsb_ticker_dict:
                wsb_ticker_dict[ticker] = tick_obj
            else:
                attrs = vars(tick_obj)
                for attr in attrs:
                    if attr != 'ticker':
                        vars(wsb_ticker_dict[ticker])[attr] += vars(tick_obj)[attr]

        generate_sentiment_report(wsb_ticker_dict)
        print(wsb_ticker_dict)
