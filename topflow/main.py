import base64
import datetime
from pickle import TRUE
import dateutil.parser
import firebase_admin
import json
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
            default_app = firebase_admin.initialize_app()

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

    def add_flow(self, symbol, entry_price, tweet_id, quality, watching=False):

        symbol_json = self.parse_symbol(symbol)

        userEntry = {
            'symbol': symbol_json["symbol"],
            "badges": {},
            "entry_date": datetime.datetime.now().strftime("%Y-%m-%d"),
            "entry_price": float(entry_price),
            "exit_price": None,
            "exit_date": None,
            "tweet_id": tweet_id,
            "flow_quality": quality,
            "trade_type": 0
        }

        if watching:
            userEntry["badges"] = {'watching': True}

        print ('adding to watchlist ', symbol)

        # add public data
        self.firestore_db.collection(u'users').document("public").collection("journal").document(symbol).set(userEntry)
        # add to my private journal also
        # self.firestore_db.collection(u'users').document("JbVEnS9uhWR3HEcOYBWE1uKsliz2").collection("journal").document(symbol).set(userEntry)


    def track_flow(self, symbol):
        # create the symbol json
        symbol_json = self.parse_symbol(symbol)
        tfContract = {
            'symbol': symbol_json["symbol"],
            'max_price': 0,
            'low_price': 999999,
            'current_open_interest': 0,
            "is_expired": symbol_json["expiration"].date() < datetime.datetime.now().date(),
        }

        # add topflow data if it doesnt already exit
        existing_flow = self.firestore_db.collection(u'topflow').document(symbol).get()
        if not existing_flow.exists:
            self.firestore_db.collection(u'topflow').document(symbol).set(tfContract)

            # update data
            self.getHistoricalData(symbol, True)
            self.updateFlowData(symbol, tfContract)


    def update_data(self):
        # pull the list of TopFlow collection and fetch data for each existing symbol that is not expired
        topflow = self.firestore_db.collection(u'topflow').where(u'is_expired', u'==', False).stream()

        for flow in topflow:
            flow_dict = flow.to_dict()
            symbol = flow_dict["symbol"]
            try:
                self.updateFlowData(symbol, flow_dict)
            except Exception as e:
                print("Could not update flow for ", symbol, str(e))
            

    def updateFlowData(self, symbol, flow_dict):
        print("Fetch Data for ", symbol)
        symbol_json = self.parse_symbol(symbol)


        if symbol_json['expiration'].date() < datetime.datetime.now().date():
            # already expired, mark it as such
            print ("Contract already expired: ", symbol)
            contract = {
                "is_expired": symbol_json['expiration'].date() < datetime.datetime.now().date(),
                "last_updated": firestore.SERVER_TIMESTAMP,
            }

            self.firestore_db.collection(u'topflow').document(symbol).update(contract)
            return

            
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
        min_price =  min(low_price, current_low) if low_price is not None and low_price > 0.01 else current_low

        previous_oi = flow_dict["current_open_interest"]

        """
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

        """
                

         # add the daily price for this symbol
        currentPricing = self.getHistoricalData(symbol, False)

        print (currentPricing)

        # create the updated contract
        contract = {
            'symbol': symbol,
            'max_price': max_price,
            'low_price': min_price,
            'current_open_interest': open_interest,
            'last_close': currentPricing['close_price'] if currentPricing is not None else 0,
            "is_expired": symbol_json['expiration'].date() < datetime.datetime.now().date(),
            "last_updated": firestore.SERVER_TIMESTAMP,
        }


        # add the daily record to its collection
        oi = {
            'date': firestore.SERVER_TIMESTAMP,
            'open_interest': open_interest,
        }

        today = datetime.datetime.now().strftime("%Y-%m-%d")

        # add data to db
       
       
        self.firestore_db.collection(u'topflow').document(symbol).update(contract)
        self.firestore_db.collection(u'topflow').document(symbol).collection("open_interest").document(today).set(oi)

        oi_query = self.firestore_db.collection(u'topflow').document(symbol).collection("open_interest")
        oi_snapshot = oi_query.get()
        oi_count = len(oi_snapshot)
        weeklyExp = symbol_json['expiration'].date() < (datetime.datetime.today() + datetime.timedelta(days=7)).date(),
        print (oi_count, symbol)

        # add a message if the OI changes drastically (more than 30% either direction) and increased over 1K OI
        if previous_oi > 0:
            percentage_change = ((open_interest - previous_oi) / previous_oi) * 100

            if abs(percentage_change) > 30 and (open_interest >= 1000 or previous_oi >= 1000):
                m = "{symbol} Open Interest {direction} {change}% from {prevoi} to {newoi}.".format(
                    symbol = symbol,
                    direction = 'increased' if percentage_change > 0 else 'decreased',
                    change = abs(round(percentage_change)),
                    prevoi = previous_oi,
                    newoi = open_interest
                )

                self.addMessage(symbol, m)

            # if this is a flow play (we know since i uploaded the flow_data), then check for revisiting whales
            
            # OI bumped up and we have been tracking this already for at least a week (and not an ETF)
            ignoreList = ["SPY", "QQQ"]
            if percentage_change > 30 and previous_oi >= 1000 and not weeklyExp and oi_count > 7 and not any([x in symbol for x in ignoreList]):
                m = "Whale Reloading?"
                self.addMessage(symbol, m)

            # OI bumped up and the options price is -50% from the max_price
            if percentage_change > 30 and not weeklyExp and (currentPricing is not None and currentPricing['low_price'] < max_price * 0.5):
                m = "Whale Dip Buying?"
                self.addMessage(symbol, m)



                """
                if percentage_change < -30 and 'my_exit_date' not in flow_dict:
                    # OI decreased by more than 30%, and havent yet exited
                    badges["poop"] = True
                    contract = {
                        'badges': badges
                    }
                    self.firestore_db.collection(u'topflow').document(symbol).update(contract)
                """

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
                    'low_price': low_price if low_price > 0.01 else min(open_price, close_price),
                    'high_price': high_price,
                    'close_price': close_price
                }

                today = dateutil.parser.parse(tick['begins_at']).strftime("%Y-%m-%d")

                self.firestore_db.collection(u'topflow').document(symbol).collection("historical_price").document(today).set(oi)

                return oi
        else:
            return None


    # Copy trades from public to private amits journal
    def copy_flow(self):
    # get current public flow
        self.firestore_db = firestore.client()
        publicTrades = self.firestore_db.collection(u'users').document(u'public').collection('journal').get()
        
        # for each trade
        for doc in publicTrades:
            # print(f'{doc.id} => {doc._data}')
            # if it doesnt exist in private journal
            privateTrade = self.firestore_db.collection(u'users').document(u'JbVEnS9uhWR3HEcOYBWE1uKsliz2').collection('journal').document(doc.id).get()
            if not privateTrade.exists:
                # copy the trade over 
                print("copy trade: ", doc.id)
                self.firestore_db.collection(u'users').document(u'JbVEnS9uhWR3HEcOYBWE1uKsliz2').collection('journal').document(doc.id).set(doc._data)

            else:
                print ("trade already exists:", doc.id)

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

# Entry Point: Firestore Trigger
def newFlowTrigger(data, context):
    """ Triggered by a change to a Firestore document.
    Args:
        data (dict): The event payload.
        context (google.cloud.functions.Context): Metadata for the event.
    """
    trigger_resource = context.resource

    print('Track new flow from: %s' % trigger_resource)

    newData = data["value"]["fields"]
    symbol = newData["symbol"]["stringValue"]

    h = Helpers()
    h.track_flow(symbol)
    h.getHistoricalData(symbol, True)

    return f"OK"


def main(args = None):
    if len(args) > 1:
        h = Helpers()

        if args is not None and args[1] == 'add' :
            symbol = args[2]
            entry_price = args[3]
            tweet_id= args[4]
            quality=args[5]
            h.add_flow(symbol, entry_price, tweet_id, quality, True)
        elif args is not None and args[1] == 'update' :
            h.update_data()
        

main(args = sys.argv)

