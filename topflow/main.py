import base64
import datetime
import dateutil.parser
import firebase_admin
import flask
import hashlib
import hmac
import os
import pyotp
import re
import robin_stocks
import sys
from twitivity import Event

from firebase_admin import credentials
from firebase_admin import firestore
from hashlib import sha256

class Helpers:
    firestore_db = None

    def __init__(self):
        # initialize with firebase
        if not firebase_admin._apps:
            cred = credentials.Certificate('serviceAccountKey.json') 
            default_app = firebase_admin.initialize_app(cred)

        self.firestore_db = firestore.client()

        # initialise with options data api (robinhood)
        username = os.environ.get("rh_username")
        pwd = os.environ.get("rh_pwd")
        twofa = os.environ.get("rh_twofa")

        print(twofa)
        totp = pyotp.TOTP(twofa).now()
        robin_stocks.robinhood.login(username = username, 
                        password=pwd, 
                        mfa_code=totp,
                        store_session=False)


    def parse_symbol(self, symbol):
        # Get data for this symbol
        option_regex = re.compile(r'''(
                                (\w{1,6})            # beginning ticker, 1 to 6 word characters
                                (\s+)?               # optional separator
                                (\d{6})              # 6 digits for yymmdd
                                ([CP])               # C or P for call or put
                                (\d+\.?\d*)            # 1-8 digits for strike price
                                )''', re.VERBOSE | re.IGNORECASE)


        result = option_regex.search(symbol)

        if result is None:
            return None

        ticker = result.group(2)
        expiration = result.group(4)
        option_type = "CALL" if result.group(5) == "C" else "PUT"
        strike = result.group(6)

        exp = datetime.datetime.strptime(expiration, "%y%m%d")


        # create the symbol json
        symbol_json = {
            'symbol': symbol,
            'ticker': ticker,
            'expiration': exp,
            'option_type': option_type,
            'strike': strike
        }

        return symbol_json

    def add_flow(self, symbol, entry_price, tweet_id, quality):

        # create the symbol json
        symbol_json = self.parse_symbol(symbol)
        contract = {
            'symbol': symbol_json["symbol"],
            'max_price': 0,
            'low_price': 999999,
            'current_open_interest': 0,
            "is_expired": symbol_json["expiration"] < datetime.datetime.now(),
            "entry_date": datetime.datetime.now().strftime("%Y-%m-%d"),
            "entry_price": float(entry_price),
            "tweet_id": tweet_id,
            "flow_quality": quality
        }

        print ('adding ', symbol)

        # add data
        self.firestore_db.collection(u'topflow').document(symbol).set(contract)

        # update data
        self.updateFlowData(symbol, contract)

    def update_data(self):
        # pull the list of TopFlow collection and fetch data for each existing symbol that is not expired
        topflow = self.firestore_db.collection(u'topflow').where(u'is_expired', u'==', False).stream()

        for flow in topflow:
            flow_dict = flow.to_dict()
            symbol = flow_dict["symbol"]
            self.updateFlowData(symbol, flow_dict)
            

    def updateFlowData(self, symbol, flow_dict):
        print("Fetch Data for ", symbol)
        symbol_json = self.parse_symbol(symbol)

        data = robin_stocks.robinhood.options.get_option_market_data(
                                        inputSymbols=symbol_json['ticker'],
                                        expirationDate=symbol_json['expiration'].strftime("%Y-%m-%d"),
                                        strikePrice=symbol_json['strike'],
                                        optionType=symbol_json['option_type'])[0][0]

        open_interest = data["open_interest"]
        low_price = float(data["low_price"]) if data["low_price"] is not None else 99999
        high_price = float(data["high_price"]) if data["high_price"] is not None else 0

        max_price = 0 if high_price is None else float(high_price)
        min_price = 0 if low_price is None else float(low_price)
        
        current_max = float(flow_dict['max_price'])
        current_low = float(flow_dict['low_price'])
        
        max_price =  max(max_price, current_max)
        min_price =  min(low_price, current_low) if low_price is not None and low_price > 0 else current_low

        previous_oi = flow_dict["current_open_interest"]

        entry_price = float(flow_dict["entry_price"])

        # determine new badges to earn
        badges = {} if 'badges' not in flow_dict else flow_dict["badges"]
        if ('my_exit_date' in flow_dict):

            exit_price = float(flow_dict["my_exit_price"])
            gain = (exit_price - entry_price ) / entry_price

            # badges you earn after exiting
            
            # scalper badge
            if gain > 0 and (flow_dict["my_exit_date"] == flow_dict["entry_date"]):
                badges["scalper"] = True

            # quickie badge, trade went 50% higher from exit price
            if gain > 0 and high_price > (exit_price * 1.5):
                badges["quickie"] = True

            # piker
            if gain < 0 and (high_price - entry_price) > 0:
                badges["piker"] = True

            # diamond hands
            if gain > 0 and "coal" in badges:
                badges.pop('coal')
                badges["diamond"] = True

        else:
            # hasnt exited position yet
            if 'poop' not in badges:
                # buyer has not exited yet
                if low_price > 0 and low_price < (entry_price * 0.5):
                    # current position went below 50%, but buyer is still there so may still work.
                    badges["coal"] = True

                

        # create the updated contract
        contract = {
            'symbol': symbol,
            'max_price': max_price,
            'low_price': min_price,
            'current_open_interest': open_interest,
            "is_expired": symbol_json['expiration'] < datetime.datetime.now(),
            "badges": badges,
            "last_updated": firestore.SERVER_TIMESTAMP
        }


        # add the daily record to its collection
        oi = {
            'date': firestore.SERVER_TIMESTAMP,
            'open_interest': open_interest,
        }

        today = datetime.datetime.now().strftime("%Y-%m-%d")

        # add data to db
        # add the daily price for this symbol
        self.getHistoricalData(symbol, False)
        self.firestore_db.collection(u'topflow').document(symbol).update(contract)
        self.firestore_db.collection(u'topflow').document(symbol).collection("open_interest").document(today).set(oi)

        # add a message if the OI changes drastically (more than 30% either direction)
        if previous_oi > 0:
            percentage_change = ((open_interest - previous_oi) / previous_oi) * 100

            if abs(percentage_change) > 30:
                m = "{symbol} Open Interest {direction} {change}% from {prevoi} to {newoi}.".format(
                    symbol = symbol,
                    direction = 'increased' if percentage_change > 0 else 'decreased',
                    change = abs(round(percentage_change)),
                    prevoi = previous_oi,
                    newoi = open_interest
                )

                self.addMessage(symbol, m)

                if percentage_change < -30 and 'my_exit_date' not in flow_dict:
                    # OI decreased by more than 30%, and havent yet exited
                    badges["poop"] = True
                    contract = {
                        'badges': badges
                    }
                    self.firestore_db.collection(u'topflow').document(symbol).update(contract)


    def addMessage(self, symbol, message):
        print('activity: ' + message)
        m = {
            'message': message,
            'date': firestore.SERVER_TIMESTAMP,
            'symbol': symbol
        }
        self.firestore_db.collection(u'activity').document().set(m)


    def getHistoricalData(self, symbol, is_new):

        print("get pricing data for ", symbol)

        # initialize with firebase
        if not firebase_admin._apps:
            cred = credentials.Certificate('serviceAccountKey.json') 
            default_app = firebase_admin.initialize_app(cred)

        firestore_db = firestore.client()

        # pull the list of TopFlow collection and fetch data for each existing symbol that is not expired
        symbol_json = self.parse_symbol(symbol)
        print("Fetch Historical Data for ",  symbol_json['ticker'],
                                        symbol_json['expiration'].strftime("%Y-%m-%d"),
                                        symbol_json['strike'],
                                        symbol_json['option_type'],
                                        'day',
                                        'week' if is_new else 'day',
                                        'regular')

        data = robin_stocks.robinhood.get_option_historicals(
                                        symbol=symbol_json['ticker'],
                                        expirationDate=symbol_json['expiration'].strftime("%Y-%m-%d"),
                                        strikePrice=symbol_json['strike'],
                                        optionType=symbol_json['option_type'],
                                        interval='day',
                                        span='week' if is_new else 'week',
                                        bounds='regular')
        if data is not None:
            for tick in data:
                open_price = float(tick["open_price"])
                low_price = float(tick["low_price"])
                high_price = float(tick["high_price"])
                close_price = float(tick["close_price"])

                # add the daily record to its collection
                oi = {
                    'date': tick['begins_at'],
                    'open_price': open_price,
                    'low_price': low_price,
                    'high_price': high_price,
                    'close_price': close_price
                }

                today = dateutil.parser.parse(tick['begins_at']).strftime("%Y-%m-%d")

                self.firestore_db.collection(u'topflow').document(symbol).collection("historical_price").document(today).set(oi)




# CMDLine: add a new top flow to the db
def add_flow(request):
    request_json = request.get_json(silent=True)
    request_args = request.args

    if request_json and 'symbol' in request_json:
        symbol = request_json['symbol']
        entry_price = request_json['entry_price']
        tweet_id = request_json['tweet_id']
    
    elif request_args and 'symbol' in request_args:
        symbol = request_args['symbol']
        entry_price = request_args['entry_price']
        tweet_id = request_args['tweet_id']

    else:
        symbol = None
        entry_price = 0
        tweet_id = 0

    if symbol is not None:
        h = Helpers()
        h.add_flow(symbol, entry_price, tweet_id)
        h.getHistoricalData(symbol, True)

        return f'OK'

def parseTwitterPost(data) :
    if ('tweet_create_events' in data):
        events = data['tweet_create_events']
        
        m = events[0]['text']
        print(m)

        if m.startswith("$"):
            print("parsing the tweet: ", m)
            line = m.split('\n')[0]
            tweet_regex = re.compile(r'''
                (\$((.)+)?      #g2: symbol
                (\sat\s){1}     #g4: at
                \$([\d.]*)\s    #g5: price
                (\[(.*)\])+)    #g7: rating
            ''', re.VERBOSE | re.IGNORECASE)


            result = tweet_regex.search(line)

            tweet_id = events[0]['id_str']
            symbol = result.group(2)
            price = result.group(5)
            rating = len(result.group(7))

            # call add_flow
            h = Helpers()
            h.add_flow(symbol, price, tweet_id, rating)


# Entry Point: update the flow stored in firebase
def update_flow(request):
    h = Helpers()
    h.update_data()

    return f'OK'

# Entry Point: Twitter WebHooks
def twitter(request):
    print("Twitter Hook", request)
    if request.method == "GET" or request.method == "PUT":
        hash_digest = hmac.digest(
            key=os.environ.get("consumer_secret").encode("utf-8"),
            msg=request.args.get("crc_token").encode("utf-8"),
            digest=hashlib.sha256,
        )
        print("returning CRC Response Token", hash_digest)
        return {
            "response_token": "sha256="
            + base64.b64encode(hash_digest).decode("ascii")
        }
    elif request.method == "POST":
        print ("Parsing a Twitter Post")
        data = request.get_json()
        parseTwitterPost(data)
        return {"Successfully Parsed Twitter Request": 200}


def main(args = None):
    if len(args) > 1:
        h = Helpers()

        if args is not None and args[1] == 'add' :
            symbol = args[2]
            entry_price = args[3]
            tweet_id= args[4]
            quality=args[5]
            h.add_flow(symbol, entry_price, tweet_id, quality)
        elif args is not None and args[1] == 'update' :
            h.update_data()


main(args = sys.argv)

