# steam-partygames

Dirty hack to answer the following question: “Given n people with steam accounts, four controllers and a beamer: what games are available for playing local co-op?”

Used this opportunity to play around with redis.

## Installation

1. Install local redis server (or use remote redis server and add address in code).
2. Put Steam API key in `.STEAM_API_KEY`
3. Setup virtualenv:
```bash
virtualenv --no-site-packages ENV
. ./ENV/bin/activate
pip install -r requirements.txt
```
4. Edit variable `party_steam_usernames` in `steanmparty.ps`
5. Run. Wait. Enjoy game list.
