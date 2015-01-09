#!/usr/bin/env python

import requests
from bs4 import BeautifulSoup
import json
import redis
import itertools
from pprint import pprint
import re

get_games_url = \
'http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key=%s&steamid=%s&format=json&include_appinfo=1&include_played_free_games=1'
get_steamid_url = \
'http://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/?key=%s&vanityurl=%s'

# initialize redis
redis = redis.StrictRedis()
assert redis.ping()

# open Steam API key
with open('STEAM_API_KEY', 'r') as f:
    apikey = f.read().strip()

def getcached(url, expiration=600):
    key = 'pagecache:%s' % url
    if redis.exists(key):
        return redis.get(key)
    else:
        r = requests.get(url)
        assert r.status_code == 200
        redis.setex(key, expiration, r.text)
        return r.text

def UsernameToSteamID(username='hreese'):
    resp = json.loads(getcached(get_steamid_url % (apikey, username)))
    assert resp['response']['success'] == 1 and resp['response'].has_key('steamid')
    return int(resp['response']['steamid'])

# get game list
def GetUserGames(steamid):
    gamespage = getcached(get_games_url % (apikey, steamid))
    gamelist = json.loads(gamespage)
    GamesByID = dict(((g['appid'], g['name']) for g in gamelist['response']['games']))
    redis.hmset('steam:games:id2name', GamesByID)
    return GamesByID

# update/store game info in redis
def RetrieveGameInfo(games):
    for gameid in games.keys():
        print "Processing %s (%d)" % (games[gameid], gameid)
        gamestorepage = getcached('http://store.steampowered.com/app/%d/' % gameid, 3600 * 24)
        soup = BeautifulSoup(gamestorepage)
        try:
            traits = [x.text for x in soup.find('div', {'id': 'category_block'}).findChildren('a')]
        except AttributeError, e:
            pass
        # forward index
        redis.hmset('steam:game:traits:%d' % gameid, dict(zip(traits, itertools.repeat(1))))
        # reverse index
        for trait in traits:
            redis.hmset('steam:traits:%s' % trait, { gameid: 1 })

if __name__ == "__main__":
    steamid = UsernameToSteamID('hreese')
    mygames = GetUserGames(steamid)
    ### only needed once and after buying games
    #RetrieveGameInfo(mygames)
    ###
    names_by_id = redis.hgetall('steam:games:id2name')

    traits_no_eula = (t for t in (x.replace('steam:traits:', '') for x in redis.keys('steam:traits:*')) if not re.search('EULA', t, re.I))

    games_full_controller_support    = set(redis.hgetall('steam:traits:Full controller support').keys())
    games_partial_controller_support = set(redis.hgetall('steam:traits:Partial Controller Support').keys())
    games_local_coop                 = set(redis.hgetall('steam:traits:Local Co-op').keys())
    games_i_own                      = set(mygames.keys())

    print("\n=====[ Local Co-op and Full Controller Support ]=====\n")
    partygames = games_local_coop.intersection(games_full_controller_support)
    print "\n".join(sorted(["* " + names_by_id[g] for g in partygames]))

    print("\n=====[ Local Co-op and Partial Controller Support ]=====\n")
    partygames_maybe = games_local_coop.intersection(games_partial_controller_support)
    print "\n".join(sorted(["* " + names_by_id[g] for g in partygames_maybe]))
