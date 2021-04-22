import json

from twitivity import Event
from pprint import pprint
import re


            
m = '''$TEST 210716C65 at $4.99 [$$$]

Size: 100M
Time: July
Urgency: A/AA

#getthatcashmoney  #blackboxstocks'''

line = m.split('\n')[0] #first line has details

# https://regexr.com 
# REGEX:    (\$((.)+)?(\sat\s){1}\$([\d.]*)\s(\[(.*)\])+)  
# EXAMPLE:  $TEST 210716C65 at $4.99 [$$$]

tweet_regex = re.compile(r'''
(\$((.)+)?      #g2: symbol
(\sat\s){1}     #g4: at
\$([\d.]*)\s    #g5: price
(\[(.*)\])+)    #g7: rating
''', re.VERBOSE | re.IGNORECASE)


result = tweet_regex.search(line)

ticker = result.group(2)

symbol = result.group(2)
price = result.group(5)
rating = result.group(7)

print("symbol: ", symbol)
print("price: ", price)
print("rating: ", rating)

            


    

    
    