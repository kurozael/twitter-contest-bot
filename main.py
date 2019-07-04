from TwitterAPI import TwitterAPI
import threading
import time
import json
import os.path
import sys

# Load our configuration from the JSON file.
with open('config.json') as data_file:    
        data = json.load(data_file)

# These vars are loaded in from config.
consumer_key = data["consumer-key"]
consumer_secret = data["consumer-secret"]
access_token_key = data["access-token-key"]
access_token_secret = data["access-token-secret"]
retweet_update_time = data["retweet-update-time"]
scan_update_time = data["scan-update-time"]
rate_limit_update_time = data["rate-limit-update-time"]
min_ratelimit = data["min-ratelimit"]
min_ratelimit_retweet = data["min-ratelimit-retweet"]
min_ratelimit_search = data["min-ratelimit-search"]
search_queries = data["search-queries"]
follow_keywords = data["follow-keywords"]
fav_keywords = data["fav-keywords"]

# Don't edit these unless you know what you're doing.
api = TwitterAPI(consumer_key, consumer_secret, access_token_key, access_token_secret)
post_list = list()
ignore_list = list()
ratelimit=[999,999,100]
ratelimit_search=[999,999,100]

if os.path.isfile('ignorelist'):
        print("Loading ignore list")
        with open('ignorelist') as f:
                ignore_list = f.read().splitlines()
        f.close()


# Print and log the text
def LogAndPrint( text ):
        tmp = str(text)
        tmp = text.replace("\n","")
        print(tmp)
        f_log = open('log', 'a')
        f_log.write(tmp + "\n")
        f_log.close()

def CheckError( r ):
        r = r.json()
        if 'errors' in r:
                LogAndPrint("We got an error message: " + r['errors'][0]['message'] + " Code: " + str(r['errors'][0]['code']) )
                #sys.exit(r['errors'][0]['code'])

def CheckRateLimit():
        c = threading.Timer(rate_limit_update_time, CheckRateLimit)
        c.daemon = True;
        c.start()

        global ratelimit
        global ratelimit_search

        if ratelimit[2] < min_ratelimit:
                print("Ratelimit too low -> Cooldown (" + str(ratelimit[2]) + "%)")
                time.sleep(200)
        
        r = api.request('application/rate_limit_status').json()


        if 'resources' in r:
                for res_family in r['resources']:
                        for res in r['resources'][res_family]:
                                limit = r['resources'][res_family][res]['limit']
                                remaining = r['resources'][res_family][res]['remaining']
                                percent = float(remaining)/float(limit)*100

                                if res == "/search/tweets":
                                        ratelimit_search=[limit,remaining,percent]

                                if res == "/application/rate_limit_status":
                                        ratelimit=[limit,remaining,percent]

                                #print(res_family + " -> " + res + ": " + str(percent))
                                if percent < 5.0:
                                        LogAndPrint(res_family + " -> " + res + ": " + str(percent) + "  !!! <5% Emergency exit !!!")                           
                                        sys.exit(res_family + " -> " + res + ": " + str(percent) + "  !!! <5% Emergency exit !!!")
                                elif percent < 30.0:
                                        LogAndPrint(res_family + " -> " + res + ": " + str(percent) + "  !!! <30% alert !!!")                           
                                elif percent < 70.0:
                                        print(res_family + " -> " + res + ": " + str(percent))


# Update the Retweet queue (this prevents too many retweets happening at once.)
def UpdateQueue():
        u = threading.Timer(retweet_update_time, UpdateQueue)
        u.daemon = True;
        u.start()

        print("=== CHECKING RETWEET QUEUE ===")

        print("Queue length: " + str(len(post_list)))

        if len(post_list) > 0:

                if not ratelimit[2] < min_ratelimit_retweet:

                        post = post_list[0]
                        LogAndPrint("Retweeting: " + str(post['id']) + " " + str(post['text'].encode('utf8')))

                        CheckForFollowRequest(post)
                        CheckForFavoriteRequest(post)

                        r = api.request('statuses/retweet/:' + str(post['id']))
                        CheckError(r)
                        post_list.pop(0)
                
                else:
        
                        print("Ratelimit at " + str(ratelimit[2]) + "% -> pausing retweets")


# Check if a post requires you to follow the user.
# Be careful with this function! Twitter may write ban your application for following too aggressively
def CheckForFollowRequest(item):
        text = item['text']
        if any(x in text.lower() for x in follow_keywords):
                try:
                        r = api.request('friendships/create', {'screen_name': item['retweeted_status']['user']['screen_name']})
                        CheckError(r)
                        LogAndPrint("Follow: " + item['retweeted_status']['user']['screen_name'])
                except:
                        user = item['user']
                        screen_name = user['screen_name']
                        r = api.request('friendships/create', {'screen_name': screen_name})
                        CheckError(r)
                        LogAndPrint("Follow: " + screen_name)


# Check if a post requires you to favorite the tweet.
# Be careful with this function! Twitter may write ban your application for favoriting too aggressively
def CheckForFavoriteRequest(item):
        text = item['text']

        if any(x in text.lower() for x in fav_keywords):
                try:
                        r = api.request('favorites/create', {'id': item['retweeted_status']['id']})
                        CheckError(r)
                        LogAndPrint("Favorite: " + str(item['retweeted_status']['id']))
                except:
                        r = api.request('favorites/create', {'id': item['id']})
                        CheckError(r)
                        LogAndPrint("Favorite: " + str(item['id']))


# Scan for new contests, but not too often because of the rate limit.
def ScanForContests():
        t = threading.Timer(scan_update_time, ScanForContests)
        t.daemon = True;
        t.start()
        
        global ratelimit_search
        
        if not ratelimit_search[2] < min_ratelimit_search:
        
                print("=== SCANNING FOR NEW CONTESTS ===")


                for search_query in search_queries:

                        print("Getting new results for: " + search_query)
                
                        try:
                                r = api.request('search/tweets', {'q':search_query, 'result_type':"recent", 'count':100})
                                CheckError(r)
                                c=0
                                        
                                for item in r:
                                        
                                        c=c+1
                                        user_item = item['user']
                                        screen_name = user_item['screen_name']
                                        text = item['text']
                                        text = text.replace("\n","")
                                        id = str(item['id'])
                                        original_screen_name = screen_name
                                        original_id=id
                                        is_retweet = 0

                                        if 'retweeted_status' in item:

                                                is_retweet = 1
                                                original_item = item['retweeted_status']
                                                original_id = str(original_item['id'])
                                                original_user_item = original_item['user']
                                                original_screen_name = original_user_item['screen_name']

                                        if not original_id in ignore_list:

                                                if not original_screen_name in ignore_list:
                                
                                                        if not screen_name in ignore_list:
        
                                                                if item ['retweet_count'] > 50:

                                                                        post_list.append(item)                                                                       
                                                                        f_ign = open('ignorelist', 'a')

                                                                        if is_retweet:
                                                                                print(id + " - " + screen_name + " retweeting " + original_id + " - " + original_screen_name + ": " )
                                                                                ignore_list.append(original_id)
                                                                                f_ign.write(original_id + "\n")
                                                                        else:
                                                                                print(id + " - " + screen_name + ": " )
                                                                                ignore_list.append(id)
                                                                                f_ign.write(id + "\n")

                                                                        f_ign.close()

                                                else:
                        
                                                        if is_retweet:
                                                                print(id + " ignored: " + screen_name + " on ignore list")
                                                        else:
                                                                print(screen_name + " in ignore list")

                                        else:
        
                                                if is_retweet:
                                                        print(id + " ignored: " + original_id + " on ignore list")
                                                else:
                                                        print(id + " in ignore list")
                                
                                print("Got " + str(c) + " results")

                        except Exception as e:
                                print("Could not connect to TwitterAPI - are your credentials correct?")
                                print("Exception: " + str(e))

        else:

                print("Search skipped! Queue: " + str(len(post_list)) + " Ratelimit: " + str(ratelimit_search[1]) + "/" + str(ratelimit_search[0]) + " (" + str(ratelimit_search[2]) + "%)")


CheckRateLimit()
ScanForContests()
UpdateQueue()

while (True):
    time.sleep(100)
