#!/usr/bin/env python

import requests
from bs4 import BeautifulSoup
import json
import redis
import itertools
from pprint import pprint
import re
import sys
import uuid

#################### EDIT THIS #######################
party_steam_usernames = ('hreese', 'aykura2342', 'lauri.banane', 'faselbart')
######################################################

get_games_url = \
'http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key=%s&steamid=%s&format=json&include_appinfo=1&include_played_free_games=1'
get_steamid_url = \
'http://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/?key=%s&vanityurl=%s'
get_friends_url = \
'http://api.steampowered.com/ISteamUser/GetFriendList/v0001/?key=%s&steamid=%d'
get_player_summaries_url = \
'http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key=%s&steamids=%s'

# initialize redis
redis = redis.StrictRedis()
assert redis.ping()

# open Steam API key
with open('.STEAM_API_KEY', 'r') as f:
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

def UsernameToSteamID(username):
    resp = json.loads(getcached(get_steamid_url % (apikey, username)))
    assert resp['response']['success'] == 1 and resp['response'].has_key('steamid')
    steamid = int(resp['response']['steamid'])
    redis.hset('steam:user:name2id', username, steamid)
    redis.hset('steam:user:id2name', steamid, username)
    return steamid

# get game list
def GetUserGames(steamid):
    gamespage = getcached(get_games_url % (apikey, steamid))
    gamelist = json.loads(gamespage)
    GamesByID = dict(((g['appid'], g['name']) for g in gamelist['response']['games']))
    redis.hmset('steam:games:id2name', GamesByID)
    redis.sadd('steam:player:owns:%s' % steamid, *GamesByID.keys())
    return GamesByID

# get friends
def GetFriends(steamid):
    resp = json.loads(getcached(get_friends_url % (apikey, steamid)))
    friends_ids = [int(x['steamid']) for x in resp['friendslist']['friends'] if x['relationship'] == 'friend']
    f = {}
    # split into chunks of 100
    for somefriends in [friends_ids[i:i+100] for i in xrange(0,len(friends_ids),100)]:
        friendsarg = ",".join([str(x) for x in somefriends])
        friendinfos = json.loads(getcached(get_player_summaries_url % (apikey, friendsarg)))
        f.update(friendinfos)
    redis.hmset('steam:user:id2name', dict([(int(x['steamid']), x['personaname']) for x in f['response']['players']]))
    redis.hmset('steam:user:name2id', dict([(x['personaname'], int(x['steamid'])) for x in f['response']['players']]))
    return [int(x['steamid']) for x in f['response']['players']]

# update/store game info in redis
def RetrieveGameInfo(games):
    for gameid in games.keys():
        sys.stderr.write("Processing %s (%d) " % (games[gameid], gameid))
        if redis.sismember('steam:game:traitsknown', gameid):
            sys.stderr.write("already processed, skipped.\n")
            continue
        gamestorepage = getcached('http://store.steampowered.com/app/%d/' % gameid, 3600 * 24)
        soup = BeautifulSoup(gamestorepage)
        try:
            categories = soup.find('div', {'id': 'category_block'}).findChildren('a')
            if len(categories) > 0:
                traits = [x.text for x in categories]
            else:
                raise AttributeError()
        except AttributeError, e:
            sys.stderr.write("no traits found, skipping.\n")
            # add to list so no more testing is done for these
            redis.sadd('steam:game:traitsknown', gameid)
            continue
        # global trait list
        redis.sadd('steam:traits', *traits)
        # forward index (game -> traits)
        redis.sadd('steam:game:traits:%d' % gameid, traits)
        # reverse index (trait -> games)
        for trait in traits:
            redis.sadd('steam:game:hastrait:%s' % trait, gameid)
        redis.sadd('steam:game:traitsknown', gameid)
        sys.stderr.write("done.\n")

if __name__ == "__main__":
    steamid = UsernameToSteamID('hreese')
    mygames = GetUserGames(steamid)
    all_games = mygames
    for f in GetFriends(steamid):
        sys.stderr.write("Retrieving game list for user %s\n" % f)
        all_games.update(GetUserGames(f))
    RetrieveGameInfo(all_games)
    names_by_id = redis.hgetall('steam:games:id2name')

    #traits_no_eula = [t for t in redis.smembers('steam:traits') if not re. search('EULA', t, re.I)]
    #games_full_controller_support    = redis.smembers('steam:game:hastrait:Full controller support')
    #games_partial_controller_support = redis.smembers('steam:game:hastrait:Partial Controller Support')
    #games_local_coop                 = redis.smembers('steam:game:hastrait:Local Co-op')
    #games_i_own                      = set(mygames.keys())

    all_players_set_name = 'temp:%s' % str(uuid.uuid4())

    party_player_ids = redis.hmget('steam:user:name2id', party_steam_usernames)
    redis.sunionstore(all_players_set_name, ['steam:player:owns:%s' % p for p in party_player_ids])
    available_games = redis.smembers(all_players_set_name)
    controllerfullgames = redis.sinter('steam:game:hastrait:Local Co-op', 'steam:game:hastrait:Full controller support', all_players_set_name)
    controllerpartgames = redis.sinter('steam:game:hastrait:Local Co-op', 'steam:game:hastrait:Partial Controller Support', all_players_set_name)

    print("\n=====[ All games available ]=====\n")
    print "\n".join(sorted(["* " + names_by_id[g] for g in available_games]))

    print("\n=====[ Local Co-op and Full Controller Support ]=====\n")
    print "\n".join(sorted(["* " + names_by_id[g] for g in controllerfullgames]))

    print("\n=====[ Local Co-op and Partial Controller Support ]=====\n")
    print "\n".join(sorted(["* " + names_by_id[g] for g in controllerpartgames]))
